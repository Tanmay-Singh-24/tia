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
from tia.mapper import build
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


def build_map(root: Path) -> None:
    """Run the instrumented suite in-process the way `tia build` does."""
    config = Config(packages=["mini"], upstream="main")
    result = run_pytest(root, "--cov=mini", "--cov-context=test", "--cov-report=")
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

    # Warm a .pyc by importing the module the ordinary way.
    warm = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        cwd=mini_project,
        capture_output=True,
        text=True,
        check=False,
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
