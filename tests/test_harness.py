"""The safety experiment's own logic (task D8).

The harness decides what counts as a miss. If that arithmetic is wrong, every
published safety number is wrong, so the classification and the summary are
tested directly rather than inferred from a run.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))

from harness import (  # noqa: E402
    OUTCOME_CAUGHT,
    OUTCOME_EQUIVALENT,
    OUTCOME_ERROR,
    OUTCOME_MISS,
    MutantResult,
    summarise,
)


def result(
    index: int,
    outcome: str,
    *,
    ratio: float | None = None,
    fell_back: bool = False,
    reasons: list[str] | None = None,
    full_s: float = 10.0,
    selected_s: float = 1.0,
) -> MutantResult:
    return MutantResult(
        index=index,
        mutation={"path": "m.py", "lineno": index},
        outcome=outcome,
        full_suite_s=full_s,
        selected_s=selected_s,
        selection_ratio=ratio,
        full_suite_selected=fell_back,
        fallback_reasons=reasons or [],
    )


def test_equivalent_mutants_are_excluded_from_the_denominator() -> None:
    """A mutant the full suite cannot detect says nothing about selection."""
    summary = summarise(
        [
            result(0, OUTCOME_EQUIVALENT),
            result(1, OUTCOME_CAUGHT, ratio=0.1),
            result(2, OUTCOME_CAUGHT, ratio=0.2),
        ]
    )
    assert summary["equivalent"] == 1
    assert summary["non_equivalent"] == 2
    assert summary["miss_rate"] == 0.0


def test_a_single_miss_is_reported_and_detailed() -> None:
    summary = summarise(
        [result(0, OUTCOME_CAUGHT, ratio=0.1), result(1, OUTCOME_MISS, ratio=0.05)]
    )
    assert summary["misses"] == 1
    assert summary["miss_rate"] == 0.5
    assert len(summary["misses_detail"]) == 1
    assert summary["misses_detail"][0]["mutation"]["lineno"] == 1


def test_fallbacks_count_as_caught_but_are_reported_separately() -> None:
    """Falling back cannot miss — it runs everything — but it is not free."""
    summary = summarise(
        [
            result(0, OUTCOME_CAUGHT, fell_back=True, reasons=["DEPENDENCY_CHANGED"]),
            result(1, OUTCOME_CAUGHT, ratio=0.1),
        ]
    )
    assert summary["misses"] == 0
    assert summary["fallback_count"] == 1
    assert summary["fallback_frequency"] == 0.5
    assert summary["fallback_by_reason"] == {"DEPENDENCY_CHANGED": 1}


def test_fallback_runs_are_excluded_from_the_selection_ratio() -> None:
    """A fallback selects 100% by definition; averaging it in hides the real spread."""
    summary = summarise(
        [
            result(0, OUTCOME_CAUGHT, fell_back=True, reasons=["NO_MAP"]),
            result(1, OUTCOME_CAUGHT, ratio=0.2),
            result(2, OUTCOME_CAUGHT, ratio=0.4),
        ]
    )
    assert summary["selection_ratio"]["n"] == 2
    assert summary["selection_ratio"]["median"] == 0.3


def test_errors_are_counted_and_never_silently_pass() -> None:
    summary = summarise(
        [result(0, OUTCOME_ERROR), result(1, OUTCOME_CAUGHT, ratio=0.1)]
    )
    assert summary["errors"] == 1
    assert summary["non_equivalent"] == 1


def test_empty_run_does_not_divide_by_zero() -> None:
    summary = summarise([])
    assert summary["miss_rate"] is None
    assert summary["selection_ratio"]["median"] is None


def test_all_equivalent_yields_no_miss_rate() -> None:
    """If every mutant was equivalent the experiment measured nothing — say so."""
    summary = summarise([result(0, OUTCOME_EQUIVALENT), result(1, OUTCOME_EQUIVALENT)])
    assert summary["non_equivalent"] == 0
    assert summary["miss_rate"] is None
