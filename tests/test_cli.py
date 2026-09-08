"""The CLI surface (SPEC B.7).

Safety note for anyone extending this file: never invoke `tia build` through
the CLI runner from inside tia's own repository. `build` runs the project's
suite, so doing that makes tia's tests spawn tia's tests — a fork bomb that
took a machine down once already. Build behaviour is covered in
test_end_to_end.py against a miniature project instead.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from tia import __version__
from tia.cli import EXIT_MAP_UNUSABLE, EXIT_OK, EXIT_USAGE, app

runner = CliRunner()

COMMANDS = ["init", "build", "select", "run", "status", "explain"]


def _all_output(result) -> str:
    """Stdout plus stderr, across click versions that split them and ones that don't."""
    text = result.output
    with contextlib.suppress(ValueError):
        text += result.stderr
    return text


@pytest.fixture
def in_repo(git_repo: Path) -> Iterator[Path]:
    """Run the CLI from inside a throwaway git repository."""
    previous = Path.cwd()
    os.chdir(git_repo)
    try:
        yield git_repo
    finally:
        os.chdir(previous)


def test_help_lists_every_command() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == EXIT_OK
    for command in COMMANDS:
        assert command in result.output


def test_bare_invocation_prints_help() -> None:
    result = runner.invoke(app, [])
    assert result.exit_code == EXIT_OK
    assert "Usage:" in result.output


def test_version_flag() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == EXIT_OK
    assert __version__ in result.output


@pytest.mark.parametrize("command", COMMANDS)
def test_command_help_works(command: str) -> None:
    result = runner.invoke(app, [command, "--help"])
    assert result.exit_code == EXIT_OK
    assert "Usage:" in result.output


def test_select_rejects_an_unknown_format() -> None:
    result = runner.invoke(app, ["select", "--format", "yaml"])
    assert result.exit_code == EXIT_USAGE


def test_init_writes_config_and_gitignores_the_map(in_repo: Path) -> None:
    result = runner.invoke(app, ["init", "-p", "mini"])
    assert result.exit_code == EXIT_OK, _all_output(result)
    assert (in_repo / ".tia.toml").exists()
    assert '"mini"' in (in_repo / ".tia.toml").read_text()
    assert (in_repo / ".tia").is_dir()
    assert ".tia/" in (in_repo / ".gitignore").read_text()


def test_init_is_idempotent(in_repo: Path) -> None:
    runner.invoke(app, ["init"])
    first = (in_repo / ".gitignore").read_text()
    result = runner.invoke(app, ["init"])
    assert result.exit_code == EXIT_OK
    assert (in_repo / ".gitignore").read_text() == first


def test_status_without_a_map_exits_three(in_repo: Path) -> None:
    """Exit code 3 is 'map unusable' (SPEC B.7)."""
    result = runner.invoke(app, ["status"])
    assert result.exit_code == EXIT_MAP_UNUSABLE


def test_explain_rejects_a_malformed_target(in_repo: Path) -> None:
    result = runner.invoke(app, ["explain", "src/app.py"])
    assert result.exit_code == EXIT_USAGE
    assert "PATH:LINE" in _all_output(result)


def test_explain_rejects_a_non_numeric_line(in_repo: Path) -> None:
    result = runner.invoke(app, ["explain", "src/app.py:middle"])
    assert result.exit_code == EXIT_USAGE


def test_explain_without_a_map_exits_three(in_repo: Path) -> None:
    result = runner.invoke(app, ["explain", "src/app.py:42"])
    assert result.exit_code == EXIT_MAP_UNUSABLE


def test_select_without_a_map_reports_no_map_and_succeeds(in_repo: Path) -> None:
    """No map means the full suite — which is a normal outcome, not an error."""
    result = runner.invoke(app, ["select"])
    assert result.exit_code == EXIT_OK
    assert "NO_MAP" in _all_output(result)


def test_select_json_is_machine_readable(in_repo: Path) -> None:
    import json

    result = runner.invoke(app, ["select", "--format", "json"])
    assert result.exit_code == EXIT_OK
    payload = json.loads(result.output)
    assert payload["full_suite"] is True
    assert payload["primary_reason"] == "NO_MAP"
    assert payload["selection_ratio"] == 1.0


def test_outside_a_git_repository_is_a_usage_error(tmp_path: Path) -> None:
    previous = Path.cwd()
    os.chdir(tmp_path)
    try:
        result = runner.invoke(app, ["status"])
        assert result.exit_code == EXIT_USAGE
    finally:
        os.chdir(previous)
