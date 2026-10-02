"""The import graph is a supplement to the map, not a foundation. These tests
pin what it does see — and one that pins what it deliberately does not.
"""

from __future__ import annotations

from pathlib import Path

from tia.importgraph import build, module_name_for


def write(root: Path, path: str, source: str) -> str:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(source, encoding="utf-8")
    return path


def test_module_name_for_strips_the_source_root() -> None:
    assert module_name_for("src/attr/_funcs.py", ["src"]) == "attr._funcs"
    assert module_name_for("src/attr/__init__.py", ["src"]) == "attr"
    assert module_name_for("pkg/core.py", [""]) == "pkg.core"
    assert module_name_for("src/attr/data.json", ["src"]) is None


def test_direct_import_is_recorded(tmp_path: Path) -> None:
    paths = [
        write(tmp_path, "src/pkg/__init__.py", ""),
        write(tmp_path, "src/pkg/core.py", "VALUE = 1\n"),
        write(tmp_path, "src/pkg/api.py", "from pkg.core import VALUE\n"),
    ]
    graph = build(tmp_path, paths, ["src"])
    assert graph.importers["src/pkg/core.py"] == frozenset({"src/pkg/api.py"})


def test_relative_import_resolves_against_the_package(tmp_path: Path) -> None:
    paths = [
        write(tmp_path, "src/pkg/__init__.py", ""),
        write(tmp_path, "src/pkg/core.py", "VALUE = 1\n"),
        write(tmp_path, "src/pkg/api.py", "from .core import VALUE\n"),
    ]
    graph = build(tmp_path, paths, ["src"])
    assert "src/pkg/api.py" in graph.importers["src/pkg/core.py"]


def test_closure_is_transitive(tmp_path: Path) -> None:
    paths = [
        write(tmp_path, "src/pkg/__init__.py", ""),
        write(tmp_path, "src/pkg/core.py", "VALUE = 1\n"),
        write(tmp_path, "src/pkg/middle.py", "from pkg.core import VALUE\n"),
        write(tmp_path, "src/pkg/top.py", "from pkg.middle import VALUE\n"),
        write(tmp_path, "src/pkg/unrelated.py", "X = 2\n"),
    ]
    graph = build(tmp_path, paths, ["src"])
    closure = graph.closure("src/pkg/core.py")
    assert closure == frozenset(
        {"src/pkg/core.py", "src/pkg/middle.py", "src/pkg/top.py"}
    )
    assert "src/pkg/unrelated.py" not in closure


def test_import_cycle_terminates(tmp_path: Path) -> None:
    paths = [
        write(tmp_path, "src/pkg/__init__.py", ""),
        write(tmp_path, "src/pkg/a.py", "from pkg import b\n"),
        write(tmp_path, "src/pkg/b.py", "from pkg import a\n"),
    ]
    graph = build(tmp_path, paths, ["src"])
    assert "src/pkg/b.py" in graph.closure("src/pkg/a.py")


def test_unparseable_file_does_not_break_the_graph(tmp_path: Path) -> None:
    paths = [
        write(tmp_path, "src/pkg/__init__.py", ""),
        write(tmp_path, "src/pkg/core.py", "VALUE = 1\n"),
        write(tmp_path, "src/pkg/broken.py", "def (((\n"),
        write(tmp_path, "src/pkg/api.py", "from pkg.core import VALUE\n"),
    ]
    graph = build(tmp_path, paths, ["src"])
    assert "src/pkg/api.py" in graph.importers["src/pkg/core.py"]


def test_dynamic_import_is_invisible(tmp_path: Path) -> None:
    """The honest limitation, pinned as a test so the report cannot drift.

    A module loaded by name at run time creates a real dependency that this
    graph cannot see. SAFETY.md states this; here it is, demonstrated.
    """
    paths = [
        write(tmp_path, "src/pkg/__init__.py", ""),
        write(tmp_path, "src/pkg/core.py", "VALUE = 1\n"),
        write(
            tmp_path,
            "src/pkg/dynamic.py",
            "import importlib\nmod = importlib.import_module('pkg.core')\n",
        ),
    ]
    graph = build(tmp_path, paths, ["src"])
    assert "src/pkg/dynamic.py" not in graph.importers.get(
        "src/pkg/core.py", frozenset()
    )


def test_third_party_imports_are_ignored(tmp_path: Path) -> None:
    paths = [
        write(tmp_path, "src/pkg/__init__.py", ""),
        write(tmp_path, "src/pkg/api.py", "import os\nimport pytest\n"),
    ]
    graph = build(tmp_path, paths, ["src"])
    assert graph.importers == {}
