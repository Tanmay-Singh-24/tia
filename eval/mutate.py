"""Line-precise, deterministic defect injection (SPEC B.9).

Written rather than borrowed from mutmut or cosmic-ray, because those optimise
for covering the mutation space while this experiment needs the opposite: one
defect, at a line we choose, so the selector can be asked about exactly that
line.

Two design decisions matter.

**Surgical source edits, not `ast.unparse`.** Rewriting the tree and unparsing
it would reformat the whole module and move every line number in it. The diff
tia then sees would be the entire file rather than one line, and the experiment
would measure nothing useful. So mutations are applied as character-span
replacements located by AST node positions, leaving every other byte — and
every other line number — untouched.

**Bytecode caches are invalidated explicitly.** See D-0008. CPython validates a
cached .pyc against (source mtime in whole seconds, source size). Most single
site mutations preserve size, and a harness writes them well within one second,
so without this the mutant silently never runs, the suite passes, and the
harness records an equivalent mutant. That failure is invisible and it would
make the safety metric meaningless.
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import random
from dataclasses import dataclass
from pathlib import Path

# --- operator families (SPEC B.9) -----------------------------------------

COMPARISON_FLIP = {
    "<": "<=",
    "<=": "<",
    ">": ">=",
    ">=": ">",
    "==": "!=",
    "!=": "==",
}

ARITHMETIC_SWAP = {"+": "-", "-": "+", "*": "/", "/": "*"}

BOOLEAN_SWAP = {"and": "or", "or": "and"}

FAMILY_COMPARISON = "comparison_flip"
FAMILY_ARITHMETIC = "arithmetic_swap"
FAMILY_BOOLEAN = "boolean_negation"
FAMILY_CONSTANT = "constant_perturbation"
FAMILY_RETURN = "return_replacement"
FAMILY_CONDITIONAL = "conditional_forcing"


@dataclass(frozen=True)
class Mutation:
    """One defect: replace [col, end_col) on `lineno` of `path` with `after`."""

    path: str
    lineno: int
    col: int
    end_col: int
    family: str
    before: str
    after: str

    @property
    def label(self) -> str:
        return (
            f"{self.path}:{self.lineno} {self.family} {self.before!r}->{self.after!r}"
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "lineno": self.lineno,
            "family": self.family,
            "before": self.before,
            "after": self.after,
        }


def _line_span(lines: list[str], lineno: int, col: int, end_col: int) -> str:
    return lines[lineno - 1][col:end_col]


def _single_line(node: ast.AST) -> bool:
    """Only mutate spans that live on one line, so the diff stays one line."""
    start = getattr(node, "lineno", None)
    end = getattr(node, "end_lineno", None)
    return start is not None and start == end


def _between(left: ast.expr, right: ast.expr) -> tuple[int, int, int] | None:
    """The (lineno, col, end_col) span of the operator text between two nodes."""
    if left.end_lineno != right.lineno or left.end_col_offset is None:
        return None
    return left.end_lineno, left.end_col_offset, right.col_offset


def find_mutations(source: str, path: str) -> list[Mutation]:
    """Every mutation this file admits, in a stable order.

    Stable ordering matters: with a fixed seed the harness must pick the same
    site every time, or a published result cannot be reproduced.
    """
    tree = ast.parse(source)
    lines = source.splitlines()
    found: list[Mutation] = []

    # Python 3.12 gives the literal segments *inside* an f-string their own
    # Constant nodes with real positions. Mutating one rewrites part of the
    # format string and usually produces a SyntaxError, so they are excluded.
    inside_fstring: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.JoinedStr):
            for child in ast.walk(node):
                inside_fstring.add(id(child))

    def add(lineno: int, col: int, end_col: int, family: str, after: str) -> None:
        if (
            lineno < 1
            or lineno > len(lines)
            or col < 0
            or end_col > len(lines[lineno - 1])
        ):
            return
        before = _line_span(lines, lineno, col, end_col)
        if not before.strip() or before == after:
            return
        found.append(Mutation(path, lineno, col, end_col, family, before, after))

    for node in ast.walk(tree):
        # 1. comparison flip
        if isinstance(node, ast.Compare) and len(node.ops) == 1:
            span = _between(node.left, node.comparators[0])
            if span:
                lineno, start, stop = span
                text = _line_span(lines, lineno, start, stop).strip()
                offset = _line_span(lines, lineno, start, stop).index(text)
                if text in COMPARISON_FLIP:
                    add(
                        lineno,
                        start + offset,
                        start + offset + len(text),
                        FAMILY_COMPARISON,
                        COMPARISON_FLIP[text],
                    )

        # 2. arithmetic swap
        elif isinstance(node, ast.BinOp):
            span = _between(node.left, node.right)
            if span:
                lineno, start, stop = span
                raw = _line_span(lines, lineno, start, stop)
                text = raw.strip()
                if text in ARITHMETIC_SWAP:
                    offset = raw.index(text)
                    add(
                        lineno,
                        start + offset,
                        start + offset + len(text),
                        FAMILY_ARITHMETIC,
                        ARITHMETIC_SWAP[text],
                    )

        # 3. boolean negation: and <-> or
        elif isinstance(node, ast.BoolOp) and len(node.values) >= 2:
            span = _between(node.values[0], node.values[1])
            if span:
                lineno, start, stop = span
                raw = _line_span(lines, lineno, start, stop)
                text = raw.strip()
                if text in BOOLEAN_SWAP:
                    offset = raw.index(text)
                    add(
                        lineno,
                        start + offset,
                        start + offset + len(text),
                        FAMILY_BOOLEAN,
                        BOOLEAN_SWAP[text],
                    )

        # 4. constant perturbation
        elif (
            isinstance(node, ast.Constant)
            and _single_line(node)
            and id(node) not in inside_fstring
        ):
            col, end_col = node.col_offset, node.end_col_offset or 0
            value = node.value
            if isinstance(value, bool):
                add(
                    node.lineno,
                    col,
                    end_col,
                    FAMILY_CONSTANT,
                    "False" if value else "True",
                )
            elif isinstance(value, int):
                add(node.lineno, col, end_col, FAMILY_CONSTANT, str(value + 1))
            elif isinstance(value, str) and len(value) < 60 and '"""' not in value:
                add(node.lineno, col, end_col, FAMILY_CONSTANT, '"tia-mutant"')

        # 5. return value replacement
        elif isinstance(node, ast.Return) and node.value is not None:
            already_none = (
                isinstance(node.value, ast.Constant) and node.value.value is None
            )
            if (
                _single_line(node.value)
                and node.value.end_col_offset is not None
                and not already_none
            ):
                add(
                    node.value.lineno,
                    node.value.col_offset,
                    node.value.end_col_offset,
                    FAMILY_RETURN,
                    "None",
                )

        # 6. conditional forcing
        elif isinstance(node, ast.If) and _single_line(node.test):
            if node.test.end_col_offset is not None:
                for forced in ("True", "False"):
                    add(
                        node.test.lineno,
                        node.test.col_offset,
                        node.test.end_col_offset,
                        FAMILY_CONDITIONAL,
                        forced,
                    )

    # A mutation that cannot be parsed is not a defect, it is a typo. Dropping
    # them here keeps the experiment honest: every mutant the harness runs is
    # real code that the suite could in principle accept.
    valid = [m for m in found if _parses(apply_mutation(source, m))]

    # Stable, deterministic ordering: with a fixed seed the harness must pick
    # the same site every time, or a published result cannot be reproduced.
    valid.sort(key=lambda m: (m.lineno, m.col, m.family, m.after))
    return valid


