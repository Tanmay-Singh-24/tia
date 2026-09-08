"""Orchestration: diff -> classify -> query the map -> decision.

This is where the pieces meet. It produces a `Decision`, which is the object
`tia select`, `tia run` and the pytest plugin all consume, and which serialises
straight to JSON for the evaluation harness.

The invariant this module exists to uphold: if anything at all is uncertain,
`Decision.full_suite` is True and every test runs.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
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
    is_ancestor,
    resolve_base,
)
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

    @property
    def primary_reason(self) -> Reason:
        """The single reason to print on a banner."""
        if self.fallback_reasons:
            return self.fallback_reasons[0]
        if not self.verdicts:
            return Reason.NO_CHANGES
        return self.verdicts[0].reason

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
            "selected": sorted(self.selected),
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


def fallback(reason: Reason, **kwargs: Any) -> Decision:
    """Abandon selection. Always says why."""
    return Decision(full_suite=True, fallback_reasons=[reason], **kwargs)


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
        resolved_base = base or resolve_base(repo_root, config.upstream)
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
    if map_commit and not is_ancestor(repo_root, map_commit, resolved_base):
        return fallback(Reason.MAP_STALE, **common)

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
        changes, mapped_files=mapped, always_full=config.always_full
    )

    fallbacks = [v.reason for v in verdicts if v.is_fallback]
    if fallbacks:
        decision = Decision(full_suite=True, verdicts=verdicts, **common)
        decision.fallback_reasons = fallbacks
        return decision

    selected: set[str] = set()
    explanations: list[Explanation] = []
    for verdict in verdicts:
        _apply(conn, verdict, selected, explanations)

    return Decision(
        full_suite=False,
        selected=selected,
        verdicts=verdicts,
        explanations=explanations,
        **common,
    )


def _apply(
    conn: sqlite3.Connection,
    verdict: Verdict,
    selected: set[str],
    explanations: list[Explanation],
) -> None:
    """Turn one non-fallback verdict into tests, recording why each was chosen."""
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
    else:  # Reason.SELECTED
        found = db.tests_for_lines(conn, change.lookup_path, change.old_lines)

    for nodeid in sorted(found - selected):
        explanations.append(
            Explanation(
                nodeid=nodeid,
                reason=reason,
                source_path=change.lookup_path,
                lines=sorted(change.old_lines)[:10],
            )
        )
    selected |= found
