"""Clients for the official USD to COP exchange rate (TRM)."""

import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

import httpx

from app.domain.entities import LOCAL_TIMEZONE

CURRENT_URL = "https://co.dolarapi.com/v1/trm"
HISTORY_URL = "https://www.datos.gov.co/resource/32sa-8pi3.json"
TIMEOUT_SECONDS = 10.0
HISTORY_PAGE_SIZE = 5000
RATE_PLACES = Decimal("0.0001")


class TrmError(Exception):
    """The rate source is unreachable or answered something that cannot be used."""


@dataclass(frozen=True)
class PublishedRate:
    day: date
    value: Decimal


def build_client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT_SECONDS, follow_redirects=True)


def _parse_value(raw: object) -> Decimal:
    try:
        value = Decimal(str(raw))
    except InvalidOperation:
        raise TrmError("The rate is not a number") from None
    if not value.is_finite() or value <= 0:
        raise TrmError("The rate must be positive")
    return value.quantize(RATE_PLACES)


def _get_json(client: httpx.Client, url: str, params: dict | None = None) -> object:
    try:
        response = client.get(url, params=params)
        response.raise_for_status()
        # Floats are read as decimals so the rate keeps the digits the source published.
        return json.loads(response.text, parse_float=Decimal)
    except (httpx.HTTPError, ValueError) as error:
        raise TrmError(f"Could not read {url}: {error.__class__.__name__}") from error


def fetch_current() -> PublishedRate:
    """The rate in force now, dated by the Colombian calendar day of its last update."""
    with build_client() as client:
        body = _get_json(client, CURRENT_URL)

    if not isinstance(body, dict) or body.get("unidad") != "COP":
        raise TrmError("Unexpected answer from the rate source")
    try:
        updated = datetime.fromisoformat(str(body["fechaActualizacion"]).replace("Z", "+00:00"))
        value = _parse_value(body["valor"])
    except (KeyError, ValueError):
        raise TrmError("Unexpected answer from the rate source") from None
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=LOCAL_TIMEZONE)
    return PublishedRate(day=updated.astimezone(LOCAL_TIMEZONE).date(), value=value)


def fetch_history(start: date) -> list[PublishedRate]:
    """Rates published since `start`, one per validity period, dated by the first day it applies."""
    rates: list[PublishedRate] = []
    offset = 0
    with build_client() as client:
        while True:
            body = _get_json(
                client,
                HISTORY_URL,
                {
                    "$where": f"vigenciadesde >= '{start.isoformat()}T00:00:00.000'",
                    "$order": "vigenciadesde",
                    "$limit": HISTORY_PAGE_SIZE,
                    "$offset": offset,
                },
            )
            if not isinstance(body, list):
                raise TrmError("Unexpected answer from the open data portal")
            for item in body:
                try:
                    day = date.fromisoformat(str(item["vigenciadesde"])[:10])
                    rates.append(PublishedRate(day=day, value=_parse_value(item["valor"])))
                except (KeyError, TypeError, ValueError, TrmError):
                    raise TrmError("Unexpected row from the open data portal") from None
            if len(body) < HISTORY_PAGE_SIZE:
                return rates
            offset += HISTORY_PAGE_SIZE
