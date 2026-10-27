from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db import models
from app.domain.entities import AccountType, Currency
from app.domain.errors import DomainError
from app.domain.fx import FxRates
from app.domain.periods import local_today
from app.domain.wealth import compute_wealth
from app.schemas.reports import LoanOut, RateUsed, WealthAccount, WealthOut
from app.services import crypto as crypto_service
from app.services.balances import account_balances, to_domain_account
from app.services.fx_rates import rate_on_or_before

# Held apart from the user's money: they never take part in the valuation.
OUTSIDE_WEALTH = frozenset({AccountType.EXCHANGE.value, AccountType.SYSTEM.value})
MISSING_RATE = (
    "Hay saldos en dólares y no hay una TRM registrada para convertirlos. Sincroniza la TRM e intenta de nuevo."
)


def _value_in_cop(fx: FxRates, balance: Decimal, currency: str, today: date) -> Decimal:
    if balance == 0:
        return Decimal(0)
    return fx.to_cop(balance, Currency(currency), today)


def current_wealth(db: Session) -> WealthOut:
    """Balances valued in COP with the latest USD rate that is not in the future."""
    today = local_today()
    rows = list(db.scalars(select(models.Account).order_by(models.Account.name)))
    balances = account_balances(db)
    rate = rate_on_or_before(db, today)
    fx = FxRates({Currency.USD: {rate.date: rate.value}}) if rate else FxRates()

    counted = [row for row in rows if row.type not in OUTSIDE_WEALTH]
    # An empty foreign currency account needs no rate to be worth zero.
    valued = [row for row in counted if rate or row.currency == Currency.COP.value or balances[row.id] != 0]
    try:
        wealth = compute_wealth([to_domain_account(row) for row in valued], balances, fx, today)
        values: dict = {row.id: _value_in_cop(fx, balances[row.id], row.currency, today) for row in counted}
    except DomainError:
        raise ApiError(409, "missing_fx_rate", MISSING_RATE) from None

    for row in rows:
        if row.type in OUTSIDE_WEALTH:
            try:
                values[row.id] = _value_in_cop(fx, balances[row.id], row.currency, today)
            except DomainError:
                values[row.id] = None

    by_id = {row.id: row for row in rows}
    accounts = [
        WealthAccount(
            id=row.id,
            name=row.name,
            type=row.type,
            currency=row.currency,
            archived=row.archived,
            balance=balances[row.id],
            balance_cop=values[row.id],
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
        crypto=crypto_service.wealth_block(db, rate.value if rate else None),
        rate=RateUsed(currency=Currency.USD, value=rate.value, date=rate.date) if rate else None,
    )
