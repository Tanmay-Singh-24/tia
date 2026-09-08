# tia — test impact analysis for Python

Run only the tests a change can affect. Run everything whenever that cannot be
established.

> **Status: working, pre-release.** Selection runs end to end. Safety
> validation at scale (defect injection across the corpus) is not finished, so
> the miss rate below is still `TBD` — see [Measured results](#measured-results)
> and [docs/SAFETY.md](docs/SAFETY.md).

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

## Getting started

```bash
tia init --package yourpackage   # write .tia.toml, create .tia/
tia build                        # run the suite once under instrumentation
tia select --explain             # see what a change selects, and why
tia run                          # run just those tests
```

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
tool. tia is conservative by construction: nine of the fourteen classifier
rules deliberately give up the speed benefit and run everything. How often that
happens is measured and published, not hidden.

Complete certainty is not attainable in a dynamically typed language and is not
claimed. **[docs/SAFETY.md](docs/SAFETY.md)** states exactly what is guaranteed,
what is not, and how the residual risk is measured rather than asserted. Read
it before using tia as a merge gate.

## Measured results

Every number here was produced by the harness on this machine (Apple M4, 10
cores, 16 GB, Python 3.12.10). Anything not yet measured says `TBD` rather than
something plausible.

**Corpus baselines** — median of 5 runs after a warmup, from
[`eval/results/`](eval/results/):

| repo | tests | `-n auto` | serial |
|---|---|---|---|
| scrapy | 5000 | 49.85 s | 204.85 s |
| attrs | 1412 | 2.30 s | 3.93 s |

**On attrs, one changed line** (`src/attr/_funcs.py`, single line edited):

| Metric | Value |
|---|---|
| Map build | 1334 tests, 42 files, 508,908 rows, 13.3 MB, ~10 s |
| Instrumentation slowdown | 2.2× (3.93 s → 8.55 s serial) |
| Tests selected | 31 of 1334 |
| Selected run | 0.82 s against a 3.93 s serial baseline |

**Safety, single injected defect** (`return False` → `return True` in
`attr._funcs.has`):

| | failures | wall clock |
|---|---|---|
| Full suite | 31 | 8.15 s |
| tia selection | 31 | 1.68 s |

No misses on that defect. That is one mutant, not an evaluation — the corpus-wide
figure is below and is not yet measured.

| Metric | Value | Source |
|---|---|---|
| Runtime reduction across the corpus | TBD | TBD |
| Selection ratio distribution | TBD | TBD |
| Selection precision | TBD | TBD |
| **Safety: misses / non-equivalent mutants** | **TBD** | TBD |
| Fallback frequency by reason code | TBD | TBD |
| p95 map lookup latency | TBD | TBD |

## Repository

- `docs/SPEC.md` — the specification this implementation follows.
- `docs/DECISIONS.md` — dated decision log with falsification conditions.
- `eval/` — the evaluation harness and its committed results.

## Licence

MIT.
