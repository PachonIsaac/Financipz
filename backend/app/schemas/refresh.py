import datetime as dt
from typing import Literal

from app.schemas.common import Output


class StepOut(Output):
    # `not_connected` is not a failure: there is nothing to read until a key is connected.
    status: Literal["ok", "not_connected", "error"]
    # Stable identifier and Spanish message, only when the step did not succeed.
    code: str | None
    message: str | None


class RefreshOut(Output):
    fx_rates: StepOut
    binance: StepOut
    ran_at: dt.datetime
    # True when the previous result was returned because it was too recent to run again.
    cached: bool
