import uuid
from collections.abc import Iterable, Mapping
from decimal import Decimal

from app.domain.entities import Account, Currency, Transaction, TransactionStatus, TransactionType
from app.domain.errors import DomainError


def compute_balances(
    accounts: Iterable[Account],
    transactions: Iterable[Transaction],
) -> dict[uuid.UUID, Decimal]:
    """Balance of every account, in the account's own currency.

    A balance is the initial balance plus the effect of every confirmed transaction. It can be
    negative: a credit card whose debt exceeds its payments, or an overdrawn account.
    Pending and discarded transactions do not count.
    """
    by_id = {account.id: account for account in accounts}
    balances = {account.id: account.initial_balance for account in by_id.values()}

    for transaction in transactions:
        if transaction.status is not TransactionStatus.CONFIRMED:
            continue

        source = _find(by_id, transaction.account_id, transaction)
        if transaction.currency is not source.currency:
            raise DomainError(
                f"Transaction {transaction.id} is in {transaction.currency} "
                f"but its account is in {source.currency}"
            )

        match transaction.type:
            case TransactionType.INCOME | TransactionType.ADJUSTMENT_IN:
                balances[source.id] += transaction.amount
            case TransactionType.EXPENSE | TransactionType.ADJUSTMENT_OUT:
                balances[source.id] -= transaction.amount
            case TransactionType.TRANSFER:
                balances[source.id] -= transaction.amount
                if transaction.target_account_id is not None:
                    target = _find(by_id, transaction.target_account_id, transaction)
                    balances[target.id] += _received_amount(transaction, source, target)

    return balances


def balances_by_currency(
    accounts: Iterable[Account],
    balances: Mapping[uuid.UUID, Decimal],
) -> dict[Currency, Decimal]:
    """Add up account balances without mixing currencies."""
    totals: dict[Currency, Decimal] = {}
    for account in accounts:
        totals[account.currency] = totals.get(account.currency, Decimal(0)) + balances[account.id]
    return totals


def _find(by_id: Mapping[uuid.UUID, Account], account_id: uuid.UUID, transaction: Transaction) -> Account:
    try:
        return by_id[account_id]
    except KeyError:
        raise DomainError(f"Transaction {transaction.id} refers to an unknown account {account_id}") from None


def _received_amount(transaction: Transaction, source: Account, target: Account) -> Decimal:
    if transaction.target_amount is not None:
        return transaction.target_amount
    if source.currency is not target.currency:
        raise DomainError(
            f"Transaction {transaction.id} moves {source.currency} to {target.currency} "
            "and needs a target amount"
        )
    return transaction.amount
