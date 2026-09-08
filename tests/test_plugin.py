"""The plugin form (SPEC B.7). The invariant under test is the one that matters
most on day one: `--tia` never means "no tests ran".
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


def test_tia_flag_runs_the_full_suite_for_now(pytester) -> None:
    pytester.makepyfile(test_sample=SAMPLE_SUITE)
    result = pytester.runpytest_subprocess("--tia")
    result.assert_outcomes(passed=2)
    result.stdout.fnmatch_lines(["tia: selection not implemented*"])


def test_plugin_is_inert_without_the_flag(pytester) -> None:
    pytester.makepyfile(test_sample=SAMPLE_SUITE)
    result = pytester.runpytest_subprocess()
    result.assert_outcomes(passed=2)
    assert "tia:" not in result.stdout.str()
    assert "tia:" not in result.stderr.str()
