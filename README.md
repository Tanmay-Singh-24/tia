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

```bash
pip install tia-select
```

Requires Python 3.11+. The command is `tia`; the distribution is `tia-select`
because `tia` was taken. Installing also registers the pytest plugin, so
`pytest --tia` works straight away.

From a clone, for development or to run the evaluation:

```bash
pip install -e ".[dev,eval]"
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

**Safety validation.** One defect injected at a time; the full suite must catch
it or the mutant is excluded as equivalent; then the selection runs. If the
selection passes where the full suite failed, that is a **miss**. attrs was run
at 200 mutants (seed 2026), scrapy at 30 (seed 1234). Each pair shares one map
and one set of mutation sites and differs only in whether the import closure is
consulted.

| | attrs, no graph | attrs, graph | scrapy, no graph | scrapy, graph |
|---|---|---|---|---|
| Non-equivalent defects | 184 | 184 | 27 | 27 |
| **Misses** | **0** | **0** | **0** | **0** |
| Fallback frequency | 52.7% | 50.5% | 59.3% | 29.6% |
| Net time reduction | 57.0% | **58.4%** | 40.4% | **65.2%** |
| Selection precision, median | 62.5% | 55.2% | 25.0% | 9.8% |
| Selections holding every failing test | 85/87 | 87/91 | 11/11 | 14/19 |

**Zero misses in 211 non-equivalent injected defects** across two real
codebases — after the import graph was caught letting one through at 200
mutants and repaired (D-0014).

**The import graph pays off in proportion to suite duration, not test count.**
On scrapy, whose suite takes 52 s, it halves the fallback rate and lifts the
saving from 40.4% to 65.2%. On attrs, whose suite takes 3.9 s, it is worth
almost nothing — 58.4% against 57.0% — because pytest's own startup is the
floor and there is nothing left to buy.

**Precision is the honest cost of conservatism.** A median of 55.2% on attrs
and 9.8% on scrapy: the closure selects broadly, and many selected tests do not
fail. That is what keeps the miss rate at zero. Note also that "no miss" is not
complete recall — on scrapy, 14 of 19 selections contained *every* failing test;
the others caught the defect with only some of them.

Results: [`safety_attrs_2026-10-02T161902Z_seed2026_nograph.json`](eval/results/safety_attrs_2026-10-02T161902Z_seed2026_nograph.json),
[`safety_attrs_2026-10-02T174240Z_seed2026_graph.json`](eval/results/safety_attrs_2026-10-02T174240Z_seed2026_graph.json),
[`safety_scrapy_2026-10-02T191409Z_seed1234_nograph.json`](eval/results/safety_scrapy_2026-10-02T191409Z_seed1234_nograph.json),
[`safety_scrapy_2026-10-02T182614Z_seed1234_graph.json`](eval/results/safety_scrapy_2026-10-02T182614Z_seed1234_graph.json).

**Still unmeasured:** fallback frequency over real historical commits, a third
codebase, and whether 0.6 is the right closure limit. No published number moves
without the JSON that produced it.

## Repository

- `docs/SPEC.md` — the specification this implementation follows.
- `docs/DECISIONS.md` — dated decision log with falsification conditions.
- `eval/` — the evaluation harness and its committed results.

## Licence

MIT.
