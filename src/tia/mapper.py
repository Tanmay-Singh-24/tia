"""Builds the line-to-test map from coverage.py dynamic contexts.

Phase 1 of SPEC B.2: run the suite once under instrumentation, then invert what
coverage recorded. For every source line we store the set of tests that
executed it.

The subtleties here are the ones the D-0007 spike measured, not guesses:
context strings carry a `|run` / `|setup` / `|teardown` phase suffix, there is
one empty context for lines executed at import time, and measured paths are
absolute and must be made repo-relative.
"""

from __future__ import annotations

import ast
import hashlib
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from coverage import CoverageData

from tia import db
from tia.config import Config

# The context coverage.py uses for lines executed outside any test.
IMPORT_TIME_CONTEXT = ""


@dataclass
class BuildResult:
    """What a build did, for reporting and for DECISIONS entries."""

    tests: int = 0
    files: int = 0
    coverage_rows: int = 0
    import_time_lines: int = 0
    suite_duration_s: float = 0.0
    build_duration_s: float = 0.0
    suite_exit_code: int = 0
    db_bytes: int = 0
    skipped_contexts: list[str] = field(default_factory=list)


def normalise_path(measured: str, repo_root: Path) -> str | None:
    """Absolute measured path -> POSIX path relative to the repo root.

    Returns None for anything outside the repository: site-packages, the
    standard library, a temporary directory. Those are real coverage but they
    are not code this repository's diffs can change, so they have no place in
    the map.
    """
    try:
        resolved = Path(measured).resolve()
    except OSError:
        return None
    try:
        return resolved.relative_to(repo_root).as_posix()
    except ValueError:
        return None


def split_context(context: str) -> tuple[str, str] | None:
    """`tests/t.py::test_x|run` -> ('tests/t.py::test_x', 'run').

    Returns None for the import-time context, which belongs to no test.
    Setup and teardown are kept: a fixture touching a line is a genuine
    dependency, and dropping them would be a silent miss waiting to happen.
    """
    if context == IMPORT_TIME_CONTEXT:
        return None
    nodeid, _, phase = context.rpartition("|")
    if not nodeid:
        # A context with no phase suffix. Treat the whole string as the nodeid.
        return context, ""
    return nodeid, phase


def file_kind(path: str) -> str:
    """Classify a repo-relative path for the `file` table."""
    name = Path(path).name
    parts = Path(path).parts
    if name.startswith("test_") or name.endswith("_test.py") or "tests" in parts:
        return db.KIND_TEST
    if path.endswith(".py"):
        return db.KIND_SOURCE
    if name in {
        "pyproject.toml",
        "setup.cfg",
        "setup.py",
        "tox.ini",
        "pytest.ini",
        ".coveragerc",
    }:
        return db.KIND_CONFIG
    return db.KIND_OTHER


def test_file_of(nodeid: str) -> str:
    """The file part of a pytest nodeid."""
    return nodeid.split("::", 1)[0]


