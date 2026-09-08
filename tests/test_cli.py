"""The CLI surface is a contract (SPEC B.7): the seven entry points exist, and
an unimplemented command says so and exits 2 rather than pretending to work.
"""

from __future__ import annotations

import contextlib

import pytest
from typer.testing import CliRunner

from tia import __version__
from tia.cli import app

runner = CliRunner()

# Every command in SPEC B.7 that is reachable as `tia <command>`. The seventh
# entry point in that table is the plugin form, covered in test_plugin.py.
COMMANDS = ["init", "build", "select", "run", "status", "explain"]

# Commands that need a positional argument before they reach the stub.
ARGS = {"explain": ["src/app.py:42"]}


def _all_output(result) -> str:
    """Stdout plus stderr, across click versions that split them and ones that don't."""
    text = result.output
    with contextlib.suppress(ValueError):  # click < 8.2 merges the streams
        text += result.stderr
    return text


def test_help_lists_every_command() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in COMMANDS:
        assert command in result.output


def test_bare_invocation_prints_help() -> None:
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "Usage:" in result.output


def test_version_flag() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output


@pytest.mark.parametrize("command", COMMANDS)
def test_command_is_a_stub_that_exits_two(command: str) -> None:
    result = runner.invoke(app, [command, *ARGS.get(command, [])])
    assert result.exit_code == 2, _all_output(result)
    assert "not implemented" in _all_output(result)


@pytest.mark.parametrize("command", COMMANDS)
def test_command_help_works(command: str) -> None:
    result = runner.invoke(app, [command, "--help"])
    assert result.exit_code == 0
    assert "Usage:" in result.output


def test_select_rejects_an_unknown_format() -> None:
    result = runner.invoke(app, ["select", "--format", "yaml"])
    assert result.exit_code == 2


def test_stub_echoes_what_it_parsed() -> None:
    """The stubs are how we check the SPEC B.7 option contract before it is wired."""
    result = runner.invoke(app, ["select", "--base", "upstream/main", "--explain"])
    output = _all_output(result)
    assert result.exit_code == 2
    assert "base='upstream/main'" in output
    assert "explain=True" in output


def test_run_forwards_extra_pytest_arguments() -> None:
    result = runner.invoke(app, ["run", "--", "-k", "login", "-x"])
    output = _all_output(result)
    assert result.exit_code == 2
    assert "-k" in output and "login" in output
