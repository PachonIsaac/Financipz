"""Clients for the official USD to COP exchange rate (TRM).

The open data portal is the source of truth: it publishes each rate with the period in which it is in
force. The current-rate service only says what the rate is now, so it is a fallback.
"""

import json
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal

import httpx

from app.domain.entities import LOCAL_TIMEZONE

CURRENT_URL = "https://co.dolarapi.com/v1/trm"
HISTORY_URL = "https://www.datos.gov.co/resource/32sa-8pi3.json"
TIMEOUT_SECONDS = 10.0
HISTORY_PAGE_SIZE = 1000
MAX_HISTORY_PAGES = 20
# A rate outside this range (pesos per dollar) is a broken answer, not a market move.
MIN_RATE = Decimal(1000)
MAX_RATE = Decimal(10000)
MAX_PERIOD_DAYS = 31
RATE_PLACES = Decimal("0.0001")


class TrmError(Exception):
    """The rate source is unreachable or answered something that cannot be used."""


@dataclass(frozen=True)
class PublishedRate:
    day: date
    value: Decimal


def build_client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT_SECONDS, follow_redirects=False)


def parse_value(raw: object) -> Decimal:
    """A plausible rate with four decimals. Anything else is an error."""
    try:
        value = Decimal(str(raw))
        if not value.is_finite() or not MIN_RATE <= value <= MAX_RATE:
            raise TrmError("The rate is outside the plausible range")
        return value.quantize(RATE_PLACES)
    except ArithmeticError:
        raise TrmError("The rate is not a valid number") from None


def _get_json(client: httpx.Client, url: str, params: dict | None = None) -> object:
    try:
        response = client.get(url, params=params)
        response.raise_for_status()
        # Floats are read as decimals so the rate keeps the digits the source published.
        return json.loads(response.text, parse_float=Decimal)
    except (httpx.HTTPError, ValueError) as error:
        raise TrmError(f"Could not read {url}: {error.__class__.__name__}") from error


def fetch_current() -> PublishedRate:
    """The rate the fallback service reports now, dated by the Colombian day of its last refresh."""
    with build_client() as client:
        body = _get_json(client, CURRENT_URL)

    if not isinstance(body, dict) or body.get("unidad") != "COP":
        raise TrmError("Unexpected answer from the rate source")
    try:
        updated = datetime.fromisoformat(str(body["fechaActualizacion"]).replace("Z", "+00:00"))
        value = parse_value(body["valor"])
    except (KeyError, ValueError):
        raise TrmError("Unexpected answer from the rate source") from None
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=LOCAL_TIMEZONE)
    return PublishedRate(day=updated.astimezone(LOCAL_TIMEZONE).date(), value=value)


def _row_to_days(item: object, first: date, last: date) -> list[PublishedRate]:
    """The days from `first` to `last` that one portal record covers, each with the record's rate."""
    try:
        if item["unidad"] != "COP":  # type: ignore[index]
            raise TrmError("The rate is not in pesos")
        valid_from = date.fromisoformat(str(item["vigenciadesde"])[:10])  # type: ignore[index]
        valid_to = date.fromisoformat(str(item["vigenciahasta"])[:10])  # type: ignore[index]
        value = parse_value(item["valor"])  # type: ignore[index]
    except (KeyError, TypeError, ValueError):
        raise TrmError("Unexpected row from the open data portal") from None
    if valid_to < valid_from or valid_to - valid_from > timedelta(days=MAX_PERIOD_DAYS):
        raise TrmError("Unexpected validity period from the open data portal")

    day = max(valid_from, first)
    days = []
    while day <= min(valid_to, last):
        days.append(PublishedRate(day=day, value=value))
        day += timedelta(days=1)
    return days


def fetch_history(first: date, last: date) -> list[PublishedRate]:
    """One rate per day from `first` to `last`, taken from the record whose validity covers the day."""
    by_day: dict[date, PublishedRate] = {}
    with build_client() as client:
        for page in range(MAX_HISTORY_PAGES):
            body = _get_json(
                client,
                HISTORY_URL,
                {
                    "$where": (
                        f"vigenciahasta >= '{first.isoformat()}T00:00:00.000' "
                        f"AND vigenciadesde <= '{last.isoformat()}T00:00:00.000'"
                    ),
                    "$order": "vigenciadesde",
                    "$limit": HISTORY_PAGE_SIZE,
                    "$offset": page * HISTORY_PAGE_SIZE,
                },
            )
            if not isinstance(body, list):
                raise TrmError("Unexpected answer from the open data portal")
            for item in body:
                for rate in _row_to_days(item, first, last):
                    by_day[rate.day] = rate
            if len(body) < HISTORY_PAGE_SIZE:
                return sorted(by_day.values(), key=lambda rate: rate.day)
    raise TrmError("The open data portal answered more pages than expected")
