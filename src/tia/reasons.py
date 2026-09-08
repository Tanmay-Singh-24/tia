"""Fallback reason codes — the single source of truth.

Every decision tia makes carries one of these. They are the vocabulary of
`--explain`, of the fallback-frequency metric, and of docs/SAFETY.md. Nothing
in this project may abandon selection without naming one.
"""

from __future__ import annotations

from enum import StrEnum


class Reason(StrEnum):
    """Why a test was selected, or why selection was abandoned."""

    # --- selection succeeded ------------------------------------------------
    SELECTED = "SELECTED"
    TEST_CHANGED = "TEST_CHANGED"
    CONFTEST_CHANGED = "CONFTEST_CHANGED"
    PACKAGE_INIT = "PACKAGE_INIT"
    INSERTION_NO_HISTORY = "INSERTION_NO_HISTORY"

    # --- selection abandoned: run everything --------------------------------
    UNMAPPED_FILE = "UNMAPPED_FILE"
    BUILD_CONFIG_CHANGED = "BUILD_CONFIG_CHANGED"
    DEPENDENCY_CHANGED = "DEPENDENCY_CHANGED"
    NON_SOURCE_ASSET = "NON_SOURCE_ASSET"
    USER_CONFIGURED = "USER_CONFIGURED"
    IMPORT_TIME_LINE = "IMPORT_TIME_LINE"
    MAP_STALE = "MAP_STALE"
    NO_MAP = "NO_MAP"
    CLASSIFIER_ERROR = "CLASSIFIER_ERROR"
    NO_CHANGES = "NO_CHANGES"

    @property
    def is_fallback(self) -> bool:
        """Does this reason mean the whole suite runs?"""
        return self in FALLBACK_REASONS

    @property
    def description(self) -> str:
        return DESCRIPTIONS[self]


FALLBACK_REASONS: frozenset[Reason] = frozenset(
    {
        Reason.UNMAPPED_FILE,
        Reason.BUILD_CONFIG_CHANGED,
        Reason.DEPENDENCY_CHANGED,
        Reason.NON_SOURCE_ASSET,
        Reason.USER_CONFIGURED,
        Reason.IMPORT_TIME_LINE,
        Reason.MAP_STALE,
        Reason.NO_MAP,
        Reason.CLASSIFIER_ERROR,
    }
)

DESCRIPTIONS: dict[Reason, str] = {
    Reason.SELECTED: (
        "Project source present in a fresh map: tests were chosen by line."
    ),
    Reason.TEST_CHANGED: (
        "A test file changed. Its tests always run, without consulting the map, "
        "because a new or edited test has never been observed."
    ),
    Reason.CONFTEST_CHANGED: (
        "A conftest.py changed. Every test at or below that directory runs, "
        "because fixtures defined there can affect any of them."
    ),
    Reason.PACKAGE_INIT: (
        "An __init__.py changed. Selection widens to every test touching the "
        "package, never line by line, because import side effects are not local."
    ),
    Reason.INSERTION_NO_HISTORY: (
        "Lines were inserted. Inserted lines have no old-side coordinates and "
        "cannot be looked up, so selection widens to the whole file."
    ),
    Reason.UNMAPPED_FILE: (
        "The changed file is absent from the map: it is new, or no test has "
        "ever executed it. Nothing is known, so everything runs."
    ),
    Reason.BUILD_CONFIG_CHANGED: (
        "Build or test configuration changed. It can alter how every test runs."
    ),
    Reason.DEPENDENCY_CHANGED: (
        "A dependency declaration changed. Third-party code is not in the map "
        "and an upgrade can break anything."
    ),
    Reason.NON_SOURCE_ASSET: (
        "A data file, fixture, template or asset changed. These never appear in "
        "a line-level map yet any test may read them."
    ),
    Reason.USER_CONFIGURED: ("The path matches an always_full glob in .tia.toml."),
    Reason.IMPORT_TIME_LINE: (
        "The changed line only ever executed at import time, so it belongs to "
        "no single test. Attributing it to the tests that touched the file "
        "would be unsound, because a test can import a module without executing "
        "any other line in it."
    ),
    Reason.MAP_STALE: (
        "The map was built at a commit that is not an ancestor of the change "
        "being selected, so its line numbers may not describe this code."
    ),
    Reason.NO_MAP: "No map exists. The first run always executes everything.",
    Reason.CLASSIFIER_ERROR: (
        "The classifier raised. An error in tia must never mean fewer tests."
    ),
    Reason.NO_CHANGES: "Nothing changed against the base revision.",
}
