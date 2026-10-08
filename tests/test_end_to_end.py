"""Build a real map on a miniature project, then select against real changes.

This is the test that would have caught every bug worth catching: it runs an
instrumented pytest, reads the coverage data, writes the map, edits a line and
checks that the right tests come back — with no mocking anywhere.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

import pytest

from tia import db
from tia.config import Config
from tia.mapper import DirtyTreeError, build
from tia.reasons import Reason
from tia.selector import select

# Python validates a .pyc against (source mtime in whole seconds, source size).
# A mutation that preserves file size and lands within the same second as the
# previous compile is silently ignored — the process imports stale bytecode and
# the "mutant" never runs. See D-0008: this must be enforced everywhere the
# evaluation writes source, or ineffective mutants masquerade as equivalent
# ones and the safety metric measures nothing at all.
NO_BYTECODE = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}


def run_pytest(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Run pytest the way the evaluation must: without writing bytecode."""
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
        env=NO_BYTECODE,
    )


PACKAGE = """\
def add(a, b):
    return a + b


def subtract(a, b):
    return a - b


def unused(a, b):
    return a * b
"""

TEST_ADD = """\
from mini import add


def test_add():
    assert add(1, 2) == 3


def test_add_negative():
    assert add(-1, -1) == -2
"""

TEST_SUBTRACT = """\
from mini import subtract


def test_subtract():
    assert subtract(3, 1) == 2
"""


@pytest.fixture
def mini_project(git_repo: Path, commit) -> Path:
    """A tiny installable project with two source functions and three tests."""
    (git_repo / "mini.py").write_text(PACKAGE)
    (git_repo / "tests").mkdir()
    (git_repo / "tests" / "test_add.py").write_text(TEST_ADD)
    (git_repo / "tests" / "test_subtract.py").write_text(TEST_SUBTRACT)
    (git_repo / ".tia.toml").write_text(
        '[tia]\npackages = ["mini"]\nupstream = "main"\n'
    )
    commit("mini project")
    return git_repo


def build_map(root: Path, *extra: str) -> None:
    """Run the instrumented suite in-process the way `tia build` does."""
    config = Config(packages=["mini"], upstream="main")
    result = run_pytest(
        root, "--cov=mini", "--cov-context=test", "--cov-report=", *extra
    )
    assert result.returncode == 0, result.stdout
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    build(root, config, commit=head, run=False)


def test_map_records_tests_and_lines(mini_project: Path) -> None:
    build_map(mini_project)
    conn = db.connect(db.map_path(mini_project))
    try:
        nodeids = db.all_test_nodeids(conn)
        assert "tests/test_add.py::test_add" in nodeids
        assert len(nodeids) == 3
        assert "mini.py" in db.mapped_source_files(conn)
    finally:
        conn.close()


def test_changing_add_selects_only_the_add_tests(mini_project: Path, commit) -> None:
    build_map(mini_project)
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=mini_project,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    # Edit the body of add() in place: line 2 is `    return a + b`.
    lines = (mini_project / "mini.py").read_text().splitlines(keepends=True)
    lines[1] = "    return a + b  # edited\n"
    (mini_project / "mini.py").write_text("".join(lines))

    decision = select(
        mini_project, Config(packages=["mini"], upstream="main"), base=base
    )
    assert not decision.full_suite
    assert decision.selected == {
        "tests/test_add.py::test_add",
        "tests/test_add.py::test_add_negative",
    }
    assert decision.primary_reason is Reason.SELECTED
    assert decision.total_tests == 3


def test_explanations_name_the_line_and_the_reason(mini_project: Path) -> None:
    build_map(mini_project)
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=mini_project,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    lines = (mini_project / "mini.py").read_text().splitlines(keepends=True)
    lines[1] = "    return a + b  # edited\n"
    (mini_project / "mini.py").write_text("".join(lines))

    decision = select(
        mini_project, Config(packages=["mini"], upstream="main"), base=base
    )
    assert decision.explanations
    for explanation in decision.explanations:
        assert explanation.source_path == "mini.py"
        assert explanation.reason is Reason.SELECTED
        assert 2 in explanation.lines


def test_no_map_means_full_suite(mini_project: Path) -> None:
    decision = select(mini_project, Config(packages=["mini"], upstream="main"))
    assert decision.full_suite
    assert decision.primary_reason is Reason.NO_MAP


