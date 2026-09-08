"""diff.py against real git repositories (SPEC B.5, task D5).

Every test here builds an actual repository and runs actual git. The cases are
the ones the SPEC calls out plus the ones that have historically broken this
kind of tool: pure insertions, renames, deletions, binaries and merges.
"""

from __future__ import annotations

from pathlib import Path

from tia.diff import (
    STATUS_ADDED,
    STATUS_DELETED,
    STATUS_RENAMED,
    changed_lines,
    head_commit,
    is_ancestor,
    parse_diff,
    repo_root,
    resolve_base,
)

NUMBERED = "".join(f"line{n}\n" for n in range(1, 11))


def only(changes: list, path: str):
    matches = [c for c in changes if c.path == path]
    assert matches, f"{path} not in {[c.path for c in changes]}"
    return matches[0]


def test_repo_root_and_head(git_repo: Path, commit) -> None:
    assert repo_root(git_repo) == git_repo.resolve()
    assert len(head_commit(git_repo)) == 40


def test_single_line_edit_uses_old_side_numbers(git_repo: Path, commit) -> None:
    (git_repo / "mod.py").write_text(NUMBERED)
    base = commit("add")
    (git_repo / "mod.py").write_text(NUMBERED.replace("line5\n", "CHANGED\n"))
    commit("edit line 5")

    change = only(changed_lines(git_repo, base), "mod.py")
    assert change.old_lines == frozenset({5})
    assert not change.insertions


def test_multi_line_edit(git_repo: Path, commit) -> None:
    (git_repo / "mod.py").write_text(NUMBERED)
    base = commit("add")
    edited = NUMBERED.replace("line4\n", "A\n").replace("line5\n", "B\n")
    (git_repo / "mod.py").write_text(edited)
    commit("edit 4 and 5")

    assert only(changed_lines(git_repo, base), "mod.py").old_lines == frozenset({4, 5})


def test_pure_insertion_is_flagged_not_guessed(git_repo: Path, commit) -> None:
    """Inserted lines have no old-side coordinate. We must say so, not invent one."""
    (git_repo / "mod.py").write_text(NUMBERED)
    base = commit("add")
    (git_repo / "mod.py").write_text(NUMBERED.replace("line5\n", "line5\nNEW\n"))
    commit("insert after 5")

    change = only(changed_lines(git_repo, base), "mod.py")
    assert change.insertions is True
    # The straddling old lines are a hint only.
    assert change.old_lines == frozenset({5, 6})


def test_pure_deletion(git_repo: Path, commit) -> None:
    (git_repo / "mod.py").write_text(NUMBERED)
    base = commit("add")
    (git_repo / "mod.py").write_text(NUMBERED.replace("line5\n", ""))
    commit("delete line 5")

    change = only(changed_lines(git_repo, base), "mod.py")
    assert 5 in change.old_lines
    assert not change.insertions


def test_new_file_has_no_old_lines(git_repo: Path, commit) -> None:
    base = head_commit(git_repo)
    (git_repo / "brand_new.py").write_text("x = 1\n")
    commit("add file")

    change = only(changed_lines(git_repo, base), "brand_new.py")
    assert change.status == STATUS_ADDED
    assert change.old_lines == frozenset()


def test_deleted_file(git_repo: Path, commit) -> None:
    (git_repo / "gone.py").write_text(NUMBERED)
    base = commit("add")
    (git_repo / "gone.py").unlink()
    commit("delete file")

    change = only(changed_lines(git_repo, base), "gone.py")
    assert change.status == STATUS_DELETED


def test_rename_with_edit_maps_back_to_the_old_path(
    git_repo: Path, commit, run_git
) -> None:
    """The map knows the file by its old name. Lookups must use that name."""
    (git_repo / "old_name.py").write_text(NUMBERED)
    base = commit("add")
    run_git("mv", "old_name.py", "new_name.py")
    (git_repo / "new_name.py").write_text(NUMBERED.replace("line2\n", "EDIT\n"))
    commit("rename and edit")

    change = only(changed_lines(git_repo, base), "new_name.py")
    assert change.status == STATUS_RENAMED
    assert change.old_path == "old_name.py"
    assert change.lookup_path == "old_name.py"


def test_binary_file(git_repo: Path, commit) -> None:
    (git_repo / "blob.bin").write_bytes(bytes(range(256)))
    base = commit("add binary")
    (git_repo / "blob.bin").write_bytes(bytes(range(255, -1, -1)))
    commit("change binary")

    change = only(changed_lines(git_repo, base), "blob.bin")
    assert change.binary is True


def test_merge_commit(git_repo: Path, commit, run_git) -> None:
    (git_repo / "mod.py").write_text(NUMBERED)
    base = commit("add")
    run_git("checkout", "-q", "-b", "side")
    (git_repo / "side.py").write_text("side = 1\n")
    commit("side work")
    run_git("checkout", "-q", "main")
    (git_repo / "mod.py").write_text(NUMBERED.replace("line1\n", "MAIN\n"))
    commit("main work")
    run_git("merge", "-q", "--no-ff", "side", "-m", "merge side")

    paths = {c.path for c in changed_lines(git_repo, base)}
    assert {"mod.py", "side.py"} <= paths


def test_uncommitted_changes_are_included(git_repo: Path, commit) -> None:
    """Developers run this on dirty trees; the selection must cover the edit."""
    (git_repo / "mod.py").write_text(NUMBERED)
    base = commit("add")
    (git_repo / "mod.py").write_text(NUMBERED.replace("line3\n", "DIRTY\n"))

    change = only(changed_lines(git_repo, base), "mod.py")
    assert change.old_lines == frozenset({3})


def test_uncommitted_ignored_when_disabled(git_repo: Path, commit) -> None:
    (git_repo / "mod.py").write_text(NUMBERED)
    base = commit("add")
    (git_repo / "mod.py").write_text(NUMBERED.replace("line3\n", "DIRTY\n"))

    assert changed_lines(git_repo, base, include_uncommitted=False) == []


def test_merge_base_is_the_branch_point(git_repo: Path, commit, run_git) -> None:
    branch_point = head_commit(git_repo)
    run_git("checkout", "-q", "-b", "feature")
    (git_repo / "f.py").write_text("f = 1\n")
    commit("feature work")

    assert resolve_base(git_repo, "main") == branch_point
    assert is_ancestor(git_repo, branch_point, head_commit(git_repo))
    assert not is_ancestor(git_repo, head_commit(git_repo), branch_point)


def test_parse_diff_handles_single_line_hunk_without_count() -> None:
    """`@@ -7 +7 @@` means one line, not zero."""
    changes = parse_diff(
        "diff --git a/m.py b/m.py\n--- a/m.py\n+++ b/m.py\n@@ -7 +7 @@\n-old\n+new\n"
    )
    assert changes[0].old_lines == frozenset({7})
