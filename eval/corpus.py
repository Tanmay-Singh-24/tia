"""Corpus checkout, setup and baseline measurement (SPEC B.9).

This runs before the tool exists. Its job is to answer, with evidence, which
real repositories tia will be evaluated against, and what the *properly
optimised* baseline runtime is on each — the number every later speedup claim
is measured against.

Usage:
    python eval/corpus.py list
    python eval/corpus.py prepare  --repo attrs
    python eval/corpus.py baseline --repo attrs [--runs 5] [--warmup 1]
    python eval/corpus.py clean    --repo attrs

Baselines are written to eval/results/baseline_<repo>_<date>.json and are
committed. No number this project publishes may come from anywhere else.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shlex
import shutil
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
CORPUS_DIR = ROOT / "eval" / ".corpus"
RESULTS_DIR = ROOT / "eval" / "results"
CORPUS_YAML = ROOT / "eval" / "corpus.yaml"
LOG_DIR = CORPUS_DIR / "_logs"

RESULT_SCHEMA = 1
DEFAULT_TIMEOUT_S = 1800
# A suite that has not finished in this long is not a corpus candidate: SPEC B.9
# wants total runtime under ~15 minutes so the evaluation can be iterated on.
# Overridable per invocation with --timeout.
DEFAULT_SUITE_TIMEOUT_S = 600

# pytest exit codes we care about (pytest.ExitCode).
EXIT_OK = 0
EXIT_TESTS_FAILED = 1
EXIT_NO_TESTS = 5


@dataclass(frozen=True)
class RepoSpec:
    """One corpus candidate, exactly as pinned in corpus.yaml."""

    name: str
    url: str
    sha: str
    pinned_at: str
    install: list[str]
    package: list[str] = field(default_factory=list)
    python: str = "3.12"
    suite_args: list[str] = field(default_factory=list)
    """Flags applied to EVERY run, whole-suite or selected."""

    suite_paths: list[str] = field(default_factory=list)
    """Paths that scope the whole suite. Never passed alongside nodeids: doing
    so collects the entire suite *in addition to* the selection, which silently
    turns a selected run into a full one."""

    env: dict[str, str] = field(default_factory=dict)
    status: str = "candidate"
    reason: str = ""

    @property
    def checkout(self) -> Path:
        return CORPUS_DIR / self.name / "repo"

    @property
    def venv(self) -> Path:
        return CORPUS_DIR / self.name / ".venv"

    @property
    def bin(self) -> Path:
        return self.venv / ("Scripts" if os.name == "nt" else "bin")


def load_corpus(path: Path = CORPUS_YAML) -> list[RepoSpec]:
    """Read corpus.yaml, applying the defaults block to every entry."""
    raw: dict[str, Any] = yaml.safe_load(path.read_text())
    defaults: dict[str, Any] = raw.get("defaults", {})
    specs: list[RepoSpec] = []
    for entry in raw["repos"]:
        merged = {**defaults, **entry}
        specs.append(
            RepoSpec(
                name=merged["name"],
                url=merged["url"],
                sha=merged["sha"],
                pinned_at=str(merged["pinned_at"]),
                install=list(merged.get("install", [])),
                package=list(merged.get("package", [])),
                python=str(merged.get("python", "3.12")),
                suite_args=list(merged.get("suite_args", [])),
                suite_paths=list(merged.get("suite_paths", [])),
                env={str(k): str(v) for k, v in (merged.get("env") or {}).items()},
                status=merged.get("status", "candidate"),
                reason=merged.get("reason", ""),
            )
        )
    return specs


def find_spec(name: str) -> RepoSpec:
    for spec in load_corpus():
        if spec.name == name:
            return spec
    known = ", ".join(s.name for s in load_corpus())
    raise SystemExit(f"unknown repo {name!r}; corpus.yaml has: {known}")


# --------------------------------------------------------------------------
# process helpers
# --------------------------------------------------------------------------


@dataclass
class Ran:
    """The outcome of one subprocess: what ran, how long, and what it said."""

    command: str
    exit_code: int
    duration_s: float
    stdout: str
    stderr: str
    timed_out: bool = False

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


def run(
    command: list[str],
    cwd: Path,
    *,
    env: dict[str, str] | None = None,
    timeout_s: int = DEFAULT_TIMEOUT_S,
    log_name: str | None = None,
) -> Ran:
    """Run a command, timing it with a monotonic clock, and log the output."""
    started = time.perf_counter()
    timed_out = False
    try:
        proc = subprocess.run(  # noqa: S603
            command,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
        exit_code, out, err = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = -1
        out = (
            exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        )
        err = (
            exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        )
    duration = time.perf_counter() - started

    if log_name:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        (LOG_DIR / f"{log_name}.log").write_text(
            f"$ {shlex.join(command)}\n(cwd={cwd})\n"
            f"exit={exit_code} timed_out={timed_out} duration={duration:.2f}s\n"
            f"--- stdout ---\n{out}\n--- stderr ---\n{err}\n"
        )
    return Ran(shlex.join(command), exit_code, duration, out, err, timed_out)


def venv_env(spec: RepoSpec) -> dict[str, str]:
    """An environment with the corpus venv first on PATH and no user site-packages."""
    env = dict(os.environ)
    env["PATH"] = f"{spec.bin}{os.pathsep}{env.get('PATH', '')}"
    env["VIRTUAL_ENV"] = str(spec.venv)
    env.pop("PYTHONHOME", None)
    env["PYTHONDONTWRITEBYTECODE"] = "0"  # let .pyc caches warm, like a real run
    # Per-repo environment from corpus.yaml. rich, for example, runs its own
    # suite as `TERM=unknown pytest` because its output tests are sensitive to
    # the terminal; measuring it any other way measures a different suite.
    env.update(spec.env)
    return env


# --------------------------------------------------------------------------
# prepare
# --------------------------------------------------------------------------


def clone(spec: RepoSpec) -> Ran | None:
    """Blobless partial clone, then check out the pinned SHA.

    Not `--depth 1`: later milestones need real history (merge-base resolution
    in D5, historical commit sampling for fallback frequency). A blobless clone
    keeps every commit and tree while deferring file contents, which costs
    about as little as a shallow clone but does not amputate the history.
    """
    if (spec.checkout / ".git").exists():
        print(f"[{spec.name}] checkout exists, skipping clone")
        return None
    spec.checkout.parent.mkdir(parents=True, exist_ok=True)
    result = run(
        [
            "git",
            "clone",
            "--filter=blob:none",
            "--no-checkout",
            spec.url,
            str(spec.checkout),
        ],
        cwd=CORPUS_DIR,
        timeout_s=1800,
        log_name=f"{spec.name}_clone",
    )
    if not result.ok:
        return result
    return run(
        ["git", "checkout", "--detach", spec.sha],
        cwd=spec.checkout,
        timeout_s=1800,
        log_name=f"{spec.name}_checkout",
    )


def make_venv(spec: RepoSpec) -> Ran | None:
    if (spec.bin / "python").exists():
        print(f"[{spec.name}] venv exists, skipping")
        return None
    interpreter = shutil.which(f"python{spec.python}") or sys.executable
    return run(
        [interpreter, "-m", "venv", str(spec.venv)],
        cwd=CORPUS_DIR,
        timeout_s=600,
        log_name=f"{spec.name}_venv",
    )


def install(spec: RepoSpec) -> list[Ran]:
    """Run the repo's pinned install commands, plus the tools the baseline needs."""
    env = venv_env(spec)
    commands = [
        "python -m pip install --upgrade pip",
        *spec.install,
        # -n auto is part of the *optimised* baseline (SPEC B.9), so xdist has
        # to be present even when the project does not use it itself.
        "python -m pip install pytest-xdist",
    ]
    results: list[Ran] = []
    for index, command in enumerate(commands):
        print(f"[{spec.name}] $ {command}")
        result = run(
            shlex.split(command),
            cwd=spec.checkout,
            env=env,
            timeout_s=1800,
            log_name=f"{spec.name}_install_{index}",
        )
        results.append(result)
        if not result.ok:
            print(f"[{spec.name}] install step failed (exit {result.exit_code})")
            break
    return results