def test_changing_an_asset_falls_back(mini_project: Path, commit) -> None:
    build_map(mini_project)
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=mini_project,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    (mini_project / "data.json").write_text("{}\n")
    commit("add data")

    decision = select(
        mini_project, Config(packages=["mini"], upstream="main"), base=base
    )
    assert decision.full_suite
    assert Reason.NON_SOURCE_ASSET in decision.fallback_reasons


def test_stale_map_falls_back(mini_project: Path, commit, run_git) -> None:
    """A map built on a commit that is not an ancestor cannot be trusted."""
    build_map(mini_project)
    conn = db.connect(db.map_path(mini_project))
    try:
        # Pretend the map was built on an unrelated commit.
        db.set_meta(conn, "built_at_commit", "0" * 40)
        conn.commit()
    finally:
        conn.close()

    lines = (mini_project / "mini.py").read_text().splitlines(keepends=True)
    lines[1] = "    return a + b  # edited\n"
    (mini_project / "mini.py").write_text("".join(lines))

    decision = select(mini_project, Config(packages=["mini"], upstream="main"))
    assert decision.full_suite
    assert decision.primary_reason is Reason.MAP_STALE


def _git(repo: Path, *args: str) -> str:
    """Run a git command in the fixture repo and return its stdout."""
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()


def test_selection_catches_an_injected_defect(mini_project: Path) -> None:
    """The safety property in miniature: what the full suite catches, we catch."""
    build_map(mini_project)
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=mini_project,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()

    lines = (mini_project / "mini.py").read_text().splitlines(keepends=True)
    lines[1] = "    return a - b\n"  # the defect
    (mini_project / "mini.py").write_text("".join(lines))

    full = run_pytest(mini_project)
    assert full.returncode != 0, (
        f"the mutant must be caught by the full suite: {full.stdout}"
    )

    decision = select(
        mini_project, Config(packages=["mini"], upstream="main"), base=base
    )
    assert not decision.full_suite
    selected = run_pytest(mini_project, *sorted(decision.selected))
    assert selected.returncode != 0, "MISS: the selection did not catch the defect"


def test_same_size_mutation_is_invisible_without_invalidation(
    mini_project: Path,
) -> None:
    """Pins D-0008, the trap that would have made the safety metric meaningless.

    Python validates a cached .pyc against (source mtime in whole seconds,
    source size). A mutation that preserves both is silently ignored: the
    process imports the old bytecode, the "mutant" never runs, the full suite
    passes, and the harness records an equivalent mutant. The safety metric
    would then be computed over a denominator of mutations that never happened.

    The condition is forced here rather than raced for, so the test is
    deterministic: the mutant is written at the original file's exact mtime.

    Note that PYTHONDONTWRITEBYTECODE alone does not save you — it stops Python
    *writing* caches, not *reading* one that already exists. Invalidation has
    to be explicit.
    """
    source = mini_project / "mini.py"
    original = source.read_text()
    mutated = original.replace("    return a + b\n", "    return a - b\n")
    assert len(mutated) == len(original), "only meaningful at equal size"

    # Warm a .pyc by importing the module the ordinary way. Bytecode writing is
    # switched on explicitly: if the caller's environment carries
    # PYTHONDONTWRITEBYTECODE, no cache is written and the precondition below
    # fails for a reason that has nothing to do with what this test pins.
    warm_env = {k: v for k, v in os.environ.items() if k != "PYTHONDONTWRITEBYTECODE"}
    warm = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        cwd=mini_project,
        capture_output=True,
        text=True,
        check=False,
        env=warm_env,
    )
    assert warm.returncode == 0
    cached = Path(importlib.util.cache_from_source(str(source)))
    assert cached.exists(), "expected a .pyc to exist for this test to mean anything"

    # Write the mutant and forge the mtime so the cache still looks valid.
    before = source.stat()
    source.write_text(mutated)
    os.utime(source, (before.st_atime, before.st_mtime))

    missed = run_pytest(mini_project)
    assert missed.returncode == 0, (
        "expected the stale .pyc to hide the mutation; if this now fails, "
        "Python's cache validation changed and D-0008 needs revisiting"
    )

    # Explicit invalidation is what actually fixes it.
    cached.unlink()
    caught = run_pytest(mini_project)
    assert caught.returncode != 0, "after invalidation the mutant must be caught"


