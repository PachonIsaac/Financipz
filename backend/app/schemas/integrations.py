import datetime as dt

from pydantic import Field, SecretStr, field_validator

from app.schemas.common import Input, Output
from app.schemas.reports import Cents


class BinanceConnect(Input):
    """SecretStr keeps the values out of reprs and logs."""

    api_key: SecretStr = Field(min_length=8, max_length=256)
    api_secret: SecretStr = Field(min_length=8, max_length=256)

    @field_validator("api_key", "api_secret")
    @classmethod
    def no_whitespace(cls, value: SecretStr) -> SecretStr:
        text = value.get_secret_value()
        if any(character.isspace() for character in text):
            raise ValueError("must not contain spaces")
        if not text.isascii():
            raise ValueError("must only contain ASCII characters")
        return value


class NoticeOut(Output):
    code: str
    message: str


class IntegrationOut(Output):
    provider: str
    # active, error or disconnected. For `error`, `warnings` says why.
    status: str
    last_synced_at: dt.datetime | None
    warnings: list[NoticeOut]


class SyncOut(Output):
    snapshot_date: dt.date
    # Assets held, and how many of them could not be priced in dollars (kept with a null value).
    assets: int
    unpriced_assets: int
    total_usd: Cents
    new_trades: int
    # False when the number of requests ran out or the exchange asked to slow down.
    trades_complete: bool
    warnings: list[NoticeOut]
    last_synced_at: dt.datetime
