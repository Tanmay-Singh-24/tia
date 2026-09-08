"""The defect injector (SPEC B.9, task D8).

A mutator that silently produces a non-mutation would make the whole safety
experiment report a perfect score over nothing, so these tests check the two
properties the experiment depends on: the mutation is real and lands on exactly
one line, and the choice is reproducible from a seed.
"""

from __future__ import annotations

import ast
import importlib.util
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))

from mutate import (  # noqa: E402
    FAMILY_ARITHMETIC,
    FAMILY_BOOLEAN,
    FAMILY_COMPARISON,
    FAMILY_CONDITIONAL,
    FAMILY_CONSTANT,
    FAMILY_RETURN,
    apply_mutation,
    choose,
    find_mutations,
    invalidate_bytecode,
    write_mutant,
)

SAMPLE = """\
def compare(a, b):
    if a < b:
        return True
    return False


def arithmetic(a, b):
    return a + b


def boolean(a, b):
    return a and b


def constants():
    return 41


def flag():
    return True
"""


def families(source: str) -> set[str]:
    return {m.family for m in find_mutations(source, "sample.py")}


def test_all_six_operator_families_are_produced() -> None:
    found = families(SAMPLE)
    assert FAMILY_COMPARISON in found
    assert FAMILY_ARITHMETIC in found
    assert FAMILY_BOOLEAN in found
    assert FAMILY_CONSTANT in found
    assert FAMILY_RETURN in found
    assert FAMILY_CONDITIONAL in found


def test_every_mutation_changes_exactly_one_line() -> None:
    """The selector is asked about one line. The diff must be one line."""
    original = SAMPLE.splitlines()
    for mutation in find_mutations(SAMPLE, "sample.py"):
        mutated = apply_mutation(SAMPLE, mutation).splitlines()
        assert len(mutated) == len(original), mutation.label
        differing = [
            i for i, (a, b) in enumerate(zip(original, mutated, strict=True)) if a != b
        ]
        assert differing == [mutation.lineno - 1], mutation.label


def test_every_mutation_still_parses() -> None:
    """A mutation that breaks the syntax is a typo, not a defect."""
    for mutation in find_mutations(SAMPLE, "sample.py"):
        ast.parse(apply_mutation(SAMPLE, mutation))


def test_every_mutation_actually_changes_the_source() -> None:
    for mutation in find_mutations(SAMPLE, "sample.py"):
        assert apply_mutation(SAMPLE, mutation) != SAMPLE, mutation.label


def test_comparison_flip_is_correct() -> None:
    flips = [
        m for m in find_mutations(SAMPLE, "sample.py") if m.family == FAMILY_COMPARISON
    ]
    assert flips
    assert flips[0].before == "<"
    assert flips[0].after == "<="
    assert "if a <= b:" in apply_mutation(SAMPLE, flips[0])


def test_fstring_internals_are_never_mutated() -> None:
    """Python 3.12 gives f-string literal segments real positions. Leave them."""
    source = 'def f(exc):\n    return f"{type(exc).__name__}: {exc}"\n'
    for mutation in find_mutations(source, "s.py"):
        ast.parse(apply_mutation(source, mutation))
        assert mutation.before not in {": ", ": {"}


def test_choice_is_reproducible_from_a_seed() -> None:
    """A published safety result has to be replayable."""
    mutations = find_mutations(SAMPLE, "sample.py")
    first = choose(mutations, random.Random(1234))
    second = choose(mutations, random.Random(1234))
    assert first == second
    assert first is not None


def test_choice_can_be_restricted_to_covered_lines() -> None:
    mutations = find_mutations(SAMPLE, "sample.py")
    picked = choose(mutations, random.Random(7), lines={2})
    assert picked is not None
    assert picked.lineno == 2


def test_choice_returns_none_when_no_site_is_covered() -> None:
    mutations = find_mutations(SAMPLE, "sample.py")
    assert choose(mutations, random.Random(7), lines={9999}) is None


def test_write_mutant_invalidates_bytecode(tmp_path: Path) -> None:
    """D-0008: without this a same-size mutation is silently ignored."""
    target = tmp_path / "m.py"
    target.write_text("def f():\n    return 1 + 2\n")
    cached = Path(importlib.util.cache_from_source(str(target)))
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_bytes(b"stale")

    mutation = next(
        m
        for m in find_mutations(target.read_text(), "m.py")
        if m.family == FAMILY_ARITHMETIC
    )
    write_mutant(tmp_path, mutation, target.read_text())

    assert not cached.exists(), "the stale .pyc must be gone"
    assert "1 - 2" in target.read_text()


def test_invalidate_bytecode_is_safe_when_absent(tmp_path: Path) -> None:
    target = tmp_path / "nothing.py"
    target.write_text("x = 1\n")
    invalidate_bytecode(target)  # must not raise


@pytest.mark.parametrize("family", [FAMILY_RETURN, FAMILY_CONDITIONAL])
def test_families_land_on_the_expected_construct(family: str) -> None:
    mutations = [m for m in find_mutations(SAMPLE, "sample.py") if m.family == family]
    assert mutations
    for mutation in mutations:
        line = SAMPLE.splitlines()[mutation.lineno - 1]
        assert ("return" in line) if family == FAMILY_RETURN else ("if " in line)
