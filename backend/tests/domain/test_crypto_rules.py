from decimal import Decimal

from app.domain.crypto import drop_earn_tokens, merge_quantities, select_symbols, summarize_values, value_in_usd

D = Decimal
PRICES = {
    "BTCUSDT": D("80000"),
    "ETHUSDT": D("2500.5"),
    "XYZBTC": D("0.00001"),
    "NOUSDT": D("0"),
}


def test_merge_adds_the_same_asset_across_wallets_and_drops_zeros():
    spot = [("BTC", D("0.5")), ("ETH", D("0")), ("USDT", D("10"))]
    funding = [("BTC", D("0.25")), ("BNB", D("2"))]

    assert merge_quantities(spot, funding) == {"BNB": D("2"), "BTC": D("0.75"), "USDT": D("10")}


def test_stablecoins_are_worth_one_dollar():
    assert value_in_usd("USDT", D("12.345"), {}) == D("12.35")
    assert value_in_usd("USDC", D("3"), PRICES) == D("3.00")


def test_direct_usdt_price():
    assert value_in_usd("ETH", D("2"), PRICES) == D("5001.00")


def test_falls_back_through_btc():
    # 100 * 0.00001 BTC * 80000
    assert value_in_usd("XYZ", D("100"), PRICES) == D("80.00")


def test_the_btc_fallback_needs_the_btc_price():
    assert value_in_usd("XYZ", D("100"), {"XYZBTC": D("0.00001")}) is None


def test_unknown_or_zero_priced_assets_have_no_value():
    assert value_in_usd("ABC", D("1"), PRICES) is None
    assert value_in_usd("NO", D("1"), PRICES) is None


def test_summary_counts_priced_and_unpriced():
    totals = summarize_values([D("10.50"), None, D("4.25"), None, None])

    assert totals.total_usd == D("14.75")
    assert (totals.priced, totals.unpriced) == (2, 3)


def test_summary_of_nothing_is_zero():
    totals = summarize_values([])

    assert totals.total_usd == D("0")
    assert (totals.priced, totals.unpriced) == (0, 0)


def test_symbols_combine_previous_trades_and_held_assets_against_listed_pairs():
    listed = {"BTCUSDT", "BTCUSDC", "ETHUSDT", "ETHBTC", "BNBUSDT", "DOGEUSDT"}

    symbols = select_symbols(["BTC", "ETH", "USDT"], ["DOGEUSDT", "OLDUSDT"], listed)

    # Previous trades first (even if no longer listed), then guessed pairs by asset and quote priority.
    assert symbols == ["DOGEUSDT", "OLDUSDT", "BTCUSDT", "BTCUSDC", "ETHUSDT", "ETHBTC"]


def test_a_pair_is_not_repeated_and_unlisted_guesses_are_dropped():
    symbols = select_symbols(["BTC", "BTC"], ["BTCUSDT"], {"BTCUSDT"})

    assert symbols == ["BTCUSDT"]


def test_an_asset_is_not_paired_with_itself():
    assert select_symbols(["USDT"], [], {"USDTUSDT", "USDTBTC"}) == ["USDTBTC"]


LD_PRICES = {"BTCUSDT": D("80000"), "LDOUSDT": D("2"), "BNBUSDT": D("600")}


def test_earn_wrappers_of_priced_assets_are_dropped():
    entries = [("LDBTC", D("1")), ("BTC", D("2")), ("LDUSDT", D("5")), ("LDBNB", D("1"))]

    kept = [asset for asset, _ in drop_earn_tokens(entries, LD_PRICES)]
    # LDBTC and LDUSDT wrap priced assets. LDBNB also wraps one (BNB is priced).
    assert kept == ["BTC"]


def test_a_token_that_really_starts_with_ld_is_kept():
    # LDO has its own price and "O" is not a priced asset.
    assert drop_earn_tokens([("LDO", D("3"))], LD_PRICES) == [("LDO", D("3"))]


def test_an_ld_entry_with_its_own_price_is_kept_even_if_the_base_is_priced():
    prices = {"BTCUSDT": D("80000"), "LDBTCUSDT": D("1")}

    assert drop_earn_tokens([("LDBTC", D("1"))], prices) == [("LDBTC", D("1"))]


def test_an_ld_entry_whose_base_cannot_be_priced_is_kept():
    assert drop_earn_tokens([("LDXYZ", D("1"))], LD_PRICES) == [("LDXYZ", D("1"))]


def test_a_bare_ld_is_not_a_wrapper():
    assert drop_earn_tokens([("LD", D("1"))], LD_PRICES) == [("LD", D("1"))]
