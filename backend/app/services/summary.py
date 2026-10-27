import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.db import models
from app.domain.entities import LOCAL_TIMEZONE, TransactionStatus
from app.domain.errors import DomainError
from app.domain.flow import FlowSummary, cash_flow
from app.domain.periods import local_today, month_bounds, month_start, parse_month, trailing_months
from app.schemas.reports import CategoryAmount, MonthTotals, SummaryOut
from app.services.balances import to_domain_account, to_domain_transaction
from app.services.fx_rates import load_rates

TREND_MONTHS = 6
UNCATEGORIZED_NAME = "Sin categoría"


def resolve_month(value: str | None) -> date:
    """First day of the requested month, or of the current one in Colombia when none is requested."""
    if value is None:
        return month_start(local_today())
    try:
        return parse_month(value)
    except DomainError:
        raise ApiError(422, "invalid_month", "El mes debe tener el formato AAAA-MM.") from None


def _local_midnight(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, tzinfo=LOCAL_TIMEZONE)


def _by_category(
    amounts: dict[uuid.UUID | None, Decimal], categories: dict[uuid.UUID, models.Category]
) -> list[CategoryAmount]:
    items = []
    for category_id, amount in amounts.items():
        category = categories.get(category_id) if category_id is not None else None
        items.append(
            CategoryAmount(
                category_id=category_id,
                name=category.name if category else UNCATEGORIZED_NAME,
                color=category.color if category else None,
                amount=amount,
            )
        )
    return sorted(items, key=lambda item: (-item.amount, item.name))


def _totals(month: date, flow: FlowSummary) -> MonthTotals:
    return MonthTotals(
        month=month.strftime("%Y-%m"), income=flow.income, expenses=flow.expenses, balance=flow.balance
    )


def monthly_summary(db: Session, month: date) -> SummaryOut:
    """Cash flow of `month` and of the five before it, using four queries in total."""
    months = trailing_months(month, TREND_MONTHS)
    window_start = months[0]
    window_end = month_bounds(month)[1]

    accounts = [to_domain_account(row) for row in db.scalars(select(models.Account))]
    transactions = [
        to_domain_transaction(row)
        for row in db.scalars(
            select(models.Transaction).where(
                models.Transaction.status == TransactionStatus.CONFIRMED.value,
                models.Transaction.date >= _local_midnight(window_start),
                models.Transaction.date < _local_midnight(window_end),
            )
        )
    ]
    categories = {row.id: row for row in db.scalars(select(models.Category))}
    fx = load_rates(db, window_start, window_end)

    flows: dict[date, FlowSummary] = {}
    try:
        for first_day in months:
            start, end = month_bounds(first_day)
            flows[first_day] = cash_flow(accounts, transactions, start, end, fx)
    except DomainError:
        raise ApiError(
            409,
            "missing_fx_rate",
            "Hay movimientos en dólares sin una TRM registrada para convertirlos. Sincroniza la TRM e intenta de nuevo.",
        ) from None

    current = flows[month]
    return SummaryOut(
        month=month.strftime("%Y-%m"),
        income=current.income,
        expenses=current.expenses,
        balance=current.balance,
        income_by_category=_by_category(current.income_by_category, categories),
        expenses_by_category=_by_category(current.expenses_by_category, categories),
        trend=[_totals(first_day, flows[first_day]) for first_day in months],
    )
