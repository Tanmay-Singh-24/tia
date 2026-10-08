"""The safety experiment's own logic (task D8).

The harness decides what counts as a miss. If that arithmetic is wrong, every
published safety number is wrong, so the classification and the summary are
tested directly rather than inferred from a run.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))

import corpus  # noqa: E402
from harness import (  # noqa: E402
    OUTCOME_CAUGHT,
    OUTCOME_EQUIVALENT,
    OUTCOME_ERROR,
    OUTCOME_MISS,
    MutantResult,
    count_executed,
    replay_sites,
    resumable,
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


# --- replay ---------------------------------------------------------------
# `make reproduce` stands or falls on replay: it must run exactly the recorded
# defects, and must refuse rather than quietly run a different one.

SOURCE = "def f(a, b):\n    if a < b:\n        return a + b\n    return 0\n"


def _spec(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> corpus.RepoSpec:
    monkeypatch.setattr(corpus, "CORPUS_DIR", tmp_path)
    spec = corpus.RepoSpec(
        name="demo", url="", sha="abc123", pinned_at="2026-01-01", install=[]
    )
    spec.checkout.mkdir(parents=True)
    (spec.checkout / "mod.py").write_text(SOURCE)
    return spec


def _recorded(tmp_path: Path, mutations: list[dict], repo: str = "demo") -> Path:
    path = tmp_path / "recorded.json"
    path.write_text(
        json.dumps(
            {
                "repo": repo,
                "sha": "abc123",
                "seed": 7,
                "mutants": [
                    {"index": i, "mutation": m} for i, m in enumerate(mutations)
                ],
            }
        )
    )
    return path


def test_replay_relocates_the_recorded_mutation(tmp_path, monkeypatch) -> None:
    spec = _spec(tmp_path, monkeypatch)
    recorded = {
        "path": "mod.py",
        "lineno": 2,
        "family": "comparison_flip",
        "before": "<",
        "after": "<=",
    }
    sites = replay_sites(spec, _recorded(tmp_path, [recorded]))
    assert len(sites) == 1
    assert sites[0].as_dict() == recorded


def test_replay_refuses_a_mutation_the_source_no_longer_admits(
    tmp_path, monkeypatch
) -> None:
    """Substituting a nearby mutant is how a reproduction quietly stops being one."""
    spec = _spec(tmp_path, monkeypatch)
    gone = {
        "path": "mod.py",
        "lineno": 2,
        "family": "comparison_flip",
        "before": ">",  # the source has '<' here
        "after": ">=",
    }
    with pytest.raises(SystemExit, match="cannot replay"):
        replay_sites(spec, _recorded(tmp_path, [gone]))


def test_replay_refuses_another_repositorys_results(tmp_path, monkeypatch) -> None:
    spec = _spec(tmp_path, monkeypatch)
    with pytest.raises(SystemExit, match="not demo"):
        replay_sites(spec, _recorded(tmp_path, [], repo="attrs"))


# --- reading pytest's own output -------------------------------------------


def test_count_executed_counts_what_ran_not_what_was_skipped() -> None:
    out = (
        "...\n= 1 failed, 30 passed, 10 skipped, 1 xfailed, 1381 deselected in 1.68s ="
    )
    assert count_executed(out) == 32


def test_count_executed_reads_the_quiet_summary() -> None:
    assert count_executed("....\n31 passed, 1381 deselected in 0.98s\n") == 31


def test_count_executed_with_no_summary_is_zero() -> None:
    assert count_executed("ERROR: file or directory not found: nope.py\n") == 0


# --- resuming an interrupted run -------------------------------------------


def _prior(mutations, graph: bool = True) -> dict:
    return {
        "use_import_graph": graph,
        "mutants": [
            {"index": i, "mutation": m.as_dict(), "outcome": OUTCOME_CAUGHT}
            for i, m in enumerate(mutations)
        ],
    }


def _mutations():
    from mutate import find_mutations

    source = "def f(a, b):\n    if a < b:\n        return a + b\n    return 0\n"
    return find_mutations(source, "mod.py")


def test_resume_continues_a_run_of_the_same_mutations() -> None:
    mutations = _mutations()
    done = resumable(_prior(mutations[:2]), mutations, True, "x.json")
    assert [r.mutation for r in done] == [m.as_dict() for m in mutations[:2]]


def test_resume_refuses_a_run_of_different_mutations() -> None:
    mutations = _mutations()
    with pytest.raises(SystemExit, match="refusing to resume"):
        resumable(_prior(mutations[1:3]), mutations, True, "x.json")


def test_resume_refuses_the_other_arm() -> None:
    mutations = _mutations()
    with pytest.raises(SystemExit, match="other arm"):
        resumable(_prior(mutations[:2], graph=False), mutations, True, "x.json")
