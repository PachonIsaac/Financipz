import datetime as dt
import uuid
from decimal import Decimal

from pydantic import AwareDatetime

from app.schemas.common import Output
from app.schemas.enums import TradeSide
from app.schemas.reports import Cents, RateUsed


class PortfolioAsset(Output):
    asset: str
    quantity: Decimal
    # Null when the asset could not be priced.
    value_usd: Cents | None
    # Null when there is no value or no USD rate.
    value_cop: Cents | None


class PortfolioOut(Output):
    """Latest stored snapshot. Without any sync yet, `snapshot_date` is null and there are no assets."""

    snapshot_date: dt.date | None
    # Sum of the priced assets; null when there is no snapshot.
    total_usd: Cents | None
    total_cop: Cents | None
    unpriced_assets: int
    rate: RateUsed | None
    assets: list[PortfolioAsset]


class HistoryPoint(Output):
    date: dt.date
    total_usd: Cents


class TradeOut(Output):
    id: uuid.UUID
    account_id: uuid.UUID
    pair: str
    side: TradeSide
    quantity: Decimal
    price: Decimal
    fee: Decimal
    fee_asset: str | None
    executed_at: AwareDatetime
    external_id: str


class TradePage(Output):
    items: list[TradeOut]
    # Pass it as `cursor` to get the next page. Null when there are no more.
    next_cursor: str | None