def prepare(spec: RepoSpec) -> bool:
    """Clone, create the venv, install. Returns True when the repo is runnable."""
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)
    for step in (clone, make_venv):
        result = step(spec)
        if result is not None and not result.ok:
            print(f"[{spec.name}] {step.__name__} failed:\n{result.stderr[-2000:]}")
            return False
    installs = install(spec)
    if not all(r.ok for r in installs):
        return False

    # A zero exit from pip is not evidence the suite runs. attrs, for one,
    # declares its test dependencies as a PEP 735 dependency-group, so
    # `pip install -e ".[tests]"` installs nothing and still exits 0. The only
    # honest definition of "prepared" is "pytest can collect the suite".
    count, result = collect_tests(spec)
    if result.exit_code != EXIT_OK or not count:
        print(
            f"[{spec.name}] prepared but collection failed "
            f"(exit {result.exit_code}, tests={count}):\n"
            f"{(result.stdout + result.stderr)[-1500:]}"
        )
        return False
    print(f"[{spec.name}] prepared: {count} tests collectable")
    return True


# --------------------------------------------------------------------------
# measure
# --------------------------------------------------------------------------

COLLECTED_RE = re.compile(r"(\d+)\s+tests?\s+collected")
PER_FILE_RE = re.compile(r"^\S+\.py: (\d+)$", re.MULTILINE)


