"""The safety classifier — the heart of the guarantee (SPEC B.6).

Every changed path is routed to exactly one outcome. This module is the whole
argument for why tia is safe to use, so it is written to be read aloud: one
function, one rule per branch, in the order the SPEC states them.

The governing principle: be selective where confident, exhaustive everywhere
else. Two of the three problems the proposal identifies are answered here by
deliberately giving up the speed benefit.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import PurePosixPath

from tia.diff import FileChange
from tia.reasons import Reason

# Changing any of these can alter how every test runs.
BUILD_CONFIG_FILES = frozenset(
    {
        "pyproject.toml",
        "setup.cfg",
        "setup.py",
        "tox.ini",
        "pytest.ini",
        ".coveragerc",
        "conftest.py",  # handled earlier, listed for completeness
    }
)

DEPENDENCY_FILES = frozenset(
    {
        "poetry.lock",
        "uv.lock",
        "Pipfile",
        "Pipfile.lock",
        "pdm.lock",
        "environment.yml",
    }
)

DEPENDENCY_GLOBS = ("requirements*.txt", "requirements/*.txt", "constraints*.txt")

# SPEC B.6 enumerates asset suffixes (.json, .yaml, .sql, .html, .csv). We are
# stricter: anything that is not a .py file is treated as an asset the map
# cannot see. Enumerating suffixes means the first unlisted one — .proto, .pyx,
# a Makefile — silently takes the fast path, and that is exactly the shape of a
# silent miss. The cost of being broad here is speed we can measure; the cost
# of being narrow is a defect we cannot.


@dataclass(frozen=True)
class Verdict:
    """What to do about one changed path, and why."""

    change: FileChange
    reason: Reason
    scope: str
    """'line', 'file', 'directory', 'package' or 'all'."""

    detail: str = ""

    @property
    def is_fallback(self) -> bool:
        return self.reason.is_fallback


def is_test_path(path: str) -> bool:
    """Does this path hold tests?

    Deliberately generous. Misjudging a test file as source would consult the
    map for a test that may never have been observed; misjudging source as a
    test only costs us some speed.
    """
    posix = PurePosixPath(path)
    if posix.suffix != ".py":
        return False
    name = posix.name
    if name.startswith("test_") or name.endswith("_test.py"):
        return True
    return any(part in {"tests", "test", "testing"} for part in posix.parts[:-1])


def is_dependency_path(path: str) -> bool:
    name = PurePosixPath(path).name
    if name in DEPENDENCY_FILES:
        return True
    return any(
        fnmatch.fnmatch(path, glob) or fnmatch.fnmatch(name, glob)
        for glob in DEPENDENCY_GLOBS
    )


def classify(
    change: FileChange,
    *,
    mapped_files: frozenset[str],
    always_full: list[str],
) -> Verdict:
    """Route one changed path to exactly one outcome.

    The order of these branches is the guarantee. Anything that can affect the
    whole suite is caught before we ever consult the map.
    """
    path = change.path
    lookup = change.lookup_path
    name = PurePosixPath(path).name

    # 1. User override always wins.
    for glob in always_full:
        if fnmatch.fnmatch(path, glob):
            return Verdict(change, Reason.USER_CONFIGURED, "all", f"matches {glob!r}")

    # 2. conftest.py: fixtures reach every test at or below its directory.
    if name == "conftest.py":
        directory = str(PurePosixPath(path).parent)
        return Verdict(change, Reason.CONFTEST_CHANGED, "directory", directory)

    # 3. A changed test always runs. The map has never seen it in this form.
    if is_test_path(path):
        return Verdict(change, Reason.TEST_CHANGED, "file", path)

    # 4. Dependency declarations: third-party code is not in the map.
    if is_dependency_path(path):
        return Verdict(change, Reason.DEPENDENCY_CHANGED, "all", name)

    # 5. Build and test configuration.
    if name in BUILD_CONFIG_FILES:
        return Verdict(change, Reason.BUILD_CONFIG_CHANGED, "all", name)

    # 6. Anything that is not Python source is an asset the map cannot see.
    suffix = PurePosixPath(path).suffix
    if suffix != ".py":
        return Verdict(change, Reason.NON_SOURCE_ASSET, "all", suffix or name)

    # 7. __init__.py: import side effects are not local to a line.
    if name == "__init__.py":
        package = str(PurePosixPath(path).parent)
        return Verdict(change, Reason.PACKAGE_INIT, "package", package)

    # 8. Project source the map has never recorded.
    if lookup not in mapped_files:
        return Verdict(change, Reason.UNMAPPED_FILE, "all", lookup)

    # 9. Inserted lines have no old-side coordinates to look up.
    if change.insertions:
        return Verdict(change, Reason.INSERTION_NO_HISTORY, "file", lookup)

    # 10. A deleted file cannot be looked up by line either.
    if change.status == "D":
        return Verdict(change, Reason.UNMAPPED_FILE, "all", lookup)

    # 11. Everything above failed to apply: the map can answer this by line.
    return Verdict(change, Reason.SELECTED, "line", lookup)


def classify_all(
    changes: list[FileChange],
    *,
    mapped_files: frozenset[str],
    always_full: list[str],
) -> list[Verdict]:
    """Classify every change. A classifier that raises falls back, never fails."""
    verdicts: list[Verdict] = []
    for change in changes:
        try:
            verdicts.append(
                classify(change, mapped_files=mapped_files, always_full=always_full)
            )
        except Exception as exc:  # noqa: BLE001 - an error must never mean fewer tests
            verdicts.append(
                Verdict(
                    change,
                    Reason.CLASSIFIER_ERROR,
                    "all",
                    f"{type(exc).__name__}: {exc}",
                )
            )
    return verdicts
