"""Static import graph (SPEC B.8).

Why this exists, concretely. The map answers "which tests executed this line".
It cannot answer that for a line that ran while a module was being imported,
because coverage attributes import-time execution to no test at all — so
`IMPORT_TIME_LINE` surrenders and runs the whole suite. Measured on the corpus,
that single rule accounted for **every** fallback and fired on 50-60% of
changes. The import graph is what turns "I cannot tell, run everything" into
"these are the modules that import you, run their tests".

What it can and cannot see, stated plainly because the report must not
overclaim: this reads `import` and `from ... import` statements out of the
source with `ast`. It sees nothing of `importlib.import_module`, `getattr`
dispatch, monkeypatching, entry points or plugin registries. The line-level map
partly compensates, because it records what actually executed rather than what
the source appears to say. Neither mechanism is complete, and `docs/SAFETY.md`
says so.
"""

from __future__ import annotations

import ast
from collections import deque
from dataclasses import dataclass
from pathlib import Path

__all__ = ["ImportGraph", "build", "infer_source_roots", "module_name_for"]


def module_name_for(path: str, source_roots: list[str]) -> str | None:
    """The dotted module name a repo-relative POSIX path would be imported as.

    `src/attr/_funcs.py` under source root `src` is `attr._funcs`; a package
    `__init__.py` is the package itself.
    """
    for root in sorted(source_roots, key=len, reverse=True):
        prefix = root.rstrip("/") + "/"
        if root and not path.startswith(prefix):
            continue
        rest = path[len(prefix) :] if root else path
        if not rest.endswith(".py"):
            return None
        parts = rest[: -len(".py")].split("/")
        if parts and parts[-1] == "__init__":
            parts.pop()
        return ".".join(parts) if parts else None
    return None


def infer_source_roots(root: Path, paths: list[str]) -> list[str]:
    """Work out the import roots from the layout, when none are configured.

    A file's package root is the first ancestor directory that is *not* itself
    a package. For `src/tia/db.py`, `src/tia/` has an `__init__.py` and `src/`
    does not, so the import root is `src` and the module is `tia.db`. Getting
    this wrong is silent: every module name comes out prefixed with `src.`,
    nothing resolves, and the graph is simply empty.
    """
    roots: set[str] = set()
    for path in paths:
        parts = path.split("/")[:-1]
        while parts and (root / "/".join(parts) / "__init__.py").exists():
            parts.pop()
        roots.add("/".join(parts))
    return sorted(roots)


def _imports_in(source: str) -> set[tuple[str, int]]:
    """Every (module, relative level) this source imports.

    A syntax error yields nothing rather than raising: a graph that refuses to
    build because one file in the repository is unparseable is useless, and the
    caller falls back to the whole suite anyway.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()

    found: set[tuple[str, int]] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add((alias.name, 0))
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                found.add((node.module, node.level))
            # `from . import thing` names no module; the package itself is the
            # dependency, and `thing` may be a submodule of it.
            for alias in node.names:
                joined = f"{node.module}.{alias.name}" if node.module else alias.name
                found.add((joined, node.level))
    return found


def _resolve(module: str, level: int, package: list[str]) -> str:
    """Resolve a relative import against the importing module's package.

    `package` is the importer's containing package, already split. The
    distinction that matters: inside `pkg/api.py` a level-1 import means `pkg`,
    but inside `pkg/__init__.py` it also means `pkg` — so the caller works out
    the package, because only it knows whether the file is a package __init__.
    """
    if level == 0:
        return module
    base = package[: len(package) - (level - 1)] if level > 1 else package
    return ".".join([*base, module]) if module else ".".join(base)


@dataclass(frozen=True)
class ImportGraph:
    """Which project files import which other project files."""

    importers: dict[str, frozenset[str]]
    """imported path -> the paths that import it directly."""

    @property
    def files(self) -> frozenset[str]:
        seen: set[str] = set()
        for imported, importing in self.importers.items():
            seen.add(imported)
            seen |= importing
        return frozenset(seen)

    def closure(self, path: str) -> frozenset[str]:
        """Every file that transitively imports `path`, including `path`.

        Breadth-first over the reverse edges, with a visited set, so an import
        cycle terminates rather than spinning.
        """
        seen = {path}
        queue = deque([path])
        while queue:
            current = queue.popleft()
            for importer in self.importers.get(current, frozenset()):
                if importer not in seen:
                    seen.add(importer)
                    queue.append(importer)
        return frozenset(seen)

    def edges(self) -> list[tuple[str, str]]:
        """(importer, imported) pairs, for persistence."""
        return [
            (importer, imported)
            for imported, importing in sorted(self.importers.items())
            for importer in sorted(importing)
        ]


def build(root: Path, paths: list[str], source_roots: list[str]) -> ImportGraph:
    """Build the reverse import graph over the given repo-relative paths."""
    roots = source_roots or infer_source_roots(root, paths) or [""]

    # module name -> file, so an import can be resolved back to a project file.
    by_module: dict[str, str] = {}
    for path in paths:
        name = module_name_for(path, roots)
        if name:
            by_module.setdefault(name, path)

    importers: dict[str, set[str]] = {}
    for path in paths:
        importer_module = module_name_for(path, roots)
        if importer_module is None:
            continue
        # A package's __init__ *is* its package; any other module lives inside
        # its parent package.
        parts = importer_module.split(".") if importer_module else []
        package = parts if path.endswith("__init__.py") else parts[:-1]
        try:
            source = (root / path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        for module, level in _imports_in(source):
            resolved = _resolve(module, level, package)
            target = by_module.get(resolved)
            if target is None and "." in resolved:
                # `from pkg.mod import name` resolves to pkg.mod when `name` is
                # not itself a module.
                target = by_module.get(resolved.rsplit(".", 1)[0])
            if target is not None and target != path:
                importers.setdefault(target, set()).add(path)

    return ImportGraph({k: frozenset(v) for k, v in importers.items()})
