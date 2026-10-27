from decimal import Decimal
from urllib.parse import parse_qsl

import httpx
import pytest

from app.integrations import binance
from tests.api.binance_fake import FakeExchange
from app.integrations.binance import BinanceClient, BinanceError, Credentials, WalletRead, sign

D = Decimal
KEY = "invented-key-0001"
SECRET = "invented-secret-0001"


def make_client(handler, requests: list | None = None) -> BinanceClient:
    def recording(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(request)
        return handler(request)

    http = httpx.Client(base_url=binance.BASE_URL, transport=httpx.MockTransport(recording), follow_redirects=False)
    return BinanceClient(Credentials(KEY, SECRET), http=http, clock=lambda: 1700000000.5, sleep=lambda seconds: None)


def reply(body, status: int = 200, headers: dict | None = None):
    return lambda request: httpx.Response(status, json=body, headers=headers)


def test_signature_matches_a_published_hmac_vector():
    # Example from the exchange's public documentation, with the secret used there.
    secret = "NhqPtmdSJYdKjVHjA7PZj4Mge3R5YNiP1e3UZjInClVN65XAbvqqM6A7H5fATj0j"
    query = (
        "symbol=LTCBTC&side=BUY&type=LIMIT&timeInForce=GTC&quantity=1&price=0.1"
        "&recvWindow=5000&timestamp=1499827319559"
    )

    assert sign(secret, query) == "c8db56825ae71d6d79447849e617115f4a920fa2acdcab2b053c4b2838bd6b71"


def test_signature_matches_the_standard_test_vector():
    assert sign("Jefe", "what do ya want for nothing?") == (
        "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843"
    )


def test_a_signed_request_carries_header_window_timestamp_and_a_valid_signature_last():
    seen: list[httpx.Request] = []
    client = make_client(reply({"enableReading": True}), seen)

    client.api_restrictions()

    request = seen[0]
    assert request.headers["X-MBX-APIKEY"] == KEY
    assert request.url.path == "/sapi/v1/account/apiRestrictions"
    raw = request.url.query.decode()
    signed_part, _, signature = raw.rpartition("&signature=")
    params = dict(parse_qsl(signed_part))
    assert params == {"recvWindow": "5000", "timestamp": "1700000000500"}
    assert signature == sign(SECRET, signed_part)
    assert SECRET not in str(request.url)


def test_public_requests_are_not_signed_and_send_no_key():
    seen: list[httpx.Request] = []
    client = make_client(reply([{"symbol": "BTCUSDT", "price": "80000.10"}]), seen)

    assert client.prices() == {"BTCUSDT": D("80000.10")}

    assert "X-MBX-APIKEY" not in seen[0].headers
    assert b"signature" not in seen[0].url.query


def test_the_client_never_writes_to_the_exchange():
    seen: list[httpx.Request] = []
    handlers = {
        "/api/v3/account": {"balances": []},
        "/sapi/v1/asset/get-funding-asset": [],
        "/sapi/v1/simple-earn/flexible/position": {"rows": [], "total": 0},
        "/sapi/v1/simple-earn/locked/position": {"rows": [], "total": 0},
        "/api/v3/myTrades": [],
        "/api/v3/ticker/price": [],
        "/sapi/v1/account/apiRestrictions": {},
    }
    client = make_client(lambda request: httpx.Response(200, json=handlers[request.url.path]), seen)

    client.api_restrictions()
    client.spot_balances()
    client.funding_balances()
    client.earn_flexible_balances()
    client.earn_locked_balances()
    client.trades("BTCUSDT", 0)
    client.prices()

    # The exchange only offers the funding wallet through a POST (it reads, it does not change anything).
    assert {(r.method, r.url.path) for r in seen if r.method != "GET"} == {("POST", "/sapi/v1/asset/get-funding-asset")}
    assert not any("order" in r.url.path or "withdraw" in r.url.path or "transfer" in r.url.path for r in seen)


@pytest.mark.parametrize(
    ("status", "body", "kind"),
    [
        (401, {"code": -2015, "msg": "Invalid API-key, IP, or permissions for action."}, binance.ACCESS_DENIED),
        (400, {"code": -2015, "msg": "x"}, binance.ACCESS_DENIED),
        (400, {"code": -2014, "msg": "API-key format invalid."}, binance.INVALID_CREDENTIALS),
        (400, {"code": -1022, "msg": "Signature for this request is not valid."}, binance.INVALID_CREDENTIALS),
        (400, {"code": -2008, "msg": "Invalid Api-Key ID."}, binance.INVALID_CREDENTIALS),
        (400, {"code": -1021, "msg": "Timestamp for this request is outside of the recvWindow."}, binance.CLOCK_SKEW),
        (429, {"code": -1003, "msg": "Too many requests."}, binance.RATE_LIMITED),
        (418, {"code": -1003, "msg": "banned"}, binance.RATE_LIMITED),
        (200, {"code": -1003, "msg": "weird"}, binance.RATE_LIMITED),
        (503, {"msg": "Service Unavailable"}, binance.UNAVAILABLE),
        (500, {"code": -1000, "msg": "unknown"}, binance.UNAVAILABLE),
        (400, {"code": -1100, "msg": "Illegal characters"}, binance.REJECTED),
        (403, {"msg": "WAF"}, binance.ACCESS_DENIED),
        (404, {"msg": "nope"}, binance.REJECTED),
    ],
)
def test_binance_errors_map_to_a_kind_without_leaking_credentials(status, body, kind):
    client = make_client(reply(body, status))

    with pytest.raises(BinanceError) as caught:
        client.api_restrictions()

    assert caught.value.kind == kind
    text = f"{caught.value!r} {caught.value}"
    assert KEY not in text and SECRET not in text


def test_the_rate_limit_answer_keeps_the_retry_hint():
    client = make_client(reply({"code": -1003}, 429, {"Retry-After": "30"}))

    with pytest.raises(BinanceError) as caught:
        client.api_restrictions()

    assert caught.value.retry_after == 30


def test_a_network_failure_is_unavailable_and_hides_the_url():
    def boom(request):
        raise httpx.ConnectError("connection refused for " + str(request.url))

    client = make_client(boom)

    with pytest.raises(BinanceError) as caught:
        client.api_restrictions()

    assert caught.value.kind == binance.UNAVAILABLE
    assert caught.value.__cause__ is None
    assert "signature" not in f"{caught.value!r}"


def test_a_timeout_is_unavailable():
    def slow(request):
        raise httpx.ReadTimeout("slow")

    with pytest.raises(BinanceError) as caught:
        make_client(slow).api_restrictions()

    assert caught.value.kind == binance.UNAVAILABLE


@pytest.mark.parametrize("body", ["not json", "<html>", ""])
def test_a_body_that_is_not_json_is_a_bad_response(body):
    client = make_client(lambda request: httpx.Response(200, text=body))

    with pytest.raises(BinanceError) as caught:
        client.api_restrictions()

    assert caught.value.kind == binance.BAD_RESPONSE


def test_a_redirect_is_not_followed():
    client = make_client(lambda request: httpx.Response(302, headers={"Location": "https://elsewhere.test/"}, text=""))

    with pytest.raises(BinanceError) as caught:
        client.api_restrictions()

    assert caught.value.kind == binance.BAD_RESPONSE


def test_the_client_has_timeouts_and_does_not_follow_redirects():
    http = binance.build_http_client()

    assert http.follow_redirects is False
    assert http.timeout.read == binance.TIMEOUT_SECONDS
    assert str(http.base_url).rstrip("/") == binance.BASE_URL
    http.close()


def test_the_restrictions_must_be_an_object():
    with pytest.raises(BinanceError) as caught:
        make_client(reply([1, 2])).api_restrictions()

    assert caught.value.kind == binance.BAD_RESPONSE


def test_spot_balances_add_free_and_locked():
    body = {"balances": [{"asset": "BTC", "free": "0.5", "locked": "0.25"}, {"asset": "USDT", "free": "10", "locked": "0"}]}

    assert make_client(reply(body)).spot_balances() == WalletRead([("BTC", D("0.75")), ("USDT", D("10"))])


@pytest.mark.parametrize(
    "body",
    [
        {"balances": "x"},
        {"nothing": []},
        [],
        {"balances": [{"asset": "BTC", "free": "abc", "locked": "0"}]},
        {"balances": [{"asset": "BTC", "free": "-1", "locked": "0"}]},
        {"balances": [{"asset": "BTC", "free": "NaN", "locked": "0"}]},
        {"balances": [{"asset": "BTC", "free": "1"}]},
        {"balances": ["x"]},
    ],
)
def test_garbled_spot_balances_are_a_bad_response(body):
    with pytest.raises(BinanceError) as caught:
        make_client(reply(body)).spot_balances()

    assert caught.value.kind == binance.BAD_RESPONSE


def test_funding_balances_include_frozen_amounts():
    body = [{"asset": "BNB", "free": "1", "locked": "0.5", "freeze": "0.25", "withdrawing": "0", "btcValuation": "0"}]

    assert make_client(reply(body)).funding_balances() == WalletRead([("BNB", D("1.75"))])


def test_earn_positions_are_read_page_by_page():
    pages = {
        "1": {"rows": [{"asset": "USDT", "totalAmount": "5"}, {"asset": "BTC", "totalAmount": "0.1"}], "total": 3},
        "2": {"rows": [{"asset": "ETH", "totalAmount": "2"}], "total": 3},
    }
    seen: list[httpx.Request] = []
    client = make_client(lambda request: httpx.Response(200, json=pages[request.url.params["current"]]), seen)

    positions = client.earn_flexible_balances()

    assert positions == WalletRead([("USDT", D("5")), ("BTC", D("0.1")), ("ETH", D("2"))])
    assert len(seen) == 2


def test_locked_earn_positions_use_the_amount_field():
    body = {"rows": [{"asset": "BNB", "amount": "3"}], "total": 1}

    assert make_client(reply(body)).earn_locked_balances() == WalletRead([("BNB", D("3"))])


def test_earn_pagination_that_never_ends_is_a_bad_response():
    body = {"rows": [{"asset": "BNB", "amount": "3"}], "total": 10**6}

    with pytest.raises(BinanceError) as caught:
        make_client(reply(body)).earn_locked_balances()

    assert caught.value.kind == binance.BAD_RESPONSE


def test_prices_skip_entries_that_cannot_be_read():
    body = [
        {"symbol": "BTCUSDT", "price": "80000"},
        {"symbol": "ETHUSDT", "price": "abc"},
        {"symbol": "dogeusdt", "price": "1"},
        {"symbol": "ZEROUSDT", "price": "0"},
        {"price": "1"},
    ]

    assert make_client(reply(body)).prices() == {"BTCUSDT": D("80000")}


def test_trades_are_parsed():
    body = [
        {"symbol": "BTCUSDT", "id": 28457, "orderId": 100, "price": "4.00000100", "qty": "12.00000000",
         "quoteQty": "48.000012", "commission": "10.10000000", "commissionAsset": "BNB",
         "time": 1700000000123, "isBuyer": True, "isMaker": False, "isBestMatch": True},
    ]
    seen: list[httpx.Request] = []

    trades = make_client(reply(body), seen).trades("BTCUSDT", 28000)

    params = dict(seen[0].url.params)
    assert params["symbol"] == "BTCUSDT" and params["fromId"] == "28000" and params["limit"] == "1000"
    trade = trades[0]
    assert (trade.trade_id, trade.side, trade.quantity, trade.price) == (28457, "buy", D("12"), D("4.000001"))
    assert (trade.fee, trade.fee_asset) == (D("10.1"), "BNB")
    assert trade.executed_at.isoformat() == "2023-11-14T22:13:20.123000+00:00"


@pytest.mark.parametrize(
    "row",
    [
        {"id": "1", "price": "1", "qty": "1", "time": 1, "isBuyer": True},
        {"id": 1, "price": "0", "qty": "1", "time": 1, "isBuyer": True},
        {"id": 1, "price": "1", "qty": "x", "time": 1, "isBuyer": True},
        {"id": 1, "price": "1", "qty": "1", "time": "now", "isBuyer": True},
        {"id": 1, "price": "1", "qty": "1", "time": 10**30, "isBuyer": True},
        {"id": 1, "price": "1", "qty": "1", "time": 1, "isBuyer": "yes"},
        {"id": True, "price": "1", "qty": "1", "time": 1, "isBuyer": True},
    ],
)
def test_garbled_trades_are_a_bad_response(row):
    with pytest.raises(BinanceError) as caught:
        make_client(reply([row])).trades("BTCUSDT", 0)

    assert caught.value.kind == binance.BAD_RESPONSE


def test_requests_are_spaced_and_counted():
    pauses: list[float] = []
    http = httpx.Client(base_url=binance.BASE_URL, transport=httpx.MockTransport(reply([])))
    client = BinanceClient(Credentials(KEY, SECRET), http=http, sleep=pauses.append)

    client.prices()
    client.prices()
    client.prices()

    assert client.requests_made == 3
    assert pauses == [binance.MIN_INTERVAL_SECONDS] * 2


def test_credentials_and_client_hide_secrets_in_their_representation():
    client = make_client(reply({}))

    assert KEY not in repr(Credentials(KEY, SECRET)) and SECRET not in repr(Credentials(KEY, SECRET))
    assert KEY not in repr(client) and SECRET not in repr(client)


@pytest.mark.parametrize("name", ["btc", "BTC\n", "ÑANDÚ", "BTC/USDT", "", "A" * 21, None, 7, "BT C"])
def test_rows_with_an_unusable_asset_name_are_skipped_and_counted(name):
    body = {"balances": [{"asset": name, "free": "1", "locked": "0"}, {"asset": "BTC", "free": "2", "locked": "0"}]}

    wallet = make_client(reply(body)).spot_balances()

    assert wallet == WalletRead([("BTC", D("2"))], skipped=1)


def test_unusable_asset_names_are_skipped_in_every_wallet():
    bad = {"asset": "ñu", "free": "1", "locked": "0", "freeze": "0", "totalAmount": "1", "amount": "1"}
    earn = {"rows": [bad, {"asset": "BNB", "totalAmount": "1", "amount": "1"}], "total": 2}

    assert make_client(reply([bad])).funding_balances() == WalletRead([], skipped=1)
    assert make_client(reply(earn)).earn_flexible_balances() == WalletRead([("BNB", D("1"))], skipped=1)
    assert make_client(reply(earn)).earn_locked_balances() == WalletRead([("BNB", D("1"))], skipped=1)


def test_a_symbol_with_a_trailing_newline_is_not_a_price():
    body = [{"symbol": "BTCUSDT\n", "price": "1"}, {"symbol": "ÑUSDT", "price": "1"}]

    assert make_client(reply(body)).prices() == {}


def test_a_fee_asset_that_is_not_usable_is_dropped_not_stored():
    row = {"id": 1, "price": "1", "qty": "1", "time": 1, "isBuyer": True, "commission": "1", "commissionAsset": "ñu"}

    assert make_client(reply([row])).trades("BTCUSDT", 0)[0].fee_asset is None


@pytest.mark.parametrize("status", [300, 301, 302, 304, 307])
def test_a_redirect_with_a_json_body_is_never_data(status):
    client = make_client(lambda request: httpx.Response(status, json={"balances": []}, headers={"Location": "https://elsewhere.test/"}))

    with pytest.raises(BinanceError) as caught:
        client.spot_balances()

    assert caught.value.kind == binance.BAD_RESPONSE


@pytest.mark.parametrize("status", [199, 1])
def test_other_non_success_statuses_are_not_data(status):
    # Statuses outside 2xx that httpx can represent.
    client = make_client(lambda request: httpx.Response(status, json={"balances": []}))

    with pytest.raises(BinanceError):
        client.spot_balances()


def test_a_key_that_cannot_be_encoded_becomes_an_error_that_does_not_quote_it():
    secret_text = "clave-ñ-\u00e9"
    http = httpx.Client(base_url=binance.BASE_URL, transport=httpx.MockTransport(reply({})))
    client = BinanceClient(Credentials(secret_text, "invented-secret-0001"), http=http, sleep=lambda s: None)

    with pytest.raises(BinanceError) as caught:
        client.api_restrictions()

    assert caught.value.kind == binance.INVALID_CREDENTIALS
    assert caught.value.__cause__ is None and caught.value.__suppress_context__
    assert secret_text not in f"{caught.value!r} {caught.value}"


def test_a_secret_that_cannot_be_encoded_becomes_an_error():
    http = httpx.Client(base_url=binance.BASE_URL, transport=httpx.MockTransport(reply({})))
    client = BinanceClient(Credentials("invented-key-0001", "mal-\ud800-secreto"), http=http, sleep=lambda s: None)

    with pytest.raises(BinanceError) as caught:
        client.api_restrictions()

    assert caught.value.kind == binance.INVALID_CREDENTIALS


def test_the_fake_exchange_rejects_anything_outside_the_read_only_list():
    fake = FakeExchange()
    client = fake.client(Credentials(KEY, SECRET))

    with pytest.raises(AssertionError):
        client._request("/api/v3/order", {"symbol": "BTCUSDT"}, signed=True, method="POST")
    with pytest.raises(AssertionError):
        client._request("/sapi/v1/capital/withdraw/apply", signed=True)


def test_the_fake_exchange_checks_the_signature_and_the_key():
    fake = FakeExchange()
    good = fake.client(Credentials(KEY, SECRET))
    assert good.api_restrictions() is not None

    # A request signed with another secret does not pass what the exchange would check.
    other_http = httpx.Client(base_url=binance.BASE_URL, transport=httpx.MockTransport(fake.handle))
    other = BinanceClient(Credentials(KEY, "other-secret-0002"), http=other_http, sleep=lambda s: None)
    with pytest.raises(AssertionError):
        other.api_restrictions()