def test_plugin_filters_and_reports_deselection(mini_project: Path) -> None:
    """`pytest --tia` on a real map: filters, and pytest's summary says so."""
    build_map(mini_project)
    lines = (mini_project / "mini.py").read_text().splitlines(keepends=True)
    lines[1] = "    return a + b  # edited\n"
    (mini_project / "mini.py").write_text("".join(lines))

    result = run_pytest(mini_project, "--tia", "--tia-base", "main")
    assert result.returncode == 0, result.stdout
    assert "tia: selected 2 of 3 tests" in result.stdout
    assert "2 passed, 1 deselected" in result.stdout


def test_plugin_never_runs_zero_tests(mini_project: Path) -> None:
    """A selection that matches nothing collected must widen, not empty the run."""
    build_map(mini_project)
    # Change only a function no test ever executes: a valid, empty selection.
    lines = (mini_project / "mini.py").read_text().splitlines(keepends=True)
    lines[9] = "    return a * b  # edited\n"
    (mini_project / "mini.py").write_text("".join(lines))

    result = run_pytest(mini_project, "--tia", "--tia-base", "main")
    assert result.returncode == 0, result.stdout
    assert " 0 passed" not in result.stdout
    assert "no collected test" in result.stdout or "3 passed" in result.stdout


def test_changing_a_line_the_map_never_saw_widens_to_the_file(
    mini_project: Path,
) -> None:
    """A comment carries no coverage, so the line-level lookup comes back
    empty. Selecting nothing there would report ignorance as safety. CI caught
    exactly this shape on a real change and printed "selected 0 of 115".
    """
    target = mini_project / "mini.py"
    target.write_text(target.read_text() + "\n# a comment the map cannot see\n")
    _git(mini_project, "add", "mini.py")
    _git(mini_project, "commit", "-m", "add a comment")
    build_map(mini_project)
    base = _git(mini_project, "rev-parse", "HEAD")

    target.write_text(
        target.read_text().replace(
            "# a comment the map cannot see", "# an edited comment"
        )
    )
    _git(mini_project, "add", "mini.py")
    _git(mini_project, "commit", "-m", "edit the comment")

    decision = select(
        mini_project, Config(packages=["mini"], upstream="main"), base=base
    )
    # The guarantee: never an empty selection presented as a confident answer.
    # (The LINE_NOT_IN_MAP label is applied to the explanations but does not yet
    # propagate to Decision.primary_reason — see the TODO in selector.py.)
    assert decision.selected or decision.full_suite, (
        "a line the map never saw must never produce an empty selection"
    )
    assert len(decision.selected) >= 1


def test_import_closure_reaches_tests_defined_in_a_closure_file(
    mini_project: Path,
) -> None:
    """The closure must find tests DEFINED in a file it reaches, not only tests
    that executed it.

    This is D-0014, found at 200 mutants and not at 50. A project that measures
    coverage for its package only records no coverage rows for its test files,
    so asking "which tests executed this test file" returns nothing and the
    closure silently yields an empty answer for exactly the dependency it
    exists to find.
    """
    target = mini_project / "mini.py"
    # A module-level call: its dependency on the source line is established at
    # import time, so no test is ever recorded as covering it.
    (mini_project / "tests" / "test_importtime.py").write_text(
        "import mini\n\nPRECOMPUTED = mini.add(1, 2)\n\n\n"
        "def test_precomputed():\n    assert PRECOMPUTED == 3\n",
        encoding="utf-8",
    )
    _git(mini_project, "add", "-A")
    _git(mini_project, "commit", "-m", "add an import-time dependency")
    build_map(mini_project)
    base = _git(mini_project, "rev-parse", "HEAD")

    lines = target.read_text().splitlines(keepends=True)
    lines[1] = "    return a - b\n"  # the defect, on the import-time line
    target.write_text("".join(lines))
    _git(mini_project, "add", "mini.py")
    _git(mini_project, "commit", "-m", "inject a defect")

    decision = select(
        mini_project, Config(packages=["mini"], upstream="main"), base=base
    )
    if decision.full_suite:
        return  # falling back is always safe
    assert any("test_importtime" in nodeid for nodeid in decision.selected), (
        "the import-time dependent test must be selected, not silently dropped"
    )


# --- map drift (D-0016) ---------------------------------------------------
# The map speaks the line numbers of the commit it was built at. These pin the
# two ways those numbers can stop describing the code being selected for.


