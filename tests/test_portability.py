"""Things that only break on someone else's machine.

Found by the Windows CI job: an em dash in tia's own output is byte 0x97 in the
Windows console code page, so a caller decoding the output as UTF-8 failed —
and a character the code page lacks entirely can crash the print.
"""

from __future__ import annotations

import ast
from pathlib import Path

SOURCE = Path(__file__).resolve().parent.parent / "src" / "tia"


def _docstring_ids(tree: ast.AST) -> set[int]:
    ids: set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if not isinstance(body, list) or not body:
            continue
        first = body[0]
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)) and (
            isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
        ):
            ids.add(id(first.value))
        # attribute docstrings: a bare string straight after an assignment
        for prev, cur in zip(body, body[1:], strict=False):
            if isinstance(prev, (ast.Assign, ast.AnnAssign)) and isinstance(
                cur, ast.Expr
            ):
                ids.add(id(cur.value))
    return ids


def test_tias_own_output_is_ascii() -> None:
    offenders = []
    for path in sorted(SOURCE.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        documentation = _docstring_ids(tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in documentation
                and not node.value.isascii()
            ):
                offenders.append(f"{path.name}:{node.lineno} {node.value[:50]!r}")
    assert not offenders, "non-ASCII in output strings:\n" + "\n".join(offenders)
