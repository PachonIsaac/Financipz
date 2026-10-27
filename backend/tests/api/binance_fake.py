"""An in-memory stand-in for the exchange, served through httpx's mock transport. Nothing touches the network."""

from collections.abc import Callable

import httpx

from app.integrations import binance
from app.integrations.binance import BinanceClient, Credentials

API_KEY = "invented-key-0001"
API_SECRET = "invented-secret-0001"


def safe_restrictions(**overrides) -> dict:
    restrictions = {
        "ipRestrict": True,
        "createTime": 1700000000000,
        "enableReading": True,
        "enableWithdrawals": False,
        "enableInternalTransfer": False,
        "permitsUniversalTransfer": False,
        "enableMargin": False,
        "enableFutures": False,
        "enableSpotAndMarginTrading": False,
        "enableVanillaOptions": False,
        "enablePortfolioMarginTrading": False,
        "enableFixApiTrade": False,
        "enableFixReadOnly": True,
    }
    restrictions.update(overrides)
    return restrictions


def balance(asset: str, free: str, locked: str = "0") -> dict:
    return {"asset": asset, "free": free, "locked": locked}


def trade_row(symbol: str, trade_id: int, buyer: bool = True, price: str = "100", qty: str = "1",
              time: int = 1700000000000, commission: str = "0.001", fee_asset: str = "BNB") -> dict:
    return {
        "symbol": symbol, "id": trade_id, "orderId": 1, "price": price, "qty": qty, "quoteQty": "0",
        "commission": commission, "commissionAsset": fee_asset, "time": time + trade_id,
        "isBuyer": buyer, "isMaker": False, "isBestMatch": True,
    }


def error(status: int, code: int, msg: str = "invented error") -> Callable:
    return lambda request: httpx.Response(status, json={"code": code, "msg": msg})


class FakeExchange:
    """Answers like the exchange. Set an attribute, or an entry in `overrides`, to change what it says."""

    def __init__(self) -> None:
        self.restrictions = safe_restrictions()
        self.spot = [balance("BTC", "0.5", "0.25"), balance("USDT", "100")]
        self.funding: list = []
        self.earn_flexible: list = []
        self.earn_locked: list = []
        self.prices = [
            {"symbol": "BTCUSDT", "price": "80000.00"},
            {"symbol": "ETHUSDT", "price": "2500.00"},
            {"symbol": "ETHBTC", "price": "0.03"},
            {"symbol": "XYZBTC", "price": "0.00001"},
            {"symbol": "BNBUSDT", "price": "600.00"},
        ]
        self.trades: dict[str, list[dict]] = {}
        # Path -> handler that replaces the normal answer.
        self.overrides: dict[str, Callable[[httpx.Request], httpx.Response]] = {}
        self.requests: list[httpx.Request] = []
        # The encryption key the application runs with in the tests.
        self.encryption_key = ""

    def paths(self) -> list[str]:
        return [request.url.path for request in self.requests]

    def trade_requests(self) -> list[dict]:
        return [dict(request.url.params) for request in self.requests if request.url.path == "/api/v3/myTrades"]

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path in self.overrides:
            return self.overrides[path](request)
        if path == "/sapi/v1/account/apiRestrictions":
            return httpx.Response(200, json=self.restrictions)
        if path == "/api/v3/account":
            return httpx.Response(200, json={"balances": self.spot})
        if path == "/sapi/v1/asset/get-funding-asset":
            return httpx.Response(200, json=self.funding)
        if path == "/sapi/v1/simple-earn/flexible/position":
            return httpx.Response(200, json={"rows": self.earn_flexible, "total": len(self.earn_flexible)})
        if path == "/sapi/v1/simple-earn/locked/position":
            return httpx.Response(200, json={"rows": self.earn_locked, "total": len(self.earn_locked)})
        if path == "/api/v3/ticker/price":
            return httpx.Response(200, json=self.prices)
        if path == "/api/v3/myTrades":
            params = request.url.params
            symbol, from_id, limit = params["symbol"], int(params["fromId"]), int(params["limit"])
            rows = sorted((row for row in self.trades.get(symbol, []) if row["id"] >= from_id), key=lambda r: r["id"])
            return httpx.Response(200, json=rows[:limit])
        return httpx.Response(404, json={"code": -1, "msg": "unknown path"})

    def client(self, credentials: Credentials) -> BinanceClient:
        http = httpx.Client(
            base_url=binance.BASE_URL, transport=httpx.MockTransport(self.handle), follow_redirects=False
        )
        return BinanceClient(credentials, http=http, sleep=lambda seconds: None)
