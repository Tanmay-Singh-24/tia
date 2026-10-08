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
    LINE_NOT_IN_MAP = "LINE_NOT_IN_MAP"
    IMPORT_CLOSURE = "IMPORT_CLOSURE"
    CLOSURE_TOO_LARGE = "CLOSURE_TOO_LARGE"
    MAP_STALE = "MAP_STALE"
    ENVIRONMENT_CHANGED = "ENVIRONMENT_CHANGED"
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
        Reason.CLOSURE_TOO_LARGE,
        Reason.MAP_STALE,
        Reason.ENVIRONMENT_CHANGED,
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
    Reason.IMPORT_CLOSURE: (
        "The changed line executed at import time, which the map cannot "
        "attribute to any test. Rather than surrender the whole suite, the "
        "static import graph names every module that transitively imports this "
        "file, and the tests covering those modules are selected. This sees "
        "`import` statements only: a module loaded by name at run time is "
        "invisible to it, which is why the line-level map is kept as well."
    ),
    Reason.CLOSURE_TOO_LARGE: (
        "The import closure of the changed file covers more of the suite than "
        "the configured limit. Selecting almost everything costs more to "
        "compute than it saves, so the whole suite runs instead."
    ),
    Reason.LINE_NOT_IN_MAP: (
        "The changed line is in a mapped file but the map holds no coverage "
        "for that line itself - it is a continuation line, a blank, or part of "
        "a multi-line statement that coverage attributes elsewhere. An empty "
        "line-level lookup is not evidence that no test is affected, so "
        "selection widens to every test that touched the file."
    ),
    Reason.IMPORT_TIME_LINE: (
        "The changed line executed at import time, outside any test. Coverage "
        "attributes such execution to no test at all, so a test whose "
        "dependency on this line was established while the module was being "
        "imported never appears as covering it. Line-level selection would "
        "silently omit those tests, so the whole suite runs instead. This is "
        "the rule that removed the only miss the harness has ever found "
        "(D-0009), and it is also the most expensive rule we have."
    ),
    Reason.MAP_STALE: (
        "The map was built at a different commit from the branch point of this "
        "change. Its line numbers describe that commit's code, not this one's, "
        "so it cannot be trusted. Rebuild the map at the branch point."
    ),
    Reason.ENVIRONMENT_CHANGED: (
        "The map was built under a different Python version, platform, or set "
        "of installed package versions. Coverage records the code paths that "
        "actually ran, and those depend on the environment, so the map cannot "
        "be trusted here. Rebuild it in this environment."
    ),
    Reason.NO_MAP: "No map exists. The first run always executes everything.",
    Reason.CLASSIFIER_ERROR: (
        "The classifier raised. An error in tia must never mean fewer tests."
    ),
    Reason.NO_CHANGES: "Nothing changed against the base revision.",
}
