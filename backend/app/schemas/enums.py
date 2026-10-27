from enum import StrEnum


class CategoryType(StrEnum):
    EXPENSE = "expense"
    INCOME = "income"
    TRANSFER = "transfer"


class TradeSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class TransactionSource(StrEnum):
    MANUAL = "manual"
    GMAIL = "gmail"
    SMS_UALA = "sms_uala"
    WALLET = "wallet"
    BINANCE = "binance"
    MYFINANCE_IMPORT = "myfinance_import"