def fingerprint_test(repo_root: Path, nodeid: str, cache: dict[str, str]) -> str:
    """sha256 of the test function's source, falling back to the whole file.

    Used later to notice that a test changed without the file's line numbers
    moving. Parsing is best-effort: a nodeid we cannot resolve to a function
    (parametrised ids, generated tests, odd collection) hashes its file
    instead, which is coarser but never wrong in the unsafe direction.
    """
    path = test_file_of(nodeid)
    if path in cache:
        file_hash = cache[path]
    else:
        full = repo_root / path
        try:
            source = full.read_bytes()
        except OSError:
            cache[path] = ""
            return ""
        file_hash = hashlib.sha256(source).hexdigest()
        cache[path] = file_hash

    # Strip the parametrisation and locate the function in the AST.
    remainder = nodeid.split("::", 1)[1] if "::" in nodeid else ""
    names = [part.split("[", 1)[0] for part in remainder.split("::") if part]
    if not names:
        return file_hash
    try:
        tree = ast.parse((repo_root / path).read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return file_hash

    node: ast.AST = tree
    for name in names:
        found = None
        for child in ast.iter_child_nodes(node):
            if (
                isinstance(child, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
                and child.name == name
            ):
                found = child
                break
        if found is None:
            return file_hash
        node = found
    segment = ast.dump(node)
    return hashlib.sha256(segment.encode()).hexdigest()


def coverage_command(config: Config, jobs: int | None) -> list[str]:
    """The instrumented suite command.

    `--cov-context=test` is what produces nodeid-shaped contexts (D-0007).
    `--cov-report=` suppresses report generation we do not need.
    """
    command = shlex.split(config.suite)
    # Run pytest through the interpreter tia is running under. Relying on PATH
    # picks up whatever pytest happens to be there — or none at all when tia is
    # invoked by absolute path — and the map must describe *this* environment.
    if command and command[0] == "pytest":
        command = [sys.executable, "-m", "pytest", *command[1:]]
    for package in config.packages:
        command.append(f"--cov={package}")
    if not config.packages:
        command.append("--cov=.")
    command += ["--cov-context=test", "--cov-report="]
    if jobs:
        command += ["-n", str(jobs)]
    return command


def run_suite(
    repo_root: Path, config: Config, jobs: int | None
) -> tuple[int, float, str]:
    """Run the instrumented suite. Returns (exit code, seconds, command)."""
    command = coverage_command(config, jobs)
    started = time.perf_counter()
    proc = subprocess.run(command, cwd=repo_root, check=False)  # noqa: S603
    return proc.returncode, time.perf_counter() - started, shlex.join(command)


def build(
    repo_root: Path,
    config: Config,
    *,
    jobs: int | None = None,
    commit: str = "",
    coverage_file: Path | None = None,
    run: bool = True,
) -> BuildResult:
    """Run the instrumented suite and write the map. This is `tia build`."""
    build_started = time.perf_counter()
    result = BuildResult()
    command = shlex.join(coverage_command(config, jobs))

    if run:
        result.suite_exit_code, result.suite_duration_s, command = run_suite(
            repo_root, config, jobs
        )

    data = CoverageData(basename=str(coverage_file or (repo_root / ".coverage")))
    data.read()

    path_of = coverage_file or (repo_root / ".coverage")
    if not data.measured_files():
        raise RuntimeError(
            f"no coverage data in {path_of}. Did the suite run with --cov-context=test?"
        )

    db_path = db.map_path(repo_root)
    db_path.unlink(missing_ok=True)
    conn = db.connect(db_path, create=True)
    fingerprints: dict[str, str] = {}
    test_ids: dict[str, int] = {}
    file_ids: dict[str, int] = {}

    def test_id_for(nodeid: str) -> int:
        if nodeid in test_ids:
            return test_ids[nodeid]
        test_path = test_file_of(nodeid)
        if test_path not in file_ids:
            file_ids[test_path] = db.upsert_file(conn, test_path, db.KIND_TEST)
        identifier = db.insert_test(
            conn,
            nodeid,
            file_ids[test_path],
            fingerprint_test(repo_root, nodeid, fingerprints),
        )
        test_ids[nodeid] = identifier
        return identifier

    with db.bulk_write(conn):
        for measured in data.measured_files():
            relative = normalise_path(measured, repo_root)
            if relative is None:
                continue  # outside the repo: not something a diff can change
            file_id = file_ids.setdefault(
                relative, db.upsert_file(conn, relative, file_kind(relative))
            )
            rows: list[tuple[int, int, int]] = []
            import_time: list[tuple[int, int]] = []
            for lineno, contexts in data.contexts_by_lineno(measured).items():
                for context in contexts:
                    parts = split_context(context)
                    if parts is None:
                        # Executed at import time, outside any test. Recorded as
                        # a line, not attributed to a test: the tests that
                        # depend on it were never observed running it. A change
                        # to such a line falls back (D-0007, D-0009).
                        import_time.append((file_id, lineno))
                        result.import_time_lines += 1
                        continue
                    rows.append((file_id, lineno, test_id_for(parts[0])))
            if rows:
                db.insert_coverage(conn, rows)
                result.coverage_rows += len(rows)
            if import_time:
                db.insert_import_time_lines(conn, import_time)

        result.build_duration_s = time.perf_counter() - build_started
        for key, value in {
            "schema_version": str(db.SCHEMA_VERSION),
            "built_at_commit": commit,
            "repo_root": str(repo_root),
            "built_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "suite_command": command,
            "total_tests": str(len(test_ids)),
            "build_duration_s": f"{result.build_duration_s:.3f}",
            "suite_duration_s": f"{result.suite_duration_s:.3f}",
        }.items():
            db.set_meta(conn, key, value)

    counts = db.stats(conn, db_path)
    result.tests = int(counts["tests"])
    result.files = int(counts["files"])
    result.db_bytes = int(counts["size_bytes"] or 0)
    conn.close()
    return result
