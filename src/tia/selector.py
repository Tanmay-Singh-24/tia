"""Orchestration: diff -> classify -> query the map -> decision.

This is where the pieces meet. It produces a `Decision`, which is the object
`tia select`, `tia run` and the pytest plugin all consume, and which serialises
straight to JSON for the evaluation harness.

The invariant this module exists to uphold: if anything at all is uncertain,
`Decision.full_suite` is True and every test runs.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, TypedDict

from tia import db
from tia.classifier import Verdict, classify_all
from tia.config import Config
from tia.diff import (
    FileChange,
    GitError,
    changed_lines,
    head_commit,
    resolve_base,
)
from tia.environment import differences, fingerprint
from tia.reasons import Reason


class Context(TypedDict):
    """The fields every Decision carries, whatever the outcome."""

    base: str
    head: str
    map_commit: str
    total_tests: int


@dataclass
class Explanation:
    """Why one test is in the selection: the chain a reviewer can follow."""

    nodeid: str
    reason: Reason
    source_path: str
    lines: list[int] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "nodeid": self.nodeid,
            "reason": self.reason.value,
            "source": self.source_path,
            "lines": self.lines,
        }


def test_function(nodeid: str) -> str:
    """A nodeid without its parametrisation: `t.py::test_x[1-a]` -> `t.py::test_x`.

    The parameter id begins at the first `[` after the file part. Class and
    function names cannot contain `[`, but parameter ids can contain `[` and
    `::`, so the cut is made from the left of what follows the file.
    """
    file_part, sep, rest = nodeid.partition("::")
    cut = rest.find("[")
    return file_part + sep + (rest[:cut] if cut >= 0 else rest)


@dataclass
class Decision:
    """The complete, inspectable outcome of a selection."""

    full_suite: bool
    selected: set[str] = field(default_factory=set)
    verdicts: list[Verdict] = field(default_factory=list)
    explanations: list[Explanation] = field(default_factory=list)
    base: str = ""
    head: str = ""
    map_commit: str = ""
    total_tests: int = 0
    fallback_reasons: list[Reason] = field(default_factory=list)
    detail: str = ""
    """For a whole-suite fallback, what specifically caused it."""

    @property
    def primary_reason(self) -> Reason:
        """The single reason to print on a banner."""
        if self.fallback_reasons:
            return self.fallback_reasons[0]
        if not self.verdicts:
            return Reason.NO_CHANGES
        return self.verdicts[0].reason

    @property
    def forced_paths(self) -> list[str]:
        """Test files and directories that run in full, whatever the map knows.

        A test written in this very change has never been observed, so the map
        cannot name it. Selecting a changed test file by the nodeids the map
        already holds silently dropped every new test in it — the test most
        likely to catch the change it was written for (D-0017). These paths
        are run whole instead.
        """
        if self.full_suite:
            return []
        paths: set[str] = set()
        for verdict in self.verdicts:
            if verdict.reason is Reason.TEST_CHANGED and verdict.change.status != "D":
                paths.add(verdict.change.path)
            elif verdict.reason is Reason.CONFTEST_CHANGED:
                paths.add(verdict.detail or ".")
        return sorted(paths)

    def covers(self, path: str) -> bool:
        """Is this repo-relative file inside a forced path?"""
        for forced in self.forced_paths:
            if forced == ".":
                return True
            if path == forced or path.startswith(forced.rstrip("/") + "/"):
                return True
        return False

    @property
    def changed_paths(self) -> set[str]:
        """Every file this change touches, new-side paths."""
        return {verdict.change.path for verdict in self.verdicts}

    @property
    def selected_functions(self) -> set[str]:
        return {test_function(nodeid) for nodeid in self.selected}

    def wants(self, nodeid: str, path: str | None = None) -> bool:
        """Should this collected test run?

        By nodeid; by test function, so a parametrisation the map has never
        seen still runs when another parametrisation of it was selected (D-0018);
        or by lying inside a forced path. `path` is the test's repo-relative
        file when the caller knows it better than the nodeid does.
        """
        if self.full_suite:
            return True
        if nodeid in self.selected or test_function(nodeid) in self.selected_functions:
            return True
        return self.covers(path or nodeid.split("::")[0])

    def pytest_args(self) -> list[str]:
        """What to hand pytest: forced paths whole, then each selected test
        function — not each parametrisation, so new ones run too."""
        forced = self.forced_paths
        functions = {
            test_function(nodeid)
            for nodeid in self.selected
            if not self.covers(nodeid.split("::")[0])
        }
        return [*forced, *sorted(functions)]

    def counts_by_reason(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for verdict in self.verdicts:
            counts[verdict.reason.value] = counts.get(verdict.reason.value, 0) + 1
        return counts

    def as_dict(self) -> dict[str, Any]:
        return {
            "full_suite": self.full_suite,
            "selected_count": len(self.selected),
            "total_tests": self.total_tests,
            "selection_ratio": (
                round(len(self.selected) / self.total_tests, 6)
                if self.total_tests and not self.full_suite
                else 1.0
            ),
            "primary_reason": self.primary_reason.value,
            "fallback_reasons": [r.value for r in self.fallback_reasons],
            "counts_by_reason": self.counts_by_reason(),
            "base": self.base,
            "head": self.head,
            "map_commit": self.map_commit,
            "detail": self.detail,
            "selected": sorted(self.selected),
            "forced_paths": self.forced_paths,
            "pytest_args": self.pytest_args(),
            "changes": [
                {
                    "path": v.change.path,
                    "old_path": v.change.old_path,
                    "status": v.change.status,
                    "reason": v.reason.value,
                    "scope": v.scope,
                    "detail": v.detail,
                    "old_lines": sorted(v.change.old_lines),
                    "insertions": v.change.insertions,
                }
                for v in self.verdicts
            ],
            "explanations": [e.as_dict() for e in self.explanations],
        }


def fallback(reason: Reason, detail: str = "", **kwargs: Any) -> Decision:
    """Abandon selection. Always says why."""
    return Decision(full_suite=True, fallback_reasons=[reason], detail=detail, **kwargs)


def select(
    repo_root: Path,
    config: Config,
    *,
    base: str | None = None,
    include_uncommitted: bool = True,
) -> Decision:
    """Decide which tests to run for the current change.

    Every early return here is a fallback with a reason code. There is no path
    out of this function that runs fewer tests without having proved it may.
    """
    map_file = db.map_path(repo_root)
    if not map_file.exists():
        return fallback(Reason.NO_MAP)

    try:
        conn = db.connect(map_file)
        db.migrate(conn)
    except (sqlite3.DatabaseError, ValueError, FileNotFoundError):
        return fallback(Reason.NO_MAP)

    try:
        return _select_with_map(
            conn,
            repo_root,
            config,
            base=base,
            include_uncommitted=include_uncommitted,
        )
    finally:
        conn.close()


def _select_with_map(
    conn: sqlite3.Connection,
    repo_root: Path,
    config: Config,
    *,
    base: str | None,
    include_uncommitted: bool,
) -> Decision:
    map_commit = db.get_meta(conn, "built_at_commit") or ""
    total_tests = len(db.all_test_nodeids(conn))

    try:
        head = head_commit(repo_root)
        # Always the branch point, whether the base came from config or from
        # --base/--tia-base. Diffing against a ref's tip would describe every
        # upstream commit this branch lacks, not this branch's change.
        resolved_base = resolve_base(repo_root, base or config.upstream)
    except GitError:
        return fallback(Reason.NO_MAP, map_commit=map_commit, total_tests=total_tests)

    common: Context = {
        "base": resolved_base,
        "head": head,
        "map_commit": map_commit,
        "total_tests": total_tests,
    }

    # The map speaks the line numbers of the commit it was built at. If that
    # commit is not behind the change, its coordinates may not describe this
    # code at all.
    # The map speaks the line numbers of exactly one commit. It is trusted only
    # when that commit IS the branch point. "Is an ancestor of it" is not
    # enough: if main moved on in between, the same line number names
    # different code, and the selection is confidently wrong (D-0016).
    if map_commit and map_commit != resolved_base:
        return fallback(Reason.MAP_STALE, **common)

    # The map is equally specific to the environment it was built in: the code
    # paths coverage recorded depend on the Python version, the platform and
    # the installed packages (D-0019).
    recorded = db.get_meta(conn, "environment")
    changed = differences(
        json.loads(recorded) if recorded else None, fingerprint(repo_root)
    )
    if changed:
        return fallback(
            Reason.ENVIRONMENT_CHANGED, detail="; ".join(changed[:3]), **common
        )

    try:
        changes = changed_lines(
            repo_root, resolved_base, include_uncommitted=include_uncommitted
        )
    except GitError:
        return fallback(Reason.CLASSIFIER_ERROR, **common)

    if not changes:
        return Decision(full_suite=False, **common)

    mapped = frozenset(db.mapped_source_files(conn))
    verdicts = classify_all(
        changes,
        mapped_files=mapped,
        always_full=config.always_full,
        import_time_lookup=lambda path: db.import_time_lines(conn, path),
        has_import_graph=config.use_import_graph and db.has_import_graph(conn),
    )

    fallbacks = [v.reason for v in verdicts if v.is_fallback]
    if fallbacks:
        decision = Decision(full_suite=True, verdicts=verdicts, **common)
        decision.fallback_reasons = fallbacks
        return decision

    selected: set[str] = set()
    explanations: list[Explanation] = []
    # _apply may amend a verdict — widening an empty line lookup to the file,
    # or abandoning an oversized import closure. The amended verdicts are what
    # the decision reports, so the reason a user sees is the reason that ran.
    resolved = [
        _apply(conn, verdict, selected, explanations, config, total_tests)
        for verdict in verdicts
    ]

    late_fallbacks = [v.reason for v in resolved if v.is_fallback]
    if late_fallbacks:
        decision = Decision(full_suite=True, verdicts=resolved, **common)
        decision.fallback_reasons = late_fallbacks
        return decision

    return Decision(
        full_suite=False,
        selected=selected,
        verdicts=resolved,
        explanations=explanations,
        **common,
    )


def _apply(
    conn: sqlite3.Connection,
    verdict: Verdict,
    selected: set[str],
    explanations: list[Explanation],
    config: Config,
    total_tests: int,
) -> Verdict:
    """Turn one non-fallback verdict into tests, recording why each was chosen.

    Returns the verdict that actually applied, which may differ from the one
    passed in: an empty line-level lookup widens to the file, and an import
    closure that covers too much of the suite is abandoned.
    """
    change: FileChange = verdict.change
    reason = verdict.reason
    found: set[str]

    if reason == Reason.TEST_CHANGED:
        # Tests in a changed test file always run, whether or not the map has
        # seen them. Tests the map does not know are added by nodeid-free
        # collection at run time; here we contribute what the map does know.
        found = db.tests_in_files(conn, [change.path])
    elif reason == Reason.CONFTEST_CHANGED:
        found = db.tests_under_directory(conn, verdict.detail)
    elif reason == Reason.PACKAGE_INIT:
        found = set()
        for path in db.mapped_source_files(conn):
            if path.startswith(verdict.detail.rstrip("/") + "/"):
                found |= db.tests_for_file(conn, path)
    elif reason == Reason.INSERTION_NO_HISTORY:
        found = db.tests_for_file(conn, change.lookup_path)
    elif reason == Reason.IMPORT_CLOSURE:
        # Phase 2: every module that transitively imports the changed file,
        # and every test that touched any of them.
        closure = db.import_closure(conn, change.lookup_path)
        paths = sorted(closure)
        # Two questions, both necessary. `tests_for_file` finds tests that
        # EXECUTED a file, which is the right question for source. It returns
        # nothing for a test file when the project measures coverage for its
        # package only (`--cov=attr`), because then test files have no coverage
        # rows at all — so `tests_in_files` asks the other question, which tests
        # are DEFINED in it. Asking only the first let a defect through: the
        # closure reached tests/test_cmp.py and then found nothing in it.
        # See D-0014.
        found = db.tests_in_files(conn, paths)
        for path in paths:
            found |= db.tests_for_file(conn, path)
        limit = config.closure_max_fraction
        if total_tests and len(found) > limit * total_tests:
            # Selecting most of the suite costs more to compute than it saves,
            # and a closure that large is not meaningfully a selection.
            return Verdict(
                change,
                Reason.CLOSURE_TOO_LARGE,
                "all",
                f"closure covers {len(found)} of {total_tests} tests "
                f"(limit {limit:.0%})",
            )
    else:  # Reason.SELECTED
        found = db.tests_for_lines(conn, change.lookup_path, change.old_lines)
        if not found:
            # An empty line-level lookup means the map has nothing for these
            # particular lines — they are continuation lines, blanks, or part
            # of a statement coverage attributes to its first line. That is
            # ignorance, not proof that no test is affected, so widen to every
            # test that touched the file rather than selecting nothing.
            found = db.tests_for_file(conn, change.lookup_path)
            reason = Reason.LINE_NOT_IN_MAP

    for nodeid in sorted(found - selected):
        explanations.append(
            Explanation(
                nodeid=nodeid,
                reason=reason,
                source_path=change.lookup_path,
                lines=sorted(change.old_lines)[:10],
            )
        )
    if not found and reason not in (Reason.TEST_CHANGED, Reason.CONFTEST_CHANGED):
        # Every selective rule must reach at least one recorded test. An empty
        # answer means the map knows nothing about this change — a package
        # whose files were never measured, a closure of unmeasured modules —
        # and that is ignorance, not proof that nothing needs to run. Changed
        # test files and conftest directories are exempt: they run whole
        # through forced_paths whatever the map holds.
        return replace(
            verdict,
            reason=Reason.UNMAPPED_FILE,
            scope="all",
            detail="no recorded test reaches this change",
        )
    selected |= found
    return verdict if reason is verdict.reason else replace(verdict, reason=reason)
