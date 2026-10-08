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
import re
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
    failing_tests: int | None = None
    """How many tests the FULL suite failed on this mutant."""

    failing_selected: int | None = None
    """How many of those the selection also contained."""

    precision: float | None = None
    """|F and S| / |S| (SPEC B.9 metric 3).

    The stated limitation: this proxies "genuinely related to the change" with
    "actually fails", which understates precision for a test that exercises the
    changed line without asserting on its result."""

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


FAILED_RE = re.compile(r"^(?:FAILED|ERROR)\s+(\S+?)(?:\s+-.*)?$", re.MULTILINE)


def failing_nodeids(output: str) -> set[str]:
    """Nodeids pytest reported as failed, from its short summary."""
    return {m.group(1) for m in FAILED_RE.finditer(output)}


# Counts that ran: skipped and deselected tests executed nothing that could fail.
SUMMARY_RE = re.compile(r"(\d+) (passed|failed|errors?|xfailed|xpassed)\b")
SUMMARY_LINE_RE = re.compile(r"\b\d+ [a-z]+.* in [\d.]+s")


def count_executed(output: str) -> int:
    """How many tests a pytest run executed, from its final summary line."""
    summaries = [line for line in output.splitlines() if SUMMARY_LINE_RE.search(line)]
    if not summaries:
        return 0
    return sum(int(count) for count, _ in SUMMARY_RE.findall(summaries[-1]))


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
    if nodeids is None:
        # Whole-suite run: the paths scope what gets collected.
        command += spec.suite_paths
    else:
        # Selected run: nodeids ONLY. Adding the paths here would collect the
        # entire suite alongside the selection, so a "selected" run would in
        # fact be a full one and every mutant would look caught.
        command += nodeids
    return run(
        command,
        cwd=spec.checkout,
        env=suite_env(spec),
        timeout_s=timeout_s,
        log_name=log_name,
    )


