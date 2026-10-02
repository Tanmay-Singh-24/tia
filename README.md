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

**Safety validation across both corpus repositories.** One defect injected at
a time; the full suite must catch it or the mutant is excluded as equivalent;
then the selection runs. If the selection passes where the full suite failed,
that is a miss.

| | attrs | scrapy |
|---|---|---|
| Tests in the suite | 1,334 | 4,371 |
| Baseline suite time | 3.93 s | 62.6 s |
| Non-equivalent mutants | 47 | 27 |
| **Misses** | **0** | **0** |
| Fallback, without the import graph | 59.6% | 59.3% |
| Fallback, with it | **51.1%** | **29.6%** |
| Net time reduction, without | 46.2% | 38.8% |
| Net time reduction, with | **50.7%** | **66.3%** |

Each pair is one map, one seed and one set of mutation sites, differing only in
whether the import closure is consulted — see D-0012 and D-0013 in
[docs/DECISIONS.md](docs/DECISIONS.md) for why that control matters, and for
two earlier measurements it invalidated.

Results: [`safety_attrs_2026-10-02T133350Z_seed1234_graph.json`](eval/results/safety_attrs_2026-10-02T133350Z_seed1234_graph.json), [`safety_attrs_2026-10-02T132005Z_seed1234_nograph.json`](eval/results/safety_attrs_2026-10-02T132005Z_seed1234_nograph.json),
[`safety_scrapy_2026-10-02T144233Z_seed1234_graph.json`](eval/results/safety_scrapy_2026-10-02T144233Z_seed1234_graph.json), [`safety_scrapy_2026-10-02T135205Z_seed1234_nograph.json`](eval/results/safety_scrapy_2026-10-02T135205Z_seed1234_nograph.json).

**What the numbers say.** Zero misses on 74 non-equivalent mutants across two
real codebases. The import graph roughly halves the fallback rate on scrapy and
takes its net saving to 66.3%; on attrs the gain is modest, because a
four-second suite leaves almost nothing to save once pytest's own startup is
paid. Benefit tracks absolute suite duration — not test count, and not closure
size.

**Still unmeasured:** selection precision, fallback frequency over real
historical commits, and safety at 200+ mutants per repository. No published
number moves without the JSON that produced it.

## Repository

- `docs/SPEC.md` — the specification this implementation follows.
- `docs/DECISIONS.md` — dated decision log with falsification conditions.
- `eval/` — the evaluation harness and its committed results.

## Licence

MIT.
