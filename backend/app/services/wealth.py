from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db import models
from app.domain.entities import Currency
from app.domain.errors import DomainError
from app.domain.fx import FxRates
from app.domain.periods import local_today
from app.domain.wealth import compute_wealth
from app.schemas.reports import CryptoOut, LoanOut, RateUsed, WealthAccount, WealthOut
from app.services.balances import account_balances, to_domain_account


def _latest_rate(db: Session, today) -> models.FxRate | None:
    return db.scalars(
        select(models.FxRate)
        .where(models.FxRate.currency == Currency.USD.value, models.FxRate.date <= today)
        .order_by(models.FxRate.date.desc())
        .limit(1)
    ).first()


def current_wealth(db: Session) -> WealthOut:
    """Balances valued in COP with the latest USD rate that is not in the future."""
    today = local_today()
    rows = list(db.scalars(select(models.Account).order_by(models.Account.name)))
    balances = account_balances(db)
    rate = _latest_rate(db, today)
    fx = FxRates({Currency.USD: {rate.date: rate.value}}) if rate else FxRates()

    # An empty foreign currency account needs no rate to be worth zero.
    valued = [row for row in rows if rate or row.currency == Currency.COP.value or balances[row.id] != 0]
    try:
        wealth = compute_wealth([to_domain_account(row) for row in valued], balances, fx, today)
        values = {row.id: fx.to_cop(balances[row.id], Currency(row.currency), today) for row in valued}
    except DomainError:
        raise ApiError(
            409,
            "missing_fx_rate",
            "Hay saldos en dólares y no hay una TRM registrada para convertirlos. Sincroniza la TRM e intenta de nuevo.",
        ) from None

    by_id = {row.id: row for row in rows}
    accounts = [
        WealthAccount(
            id=row.id,
            name=row.name,
            type=row.type,
            currency=row.currency,
            archived=row.archived,
            balance=balances[row.id],
            balance_cop=values.get(row.id, 0),
        )
        # Archived accounts only show while they still hold money.
        for row in rows
        if not row.archived or balances[row.id] != 0
    ]
    loans = [
        LoanOut(account_id=account_id, counterparty=by_id[account_id].counterparty, amount=amount)
        for account_id, amount in wealth.receivable_loans_by_account.items()
    ]

    return WealthOut(
        available=wealth.available,
        credit_card_debt=wealth.credit_card_debt,
        real_money=wealth.real_money,
        receivable_loans=wealth.receivable_loans,
        loans=loans,
        accounts=accounts,
        crypto=CryptoOut(),
        rate=RateUsed(currency=Currency.USD, value=rate.value, date=rate.date) if rate else None,
    )
