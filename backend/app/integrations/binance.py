"""Read-only client for the Binance REST API.

Signed requests carry the API key in a header and an HMAC-SHA256 signature of the query string, computed
with the API secret. Nothing here ever writes to the exchange. Errors never include the key, the secret,
the signature or the request URL.
"""

import hashlib
import hmac
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

import httpx

BASE_URL = "https://api.binance.com"
TIMEOUT_SECONDS = 10.0
RECV_WINDOW_MS = 5000
# Pause between requests, so a sync stays far from the exchange's rate limits.
MIN_INTERVAL_SECONDS = 0.1
TRADES_PAGE_SIZE = 1000
EARN_PAGE_SIZE = 100
MAX_EARN_PAGES = 20

# ASCII only, and matched as a whole: nothing else may reach a URL or a stored symbol.
ASSET_PATTERN = re.compile(r"[A-Z0-9]{1,20}", re.ASCII)
SYMBOL_PATTERN = re.compile(r"[A-Z0-9]{2,30}", re.ASCII)

# Kinds of failure, from the point of view of the caller.
INVALID_CREDENTIALS = "invalid_credentials"
ACCESS_DENIED = "access_denied"
CLOCK_SKEW = "clock_skew"
RATE_LIMITED = "rate_limited"
UNAVAILABLE = "unavailable"
BAD_RESPONSE = "bad_response"
REJECTED = "rejected"

# Binance error codes (the `code` field of an error body).
CODE_KINDS = {
    -1022: INVALID_CREDENTIALS,  # signature for this request is not valid
    -2008: INVALID_CREDENTIALS,  # invalid API key id
    -2014: INVALID_CREDENTIALS,  # API key format invalid
    -2015: ACCESS_DENIED,  # invalid key, IP not allowed, or missing permission
    -1002: ACCESS_DENIED,  # not authorized for this action
    -1021: CLOCK_SKEW,  # timestamp outside the receive window
    -1003: RATE_LIMITED,  # too many requests
    -1001: UNAVAILABLE,  # internal error
    -1007: UNAVAILABLE,  # timeout waiting for the backend
    -1008: RATE_LIMITED,  # server overloaded
}


class BinanceError(Exception):
    """A failed call to Binance. The message is fixed text: it never carries credentials."""

    def __init__(self, kind: str, binance_code: int | None = None, retry_after: int | None = None) -> None:
        super().__init__(kind)
        self.kind = kind
        self.binance_code = binance_code
        self.retry_after = retry_after


@dataclass(frozen=True)
class Credentials:
    api_key: str = ""
    api_secret: str = ""

    def __repr__(self) -> str:
        return "Credentials(<hidden>)"


@dataclass(frozen=True)
class WalletRead:
    """Balances of one wallet, and how many rows were left out because their asset name is not usable."""

    balances: list[tuple[str, Decimal]]
    skipped: int = 0


@dataclass(frozen=True)
class Trade:
    symbol: str
    trade_id: int
    side: str
    quantity: Decimal
    price: Decimal
    fee: Decimal
    fee_asset: str | None
    executed_at: datetime


def sign(secret: str, query: str) -> str:
    """Hex HMAC-SHA256 of the query string, as the exchange expects."""
    return hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()


def build_http_client() -> httpx.Client:
    return httpx.Client(base_url=BASE_URL, timeout=httpx.Timeout(TIMEOUT_SECONDS), follow_redirects=False)


def _bad() -> BinanceError:
    return BinanceError(BAD_RESPONSE)


def _amount(raw: object) -> Decimal:
    try:
        value = Decimal(str(raw))
    except InvalidOperation:
        raise _bad() from None
    if not value.is_finite() or value < 0:
        raise _bad()
    return value


def _wallet(rows: list[dict], amount: Callable[[dict], Decimal]) -> WalletRead:
    """Read balance rows. A row whose asset name is unusable is skipped and counted, never trusted."""
    balances: list[tuple[str, Decimal]] = []
    skipped = 0
    for row in rows:
        name = row.get("asset")
        if not isinstance(name, str) or not ASSET_PATTERN.fullmatch(name):
            skipped += 1
            continue
        balances.append((name, amount(row)))
    return WalletRead(balances, skipped)


def _rows(body: object, key: str | None = None) -> list[dict]:
    if key:
        if not isinstance(body, dict):
            raise _bad()
        body = body.get(key)
    rows = body
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        raise _bad()
    return rows


