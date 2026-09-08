"""Shared fixtures for tia's own tests.

The git fixtures build real repositories in tmp_path. Nothing about git is
mocked: the whole point of diff.py is that it agrees with git, and a mock would
only ever agree with our idea of git.
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

pytest_plugins = ["pytester"]


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=True
    )
    return proc.stdout


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """An initialised repository with one commit on `main`."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-q", "-b", "main")
    _git(root, "config", "user.email", "tia@example.test")
    _git(root, "config", "user.name", "tia tests")
    _git(root, "config", "commit.gpgsign", "false")
    (root / "README.md").write_text("seed\n")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "seed")
    return root


@pytest.fixture
def commit(git_repo: Path) -> Callable[[str], str]:
    """Commit whatever is in the tree and return the new sha."""

    def _commit(message: str) -> str:
        _git(git_repo, "add", "-A")
        _git(git_repo, "commit", "-q", "-m", message)
        return _git(git_repo, "rev-parse", "HEAD").strip()

    return _commit


@pytest.fixture
def run_git(git_repo: Path) -> Callable[..., str]:
    def _run(*args: str) -> str:
        return _git(git_repo, *args)

    return _run