def _parses(source: str) -> bool:
    try:
        ast.parse(source)
    except SyntaxError:
        return False
    return True


def apply_mutation(source: str, mutation: Mutation) -> str:
    """Return `source` with the mutation applied. Only one line changes."""
    lines = source.splitlines(keepends=True)
    index = mutation.lineno - 1
    line = lines[index]
    newline = ""
    if line.endswith("\n"):
        line, newline = line[:-1], "\n"
    mutated = line[: mutation.col] + mutation.after + line[mutation.end_col :]
    lines[index] = mutated + newline
    return "".join(lines)


def invalidate_bytecode(path: Path) -> None:
    """Delete the cached .pyc for a source file. See D-0008.

    Without this a same-size mutation written within one second of a warm cache
    is silently ignored: the interpreter validates the cache on (mtime seconds,
    size), both unchanged, and runs the old bytecode. The suite then passes and
    the mutant is misrecorded as equivalent.
    """
    cached = Path(importlib.util.cache_from_source(str(path)))
    cached.unlink(missing_ok=True)


def write_mutant(root: Path, mutation: Mutation, source: str) -> str:
    """Apply the mutation to disk and invalidate its bytecode. Returns the original."""
    target = root / mutation.path
    original = target.read_text(encoding="utf-8")
    target.write_text(apply_mutation(source, mutation), encoding="utf-8")
    invalidate_bytecode(target)
    return original


def restore(root: Path, mutation: Mutation, original: str) -> None:
    target = root / mutation.path
    target.write_text(original, encoding="utf-8")
    invalidate_bytecode(target)


def choose(
    mutations: list[Mutation], rng: random.Random, *, lines: set[int] | None = None
) -> Mutation | None:
    """Pick one mutation, optionally restricted to a set of covered lines."""
    candidates = (
        [m for m in mutations if m.lineno in lines] if lines is not None else mutations
    )
    return rng.choice(candidates) if candidates else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect or apply mutations.")
    parser.add_argument("file", type=Path)
    parser.add_argument("--line", type=int, help="only mutations on this line")
    parser.add_argument(
        "--apply", type=int, metavar="INDEX", help="apply one, print it"
    )
    args = parser.parse_args(argv)

    source = args.file.read_text(encoding="utf-8")
    mutations = find_mutations(source, str(args.file))
    if args.line:
        mutations = [m for m in mutations if m.lineno == args.line]

    if args.apply is not None:
        print(apply_mutation(source, mutations[args.apply]))
        return 0

    by_family: dict[str, int] = {}
    for mutation in mutations:
        by_family[mutation.family] = by_family.get(mutation.family, 0) + 1
        print(mutation.label)
    print(f"\n{len(mutations)} mutations: {by_family}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
