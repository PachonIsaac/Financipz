from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from app.domain.entities import Currency, TransactionType


class NotificationSource(StrEnum):
    GMAIL = "gmail"
    SMS_UALA = "sms_uala"


class NotificationKind(StrEnum):
    PURCHASE = "purchase"
    PAYMENT = "payment"
    TRANSFER_OUT = "transfer_out"
    TRANSFER_IN = "transfer_in"
    PAYROLL = "payroll"
    WITHDRAWAL = "withdrawal"
    SCHEDULED_BILL = "scheduled_bill"
    YIELD = "yield"
    CARD_BONUS = "card_bonus"
    TOP_UP = "top_up"
    IGNORED = "ignored"


# Suggested transaction type per kind. A transfer to or from an own account
# must be reclassified by the caller, who knows the user's accounts.
SUGGESTED_TYPE: dict[NotificationKind, TransactionType | None] = {
    NotificationKind.PURCHASE: TransactionType.EXPENSE,
    NotificationKind.PAYMENT: TransactionType.EXPENSE,
    NotificationKind.TRANSFER_OUT: TransactionType.EXPENSE,
    NotificationKind.TRANSFER_IN: TransactionType.INCOME,
    NotificationKind.PAYROLL: TransactionType.INCOME,
    NotificationKind.WITHDRAWAL: TransactionType.TRANSFER,
    NotificationKind.SCHEDULED_BILL: TransactionType.EXPENSE,
    NotificationKind.YIELD: TransactionType.INCOME,
    NotificationKind.CARD_BONUS: TransactionType.INCOME,
    NotificationKind.TOP_UP: TransactionType.TRANSFER,
    NotificationKind.IGNORED: None,
}


@dataclass(frozen=True)
class ParsedNotification:
    source: NotificationSource
    kind: NotificationKind
    amount: Decimal | None = None
    currency: Currency | None = None
    # Merchant, payer or payee as written in the text.
    merchant: str | None = None
    # Destination of a transfer: a recipient name, a key or an account number.
    target_text: str | None = None
    # The Bre-b key of the destination (`@alias`), when the text names one.
    target_key: str | None = None
    last_digits: str | None = None
    # Timezone-aware moment. None when the text carries no time of day.
    occurred_at: datetime | None = None
    # Calendar day when the text carries a date, even without a time.
    occurred_on: date | None = None

    @property
    def suggested_type(self) -> TransactionType | None:
        return SUGGESTED_TYPE[self.kind]

    @property
    def is_movement(self) -> bool:
        return self.kind is not NotificationKind.IGNORED