def test_map_built_before_main_moved_falls_back(mini_project: Path) -> None:
    """The shippability blocker, reproduced.

    Map built at X. Main gains four lines at the top of mini.py (X2), which
    moves add()'s body onto the line where subtract()'s body used to be. A
    branch from X2 then breaks add(). The old check only asked whether X is an
    ancestor of X2 — it is — so it looked the changed line up in X's map, found
    test_subtract, and missed the defect while reporting SELECTED.
    """
    build_map(mini_project)
    source = mini_project / "mini.py"
    source.write_text("# a\n# b\n# c\n# d\n" + source.read_text())
    _git(mini_project, "add", "mini.py")
    _git(mini_project, "commit", "-m", "main moves on")
    base = _git(mini_project, "rev-parse", "HEAD")

    _git(mini_project, "checkout", "-q", "-b", "feature")
    source.write_text(source.read_text().replace("return a + b", "return a + b + 1"))
    _git(mini_project, "add", "mini.py")
    _git(mini_project, "commit", "-m", "break add")

    decision = select(
        mini_project, Config(packages=["mini"], upstream="main"), base=base
    )
    assert decision.full_suite, (
        f"selected {sorted(decision.selected)} from a map whose line numbers "
        "no longer describe this code"
    )
    assert decision.primary_reason is Reason.MAP_STALE


def test_explicit_base_resolves_to_the_branch_point(mini_project: Path) -> None:
    """`--base main` means "this branch's changes", not "diff against main's tip".

    The pytest plugin passes --tia-base=origin/main by default. Diffing against
    the tip drags in every upstream commit the branch does not have, so the
    selection described the wrong change entirely.
    """
    build_map(mini_project)
    _git(mini_project, "checkout", "-q", "-b", "feature")
    source = mini_project / "mini.py"
    source.write_text(source.read_text().replace("return a + b", "return a + b + 1"))
    _git(mini_project, "add", "mini.py")
    _git(mini_project, "commit", "-m", "change add")

    _git(mini_project, "checkout", "-q", "main")
    (mini_project / "NOTES.txt").write_text("unrelated upstream work\n")
    _git(mini_project, "add", "NOTES.txt")
    _git(mini_project, "commit", "-m", "main moves on, unrelated")
    _git(mini_project, "checkout", "-q", "feature")

    decision = select(
        mini_project, Config(packages=["mini"], upstream="main"), base="main"
    )
    assert not decision.full_suite, decision.fallback_reasons
    assert decision.selected == {
        "tests/test_add.py::test_add",
        "tests/test_add.py::test_add_negative",
    }


def test_build_refuses_uncommitted_python(mini_project: Path) -> None:
    """A map built from unsaved edits would be stamped with HEAD's commit while
    describing different code — the same drift, created at build time."""
    source = mini_project / "mini.py"
    source.write_text(source.read_text().replace("return a + b", "return b + a"))
    with pytest.raises(DirtyTreeError, match="mini.py"):
        build_map(mini_project)


def test_build_allows_uncommitted_non_python(mini_project: Path) -> None:
    """`tia init` edits .gitignore; that moves no line numbers and must not block."""
    (mini_project / ".gitignore").write_text(".tia/\n")
    build_map(mini_project)


# --- test-file handling (D-0017) ------------------------------------------


HELPER = "def make():\n    return 1\n"

TEST_ADD_WITH_HELPER = """\
from helpers import make
from mini import add


def test_add():
    assert add(make(), 2) == 3
"""


def test_changing_a_test_helper_reaches_the_tests_that_use_it(
    mini_project: Path,
) -> None:
    """A support module under tests/ is not a test module.

    Treating every .py under tests/ as a test file meant changing a helper
    selected the tests *defined in* it — none — instead of the tests that *use*
    it. Alongside any other change, those tests were silently dropped.
    """
    tests = mini_project / "tests"
    (tests / "helpers.py").write_text(HELPER)
    (tests / "test_add.py").write_text(TEST_ADD_WITH_HELPER)
    _git(mini_project, "add", "-A")
    _git(mini_project, "commit", "-m", "add a test helper")
    build_map(mini_project)
    base = _git(mini_project, "rev-parse", "HEAD")

    (tests / "helpers.py").write_text("def make():\n    return 2\n")  # breaks test_add
    source = mini_project / "mini.py"
    source.write_text(source.read_text().replace("return a - b", "return a - b  # x"))
    # Stage only what the change is. `add -A` would also commit the build's
    # .coverage and .tia/ artefacts, which force a full-suite fallback and let
    # this test pass without testing anything.
    _git(mini_project, "add", "tests/helpers.py", "mini.py")
    _git(mini_project, "commit", "-m", "change a helper and a source line")

    decision = select(
        mini_project, Config(packages=["mini"], upstream="main"), base=base
    )
    assert decision.full_suite or "tests/test_add.py::test_add" in decision.selected, (
        f"test_add uses the changed helper but only {sorted(decision.selected)} "
        "were selected"
    )


