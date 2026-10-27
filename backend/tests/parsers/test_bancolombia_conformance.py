"""Runs the Bancolombia parser over a private dataset of real notifications.

The dataset is never versioned. The test is skipped when the file is missing,
and its failures report counts only, never the text of any notification.
Set BANCOLOMBIA_DATASET to point at a JSON-lines file with a `snippet` field.
"""

import json
import os
from collections import Counter
from pathlib import Path

import pytest

from app.parsers.bancolombia import parse_bancolombia

DEFAULT_DATASET = Path(__file__).resolve().parents[3] / "datos-privados" / "bancolombia-notificaciones.jsonl"
DATASET = Path(os.environ.get("BANCOLOMBIA_DATASET", DEFAULT_DATASET))
MIN_RECOGNIZED_RATE = 0.98


def _snippets() -> list[str]:
    with DATASET.open(encoding="utf-8") as handle:
        return [json.loads(line)["snippet"] for line in handle if line.strip()]


@pytest.mark.skipif(not DATASET.is_file(), reason="private notification dataset not available")
def test_private_dataset_is_recognized():
    outcomes: Counter[str] = Counter()
    for snippet in _snippets():
        try:
            parsed = parse_bancolombia(snippet)
        except Exception:  # noqa: BLE001 - only the count matters, never the text
            outcomes["exception"] += 1
            continue
        outcomes["unrecognized" if parsed is None else parsed.kind.value] += 1

    total = sum(outcomes.values())
    failures = outcomes["exception"]
    recognized = total - outcomes["unrecognized"] - failures
    rate = recognized / total if total else 0.0
    summary = f"total={total} recognized={recognized} unrecognized={outcomes['unrecognized']} exceptions={failures}"

    assert total > 0, "dataset is empty"
    assert failures == 0, f"parser raised on some notifications: {summary}"
    assert rate >= MIN_RECOGNIZED_RATE, f"recognition rate {rate:.3f} below {MIN_RECOGNIZED_RATE}: {summary}"
