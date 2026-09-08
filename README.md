# tia — test impact analysis for Python

Run only the tests a change can affect. Run everything whenever that cannot be
established.

> **Status: pre-alpha.** The CLI surface is declared; the selection logic is not
> implemented yet. `pytest --tia` currently runs the full suite and says so.
> No performance or safety numbers are published yet — see
> [Measured results](#measured-results).

## What it does

1. **Learning (once).** Runs the suite under `coverage.py` with dynamic contexts
   and persists, for every source line, the set of tests that executed it. The
   map lives in `.tia/map.db`, keyed to the commit it was built at.
2. **Selection (every change).** Asks git which lines changed, classifies each
   changed path, looks the trustworthy ones up in the map, and hands pytest that
   subset. Everything else falls back to the full suite with a reason code.

The selection logic is meant to be read, not trusted: `tia select --explain`
prints the chain from changed line to covering test to reason code.

## Install

Not published yet. From a clone:

```bash
pip install -e ".[dev,eval]"
```

Requires Python 3.11+.

## Usage

```
tia init                     write .tia.toml, create .tia/, add to .gitignore
tia build [--suite CMD] [--jobs N]     run the instrumented suite, build the map
tia select [--base REV] [--format nodeids|json] [--explain]
tia run [--base REV] -- <pytest args>
tia status                   map freshness, commit, size, test count, age
tia explain PATH:LINE        which tests cover this line, and why
pytest --tia [--tia-base=REV]          plugin form, for CI
```

Exit codes: `0` success, `1` test failure, `2` usage error, `3` map unusable.

## Safety

A tool that is fast but occasionally lets a defect through is worse than no
tool. tia is conservative by construction: test files, `conftest.py`,
dependency and build-config changes, non-source assets, unmapped files, a stale
map and a missing map all fall back to the full suite, each with a machine
readable reason code. How often that happens is measured and published, not
hidden.

Complete certainty is not attainable in a dynamically typed language and is not
claimed. See `docs/SAFETY.md` (written at D9) for what is guaranteed and what
is not.

## Measured results

Nothing here until the harness produces it. Every number published in this
README will link to the committed JSON under `eval/results/` that produced it.

| Metric | Value | Source |
|---|---|---|
| Runtime reduction (median) | TBD | TBD |
| Selection ratio | TBD | TBD |
| Selection precision | TBD | TBD |
| Safety: misses / non-equivalent mutants | TBD | TBD |
| Fallback frequency by reason code | TBD | TBD |
| Map build slowdown, size, p95 lookup | TBD | TBD |

## Repository

- `docs/SPEC.md` — the specification this implementation follows.
- `docs/DECISIONS.md` — dated decision log with falsification conditions.
- `eval/` — the evaluation harness and its committed results.

## Licence

MIT.
