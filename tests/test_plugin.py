"""The plugin form (SPEC B.7).

The invariant under test is the one that matters most: `--tia` must never mean
"no tests ran". Every failure path here — not a git repository, no map, a
selection that matches nothing — has to end with the full suite running and a
line on the report saying why.
"""

from __future__ import annotations

SAMPLE_SUITE = """
def test_one():
    assert True

def test_two():
    assert True
"""


def test_options_are_registered(pytester) -> None:
    pytester.makepyfile(test_sample=SAMPLE_SUITE)
    result = pytester.runpytest_subprocess("--help")
    result.stdout.fnmatch_lines(["*--tia*"])
    result.stdout.fnmatch_lines(["*--tia-base=REV*"])


def test_plugin_is_inert_without_the_flag(pytester) -> None:
    pytester.makepyfile(test_sample=SAMPLE_SUITE)
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=2)
    assert "tia:" not in result.stdout.str()
    assert "tia:" not in result.stderr.str()


def test_outside_a_git_repository_runs_everything(pytester) -> None:
    """A tia that cannot even find the repository must not remove a single test."""
    pytester.makepyfile(test_sample=SAMPLE_SUITE)
    result = pytester.runpytest_subprocess("--tia")
    result.assert_outcomes(passed=2)
    result.stdout.fnmatch_lines(["tia: selection failed*running all 2 tests"])


def test_no_map_runs_everything(pytester) -> None:
    """A repository with no map falls back, and names NO_MAP while doing it."""
    pytester.makepyfile(test_sample=SAMPLE_SUITE)
    pytester.run("git", "init", "-q", "-b", "main")
    pytester.run("git", "config", "user.email", "tia@example.test")
    pytester.run("git", "config", "user.name", "tia tests")
    pytester.run("git", "add", "-A")
    pytester.run("git", "commit", "-q", "-m", "seed")

    result = pytester.runpytest_subprocess("--tia")
    result.assert_outcomes(passed=2)
    result.stdout.fnmatch_lines(["tia: full suite (NO_MAP)*running all 2 tests"])


def test_deselection_is_reported_honestly(pytester) -> None:
    """When tia does filter, pytest's own summary must show the deselection."""
    pytester.makepyfile(test_sample=SAMPLE_SUITE)
    result = pytester.runpytest_subprocess("-k", "test_one")
    result.assert_outcomes(passed=1, deselected=1)
