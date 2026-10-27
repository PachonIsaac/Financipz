import uuid
from datetime import UTC, date, datetime

import pytest

from app.domain.entities import (
    AccountType,
    Classification,
    Currency,
    TransactionStatus,
    TransactionType,
)
from app.domain.errors import DomainError
from app.domain.flow import cash_flow
from app.domain.fx import FxRates
from tests.domain.helpers import BOGOTA, D, make_account, make_transaction

T = TransactionType
OCTOBER = (date(2026, 10, 1), date(2026, 11, 1))
FX = FxRates({Currency.USD: {date(2026, 10, 15): D("4000")}})


def flow(accounts, transactions, period=OCTOBER, fx=FX):
    return cash_flow(accounts, transactions, *period, fx)


def test_income_and_expenses_make_the_balance():
    bank = make_account()
    summary = flow(
        [bank],
        [make_transaction(bank, T.INCOME, 3000), make_transaction(bank, T.EXPENSE, 1200)],
    )

    assert summary.income == D("3000")
    assert summary.expenses == D("1200")
    assert summary.balance == D("1800")


def test_balance_can_be_negative():
    bank = make_account()
    summary = flow([bank], [make_transaction(bank, T.EXPENSE, 500)])

    assert summary.balance == D("-500")


def test_credit_card_purchase_counts_once_and_its_payment_does_not():
    bank = make_account(initial=1000)
    card = make_account(AccountType.CREDIT_CARD)
    summary = flow(
        [bank, card],
        [
            make_transaction(card, T.EXPENSE, 100),
            make_transaction(bank, T.TRANSFER, 100, target=card, classification=Classification.PAYMENT),
        ],
    )

    assert summary.expenses == D("100")


@pytest.mark.parametrize(
    "classification",
    [None, Classification.LOAN, Classification.PAYMENT, Classification.OWN_TRANSFER],
)
def test_transfers_stay_out_of_the_flow_unless_classified_as_expense(classification):
    bank = make_account()
    other = make_account(AccountType.LOAN)
    target = other if classification is Classification.LOAN else None
    summary = flow([bank, other], [make_transaction(bank, T.TRANSFER, 100, target=target, classification=classification)])

    assert summary.income == 0
    assert summary.expenses == 0


def test_transfer_classified_as_expense_counts_as_an_expense_with_its_category():
    bank = make_account()
    plumbing = uuid.uuid4()
    transfer = make_transaction(
        bank, T.TRANSFER, 80, classification=Classification.EXPENSE, category=plumbing
    )

    summary = flow([bank], [transfer])

    assert summary.expenses == D("80")
    assert summary.expenses_by_category == {plumbing: D("80")}


@pytest.mark.parametrize("kind", [T.ADJUSTMENT_IN, T.ADJUSTMENT_OUT])
def test_adjustments_stay_out_of_the_flow(kind):
    bank = make_account()
    summary = flow([bank], [make_transaction(bank, kind, 100)])

    assert summary.income == 0
    assert summary.expenses == 0


def test_exchange_accounts_stay_out_of_the_flow():
    exchange = make_account(AccountType.EXCHANGE, Currency.USD)
    summary = flow(
        [exchange],
        [make_transaction(exchange, T.INCOME, 50), make_transaction(exchange, T.EXPENSE, 20)],
    )

    assert summary.income == 0
    assert summary.expenses == 0


@pytest.mark.parametrize("status", [TransactionStatus.PENDING_REVIEW, TransactionStatus.DISCARDED])
def test_only_confirmed_transactions_count(status):
    bank = make_account()
    summary = flow([bank], [make_transaction(bank, T.EXPENSE, 100, status=status)])

    assert summary.expenses == 0


def test_foreign_currency_uses_the_rate_of_its_own_day():
    card_usd = make_account(AccountType.CREDIT_CARD, Currency.USD)
    fx = FxRates({Currency.USD: {date(2026, 10, 10): D("4000"), date(2026, 10, 20): D("4200")}})
    purchases = [
        make_transaction(card_usd, T.EXPENSE, 20, when=datetime(2026, 10, 10, 9, 0, tzinfo=BOGOTA)),
        make_transaction(card_usd, T.EXPENSE, 10, when=datetime(2026, 10, 20, 9, 0, tzinfo=BOGOTA)),
    ]

    summary = flow([card_usd], purchases, fx=fx)

    assert summary.expenses == D("122000.00")


def test_foreign_currency_without_any_rate_is_rejected():
    card_usd = make_account(AccountType.CREDIT_CARD, Currency.USD)

    with pytest.raises(DomainError, match="rate"):
        flow([card_usd], [make_transaction(card_usd, T.EXPENSE, 20)], fx=FxRates())


def test_period_includes_the_start_day_and_excludes_the_end_day():
    bank = make_account()
    transactions = [
        make_transaction(bank, T.EXPENSE, 1, when=datetime(2026, 10, 1, 0, 0, tzinfo=BOGOTA)),
        make_transaction(bank, T.EXPENSE, 10, when=datetime(2026, 10, 31, 23, 59, tzinfo=BOGOTA)),
        make_transaction(bank, T.EXPENSE, 100, when=datetime(2026, 11, 1, 0, 0, tzinfo=BOGOTA)),
        make_transaction(bank, T.EXPENSE, 1000, when=datetime(2026, 9, 30, 23, 59, tzinfo=BOGOTA)),
    ]

    assert flow([bank], transactions).expenses == D("11")


def test_days_follow_colombian_time_not_utc():
    bank = make_account()
    # 22:00 in Bogota on Oct 31 is already Nov 1 in UTC, but it belongs to October.
    late_october = make_transaction(bank, T.EXPENSE, 7, when=datetime(2026, 11, 1, 3, 0, tzinfo=UTC))
    # 00:30 in Bogota on Nov 1 is Nov 1 05:30 in UTC and belongs to November.
    early_november = make_transaction(bank, T.EXPENSE, 9, when=datetime(2026, 11, 1, 5, 30, tzinfo=UTC))

    assert flow([bank], [late_october, early_november]).expenses == D("7")


def test_totals_are_split_by_category_including_uncategorized():
    bank = make_account()
    food, salary = uuid.uuid4(), uuid.uuid4()
    summary = flow(
        [bank],
        [
            make_transaction(bank, T.EXPENSE, 30, category=food),
            make_transaction(bank, T.EXPENSE, 20, category=food),
            make_transaction(bank, T.EXPENSE, 5),
            make_transaction(bank, T.INCOME, 900, category=salary),
        ],
    )

    assert summary.expenses_by_category == {food: D("50"), None: D("5")}
    assert summary.income_by_category == {salary: D("900")}


def test_unknown_account_is_rejected():
    known = make_account()
    unknown = make_account()

    with pytest.raises(DomainError, match="unknown account"):
        flow([known], [make_transaction(unknown, T.EXPENSE, 10)])
