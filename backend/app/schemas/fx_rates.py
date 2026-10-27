import datetime as dt
from decimal import Decimal

from app.schemas.common import Output


class FxRateOut(Output):
    date: dt.date
    currency: str
    # Pesos per unit of the currency, with four decimals.
    value: Decimal
    source: str
