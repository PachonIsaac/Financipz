import datetime as dt
import uuid
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, StringConstraints, field_validator

from app.domain.entities import LOCAL_TIMEZONE
from app.schemas.common import Input, Output


class ShortcutIn(Input):
    """What the iOS shortcut sends for each SMS. The text is read and dropped: only the fields found are kept."""

    source: Literal["sms_uala"]
    text: Annotated[str, StringConstraints(min_length=1, max_length=2000)]
    received_at: dt.datetime

    @field_validator("received_at")
    @classmethod
    def local_when_naive(cls, value: dt.datetime) -> AwareDatetime:
        return value.replace(tzinfo=LOCAL_TIMEZONE) if value.tzinfo is None else value


class ShortcutOut(Output):
    # `created` or `ignored`. A repeat or a text nobody understood answers with an error instead.
    result: Literal["created", "ignored"]
    id: uuid.UUID | None


class TokenStatus(Output):
    configured: bool
    created_at: AwareDatetime | None
    last_used_at: AwareDatetime | None


class TokenCreated(Output):
    # Shown once. It cannot be read again, only replaced.
    token: str = Field(min_length=20)
    created_at: AwareDatetime
