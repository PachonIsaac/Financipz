import pytest

from app.domain.balances import balances_by_currency, compute_balances
from app.domain.entities import AccountType, Currency, TransactionStatus, TransactionType
from app.domain.errors import DomainError
from tests.domain.helpers import D, make_account, make_transaction

T = TransactionType


def test_balance_starts_at_the_initial_balance():
    account = make_account(initial=1000)

    assert compute_balances([account], [])[account.id] == D("1000")


def test_income_adds_and_expense_subtracts():
    account = make_account(initial=1000)
    transactions = [
        make_transaction(account, T.INCOME, 500),
        make_transaction(account, T.EXPENSE, 200),
    ]

    assert compute_balances([account], transactions)[account.id] == D("1300")


def test_adjustments_move_the_balance_in_the_direction_of_their_type():
    account = make_account(initial=1000)
    transactions = [
        make_transaction(account, T.ADJUSTMENT_IN, 70),
        make_transaction(account, T.ADJUSTMENT_OUT, 20),
    ]

    assert compute_balances([account], transactions)[account.id] == D("1050")


@pytest.mark.parametrize("status", [TransactionStatus.PENDING_REVIEW, TransactionStatus.DISCARDED])
def test_only_confirmed_transactions_count(status):
    account = make_account(initial=1000)
    transactions = [make_transaction(account, T.EXPENSE, 400, status=status)]

    assert compute_balances([account], transactions)[account.id] == D("1000")


def test_transfer_moves_money_between_accounts():
    bank = make_account(initial=1000)
    cash = make_account(AccountType.CASH)
    transactions = [make_transaction(bank, T.TRANSFER, 130, target=cash)]

    balances = compute_balances([bank, cash], transactions)

    assert balances[bank.id] == D("870")
    assert balances[cash.id] == D("130")


def test_transfer_without_a_known_destination_only_subtracts_from_the_source():
    bank = make_account(initial=1000)
    transactions = [make_transaction(bank, T.TRANSFER, 50)]

    assert compute_balances([bank], transactions)[bank.id] == D("950")


def test_credit_card_balance_is_negative_debt_and_a_payment_reduces_it():
    bank = make_account(initial=1000)
    card = make_account(AccountType.CREDIT_CARD)
    transactions = [
        make_transaction(card, T.EXPENSE, 300),
        make_transaction(bank, T.TRANSFER, 100, target=card),
    ]

    balances = compute_balances([bank, card], transactions)

    assert balances[card.id] == D("-200")
    assert balances[bank.id] == D("900")


def test_lending_raises_the_loan_account_and_a_repayment_lowers_it():
    bank = make_account(initial=1000)
    loan = make_account(AccountType.LOAN)
    lend = make_transaction(bank, T.TRANSFER, 400, target=loan)
    repay = make_transaction(loan, T.TRANSFER, 150, target=bank)

    balances = compute_balances([bank, loan], [lend, repay])

    assert balances[loan.id] == D("250")
    assert balances[bank.id] == D("750")


def test_a_balance_can_go_negative():
    account = make_account(initial=100)
    transactions = [make_transaction(account, T.EXPENSE, 350)]

    assert compute_balances([account], transactions)[account.id] == D("-250")


def test_cross_currency_transfer_uses_the_target_amount():
    bank = make_account(initial=1_000_000)
    card_usd = make_account(AccountType.CREDIT_CARD, Currency.USD)
    transactions = [
        make_transaction(card_usd, T.EXPENSE, 100),
        make_transaction(bank, T.TRANSFER, 400_000, target=card_usd, target_amount=100),
    ]

    balances = compute_balances([bank, card_usd], transactions)

    assert balances[bank.id] == D("600000")
    assert balances[card_usd.id] == D("0")


def test_cross_currency_transfer_without_target_amount_is_rejected():
    bank = make_account(initial=1_000_000)
    card_usd = make_account(AccountType.CREDIT_CARD, Currency.USD)
    transactions = [make_transaction(bank, T.TRANSFER, 400_000, target=card_usd)]

    with pytest.raises(DomainError, match="target amount"):
        compute_balances([bank, card_usd], transactions)


def test_transaction_currency_must_match_its_account():
    bank = make_account()
    transactions = [make_transaction(bank, T.EXPENSE, 10, currency=Currency.USD)]

    with pytest.raises(DomainError, match="USD"):
        compute_balances([bank], transactions)


def test_unknown_account_is_rejected():
    known = make_account()
    unknown = make_account()
    transactions = [make_transaction(unknown, T.EXPENSE, 10)]

    with pytest.raises(DomainError, match="unknown account"):
        compute_balances([known], transactions)


def test_unknown_target_account_is_rejected():
    bank = make_account(initial=100)
    unknown = make_account()
    transactions = [make_transaction(bank, T.TRANSFER, 10, target=unknown)]

    with pytest.raises(DomainError, match="unknown account"):
        compute_balances([bank], transactions)


def test_transaction_amount_must_be_positive():
    account = make_account()

    with pytest.raises(DomainError, match="positive"):
        make_transaction(account, T.EXPENSE, 0)
    with pytest.raises(DomainError, match="positive"):
        make_transaction(account, T.EXPENSE, -5)


def test_balances_by_currency_do_not_mix_currencies():
    cop_a = make_account(initial=100)
    cop_b = make_account(initial=50)
    usd = make_account(AccountType.SAVINGS, Currency.USD, initial=30)
    accounts = [cop_a, cop_b, usd]

    totals = balances_by_currency(accounts, compute_balances(accounts, []))

    assert totals == {Currency.COP: D("150"), Currency.USD: D("30")}