class BinanceClient:
    def __init__(
        self,
        credentials: Credentials,
        http: httpx.Client | None = None,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
        min_interval: float = MIN_INTERVAL_SECONDS,
    ) -> None:
        self._credentials = credentials
        self._http = http or build_http_client()
        self._clock = clock
        self._sleep = sleep
        self._min_interval = min_interval
        self.requests_made = 0

    def __repr__(self) -> str:
        return "BinanceClient(<hidden>)"

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "BinanceClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # --- transport -------------------------------------------------------------------------

    def _request(self, path: str, params: dict[str, object] | None = None, signed: bool = False, method: str = "GET") -> object:
        if self.requests_made and self._min_interval:
            self._sleep(self._min_interval)
        self.requests_made += 1

        query_params = dict(params or {})
        headers = {}
        try:
            if signed:
                query_params["recvWindow"] = RECV_WINDOW_MS
                query_params["timestamp"] = int(self._clock() * 1000)
                headers["X-MBX-APIKEY"] = self._credentials.api_key
            query = urlencode(query_params)
            if signed:
                query += "&signature=" + sign(self._credentials.api_secret, query)
            target = f"{path}?{query}" if query else path
            response = self._http.request(method, target, headers=headers)
        except httpx.HTTPError:
            # The original error carries the URL, which holds the signature.
            raise BinanceError(UNAVAILABLE) from None
        except ValueError:
            # A key or secret that cannot be encoded. The original error would quote it.
            raise BinanceError(INVALID_CREDENTIALS) from None
        return self._read(response)

    @staticmethod
    def _read(response: httpx.Response) -> object:
        status = response.status_code
        retry_after = None
        if status in (418, 429):
            try:
                retry_after = int(response.headers.get("Retry-After", ""))
            except ValueError:
                retry_after = None
            raise BinanceError(RATE_LIMITED, retry_after=retry_after)
        if status >= 500:
            raise BinanceError(UNAVAILABLE)

        try:
            body = response.json()
        except ValueError:
            raise _bad() from None

        if isinstance(body, dict) and isinstance(body.get("code"), int) and body["code"] < 0:
            code = body["code"]
            raise BinanceError(CODE_KINDS.get(code, REJECTED), binance_code=code)
        if status in (401, 403):
            raise BinanceError(ACCESS_DENIED)
        if status >= 400:
            raise BinanceError(REJECTED)
        if not 200 <= status < 300:
            # Redirects and anything else that is not a success are never data.
            raise _bad()
        return body

    # --- account ---------------------------------------------------------------------------

    def api_restrictions(self) -> dict:
        """What the API key is allowed to do."""
        body = self._request("/sapi/v1/account/apiRestrictions", signed=True)
        if not isinstance(body, dict):
            raise _bad()
        return body

    def spot_balances(self) -> WalletRead:
        body = self._request("/api/v3/account", {"omitZeroBalances": "true"}, signed=True)
        if not isinstance(body, dict):
            raise _bad()
        return _wallet(_rows(body, "balances"), lambda row: _amount(row.get("free")) + _amount(row.get("locked")))

    def funding_balances(self) -> WalletRead:
        body = self._request("/sapi/v1/asset/get-funding-asset", signed=True, method="POST")
        return _wallet(
            _rows(body),
            lambda row: _amount(row.get("free")) + _amount(row.get("locked")) + _amount(row.get("freeze", "0")),
        )

    def _earn_positions(self, path: str, amount_field: str) -> WalletRead:
        positions: list[tuple[str, Decimal]] = []
        skipped = 0
        read = 0
        for page in range(1, MAX_EARN_PAGES + 1):
            body = self._request(path, {"current": page, "size": EARN_PAGE_SIZE}, signed=True)
            rows = _rows(body, "rows")
            wallet = _wallet(rows, lambda row: _amount(row.get(amount_field)))
            positions.extend(wallet.balances)
            skipped += wallet.skipped
            read += len(rows)
            total = body.get("total") if isinstance(body, dict) else None
            if not rows or not isinstance(total, int) or read >= total:
                return WalletRead(positions, skipped)
        raise _bad()

    def earn_flexible_balances(self) -> WalletRead:
        return self._earn_positions("/sapi/v1/simple-earn/flexible/position", "totalAmount")

    def earn_locked_balances(self) -> WalletRead:
        return self._earn_positions("/sapi/v1/simple-earn/locked/position", "amount")

    # --- market ----------------------------------------------------------------------------

    def prices(self) -> dict[str, Decimal]:
        """Last price of every pair. Entries that cannot be read are left out."""
        prices: dict[str, Decimal] = {}
        for row in _rows(self._request("/api/v3/ticker/price")):
            symbol = row.get("symbol")
            if not isinstance(symbol, str) or not SYMBOL_PATTERN.fullmatch(symbol):
                continue
            try:
                price = _amount(row.get("price"))
            except BinanceError:
                continue
            if price > 0:
                prices[symbol] = price
        return prices

    def trades(self, symbol: str, from_id: int) -> list[Trade]:
        """Trades of one pair with id `from_id` or higher, oldest first, up to one page."""
        body = self._request(
            "/api/v3/myTrades",
            {"symbol": symbol, "fromId": from_id, "limit": TRADES_PAGE_SIZE},
            signed=True,
        )
        trades = []
        for row in _rows(body):
            trade_id = row.get("id")
            moment = row.get("time")
            if not isinstance(trade_id, int) or isinstance(trade_id, bool) or not isinstance(moment, int):
                raise _bad()
            if not isinstance(row.get("isBuyer"), bool):
                raise _bad()
            price = _amount(row.get("price"))
            if price <= 0:
                raise _bad()
            try:
                executed_at = datetime.fromtimestamp(moment / 1000, UTC)
            except (OverflowError, OSError, ValueError):
                raise _bad() from None
            fee_asset = row.get("commissionAsset")
            trades.append(
                Trade(
                    symbol=symbol,
                    trade_id=trade_id,
                    side="buy" if row["isBuyer"] else "sell",
                    quantity=_amount(row.get("qty")),
                    price=price,
                    fee=_amount(row.get("commission", "0")),
                    fee_asset=fee_asset if isinstance(fee_asset, str) and ASSET_PATTERN.fullmatch(fee_asset) else None,
                    executed_at=executed_at,
                )
            )
        return trades


def build_client(credentials: Credentials) -> BinanceClient:
    """The client used by the application. Tests replace this to avoid the network."""
    return BinanceClient(credentials)