def collect_tests(
    spec: RepoSpec, timeout_s: int = DEFAULT_SUITE_TIMEOUT_S
) -> tuple[int | None, Ran]:
    """Count collectable tests without running them."""
    # No extra -q here: suite_args already carries one, and a second turns it
    # into -qq, which replaces the "N tests collected" summary with per-file
    # counts. Both forms are parsed below regardless.
    result = run(
        [
            str(spec.bin / "pytest"),
            *spec.suite_args,
            *spec.suite_paths,
            "--collect-only",
        ],
        cwd=spec.checkout,
        env=venv_env(spec),
        timeout_s=timeout_s,
        log_name=f"{spec.name}_collect",
    )
    match = COLLECTED_RE.search(result.stdout)
    if match:
        return int(match.group(1)), result
    per_file = PER_FILE_RE.findall(result.stdout)  # the -qq form
    if per_file:
        return sum(int(n) for n in per_file), result
    nodeids = [line for line in result.stdout.splitlines() if "::" in line]
    return (len(nodeids) or None), result


def time_suite(
    spec: RepoSpec,
    *,
    runs: int,
    warmup: int,
    jobs: str | None,
    timeout_s: int = DEFAULT_SUITE_TIMEOUT_S,
) -> dict[str, Any]:
    """Time the full suite `runs` times. `jobs` is the -n value, or None for serial."""
    extra = ["-n", jobs] if jobs else []
    command = [str(spec.bin / "pytest"), *spec.suite_args, *spec.suite_paths, *extra]
    label = f"n{jobs}" if jobs else "serial"
    env = venv_env(spec)

    def abandoned(completed: int, durations: list[float]) -> dict[str, Any]:
        """A timed-out mode is red, not slow. Record it and stop."""
        print(f"[{spec.name}] {label} timed out after {timeout_s}s — abandoning")
        return {
            "command": shlex.join(command),
            "timed_out": True,
            "timeout_s": timeout_s,
            "runs": completed,
            "warmup_runs": warmup,
            "durations_s": [round(d, 3) for d in durations],
            "median_s": round(statistics.median(durations), 3) if durations else None,
            "all_green": False,
        }

    for index in range(warmup):
        print(f"[{spec.name}] warmup {index + 1}/{warmup} ({label})")
        warm = run(
            command,
            cwd=spec.checkout,
            env=env,
            timeout_s=timeout_s,
            log_name=f"{spec.name}_{label}_warmup{index}",
        )
        if warm.timed_out:
            return abandoned(0, [])

    durations: list[float] = []
    exit_codes: list[int] = []
    for index in range(runs):
        result = run(
            command,
            cwd=spec.checkout,
            env=env,
            timeout_s=timeout_s,
            log_name=f"{spec.name}_{label}_run{index}",
        )
        if result.timed_out:
            return abandoned(index, durations)
        durations.append(result.duration_s)
        exit_codes.append(-1 if result.timed_out else result.exit_code)
        print(
            f"[{spec.name}] {label} run {index + 1}/{runs}: "
            f"{result.duration_s:.2f}s exit={exit_codes[-1]}"
        )

    quartiles = statistics.quantiles(durations, n=4) if len(durations) >= 2 else []
    return {
        "command": shlex.join(command),
        "runs": runs,
        "warmup_runs": warmup,
        "durations_s": [round(d, 3) for d in durations],
        "median_s": round(statistics.median(durations), 3),
        "min_s": round(min(durations), 3),
        "max_s": round(max(durations), 3),
        "iqr_s": [round(quartiles[0], 3), round(quartiles[2], 3)]
        if quartiles
        else None,
        "timed_out": False,
        "timeout_s": timeout_s,
        "exit_codes": exit_codes,
        "all_green": all(code == EXIT_OK for code in exit_codes),
    }


