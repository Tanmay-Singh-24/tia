"""One test per row of the SPEC B.6 classifier table.

That table is the safety guarantee. If a row here is wrong, the guarantee is
wrong, so each row gets its own named case rather than being folded into a
loop.
"""

from __future__ import annotations

import pytest

from tia.classifier import classify, is_dependency_path, is_test_path
from tia.diff import FileChange
from tia.reasons import Reason

MAPPED = frozenset({"src/app/core.py", "src/app/util.py", "src/app/__init__.py"})


def change(
    path: str,
    *,
    lines: set[int] | None = None,
    insertions: bool = False,
    status: str = "M",
    old_path: str | None = None,
    binary: bool = False,
) -> FileChange:
    return FileChange(
        path=path,
        old_path=old_path,
        status=status,
        old_lines=frozenset(lines or {10}),
        insertions=insertions,
        binary=binary,
    )


def verdict_for(fc: FileChange, always_full: list[str] | None = None):
    return classify(fc, mapped_files=MAPPED, always_full=always_full or [])


# --- the table ------------------------------------------------------------


def test_test_file_changed_always_runs_without_the_map() -> None:
    v = verdict_for(change("tests/test_core.py"))
    assert v.reason is Reason.TEST_CHANGED
    assert not v.is_fallback


def test_conftest_runs_everything_at_or_below_its_directory() -> None:
    v = verdict_for(change("tests/unit/conftest.py"))
    assert v.reason is Reason.CONFTEST_CHANGED
    assert v.scope == "directory"
    assert v.detail == "tests/unit"


def test_mapped_source_gets_line_level_selection() -> None:
    v = verdict_for(change("src/app/core.py"))
    assert v.reason is Reason.SELECTED
    assert v.scope == "line"
    assert not v.is_fallback


def test_unmapped_source_falls_back() -> None:
    v = verdict_for(change("src/app/brand_new.py"))
    assert v.reason is Reason.UNMAPPED_FILE
    assert v.is_fallback


def test_package_init_never_uses_line_level() -> None:
    v = verdict_for(change("src/app/__init__.py"))
    assert v.reason is Reason.PACKAGE_INIT
    assert v.scope == "package"


@pytest.mark.parametrize(
    "path",
    ["pyproject.toml", "setup.cfg", "setup.py", "tox.ini", "pytest.ini", ".coveragerc"],
)
def test_build_config_falls_back(path: str) -> None:
    v = verdict_for(change(path))
    assert v.reason is Reason.BUILD_CONFIG_CHANGED
    assert v.is_fallback


@pytest.mark.parametrize(
    "path",
    [
        "requirements.txt",
        "requirements-dev.txt",
        "requirements/base.txt",
        "poetry.lock",
        "uv.lock",
        "Pipfile.lock",
    ],
)
def test_dependency_change_falls_back(path: str) -> None:
    v = verdict_for(change(path))
    assert v.reason is Reason.DEPENDENCY_CHANGED
    assert v.is_fallback


@pytest.mark.parametrize(
    "path",
    [
        "data/fixture.json",
        "config/settings.yaml",
        "db/schema.sql",
        "templates/page.html",
        "data/rows.csv",
        "Makefile",
        "assets/logo.png",
        "proto/service.proto",
    ],
)
def test_non_source_assets_fall_back(path: str) -> None:
    """We are stricter than the SPEC's enumeration: anything not .py is an asset."""
    v = verdict_for(change(path))
    assert v.reason is Reason.NON_SOURCE_ASSET
    assert v.is_fallback


def test_always_full_glob_wins_over_everything() -> None:
    v = verdict_for(change("src/app/core.py"), always_full=["src/app/*"])
    assert v.reason is Reason.USER_CONFIGURED
    assert v.is_fallback


def test_user_configured_beats_even_a_test_file() -> None:
    v = verdict_for(change("tests/test_core.py"), always_full=["tests/*"])
    assert v.reason is Reason.USER_CONFIGURED


