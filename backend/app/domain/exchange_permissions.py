"""Decides whether an exchange API key is safe to use: it may read and nothing else."""

from collections.abc import Mapping
from dataclasses import dataclass

READ_FLAG = "enableReading"
# Capabilities that must be explicitly off. A missing or non-boolean value is not "off".
DANGEROUS_FLAGS = (
    "enableWithdrawals",
    "enableInternalTransfer",
    "permitsUniversalTransfer",
    "enableMargin",
    "enableFutures",
    "enableSpotAndMarginTrading",
    "enableVanillaOptions",
    "enablePortfolioMarginTrading",
)
# Newer flags that older answers may omit. If present and true they are dangerous.
OPTIONAL_DANGEROUS_FLAGS = ("enableFixApiTrade",)
# Flags that are true on a safe key or that do not grant anything.
HARMLESS_FLAGS = ("ipRestrict", "enableFixReadOnly")

KNOWN_FLAGS = frozenset((READ_FLAG, *DANGEROUS_FLAGS, *OPTIONAL_DANGEROUS_FLAGS, *HARMLESS_FLAGS))


@dataclass(frozen=True)
class KeyVerdict:
    # Names of the flags that make the key unacceptable, in a stable order.
    problems: tuple[str, ...]
    # Whether the key only works from the IPs the owner listed.
    ip_restricted: bool

    @property
    def accepted(self) -> bool:
        return not self.problems


def evaluate_key_restrictions(restrictions: Mapping[str, object]) -> KeyVerdict:
    """Accept the key only if reading is on and every known or unknown capability is off.

    Fail closed: a dangerous flag that is missing or not a boolean counts as a problem, and so does any
    flag this code does not know that is true (the exchange may add new capabilities over time).
    """
    problems: list[str] = []

    if restrictions.get(READ_FLAG) is not True:
        problems.append(READ_FLAG)
    for flag in DANGEROUS_FLAGS:
        if restrictions.get(flag) is not False:
            problems.append(flag)
    for flag in OPTIONAL_DANGEROUS_FLAGS:
        if flag in restrictions and restrictions[flag] is not False:
            problems.append(flag)
    for flag in sorted(restrictions):
        if flag not in KNOWN_FLAGS and restrictions[flag] is True:
            problems.append(flag)

    return KeyVerdict(problems=tuple(problems), ip_restricted=restrictions.get("ipRestrict") is True)