def machine_info() -> dict[str, Any]:
    """Everything needed to say which machine a number came from."""

    def sysctl(key: str) -> str:
        try:
            return subprocess.run(  # noqa: S603
                ["sysctl", "-n", key], capture_output=True, text=True, check=True
            ).stdout.strip()
        except (subprocess.SubprocessError, FileNotFoundError):
            return "unknown"

    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu": sysctl("machdep.cpu.brand_string")
        if sys.platform == "darwin"
        else "unknown",
        "cpu_count": os.cpu_count(),
        "memory_bytes": int(sysctl("hw.memsize") or 0)
        if sys.platform == "darwin"
        else None,
        "python": platform.python_version(),
    }


def baseline(
    spec: RepoSpec,
    *,
    runs: int,
    warmup: int,
    serial: bool,
    parallel: bool = True,
    timeout_s: int = DEFAULT_SUITE_TIMEOUT_S,
) -> dict[str, Any]:
    """Measure the optimised baseline and write it to eval/results/."""
    count, collect_result = collect_tests(spec, timeout_s=timeout_s)
    print(f"[{spec.name}] collected {count} tests (exit {collect_result.exit_code})")

    measurements: dict[str, Any] = {}
    if parallel:
        measurements["xdist_auto"] = time_suite(
            spec, runs=runs, warmup=warmup, jobs="auto", timeout_s=timeout_s
        )
    # No point timing the slower mode when the parallel one already timed out.
    if serial and not measurements.get("xdist_auto", {}).get("timed_out"):
        measurements["serial"] = time_suite(
            spec, runs=runs, warmup=warmup, jobs=None, timeout_s=timeout_s
        )

    green = (
        all(m["all_green"] for m in measurements.values()) if measurements else False
    )
    payload: dict[str, Any] = {
        "schema": RESULT_SCHEMA,
        "experiment": "baseline",
        "generated_by": "eval/corpus.py",
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "repo": spec.name,
        "url": spec.url,
        "sha": spec.sha,
        "pinned_at": spec.pinned_at,
        "suite_args": spec.suite_args,
        "suite_paths": spec.suite_paths,
        "env": spec.env,
        "install": spec.install,
        "machine": machine_info(),
        "collect": {
            "tests": count,
            "exit_code": collect_result.exit_code,
            "duration_s": round(collect_result.duration_s, 3),
        },
        "measurements": measurements,
        "green": green,
    }

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    date = datetime.now(UTC).date().isoformat()
    out = RESULTS_DIR / f"baseline_{spec.name}_{date}.json"
    out.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"[{spec.name}] wrote {out.relative_to(ROOT)}")
    return payload


