"""The map is only valid in the environment it was built in (D-0019).

Coverage records the code paths that actually ran, and those depend on the
Python version, the platform, and the versions of everything installed. A map
built on Linux under 3.12 knows nothing of a line reached only on Windows, or
only under a newer release of a dependency.
"""

from __future__ import annotations

from pathlib import Path

from tia.environment import differences, fingerprint, installed_from_inside

BUILT = {
    "python": "3.12",
    "platform": "linux",
    "packages": {"attrs": "23.1.0", "pytest": "8.4.1", "pytest-xdist": "3.8.0"},
}


def _with(**changes: object) -> dict[str, object]:
    current = {**BUILT, "packages": dict(BUILT["packages"])}  # type: ignore[arg-type]
    current.update(changes)
    return current


def test_the_same_environment_is_compatible() -> None:
    assert differences(BUILT, _with()) == []


def test_a_different_python_version_is_not() -> None:
    assert differences(BUILT, _with(python="3.11")) == ["Python 3.12 -> 3.11"]


def test_a_different_platform_is_not() -> None:
    assert differences(BUILT, _with(platform="win32")) == ["platform linux -> win32"]


def test_an_upgraded_dependency_is_not() -> None:
    packages = {**BUILT["packages"], "attrs": "23.2.0"}  # type: ignore[dict-item]
    assert differences(BUILT, _with(packages=packages)) == ["attrs 23.1.0 -> 23.2.0"]


def test_a_removed_dependency_is_not() -> None:
    packages = {k: v for k, v in BUILT["packages"].items() if k != "attrs"}  # type: ignore[attr-defined]
    assert differences(BUILT, _with(packages=packages)) == ["attrs 23.1.0 removed"]


def test_a_newly_installed_unrelated_package_is_compatible() -> None:
    """Installing ipython after building the map changes no code path the
    suite exercised, and refusing the map for it would make tia exhausting."""
    packages = {**BUILT["packages"], "ipython": "9.0"}  # type: ignore[dict-item]
    assert differences(BUILT, _with(packages=packages), plugins=set()) == []


def test_a_newly_installed_pytest_plugin_is_not() -> None:
    """A new pytest plugin can change how every test runs — reorder them, skip
    them, patch the environment — so it invalidates the map."""
    packages = {**BUILT["packages"], "pytest-randomly": "3.15"}  # type: ignore[dict-item]
    assert differences(
        BUILT, _with(packages=packages), plugins={"pytest-randomly"}
    ) == ["new pytest plugin pytest-randomly 3.15"]


def test_a_map_with_no_recorded_environment_is_not_trusted() -> None:
    assert differences(None, _with()) == ["the map records no environment"]


def test_fingerprint_describes_this_interpreter() -> None:
    import sys

    current = fingerprint()
    assert current["python"] == f"{sys.version_info.major}.{sys.version_info.minor}"
    assert current["platform"] == sys.platform
    assert "pytest" in current["packages"]
    assert "tia-select" not in current["packages"], "tia's own version must not count"


def test_the_project_under_test_is_not_part_of_the_environment(tmp_path: Path) -> None:
    """A git-versioned project reports a new version on every commit. Counting it
    would make every CI selection fall back."""
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    # as_uri() builds real file URLs, as pip writes them: file:///C:/... on
    # Windows. Formatting a path into "file://{path}" does not.
    inside = f'{{"url": "{repo.as_uri()}", "dir_info": {{"editable": true}}}}'
    nested = f'{{"url": "{(repo / "src").as_uri()}", "dir_info": {{}}}}'
    outside = f'{{"url": "{(tmp_path / "elsewhere").as_uri()}", "dir_info": {{}}}}'
    assert installed_from_inside(inside, repo)
    assert installed_from_inside(nested, repo)
    assert not installed_from_inside(outside, repo)
    assert not installed_from_inside('{"url": "https://pypi.org/x"}', repo)
    assert not installed_from_inside(None, repo)


def test_tia_excludes_this_repository_when_fingerprinting_it() -> None:
    """tia is installed editable from this very repository."""
    root = Path(__file__).resolve().parent.parent
    assert "tia-select" not in fingerprint(root)["packages"]