def test_a_new_test_in_a_changed_test_file_actually_runs(mini_project: Path) -> None:
    """The map cannot know a test written in this very change.

    The plugin kept only tests the map knew by nodeid, so a new test — the most
    likely test to catch the change it was written for — was deselected.
    """
    build_map(mini_project)
    base = _git(mini_project, "rev-parse", "HEAD")

    test_add = mini_project / "tests" / "test_add.py"
    test_add.write_text(
        test_add.read_text() + "\n\ndef test_brand_new():\n    assert False\n"
    )
    source = mini_project / "mini.py"
    source.write_text(source.read_text().replace("return a - b", "return a - b  # x"))
    _git(mini_project, "add", "tests/test_add.py", "mini.py")  # not the artefacts
    _git(mini_project, "commit", "-m", "a new failing test and a source change")

    result = run_pytest(mini_project, "--tia", f"--tia-base={base}")
    assert "test_brand_new" in result.stdout and result.returncode != 0, (
        "the new test was not run:\n" + result.stdout
    )


def test_an_untracked_new_test_file_still_runs(mini_project: Path) -> None:
    """Locally, a test file you have not `git add`-ed yet is invisible to
    `git diff`. It is still part of the change you are about to test."""
    build_map(mini_project)
    (mini_project / "tests" / "test_untracked.py").write_text(
        "def test_not_yet_added():\n    assert False\n"
    )
    decision = select(mini_project, Config(packages=["mini"], upstream="main"))
    assert "tests/test_untracked.py" in decision.forced_paths or decision.full_suite
    result = run_pytest(mini_project, "--tia", "--tia-base=main")
    assert "test_not_yet_added" in result.stdout and result.returncode != 0, (
        result.stdout
    )


def test_tias_own_artefacts_are_not_mistaken_for_a_change(mini_project: Path) -> None:
    """Building the map leaves .coverage behind. Treating it as an untracked
    change would turn every selection into a full suite."""
    build_map(mini_project)
    assert (mini_project / ".coverage").exists()
    source = mini_project / "mini.py"
    source.write_text(source.read_text().replace("return a + b", "return a + b  # x"))
    decision = select(mini_project, Config(packages=["mini"], upstream="main"))
    assert not decision.full_suite, decision.fallback_reasons


def test_a_new_doctest_in_a_changed_source_file_runs(mini_project: Path) -> None:
    """In a --doctest-modules project, a doctest written in this change has an
    id the map has never seen and lives in a source file, not a test file."""
    build_map(mini_project, "--doctest-modules")
    base = _git(mini_project, "rev-parse", "HEAD")
    source = mini_project / "mini.py"
    source.write_text(
        source.read_text().replace(
            "def unused(a, b):\n",
            'def unused(a, b):\n    """\n    >>> unused(2, 3)\n    999\n    """\n',
        )
    )
    _git(mini_project, "add", "mini.py")
    _git(mini_project, "commit", "-m", "a new, failing doctest")

    result = run_pytest(
        mini_project, "--doctest-modules", "--tia", f"--tia-base={base}"
    )
    assert "mini.unused" in result.stdout and result.returncode != 0, result.stdout


def test_stray_untracked_files_do_not_force_a_full_suite(mini_project: Path) -> None:
    """A messy working tree must not make tia useless. Only untracked files
    that define tests — test modules, conftest.py — count as part of a change."""
    build_map(mini_project)
    (mini_project / "notes.txt").write_text("todo\n")
    (mini_project / ".DS_Store").write_bytes(b"\\x00")
    (mini_project / "scratch.py").write_text("x = 1\n")
    source = mini_project / "mini.py"
    source.write_text(source.read_text().replace("return a + b", "return a + b  # x"))
    decision = select(mini_project, Config(packages=["mini"], upstream="main"))
    assert not decision.full_suite, decision.fallback_reasons
    assert "tests/test_add.py::test_add" in decision.selected