def latest_baselines() -> list[dict[str, Any]]:
    """Every committed baseline, newest file per repo."""
    newest: dict[str, tuple[str, dict[str, Any]]] = {}
    for path in sorted(RESULTS_DIR.glob("baseline_*.json")):
        payload = json.loads(path.read_text())
        repo = payload["repo"]
        if repo not in newest or path.name > newest[repo][0]:
            newest[repo] = (path.name, payload)
    return [payload for _, payload in newest.values()]


def table() -> None:
    """Print the D2 comparison table from committed results only."""
    rows = latest_baselines()
    if not rows:
        print("no baselines in eval/results/ yet")
        return
    header = (
        "| repo | tests | green | -n auto median (s) | IQR | serial median (s) | "
        "speedup from -n auto | sha |"
    )
    print(header)
    print("|---|---|---|---|---|---|---|---|")
    for payload in sorted(rows, key=lambda r: r["repo"]):
        parallel = payload["measurements"].get("xdist_auto")
        serial = payload["measurements"].get("serial")
        iqr = parallel.get("iqr_s") if parallel else None
        speedup = (
            f"{serial['median_s'] / parallel['median_s']:.2f}x"
            if parallel and serial and parallel["median_s"]
            else "n/a"
        )
        print(
            f"| {payload['repo']} "
            f"| {payload['collect']['tests']} "
            f"| {'yes' if payload['green'] else 'NO'} "
            f"| {parallel['median_s'] if parallel else 'n/a'} "
            f"| {f'{iqr[0]}-{iqr[1]}' if iqr else 'n/a'} "
            f"| {serial['median_s'] if serial else 'n/a'} "
            f"| {speedup} "
            f"| {payload['sha'][:12]} |"
        )


def clean(spec: RepoSpec) -> None:
    target = CORPUS_DIR / spec.name
    if target.exists():
        shutil.rmtree(target)
        print(f"[{spec.name}] removed {target.relative_to(ROOT)}")


# --------------------------------------------------------------------------
# cli
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="show the pinned corpus and its status")
    sub.add_parser("table", help="print the comparison table from committed results")

    prepare_parser = sub.add_parser("prepare", help="clone, venv, install")
    prepare_parser.add_argument("--repo", required=True)

    baseline_parser = sub.add_parser("baseline", help="measure the optimised baseline")
    baseline_parser.add_argument("--repo", required=True)
    baseline_parser.add_argument("--runs", type=int, default=5)
    baseline_parser.add_argument("--warmup", type=int, default=1)
    baseline_parser.add_argument(
        "--no-serial", action="store_true", help="skip the unparallelised timing"
    )
    baseline_parser.add_argument(
        "--no-parallel",
        action="store_true",
        help="skip the -n auto timing (for suites that deadlock under xdist)",
    )
    baseline_parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_SUITE_TIMEOUT_S,
        help=f"abandon a suite run after N seconds (default {DEFAULT_SUITE_TIMEOUT_S})",
    )

    clean_parser = sub.add_parser("clean", help="delete a checkout and its venv")
    clean_parser.add_argument("--repo", required=True)

    args = parser.parse_args(argv)

    if args.command == "list":
        for spec in load_corpus():
            ready = "ready" if (spec.bin / "pytest").exists() else "not prepared"
            print(f"{spec.name:8} {spec.status:10} {spec.sha[:12]}  {ready}")
        return 0

    if args.command == "table":
        table()
        return 0

    spec = find_spec(args.repo)

    if args.command == "prepare":
        return 0 if prepare(spec) else 1
    if args.command == "baseline":
        payload = baseline(
            spec,
            runs=args.runs,
            warmup=args.warmup,
            serial=not args.no_serial,
            parallel=not args.no_parallel,
            timeout_s=args.timeout,
        )
        return 0 if payload["green"] else 1
    if args.command == "clean":
        clean(spec)
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
