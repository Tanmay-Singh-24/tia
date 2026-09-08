"""The benchmark runner: the safety experiment (SPEC B.9 metric 4).

    python eval/harness.py --repo attrs --experiment safety --n 50

For each injected defect:

1. Apply it on a scratch git branch and commit it, so tia's ordinary git path
   is exercised rather than a special harness-only path.
2. Run the full suite. If it passes, the mutant is **equivalent** — the suite
   cannot detect it — and it is excluded from the denominator.
3. Ask tia what it would select, and run exactly that.
4. If the selection passes where the full suite failed, that is a **miss**: a
   defect the full suite catches and tia does not. Misses are the only
   unacceptable outcome and are reported individually, never averaged away.

Results are written to eval/results/safety_<repo>_<date>.json and committed.
Every number this project publishes must be traceable to one of these files.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from corpus import (  # noqa: E402
    RESULTS_DIR,
    ROOT,
    Ran,
    RepoSpec,
    find_spec,
    machine_info,
    run,
    venv_env,
)
from mutate import Mutation, find_mutations, restore, write_mutant  # noqa: E402

sys.path.insert(0, str(ROOT / "src"))

from tia import db  # noqa: E402

RESULT_SCHEMA = 1
SCRATCH_BRANCH = "tia-mutant"
DEFAULT_SUITE_TIMEOUT_S = 900

# Outcomes for one mutant.
OUTCOME_EQUIVALENT = "equivalent"
OUTCOME_CAUGHT = "caught"
OUTCOME_MISS = "miss"
OUTCOME_ERROR = "error"


@dataclass
class MutantResult:
    """Everything about one injected defect, enough to root-cause it later."""

    index: int
    mutation: dict[str, Any]
    outcome: str
    full_suite_exit: int | None = None
    full_suite_s: float = 0.0
    selected_exit: int | None = None
    selected_s: float = 0.0
    selected_count: int | None = None
    total_tests: int | None = None
    selection_ratio: float | None = None
    full_suite_selected: bool = False
    primary_reason: str = ""
    fallback_reasons: list[str] = field(default_factory=list)
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return dict(self.__dict__)


def tia_version() -> str:
    try:
        from tia import __version__
    except ImportError:  # pragma: no cover
        return "unknown"
    return str(__version__)


def tia_commit() -> str:
    """Which build of tia produced this result. Without it nothing replays."""
    proc = subprocess.run(  # noqa: S603
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 else "unknown"


def git(root: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(  # noqa: S603
        ["git", *args], cwd=root, capture_output=True, text=True, check=False
    )
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {proc.stderr.strip()}")
    return proc.stdout


def suite_env(spec: RepoSpec) -> dict[str, str]:
    """The corpus environment, plus the D-0008 guard.

    PYTHONDONTWRITEBYTECODE stops a fresh stale cache appearing mid-experiment.
    It is not sufficient on its own — mutate.write_mutant also deletes the
    existing .pyc — but together they close the hole.
    """
    return {**venv_env(spec), "PYTHONDONTWRITEBYTECODE": "1"}


def run_suite(
    spec: RepoSpec,
    nodeids: list[str] | None,
    timeout_s: int,
    log_name: str,
    jobs: str | None = None,
) -> Ran:
    """Run the whole suite, or just the given nodeids.

    `jobs` is passed to xdist. On a repository whose suite takes minutes, a
    serial experiment over 50 mutants would run for hours; the comparison stays
    fair because the full run and the selected run use the same mode.
    """
    command = [str(spec.bin / "pytest"), *spec.suite_args]
    if jobs:
        command += ["-n", jobs]
    if nodeids is not None:
        command += nodeids
    return run(
        command,
        cwd=spec.checkout,
        env=suite_env(spec),
        timeout_s=timeout_s,
        log_name=log_name,
    )


def tia_select(spec: RepoSpec, base: str, timeout_s: int) -> dict[str, Any] | None:
    """Ask tia for its decision as JSON."""
    result = run(
        [str(spec.bin / "tia"), "select", "--base", base, "--format", "json"],
        cwd=spec.checkout,
        env=suite_env(spec),
        timeout_s=timeout_s,
        log_name=f"{spec.name}_tia_select",
    )
    try:
        return dict(json.loads(result.stdout))
    except (json.JSONDecodeError, ValueError):
        return None


def sample_sites(spec: RepoSpec, count: int, rng: random.Random) -> list[Mutation]:
    """Sample mutation sites uniformly across covered lines (SPEC B.9).

    Sites come from the map, so every defect lands on a line some test actually
    executed. A defect on unreachable code would test the suite, not selection.
    """
    map_file = db.map_path(spec.checkout)
    conn = db.connect(map_file)
    try:
        source_files = sorted(
            path
            for path in db.mapped_source_files(conn)
            if path.endswith(".py") and "test" not in path
        )
        covered = {path: db.covered_lines(conn, path) for path in source_files}
    finally:
        conn.close()

    # Build the full candidate pool, then sample from it uniformly: sampling a
    # file first and a line second would over-weight small files.
    pool: list[Mutation] = []
    for path in source_files:
        try:
            source = (spec.checkout / path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        lines = covered[path]
        pool.extend(m for m in find_mutations(source, path) if m.lineno in lines)

    if not pool:
        return []
    rng.shuffle(pool)
    return pool[:count]


def evaluate_one(
    spec: RepoSpec,
    mutation: Mutation,
    index: int,
    base: str,
    timeout_s: int,
    jobs: str | None = None,
) -> MutantResult:
    """Inject one defect, then answer: does the selection catch what the suite does?"""
    result = MutantResult(
        index=index, mutation=mutation.as_dict(), outcome=OUTCOME_ERROR
    )
    target = spec.checkout / mutation.path
    source = target.read_text(encoding="utf-8")

    git(spec.checkout, "checkout", "-q", "-B", f"{SCRATCH_BRANCH}-{index}", base)
    original = write_mutant(spec.checkout, mutation, source)
    try:
        git(
            spec.checkout,
            "-c",
            "user.name=tia harness",
            "-c",
            "user.email=tia@example.test",
            "commit",
            "-q",
            "-am",
            f"mutant {index}: {mutation.label}",
        )

        full = run_suite(
            spec, None, timeout_s, f"{spec.name}_mutant{index}_full", jobs=jobs
        )
        result.full_suite_exit = -1 if full.timed_out else full.exit_code
        result.full_suite_s = round(full.duration_s, 3)

        if full.exit_code == 0 and not full.timed_out:
            # The suite cannot tell this mutant from the original. Excluded from
            # the denominator — but see D-0008 for how this can lie.
            result.outcome = OUTCOME_EQUIVALENT
            result.note = "full suite passed; mutant is equivalent or undetectable"
            return result

        decision = tia_select(spec, base, timeout_s)
        if decision is None:
            result.note = "tia select produced no parseable decision"
            return result

        result.selected_count = int(decision["selected_count"])
        result.total_tests = int(decision["total_tests"])
        result.selection_ratio = float(decision["selection_ratio"])
        result.full_suite_selected = bool(decision["full_suite"])
        result.primary_reason = str(decision["primary_reason"])
        result.fallback_reasons = list(decision["fallback_reasons"])

        if decision["full_suite"]:
            # tia fell back. It runs what the full suite runs, so it cannot
            # miss; this mutant informs fallback frequency, not the miss rate.
            result.outcome = OUTCOME_CAUGHT
            result.selected_exit = result.full_suite_exit
            result.selected_s = result.full_suite_s
            result.note = "fell back to the full suite"
            return result

        nodeids = list(decision["selected"])
        if not nodeids:
            result.outcome = OUTCOME_MISS
            result.note = "selection was empty while the full suite failed"
            return result

        selected = run_suite(
            spec,
            nodeids,
            timeout_s,
            f"{spec.name}_mutant{index}_selected",
            jobs=jobs,
        )
        result.selected_exit = -1 if selected.timed_out else selected.exit_code
        result.selected_s = round(selected.duration_s, 3)
        result.outcome = OUTCOME_CAUGHT if selected.exit_code != 0 else OUTCOME_MISS
        if result.outcome == OUTCOME_MISS:
            result.note = (
                "MISS: the full suite failed and the selection passed. "
                "Root-cause this individually."
            )
        return result
    finally:
        restore(spec.checkout, mutation, original)
        git(spec.checkout, "checkout", "-q", "--force", base, check=False)
        git(
            spec.checkout,
            "branch",
            "-q",
            "-D",
            f"{SCRATCH_BRANCH}-{index}",
            check=False,
        )


def summarise(results: list[MutantResult]) -> dict[str, Any]:
    """The headline numbers. Misses are listed, never averaged away."""
    equivalent = [r for r in results if r.outcome == OUTCOME_EQUIVALENT]
    errors = [r for r in results if r.outcome == OUTCOME_ERROR]
    non_equivalent = [r for r in results if r.outcome in {OUTCOME_CAUGHT, OUTCOME_MISS}]
    misses = [r for r in results if r.outcome == OUTCOME_MISS]

    ratios = [
        r.selection_ratio
        for r in non_equivalent
        if r.selection_ratio is not None and not r.full_suite_selected
    ]
    fallbacks: dict[str, int] = {}
    for r in non_equivalent:
        if r.full_suite_selected:
            for reason in r.fallback_reasons or [r.primary_reason]:
                fallbacks[reason] = fallbacks.get(reason, 0) + 1

    fell_back = sum(1 for r in non_equivalent if r.full_suite_selected)
    return {
        "mutants_generated": len(results),
        "equivalent": len(equivalent),
        "errors": len(errors),
        "non_equivalent": len(non_equivalent),
        "misses": len(misses),
        "miss_rate": (
            round(len(misses) / len(non_equivalent), 6) if non_equivalent else None
        ),
        "fallback_count": fell_back,
        "fallback_frequency": (
            round(fell_back / len(non_equivalent), 6) if non_equivalent else None
        ),
        "fallback_by_reason": dict(sorted(fallbacks.items())),
        "selection_ratio": {
            "n": len(ratios),
            "median": round(statistics.median(ratios), 6) if ratios else None,
            "min": round(min(ratios), 6) if ratios else None,
            "max": round(max(ratios), 6) if ratios else None,
            "mean": round(statistics.fmean(ratios), 6) if ratios else None,
        },
        "wall_clock_s": {
            "full_suite_median": (
                round(statistics.median([r.full_suite_s for r in non_equivalent]), 3)
                if non_equivalent
                else None
            ),
            "selected_median": (
                round(
                    statistics.median(
                        [
                            r.selected_s
                            for r in non_equivalent
                            if not r.full_suite_selected and r.selected_s
                        ]
                    ),
                    3,
                )
                if ratios
                else None
            ),
        },
        "misses_detail": [r.as_dict() for r in misses],
    }


def safety(
    spec: RepoSpec,
    *,
    count: int,
    seed: int,
    timeout_s: int,
    jobs: str | None = None,
) -> dict[str, Any]:
    """Run the safety experiment and write the results JSON."""
    map_file = db.map_path(spec.checkout)
    if not map_file.exists():
        raise SystemExit(
            f"no map at {map_file}. Run `tia build` in {spec.checkout} first."
        )

    base = git(spec.checkout, "rev-parse", "HEAD").strip()
    conn = db.connect(map_file)
    try:
        map_commit = db.get_meta(conn, "built_at_commit") or ""
    finally:
        conn.close()
    if map_commit != base:
        print(
            f"[{spec.name}] warning: map was built at {map_commit[:7]} but HEAD is "
            f"{base[:7]}; every mutant will fall back with MAP_STALE"
        )

    rng = random.Random(seed)
    mutations = sample_sites(spec, count, rng)
    print(f"[{spec.name}] sampled {len(mutations)} mutation sites from covered lines")

    started = time.perf_counter()
    results: list[MutantResult] = []
    for index, mutation in enumerate(mutations):
        result = evaluate_one(spec, mutation, index, base, timeout_s, jobs=jobs)
        results.append(result)
        marker = {
            OUTCOME_MISS: "MISS  <<<<",
            OUTCOME_CAUGHT: "caught",
            OUTCOME_EQUIVALENT: "equivalent",
            OUTCOME_ERROR: "ERROR",
        }[result.outcome]
        selected = (
            "full" if result.full_suite_selected else str(result.selected_count or "-")
        )
        print(
            f"[{spec.name}] {index + 1:>3}/{len(mutations)} {marker:11} "
            f"selected={selected:>5}  {mutation.label}"
        )

    payload: dict[str, Any] = {
        "schema": RESULT_SCHEMA,
        "experiment": "safety",
        "generated_by": "eval/harness.py",
        "tia_version": tia_version(),
        "tia_commit": tia_commit(),
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "repo": spec.name,
        "url": spec.url,
        "sha": spec.sha,
        "map_commit": map_commit,
        "seed": seed,
        "requested": count,
        "jobs": jobs,
        "duration_s": round(time.perf_counter() - started, 1),
        "machine": machine_info(),
        "suite_args": spec.suite_args,
        "summary": summarise(results),
        "mutants": [r.as_dict() for r in results],
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    # The filename carries the seed and a timestamp. An earlier version keyed
    # on the date alone, and a same-day re-run silently overwrote the result it
    # was meant to be compared against — destroying the evidence for a miss.
    # Results are the deliverable; they are never clobbered.
    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H%M%SZ")
    out = RESULTS_DIR / f"safety_{spec.name}_{stamp}_seed{seed}.json"
    out.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"[{spec.name}] wrote {out.relative_to(ROOT)}")
    return payload


def report(payload: dict[str, Any]) -> None:
    """Print the summary a review slide is built from."""
    s = payload["summary"]
    print("\n" + "=" * 66)
    print(f"safety experiment — {payload['repo']} @ {payload['sha'][:12]}")
    print("=" * 66)
    print(f"  mutants generated        {s['mutants_generated']}")
    print(f"  equivalent (excluded)    {s['equivalent']}")
    print(f"  errors                   {s['errors']}")
    print(f"  non-equivalent           {s['non_equivalent']}")
    print(f"  MISSES                   {s['misses']}")
    print(f"  miss rate                {s['miss_rate']}")
    print()
    print(
        f"  fell back to full suite  {s['fallback_count']} ({s['fallback_frequency']})"
    )
    for reason, n in s["fallback_by_reason"].items():
        print(f"      {reason:24} {n}")
    print()
    ratio = s["selection_ratio"]
    print(f"  selection ratio (n={ratio['n']})")
    print(f"      median {ratio['median']}  min {ratio['min']}  max {ratio['max']}")
    print()
    clock = s["wall_clock_s"]
    print(f"  full suite median        {clock['full_suite_median']} s")
    print(f"  selected median          {clock['selected_median']} s")
    if s["misses"]:
        print("\n  MISSES — each must be root-caused individually:")
        for miss in s["misses_detail"]:
            print(f"      {miss['mutation']}")
            print(f"        {miss['note']}")
    print("=" * 66)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--experiment", default="safety", choices=["safety"])
    parser.add_argument("--n", type=int, default=50, help="mutation sites to sample")
    parser.add_argument("--seed", type=int, default=1234)
    parser.add_argument("--timeout", type=int, default=DEFAULT_SUITE_TIMEOUT_S)
    parser.add_argument(
        "--jobs",
        default=None,
        metavar="N",
        help="xdist workers for both the full and selected runs (e.g. auto)",
    )
    args = parser.parse_args(argv)

    spec = find_spec(args.repo)
    payload = safety(
        spec,
        count=args.n,
        seed=args.seed,
        timeout_s=args.timeout,
        jobs=args.jobs,
    )
    report(payload)
    return 1 if payload["summary"]["misses"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
