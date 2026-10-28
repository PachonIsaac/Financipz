from datetime import date

from app.domain.balances import compute_balances
from app.domain.entities import AccountType, Currency, TransactionType
from app.domain.fx import FxRates
from app.domain.wealth import compute_wealth
from tests.domain.helpers import D, make_account, make_transaction

TODAY = date(2026, 10, 26)
FX = FxRates({Currency.USD: {date(2026, 10, 26): D("4000")}})


def wealth(accounts, balances, **kwargs):
    return compute_wealth(accounts, balances, FX, TODAY, **kwargs)


def test_real_money_is_available_minus_card_debt():
    bank = make_account()
    card = make_account(AccountType.CREDIT_CARD)

    result = wealth([bank, card], {bank.id: D("1000000"), card.id: D("-300000")})

    assert result.available == D("1000000")
    assert result.credit_card_debt == D("300000")
    assert result.real_money == D("700000")


def test_real_money_is_negative_when_debt_exceeds_what_is_available():
    bank = make_account()
    card = make_account(AccountType.CREDIT_CARD)

    result = wealth([bank, card], {bank.id: D("200000"), card.id: D("-500000")})

    assert result.real_money == D("-300000")


def test_cash_bank_savings_and_wallet_are_available():
    accounts = [make_account(type) for type in (
        AccountType.CASH, AccountType.BANK, AccountType.SAVINGS, AccountType.WALLET
    )]

    result = wealth(accounts, {account.id: D("100") for account in accounts})

    assert result.available == D("400")


def test_loans_are_shown_apart_and_do_not_change_real_money():
    bank = make_account()
    loan_a = make_account(AccountType.LOAN)
    loan_b = make_account(AccountType.LOAN)
    balances = {bank.id: D("1000"), loan_a.id: D("300"), loan_b.id: D("50")}

    result = wealth([bank, loan_a, loan_b], balances)

    assert result.real_money == D("1000")
    assert result.receivable_loans == D("350")
    assert result.receivable_loans_by_account == {loan_a.id: D("300"), loan_b.id: D("50")}


def test_exchange_and_system_accounts_are_left_out():
    bank = make_account()
    exchange = make_account(AccountType.EXCHANGE, Currency.USD)
    system = make_account(AccountType.SYSTEM)
    balances = {bank.id: D("1000"), exchange.id: D("999"), system.id: D("-888")}

    result = wealth([bank, exchange, system], balances)

    assert result.available == D("1000")
    assert result.credit_card_debt == 0
    assert result.real_money == D("1000")


def test_accounts_left_out_of_the_balance_count_nowhere():
    bank = make_account()
    savings = make_account(AccountType.SAVINGS, include_in_balance=False)
    card = make_account(AccountType.CREDIT_CARD, include_in_balance=False)
    loan = make_account(AccountType.LOAN, include_in_balance=False)
    balances = {bank.id: D("1000"), savings.id: D("500"), card.id: D("-300"), loan.id: D("200")}

    result = wealth([bank, savings, card, loan], balances)

    assert result.available == D("1000")
    assert result.credit_card_debt == 0
    assert result.receivable_loans == 0
    assert result.real_money == D("1000")


def test_foreign_currency_balances_are_valued_with_the_rate_of_the_day():
    savings_usd = make_account(AccountType.SAVINGS, Currency.USD)
    card_usd = make_account(AccountType.CREDIT_CARD, Currency.USD)

    result = wealth([savings_usd, card_usd], {savings_usd.id: D("100"), card_usd.id: D("-25")})

    assert result.available == D("400000.00")
    assert result.credit_card_debt == D("100000.00")


def test_a_card_with_a_positive_balance_adds_nothing():
    bank = make_account()
    card = make_account(AccountType.CREDIT_CARD)

    result = wealth([bank, card], {bank.id: D("1000"), card.id: D("50")})

    assert result.credit_card_debt == 0
    assert result.real_money == D("1000")


def test_archived_accounts_count_unless_excluded():
    bank = make_account()
    old = make_account(archived=True)
    balances = {bank.id: D("1000"), old.id: D("40")}

    assert wealth([bank, old], balances).available == D("1040")
    assert wealth([bank, old], balances, include_archived=False).available == D("1000")


def test_wealth_from_real_transactions():
    bank = make_account(initial=1000)
    card = make_account(AccountType.CREDIT_CARD)
    accounts = [bank, card]
    transactions = [
        make_transaction(card, TransactionType.EXPENSE, 300),
        make_transaction(bank, TransactionType.TRANSFER, 100, target=card),
    ]

    result = wealth(accounts, compute_balances(accounts, transactions))

    assert result.available == D("900")
    assert result.credit_card_debt == D("200")
    assert result.real_money == D("700")
