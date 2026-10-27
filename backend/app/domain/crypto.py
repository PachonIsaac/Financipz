"""Pure rules for the crypto holdings: merging wallets, valuing in USD, choosing which pairs to read."""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal

from app.domain.fx import round_money

# Valued at one dollar each.
STABLECOINS = frozenset({"USDT", "USDC", "FDUSD", "BUSD", "TUSD", "USDP", "DAI"})
# Assets in which the pairs to look for trades are quoted, most common first.
QUOTE_ASSETS = ("USDT", "USDC", "FDUSD", "BTC", "ETH", "BNB")
USD_QUOTE = "USDT"
BRIDGE_ASSET = "BTC"


def merge_quantities(*wallets: Iterable[tuple[str, Decimal]]) -> dict[str, Decimal]:
    """Total quantity per asset across wallets. Assets that end up at zero are dropped."""
    totals: dict[str, Decimal] = {}
    for wallet in wallets:
        for asset, quantity in wallet:
            totals[asset] = totals.get(asset, Decimal(0)) + quantity
    return {asset: quantity for asset, quantity in sorted(totals.items()) if quantity > 0}


def value_in_usd(asset: str, quantity: Decimal, prices: Mapping[str, Decimal]) -> Decimal | None:
    """Value in dollars with cents, or None when there is no way to price the asset.

    Stablecoins are worth one dollar. Others use the price of `<ASSET>USDT`, or else the price of
    `<ASSET>BTC` times the price of `BTCUSDT`.
    """
    if asset in STABLECOINS:
        return round_money(quantity)

    direct = prices.get(f"{asset}{USD_QUOTE}")
    if direct is not None and direct > 0:
        return round_money(quantity * direct)

    in_bridge = prices.get(f"{asset}{BRIDGE_ASSET}")
    bridge = prices.get(f"{BRIDGE_ASSET}{USD_QUOTE}")
    if in_bridge is not None and in_bridge > 0 and bridge is not None and bridge > 0:
        return round_money(quantity * in_bridge * bridge)
    return None


@dataclass(frozen=True)
class SnapshotTotals:
    total_usd: Decimal
    priced: int
    unpriced: int


def summarize_values(values: Iterable[Decimal | None]) -> SnapshotTotals:
    """Sum of the priced values, and how many assets could and could not be priced."""
    total = Decimal(0)
    priced = unpriced = 0
    for value in values:
        if value is None:
            unpriced += 1
        else:
            total += value
            priced += 1
    return SnapshotTotals(total_usd=total, priced=priced, unpriced=unpriced)


def select_symbols(
    held_assets: Iterable[str],
    traded_symbols: Iterable[str],
    listed_symbols: Iterable[str],
    quotes: tuple[str, ...] = QUOTE_ASSETS,
) -> list[str]:
    """Pairs whose trades should be read: those traded before, then the held assets against common quotes.

    A pair that was traded before is kept even if the exchange no longer lists it. A guessed pair is
    only kept if the exchange lists it.
    """
    listed = set(listed_symbols)
    ordered = sorted(set(traded_symbols))
    seen = set(ordered)
    for asset in sorted(set(held_assets)):
        for quote in quotes:
            symbol = f"{asset}{quote}"
            if asset != quote and symbol in listed and symbol not in seen:
                seen.add(symbol)
                ordered.append(symbol)
    return ordered
