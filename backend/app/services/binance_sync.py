"""Reads the exchange account and stores a daily snapshot of the balances plus any new trades.

Everything is read from the exchange first and written afterwards in a single transaction, so a failure
leaves the previous data untouched.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import BigInteger, cast, delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db import models
from app.domain.crypto import drop_earn_tokens, merge_quantities, select_symbols, summarize_values, value_in_usd
from app.domain.entities import AccountType, Currency
from app.domain.periods import local_today
from app.integrations import binance
from app.integrations.binance import BinanceClient, BinanceError, Trade
from app.services import integrations
from app.services.integrations import Notice

EXCHANGE_ACCOUNT_NAME = "Binance"
# Requests allowed in one sync (the exchange weighs each trade query heavily). What is left over is
# read in the next sync.
MAX_REQUESTS_PER_SYNC = 120
MAX_PAGES_PER_SYMBOL = 5

# The only answer that means "this key cannot read that wallet". Any other failure could be temporary, and
# skipping the wallet would store a total that is too low.
PERMISSION_KINDS = (binance.ACCESS_DENIED,)

SKIPPED_WALLETS = {
    "funding": Notice("funding_wallet_skipped", "No se pudo leer la billetera de fondos con esta clave; se omitió."),
    "earn_flexible": Notice(
        "earn_flexible_skipped", "No se pudo leer Simple Earn flexible con esta clave; se omitió."
    ),
    "earn_locked": Notice("earn_locked_skipped", "No se pudo leer Simple Earn bloqueado con esta clave; se omitió."),
}
ASSETS_SKIPPED = Notice(
    "asset_skipped",
    "Se omitieron activos con un nombre no reconocido; no se incluyeron en el total.",
)
TRADES_INCOMPLETE = Notice(
    "trades_incomplete",
    "No se alcanzaron a traer todas las operaciones; se completarán en la próxima sincronización.",
)


@dataclass(frozen=True)
class SyncResult:
    snapshot_date: date
    assets: int
    unpriced_assets: int
    total_usd: Decimal
    new_trades: int
    trades_complete: bool
    warnings: list[Notice]
    last_synced_at: datetime


def ensure_exchange_account(db: Session) -> models.Account:
    """The USD account that holds the exchange balances. Created on first use."""
    rows = list(
        db.scalars(
            select(models.Account)
            .where(
                models.Account.type == AccountType.EXCHANGE.value,
                models.Account.currency == Currency.USD.value,
                models.Account.archived.is_(False),
            )
            .order_by(models.Account.name)
        )
    )
    for row in rows:
        if row.name == EXCHANGE_ACCOUNT_NAME:
            return row
    if rows:
        return rows[0]
    account = models.Account(
        name=EXCHANGE_ACCOUNT_NAME, type=AccountType.EXCHANGE.value, currency=Currency.USD.value
    )
    db.add(account)
    db.flush()
    return account


def _read_wallets(client: BinanceClient, prices: dict[str, Decimal]) -> tuple[dict[str, Decimal], list[Notice]]:
    """Quantity per asset across the spot, funding and earn wallets.

    The spot wallet is required. The others are skipped, with a notice, only when the key may not read them.
    """
    spot = client.spot_balances()
    skipped = spot.skipped
    # Flexible earn positions can also show up in spot as `LD<ASSET>`; they are read from the earn wallet.
    wallets = [drop_earn_tokens(spot.balances, prices)]
    notices: list[Notice] = []
    optional = (
        ("funding", client.funding_balances),
        ("earn_flexible", client.earn_flexible_balances),
        ("earn_locked", client.earn_locked_balances),
    )
    for name, read in optional:
        try:
            wallet = read()
        except BinanceError as error:
            if error.kind not in PERMISSION_KINDS:
                raise
            notices.append(SKIPPED_WALLETS[name])
            continue
        wallets.append(wallet.balances)
        skipped += wallet.skipped
    if skipped:
        notices.append(ASSETS_SKIPPED)
    return merge_quantities(*wallets), notices


def _last_trade_ids(db: Session) -> dict[str, int]:
    """Highest exchange trade id stored for each pair."""
    trade_number = cast(func.split_part(models.CryptoTrade.external_id, ":", 2), BigInteger)
    rows = db.execute(select(models.CryptoTrade.pair, func.max(trade_number)).group_by(models.CryptoTrade.pair))
    return {pair: int(last) for pair, last in rows if last is not None}


def _fetch_trades(client: BinanceClient, symbols: list[str], last_ids: dict[str, int]) -> tuple[list[Trade], bool]:
    """New trades of each pair, oldest first. The flag is False when the reading was cut short."""
    trades: list[Trade] = []
    for symbol in symbols:
        from_id = last_ids.get(symbol, -1) + 1
        for _ in range(MAX_PAGES_PER_SYMBOL):
            if client.requests_made >= MAX_REQUESTS_PER_SYNC:
                return trades, False
            try:
                page = client.trades(symbol, from_id)
            except BinanceError as error:
                if error.kind == binance.RATE_LIMITED:
                    return trades, False
                if error.kind == binance.REJECTED:
                    # The exchange does not know this pair (for example, it was delisted).
                    break
                raise
            ids = [trade.trade_id for trade in page]
            if any(trade_id < from_id for trade_id in ids) or ids != sorted(set(ids)):
                raise BinanceError(binance.BAD_RESPONSE)
            trades.extend(page)
            if len(page) < binance.TRADES_PAGE_SIZE:
                break
            from_id = ids[-1] + 1
        else:
            return trades, False
    return trades, True


def _mark_error(db: Session, row: models.Integration, notice: Notice, forget_secret: bool = False) -> None:
    db.rollback()
    if forget_secret:
        # A key that can do more than read is not kept at all.
        row.encrypted_secret = None
    row.status = "error"
    row.warnings = [notice.as_json()]
    db.commit()


def _store_balances(
    db: Session, account: models.Account, day: date, quantities: dict[str, Decimal], values: dict[str, Decimal | None]
) -> None:
    # An asset sold earlier today must not linger in today's snapshot.
    stale = delete(models.CryptoBalance).where(
        models.CryptoBalance.account_id == account.id, models.CryptoBalance.date == day
    )
    if quantities:
        stale = stale.where(models.CryptoBalance.asset.not_in(list(quantities)))
    db.execute(stale)

    if not quantities:
        return
    statement = insert(models.CryptoBalance).values(
        [
            {"account_id": account.id, "asset": asset, "date": day, "quantity": quantity, "value_usd": values[asset]}
            for asset, quantity in quantities.items()
        ]
    )
    db.execute(
        statement.on_conflict_do_update(
            constraint="uq_crypto_balances_account_id_asset_date",
            set_={"quantity": statement.excluded.quantity, "value_usd": statement.excluded.value_usd},
        )
    )


def _store_trades(db: Session, account: models.Account, trades: list[Trade]) -> int:
    if not trades:
        return 0
    statement = insert(models.CryptoTrade).values(
        [
            {
                "account_id": account.id,
                "pair": trade.symbol,
                "side": trade.side,
                "quantity": trade.quantity,
                "price": trade.price,
                "fee": trade.fee,
                "fee_asset": trade.fee_asset,
                "executed_at": trade.executed_at,
                # Trade ids are only unique within a pair.
                "external_id": f"{trade.symbol}:{trade.trade_id}",
            }
            for trade in trades
        ]
    )
    inserted = db.execute(
        statement.on_conflict_do_nothing(index_elements=[models.CryptoTrade.external_id]).returning(
            models.CryptoTrade.id
        )
    )
    return len(inserted.all())


def sync_binance(db: Session, encryption_key: str) -> SyncResult:
    """Validate the key again, read the account and store today's snapshot and the new trades."""
    row = integrations.get_row(db, integrations.BINANCE)
    if row is None:
        raise ApiError(409, "integration_not_connected", "Binance no está conectado. Conecta una clave de solo lectura primero.")
    credentials = integrations.stored_credentials(row, encryption_key)

    with binance.build_client(credentials) as client:
        try:
            notices = integrations.check_key(client)
            prices = client.prices()
            quantities, wallet_notices = _read_wallets(client, prices)
            traded = _last_trade_ids(db)
            symbols = select_symbols(quantities, traded, prices)
            trades, trades_complete = _fetch_trades(client, symbols, traded)
        except integrations.KeyRejected:
            # The key gained permissions after it was connected: stop using it.
            _mark_error(db, row, integrations.KEY_NOT_READ_ONLY, forget_secret=True)
            raise
        except ApiError as error:
            if error.code in ("binance_invalid_credentials", "binance_access_denied"):
                _mark_error(db, row, Notice(error.code, error.message))
            raise
        except BinanceError as error:
            api_error = integrations.binance_api_error(error)
            if error.kind in (binance.INVALID_CREDENTIALS, binance.ACCESS_DENIED):
                _mark_error(db, row, Notice(api_error.code, api_error.message))
            raise api_error from None

    notices = notices + wallet_notices + ([] if trades_complete else [TRADES_INCOMPLETE])
    values = {asset: value_in_usd(asset, quantity, prices) for asset, quantity in quantities.items()}
    totals = summarize_values(values.values())
    today = local_today()
    now = datetime.now(UTC)

    try:
        account = ensure_exchange_account(db)
        _store_balances(db, account, today, quantities, values)
        new_trades = _store_trades(db, account, trades)
        row.status = "active"
        row.last_synced_at = now
        row.warnings = [notice.as_json() for notice in notices]
        db.commit()
    except Exception:
        db.rollback()
        raise

    return SyncResult(
        snapshot_date=today,
        assets=len(quantities),
        unpriced_assets=totals.unpriced,
        total_usd=totals.total_usd,
        new_trades=new_trades,
        trades_complete=trades_complete,
        warnings=notices,
        last_synced_at=now,
    )
