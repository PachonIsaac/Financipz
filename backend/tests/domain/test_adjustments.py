import pytest

from app.domain.adjustments import plan_adjustment
from app.domain.entities import TransactionType
from app.domain.errors import DomainError
from tests.domain.helpers import D


def test_observed_above_computed_creates_an_adjustment_in():
    adjustment = plan_adjustment(D("1000"), D("1250"), "Cash count")

    assert adjustment.type is TransactionType.ADJUSTMENT_IN
    assert adjustment.amount == D("250")


def test_observed_below_computed_creates_an_adjustment_out_with_positive_amount():
    adjustment = plan_adjustment(D("1000"), D("700"), "Cash count")

    assert adjustment.type is TransactionType.ADJUSTMENT_OUT
    assert adjustment.amount == D("300")


def test_matching_balances_need_no_adjustment():
    assert plan_adjustment(D("1000"), D("1000.00"), "") is None


def test_works_with_negative_balances():
    adjustment = plan_adjustment(D("-200"), D("-50"), "Card statement")

    assert adjustment.type is TransactionType.ADJUSTMENT_IN
    assert adjustment.amount == D("150")


def test_difference_is_rounded_to_cents():
    adjustment = plan_adjustment(D("10.004"), D("10.50"), "Rounding")

    assert adjustment.amount == D("0.50")


@pytest.mark.parametrize("note", ["", "   "])
def test_a_note_is_required(note):
    with pytest.raises(DomainError, match="note"):
        plan_adjustment(D("1000"), D("900"), note)


def test_note_is_trimmed():
    assert plan_adjustment(D("0"), D("5"), "  Found coins ").note == "Found coins"
