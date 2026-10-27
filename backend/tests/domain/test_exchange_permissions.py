import pytest

from app.domain.exchange_permissions import DANGEROUS_FLAGS, evaluate_key_restrictions


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


def test_a_read_only_key_restricted_by_ip_is_accepted():
    verdict = evaluate_key_restrictions(safe_restrictions())

    assert verdict.accepted
    assert verdict.problems == ()
    assert verdict.ip_restricted


def test_a_read_only_key_without_ip_restriction_is_accepted_but_flagged():
    verdict = evaluate_key_restrictions(safe_restrictions(ipRestrict=False))

    assert verdict.accepted
    assert not verdict.ip_restricted


@pytest.mark.parametrize("flag", DANGEROUS_FLAGS + ("enableFixApiTrade",))
def test_every_dangerous_flag_refuses_the_key(flag):
    verdict = evaluate_key_restrictions(safe_restrictions(**{flag: True}))

    assert not verdict.accepted
    assert verdict.problems == (flag,)


@pytest.mark.parametrize("flag", DANGEROUS_FLAGS)
def test_a_missing_dangerous_flag_fails_closed(flag):
    restrictions = safe_restrictions()
    del restrictions[flag]

    verdict = evaluate_key_restrictions(restrictions)

    assert verdict.problems == (flag,)


@pytest.mark.parametrize("value", [None, "false", 0, "true"])
def test_a_non_boolean_dangerous_flag_fails_closed(value):
    verdict = evaluate_key_restrictions(safe_restrictions(enableWithdrawals=value))

    assert verdict.problems == ("enableWithdrawals",)


@pytest.mark.parametrize("value", [False, None, "true", 1])
def test_reading_must_be_enabled(value):
    verdict = evaluate_key_restrictions(safe_restrictions(enableReading=value))

    assert verdict.problems == ("enableReading",)


def test_an_unknown_flag_that_is_true_refuses_the_key():
    verdict = evaluate_key_restrictions(safe_restrictions(enableSomethingNew=True))

    assert verdict.problems == ("enableSomethingNew",)


def test_unknown_values_that_are_not_capabilities_are_ignored():
    verdict = evaluate_key_restrictions(
        safe_restrictions(enableSomethingNew=False, tradingAuthorityExpirationTime=1800000000000, note="x", extra=None)
    )

    assert verdict.accepted


@pytest.mark.parametrize("value", [True, 1, "true", "false", "", None, {}, [], {"a": 1}, [False], 0])
@pytest.mark.parametrize("name", ["enableSomethingNew", "permitsOtherThing", "ENABLEUPPER", "PermitsMixed", "enable"])
def test_an_unknown_capability_must_be_exactly_false(name, value):
    verdict = evaluate_key_restrictions(safe_restrictions(**{name: value}))

    assert verdict.problems == (name,)


@pytest.mark.parametrize("name", ["enableSomethingNew", "permitsOtherThing", "ENABLEUPPER"])
def test_an_unknown_capability_that_is_false_is_fine(name):
    assert evaluate_key_restrictions(safe_restrictions(**{name: False})).accepted


def test_the_optional_flag_may_be_absent():
    restrictions = safe_restrictions()
    del restrictions["enableFixApiTrade"]

    assert evaluate_key_restrictions(restrictions).accepted


def test_several_problems_are_all_reported_in_a_stable_order():
    verdict = evaluate_key_restrictions(safe_restrictions(enableWithdrawals=True, enableMargin=True, zzz=True))

    assert verdict.problems == ("enableWithdrawals", "enableMargin", "zzz")