def tia_select(
    spec: RepoSpec, base: str, timeout_s: int, use_import_graph: bool = True
) -> dict[str, Any] | None:
    """Ask tia for its decision as JSON."""
    result = run(
        [
            str(spec.bin / "tia"),
            "select",
            "--base",
            base,
            "--format",
            "json",
            *([] if use_import_graph else ["--no-import-graph"]),
        ],
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
    use_import_graph: bool = True,
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
        failed = failing_nodeids(full.stdout + full.stderr)
        result.failing_tests = len(failed) or None

        if full.exit_code == 0 and not full.timed_out:
            # The suite cannot tell this mutant from the original. Excluded from
            # the denominator — but see D-0008 for how this can lie.
            result.outcome = OUTCOME_EQUIVALENT
            result.note = "full suite passed; mutant is equivalent or undetectable"
            return result

        decision = tia_select(spec, base, timeout_s, use_import_graph)
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

        # Run exactly what the shipped tool would run — forced paths whole and
        # each selected test function with all its parametrisations — not the
        # bare nodeid set. Measuring anything else measures a different tool.
        # Results written before D-0018 ran the nodeid set, a subset of this.
        nodeids = list(decision.get("pytest_args") or decision["selected"])

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

        # SPEC B.9 metric 3, over the tests the selected run actually executed.
        # Measured only where tia selected: on a fallback the selection is the
        # whole suite and precision is the base rate, flattering the average.
        # Read from the run's own output, because the arguments are now test
        # functions and paths rather than the individual nodeids that ran.
        executed = count_executed(selected.stdout + selected.stderr)
        if failed and executed:
            hit = failed & failing_nodeids(selected.stdout + selected.stderr)
            result.failing_selected = len(hit)
            result.precision = round(len(hit) / executed, 4)
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


def build_payload(
    spec: RepoSpec,
    results: list[MutantResult],
    *,
    seed: int,
    count: int,
    jobs: str | None,
    map_commit: str,
    started: float,
    complete: bool,
    use_import_graph: bool = True,
    replay_of: str | None = None,
) -> dict[str, Any]:
    """The results document. Written after every mutant, not just at the end."""
    return {
        "schema": RESULT_SCHEMA,
        "experiment": "safety",
        "generated_by": "eval/harness.py",
        "tia_version": tia_version(),
        "tia_commit": tia_commit(),
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "complete": complete,
        "repo": spec.name,
        "url": spec.url,
        "sha": spec.sha,
        "map_commit": map_commit,
        "seed": seed,
        "requested": count,
        "jobs": jobs,
        "use_import_graph": use_import_graph,
        "replay_of": replay_of,
        "duration_s": round(time.perf_counter() - started, 1),
        "machine": machine_info(),
        "suite_args": spec.suite_args,
        "suite_paths": spec.suite_paths,
        "summary": summarise(results),
        "mutants": [r.as_dict() for r in results],
    }


def _net_reduction(results: list[MutantResult]) -> dict[str, Any]:
    """Total suite time with tia against without, over non-timed-out mutants."""
    kept = [r for r in results if r.full_suite_exit != -1 and r.selected_exit != -1]
    if not kept:
        return {"n": 0, "excluded_timeouts": len(results)}
    without = sum(r.full_suite_s for r in kept)
    with_tia = sum(
        r.full_suite_s if r.full_suite_selected else r.selected_s for r in kept
    )
    per_mutant = [
        1 - (r.full_suite_s if r.full_suite_selected else r.selected_s) / r.full_suite_s
        for r in kept
        if r.full_suite_s > 0
    ]
    return {
        "n": len(kept),
        "excluded_timeouts": len(results) - len(kept),
        "without_tia_s": round(without, 1),
        "with_tia_s": round(with_tia, 1),
        "total_time_reduction": round(1 - with_tia / without, 4) if without else None,
        "median_per_mutant": (
            round(statistics.median(per_mutant), 4) if per_mutant else None
        ),
    }


def _precision(results: list[MutantResult]) -> dict[str, Any]:
    """Selection precision over the mutants where tia actually selected."""
    scored = [r for r in results if r.precision is not None]
    if not scored:
        return {"n": 0}
    values = sorted(r.precision for r in scored if r.precision is not None)
    recall_complete = sum(
        1
        for r in scored
        if r.failing_tests is not None and r.failing_selected == r.failing_tests
    )
    return {
        "n": len(scored),
        "median": round(statistics.median(values), 4),
        "mean": round(statistics.fmean(values), 4),
        "min": values[0],
        "max": values[-1],
        "selections_containing_every_failing_test": recall_complete,
        "note": (
            "precision = |failing and selected| / |selected|, measured only on "
            "mutants where tia selected rather than fell back. It proxies "
            "'related to the change' with 'actually fails', which understates "
            "it for tests that exercise the changed line without asserting on it."
        ),
    }


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
        # The headline efficiency number, computed here rather than ad hoc so
        # every report quotes the same definition. Runs that TIMED OUT are
        # excluded by exit code: a timeout measures a hang, not a suite, and a
        # single hung mutant at a 600s limit otherwise swamps a sum over
        # mutants whose suite takes four seconds. (An earlier analysis excluded
        # them with a hand-picked duration threshold, which silently changed
        # the answer when the timeout setting changed.)
        "net_reduction": _net_reduction(non_equivalent),
        "precision": _precision(non_equivalent),
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


def replay_sites(spec: RepoSpec, results_file: Path) -> list[Mutation]:
    """The exact mutations a committed result used, re-located in the source.

    Re-sampling with the same seed is not reproduction: sites are drawn from
    the lines the map records as covered, and a rebuilt map covers a slightly
    different set (D-0013), so the same seed picks different mutants. A result
    records each mutation's path, line, family and before/after text; this finds
    each one again among the mutations the pinned source admits. A record that
    no longer matches exactly one candidate is a hard error — silently
    substituting a nearby mutant is how a reproduction quietly stops being one.
    """
    recorded = json.loads(results_file.read_text())
    if recorded.get("repo") != spec.name:
        raise SystemExit(
            f"{results_file.name} is a {recorded.get('repo')} result, not {spec.name}"
        )
    if recorded.get("sha") and recorded["sha"] != spec.sha:
        raise SystemExit(
            f"{results_file.name} was measured at {recorded['sha'][:12]}, "
            f"but corpus.yaml pins {spec.sha[:12]}"
        )

    by_path: dict[str, list[Mutation]] = {}
    sites: list[Mutation] = []
    for entry in recorded["mutants"]:
        want = entry["mutation"]
        path = want["path"]
        if path not in by_path:
            source = (spec.checkout / path).read_text(encoding="utf-8")
            by_path[path] = find_mutations(source, path)
        matches = [
            m
            for m in by_path[path]
            if m.lineno == want["lineno"]
            and m.family == want["family"]
            and m.before == want["before"]
            and m.after == want["after"]
        ]
        # Two identical operators on one line produce identical records. They
        # are interchangeable as defects, so the first is taken; anything
        # other than one-or-identical means the source has moved.
        if not matches:
            raise SystemExit(
                f"cannot replay mutant {entry['index']} ({path}:{want['lineno']} "
                f"{want['family']} {want['before']!r}->{want['after']!r}): "
                "the pinned source no longer admits it"
            )
        sites.append(matches[0])
    return sites


def resumable(
    prior: dict[str, Any],
    mutations: list[Mutation],
    use_import_graph: bool,
    name: str,
) -> list[MutantResult]:
    """The finished mutants of an interrupted run, if it can honestly continue.

    Its mutants must be exactly the first entries of this run's list, in order,
    and it must be the same arm. Anything else is a different experiment, and
    joining the two would produce a result no single run ever measured.
    """
    done = [MutantResult(**m) for m in prior["mutants"]]
    expected = [m.as_dict() for m in mutations[: len(done)]]
    if [r.mutation for r in done] != expected:
        raise SystemExit(
            f"{name} does not match this run's first {len(done)} mutations; "
            "refusing to resume"
        )
    if prior.get("use_import_graph", True) != use_import_graph:
        raise SystemExit(f"{name} is the other arm; refusing to resume")
    return done


def safety(
    spec: RepoSpec,
    *,
    count: int,
    seed: int,
    timeout_s: int,
    jobs: str | None = None,
    use_import_graph: bool = True,
    replay: Path | None = None,
    limit: int | None = None,
    resume: Path | None = None,
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

    if replay is not None:
        mutations = replay_sites(spec, replay)
        seed = int(json.loads(replay.read_text()).get("seed", seed))
        count = len(mutations)
        how = f"replaying {len(mutations)} recorded mutations from {replay.name}"
    else:
        rng = random.Random(seed)
        mutations = sample_sites(spec, count, rng)
        how = f"sampled {len(mutations)} mutation sites from covered lines"
    if limit is not None:
        mutations = mutations[:limit]
        how += f" (first {len(mutations)} only)"
    print(f"[{spec.name}] {how}", flush=True)

    started = time.perf_counter()
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H%M%SZ")
    arm = "graph" if use_import_graph else "nograph"
    # A --limit run is a spot check, not a reproduction, and its filename says
    # so: report.py --compare only ever reads full "_replay" files.
    tag = ("_replay" if replay else "") + ("_partial" if limit is not None else "")
    out = RESULTS_DIR / f"safety_{spec.name}_{stamp}_seed{seed}_{arm}{tag}.json"

    results: list[MutantResult] = []
    if resume is not None:
        # Continue an interrupted run. Only meaningful when the mutation list is
        # fixed, i.e. a replay: the prior file's mutants must be exactly the
        # first entries of this list, in order, or the two runs are different
        # experiments and joining them would be a fabrication.
        prior = json.loads(resume.read_text())
        results = resumable(prior, mutations, use_import_graph, resume.name)
        out = resume
        print(
            f"[{spec.name}] resuming {resume.name} at {len(results)}/{len(mutations)}"
        )

    resumed = len(results)
    for index, mutation in enumerate(mutations):
        if index < resumed:
            continue
        result = evaluate_one(
            spec,
            mutation,
            index,
            base,
            timeout_s,
            jobs=jobs,
            use_import_graph=use_import_graph,
        )
        results.append(result)

        # Checkpoint after every mutant. An experiment that only writes its
        # results at the end loses everything when it is interrupted, and a run
        # measured in hours will be interrupted.
        out.write_text(
            json.dumps(
                build_payload(
                    spec,
                    results,
                    seed=seed,
                    count=count,
                    jobs=jobs,
                    map_commit=map_commit,
                    started=started,
                    complete=index + 1 == len(mutations),
                    use_import_graph=use_import_graph,
                    replay_of=replay.name if replay else None,
                ),
                indent=2,
            )
            + "\n"
        )
        marker = {
            OUTCOME_MISS: "MISS  <<<<",
            OUTCOME_CAUGHT: "caught",
            OUTCOME_EQUIVALENT: "equivalent",
            OUTCOME_ERROR: "ERROR",
        }[result.outcome]
        selected = (
            "full" if result.full_suite_selected else str(result.selected_count or "-")
        )
        elapsed = time.perf_counter() - started
        rate = elapsed / max(index + 1 - resumed, 1)  # this session's pace
        remaining = rate * (len(mutations) - index - 1)
        print(
            f"[{spec.name}] {index + 1:>3}/{len(mutations)} {marker:11} "
            f"selected={selected:>5}  ~{remaining / 60:.0f}m left  {mutation.label}",
            flush=True,
        )

    payload = build_payload(
        spec,
        results,
        seed=seed,
        count=count,
        jobs=jobs,
        map_commit=map_commit,
        started=started,
        complete=True,
        use_import_graph=use_import_graph,
        replay_of=replay.name if replay else None,
    )
    out.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"[{spec.name}] wrote {out.relative_to(ROOT)}", flush=True)
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
    net = s["net_reduction"]
    if net.get("n"):
        print(
            f"\n  net time reduction       {net['total_time_reduction']:.1%} "
            f"({net['without_tia_s']}s -> {net['with_tia_s']}s over {net['n']} mutants"
            + (
                f", {net['excluded_timeouts']} timed-out excluded)"
                if net["excluded_timeouts"]
                else ")"
            )
        )
        print(f"  median per mutant        {net['median_per_mutant']:.1%}")
    prec = s["precision"]
    if prec.get("n"):
        print(
            f"\n  selection precision      median {prec['median']:.1%} "
            f"(mean {prec['mean']:.1%}, n={prec['n']})"
        )
        print(
            f"  selections containing every failing test: "
            f"{prec['selections_containing_every_failing_test']}/{prec['n']}"
        )
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
    parser.add_argument(
        "--replay",
        type=Path,
        metavar="RESULTS_JSON",
        help="re-run the exact mutations recorded in a committed result "
        "(ignores --n and --seed)",
    )
    parser.add_argument(
        "--published",
        action="store_true",
        help="replay the published result for this repo and arm, with the "
        "settings it was measured under (see eval/published.json)",
    )
    parser.add_argument(
        "--resume",
        type=Path,
        metavar="RESULTS_JSON",
        help="continue an interrupted replay, appending to its results file",
    )
    parser.add_argument(
        "--limit",
        type=int,
        metavar="K",
        help="run only the first K mutations (a quick check of a replay)",
    )
    parser.add_argument("--timeout", type=int, default=DEFAULT_SUITE_TIMEOUT_S)
    parser.add_argument(
        "--no-import-graph",
        action="store_true",
        help="run the Phase 1 arm: selection ignores the import closure",
    )
    parser.add_argument(
        "--jobs",
        default=None,
        metavar="N",
        help="xdist workers for both the full and selected runs (e.g. auto)",
    )
    args = parser.parse_args(argv)

    spec = find_spec(args.repo)
    if args.published:
        manifest = json.loads((ROOT / "eval" / "published.json").read_text())
        entry = manifest.get(spec.name)
        if entry is None:
            raise SystemExit(f"eval/published.json has no entry for {spec.name}")
        arm = "nograph" if args.no_import_graph else "graph"
        args.replay = RESULTS_DIR / entry[arm]
        args.jobs = entry["jobs"]
        args.timeout = entry["timeout"]

    payload = safety(
        spec,
        count=args.n,
        seed=args.seed,
        timeout_s=args.timeout,
        jobs=args.jobs,
        use_import_graph=not args.no_import_graph,
        replay=args.replay,
        limit=args.limit,
        resume=args.resume,
    )
    report(payload)
    return 1 if payload["summary"]["misses"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
