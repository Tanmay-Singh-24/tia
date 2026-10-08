"""What a selection hands pytest.

The selector's job ends in two places — the plugin's per-test filter and the
argument list `tia run` / `tia select` give pytest. Both must keep tests the map
has never seen by full id: tests in a changed test file (D-0017), and new
parametrisations of a selected test (D-0018).
"""

from __future__ import annotations

from tia.classifier import Verdict
from tia.diff import FileChange
from tia.reasons import Reason
from tia.selector import Decision


def _decision(selected: set[str], forced: list[str] | None = None) -> Decision:
    decision = Decision(full_suite=False, selected=selected)
    for path in forced or []:
        change = FileChange(
            path=path,
            old_path=None,
            status="M",
            old_lines=frozenset(),
            insertions=False,
        )
        decision.verdicts.append(Verdict(change, Reason.TEST_CHANGED, "file", path))
    return decision


def test_a_new_parametrisation_of_a_selected_test_still_runs() -> None:
    """Adding a value to a list in the source creates test_x[new], an id the map
    has never seen. Selecting by full id would drop it; selecting by test
    function keeps every parametrisation, including the new one."""
    decision = _decision(
        {"tests/test_m.py::test_positive[1]", "tests/test_m.py::test_positive[2]"}
    )
    assert decision.wants("tests/test_m.py::test_positive[-3]")
    assert not decision.wants("tests/test_m.py::TestC::test_x")
    assert decision.pytest_args() == ["tests/test_m.py::test_positive"]


def test_brackets_inside_a_parameter_do_not_confuse_the_test_function() -> None:
    decision = _decision({"tests/test_m.py::test_p[a[1]-b]"})
    assert decision.wants("tests/test_m.py::test_p[other]")
    assert decision.pytest_args() == ["tests/test_m.py::test_p"]


def test_pytest_args_run_forced_paths_whole_without_repeating_them() -> None:
    decision = _decision(
        {"tests/test_a.py::test_one", "tests/test_b.py::test_two[x]"},
        forced=["tests/test_a.py"],
    )
    assert decision.pytest_args() == ["tests/test_a.py", "tests/test_b.py::test_two"]


def test_a_root_conftest_forces_everything() -> None:
    decision = Decision(full_suite=False, selected={"tests/test_a.py::test_one"})
    change = FileChange(
        path="conftest.py",
        old_path=None,
        status="M",
        old_lines=frozenset(),
        insertions=False,
    )
    decision.verdicts.append(Verdict(change, Reason.CONFTEST_CHANGED, "directory", "."))
    assert decision.wants("anything/test_z.py::test_q")
    assert decision.pytest_args() == ["."]
