"""Git integration: merge-base resolution and hunk parsing (SPEC B.5).

We shell out to git rather than binding a library: plumbing commands are
stable, and there is no binding to keep current.

The subtlety that matters. The map was built at some commit and speaks that
commit's line numbers. A change must therefore be looked up using the
**old-side** line numbers from the diff, because those are the coordinates the
map understands. Lines that only exist on the new side — pure insertions —
have no old-side coordinate at all and cannot be looked up. We do not pretend
otherwise; see `FileChange.insertions`.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

STATUS_MODIFIED = "M"
STATUS_ADDED = "A"
STATUS_DELETED = "D"
STATUS_RENAMED = "R"


class GitError(RuntimeError):
    """A git command failed. The caller falls back to the full suite."""


def git(root: Path, *args: str) -> str:
    """Run a git plumbing command and return stdout."""
    proc = subprocess.run(  # noqa: S603
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise GitError(f"git {' '.join(args)}: {proc.stderr.strip()}")
    return proc.stdout


def repo_root(start: Path | None = None) -> Path:
    """The repository containing `start` (default: the current directory)."""
    where = start or Path.cwd()
    out = git(where, "rev-parse", "--show-toplevel").strip()
    return Path(out).resolve()


def head_commit(root: Path) -> str:
    return git(root, "rev-parse", "HEAD").strip()


def short(commit: str) -> str:
    return commit[:7] if commit else "(none)"


def resolve_base(root: Path, upstream: str) -> str:
    """The merge base of HEAD and `upstream`, or `upstream` itself if unmerged.

    Diffing against the branch point rather than against the tip is what makes
    the selection reflect *this* branch's changes and not everything that has
    landed upstream since.
    """
    try:
        return git(root, "merge-base", "HEAD", upstream).strip()
    except GitError:
        # No merge base (unrelated history, or the ref is a plain commit).
        return git(root, "rev-parse", upstream).strip()


def is_ancestor(root: Path, maybe_ancestor: str, descendant: str) -> bool:
    """True when the map's commit is actually behind the change being selected."""
    proc = subprocess.run(  # noqa: S603
        ["git", "merge-base", "--is-ancestor", maybe_ancestor, descendant],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.returncode == 0


def is_dirty(root: Path) -> bool:
    """Are there uncommitted changes? Developers run this on dirty trees."""
    return bool(git(root, "status", "--porcelain").strip())


@dataclass(frozen=True)
class FileChange:
    """One changed path, in the coordinates the map speaks."""

    path: str
    """New-side path, POSIX, relative to the repo root."""

    old_path: str | None
    """Previous path when the file was renamed, else None."""

    status: str
    """M, A, D or R."""

    old_lines: frozenset[int]
    """Old-side line numbers touched. Empty for added files and pure inserts."""

    insertions: bool
    """True when any hunk added lines that have no old-side coordinate."""

    binary: bool = False

    @property
    def lookup_path(self) -> str:
        """The path the map knows this file by."""
        return self.old_path or self.path


def _finish(
    path: str | None,
    old_path: str | None,
    status: str,
    lines: set[int],
    insertions: bool,
    binary: bool,
    out: list[FileChange],
) -> None:
    if path is None:
        return
    # A newly added file has no old side at all: `@@ -0,0 +1,N @@` would
    # otherwise leave us holding straddling "lines" 0 and 1 of a file that did
    # not exist. The classifier treats added files as unmapped regardless, but
    # the recorded data should not claim coordinates that never existed.
    if status == STATUS_ADDED:
        lines = set()
    out.append(
        FileChange(
            path=path,
            old_path=old_path if old_path and old_path != path else None,
            status=status,
            old_lines=frozenset(lines),
            insertions=insertions,
            binary=binary,
        )
    )


def parse_diff(text: str) -> list[FileChange]:
    """Parse `git diff --unified=0` output into per-file changes.

    Hunk headers are `@@ -old_start,old_count +new_start,new_count @@`:

    - `old_count > 0` — lines `old_start .. old_start + old_count - 1` existed
      before the change and can be looked up in the map directly.
    - `old_count == 0` — a pure insertion. The new lines have no old-side
      coordinates. We take the two straddling old lines as a weak signal and
      flag the file so the caller widens to file-level selection (SPEC B.5).
    """
    changes: list[FileChange] = []
    path: str | None = None
    old_path: str | None = None
    status = STATUS_MODIFIED
    lines: set[int] = set()
    insertions = False
    binary = False

    for raw in text.splitlines():
        if raw.startswith("diff --git "):
            _finish(path, old_path, status, lines, insertions, binary, changes)
            path, old_path, status = None, None, STATUS_MODIFIED
            lines, insertions, binary = set(), False, False
            parts = raw.split(" b/", 1)
            if len(parts) == 2:
                path = parts[1]
                old_path = parts[0].removeprefix("diff --git a/")
        elif raw.startswith("new file mode"):
            status = STATUS_ADDED
        elif raw.startswith("deleted file mode"):
            status = STATUS_DELETED
        elif raw.startswith("rename from "):
            old_path = raw.removeprefix("rename from ").strip()
            status = STATUS_RENAMED
        elif raw.startswith("rename to "):
            path = raw.removeprefix("rename to ").strip()
            status = STATUS_RENAMED
        elif raw.startswith("Binary files ") or raw.startswith("GIT binary patch"):
            binary = True
        else:
            match = HUNK_RE.match(raw)
            if match is None:
                continue
            old_start = int(match.group(1))
            old_count = 1 if match.group(2) is None else int(match.group(2))
            if old_count == 0:
                # Pure insertion: no old-side coordinate exists for the new
                # lines. Straddling lines are a hint, not an answer.
                insertions = True
                lines.update({old_start, old_start + 1})
            else:
                lines.update(range(old_start, old_start + old_count))

    _finish(path, old_path, status, lines, insertions, binary, changes)
    return changes


def changed_lines(
    root: Path, base: str, *, include_uncommitted: bool = True
) -> list[FileChange]:
    """Every path changed between `base` and the current state of the tree.

    When the working tree is dirty and `include_uncommitted` is set, the diff
    runs against the working tree rather than HEAD, so a developer running this
    locally selects for the code they are actually about to test.
    """
    args = ["diff", "--unified=0", "--no-color", "--find-renames", base]
    if not (include_uncommitted and is_dirty(root)):
        args.append("HEAD")
    return parse_diff(git(root, *args))