# --- the cases the table implies ------------------------------------------


def test_insertion_widens_to_file_level() -> None:
    v = verdict_for(change("src/app/core.py", insertions=True))
    assert v.reason is Reason.INSERTION_NO_HISTORY
    assert v.scope == "file"


def test_deleted_source_falls_back() -> None:
    v = verdict_for(change("src/app/core.py", status="D"))
    assert v.reason is Reason.UNMAPPED_FILE


def test_renamed_file_is_looked_up_by_its_old_path() -> None:
    v = verdict_for(
        change("src/app/renamed.py", status="R", old_path="src/app/core.py")
    )
    assert v.reason is Reason.SELECTED
    assert v.change.lookup_path == "src/app/core.py"


def test_conftest_is_checked_before_the_test_file_rule() -> None:
    """conftest.py lives in a tests directory but must not be treated as a test."""
    v = verdict_for(change("tests/conftest.py"))
    assert v.reason is Reason.CONFTEST_CHANGED


def test_dependency_file_beats_the_asset_rule() -> None:
    """requirements.txt is not a .py file, but it deserves its own reason code."""
    assert verdict_for(change("requirements.txt")).reason is Reason.DEPENDENCY_CHANGED


# --- helpers ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("tests/test_a.py", True),
        ("tests/a_test.py", True),
        ("test/helpers.py", True),
        ("src/app/testing_utils.py", False),
        ("src/app/core.py", False),
        ("tests/data/fixture.json", False),
    ],
)
def test_is_test_path(path: str, expected: bool) -> None:
    assert is_test_path(path) is expected


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("requirements.txt", True),
        ("requirements/dev.txt", True),
        ("poetry.lock", True),
        ("src/app/core.py", False),
    ],
)
def test_is_dependency_path(path: str, expected: bool) -> None:
    assert is_dependency_path(path) is expected


def test_every_reason_code_has_a_description() -> None:
    """A reason code without an explanation is not inspectable."""
    for reason in Reason:
        assert reason.description
        assert len(reason.description) > 20


# --- D-0009: the rule added after a measured miss --------------------------


def test_line_that_ran_at_import_time_falls_back() -> None:
    """A line executed at import time cannot be resolved to the tests that need it.

    This rule exists because its absence produced a real miss on attrs: line 88
    of src/attr/_cmp.py runs both inside two tests and at import time, when
    tests/test_cmp.py builds classes at module level. The map recorded only the
    two in-test executions, so selecting by that line omitted the six tests that
    actually failed.
    """
    v = classify(
        change("src/app/core.py", lines={10}),
        mapped_files=MAPPED,
        always_full=[],
        import_time_lines=frozenset({10}),
    )
    assert v.reason is Reason.IMPORT_TIME_LINE
    assert v.is_fallback


def test_import_time_lines_elsewhere_in_the_file_do_not_block_selection() -> None:
    """Only the *changed* lines matter; other import-time lines are irrelevant."""
    v = classify(
        change("src/app/core.py", lines={10}),
        mapped_files=MAPPED,
        always_full=[],
        import_time_lines=frozenset({500, 501}),
    )
    assert v.reason is Reason.SELECTED


def test_any_overlap_is_enough_to_fall_back() -> None:
    """A hunk touching one import-time line among many still cannot be trusted."""
    v = classify(
        change("src/app/core.py", lines={10, 11, 12}),
        mapped_files=MAPPED,
        always_full=[],
        import_time_lines=frozenset({12}),
    )
    assert v.reason is Reason.IMPORT_TIME_LINE


def test_a_test_file_change_still_wins_over_import_time() -> None:
    """Ordering check: changed tests run regardless of import-time execution."""
    v = classify(
        change("tests/test_core.py", lines={10}),
        mapped_files=MAPPED,
        always_full=[],
        import_time_lines=frozenset({10}),
    )
    assert v.reason is Reason.TEST_CHANGED
