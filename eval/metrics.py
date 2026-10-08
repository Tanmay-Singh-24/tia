"""Evaluation metrics shared by the harness and the report.

One definition, imported by both, so a results file and the table built from it
can never disagree about what a number means.
"""

from __future__ import annotations

from typing import Any


def time_saved_per_change(mutants: list[dict[str, Any]]) -> float | None:
    """Mean fraction of the full suite's time saved, over every measured change.

    The headline time metric (D-0020). Each change contributes a fraction in
    [0, 1], so no single change can dominate. The earlier metric summed seconds
    across changes, and a mutant that hung the suite for 291 s outweighed some
    seventy normal 4 s changes: whether it finished just under the timeout or
    just over it moved the attrs result between 58% and 37%. A fallback saves 0;
    a timed-out run measures a hang, not the suite, and is left out.
    """
    fractions = []
    for m in mutants:
        if m["outcome"] not in ("caught", "miss") or m["full_suite_s"] <= 0:
            continue
        if m["full_suite_exit"] == -1 or m["selected_exit"] == -1:
            continue
        with_tia = m["full_suite_s"] if m["full_suite_selected"] else m["selected_s"]
        fractions.append(max(0.0, 1 - with_tia / m["full_suite_s"]))
    return sum(fractions) / len(fractions) if fractions else None
