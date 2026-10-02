<h1 align="center">tia</h1>

<p align="center">
  <strong>Run only the tests your change can actually affect.</strong><br>
  And run <em>everything</em> whenever that can't be proven safe.
</p>

<p align="center">
  <a href="https://pypi.org/project/tia-select/"><img alt="PyPI" src="https://img.shields.io/pypi/v/tia-select?color=2E7D62&label=pypi"></a>
  <a href="https://pypi.org/project/tia-select/"><img alt="Python" src="https://img.shields.io/pypi/pyversions/tia-select?color=2E7D62"></a>
  <a href="https://github.com/Tanmay-Singh-24/tia/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/Tanmay-Singh-24/tia/actions/workflows/ci.yml/badge.svg"></a>
  <a href="LICENSE"><img alt="Licence" src="https://img.shields.io/badge/licence-MIT-blue"></a>
  <br>
  <img alt="Misses" src="https://img.shields.io/badge/missed%20defects-0%20of%20211-2E7D62">
  <img alt="Suite time" src="https://img.shields.io/badge/test%20time-%E2%88%9265.2%25%20on%20scrapy-2E7D62">
</p>

---

You change one line. Your CI runs all 4,371 tests and you wait a minute. Maybe
thirty of those tests could possibly be touched by what you changed — the rest
examine the payment path, the CLI, the export code. They pass. They always
pass. They ran anyway.

tia watches your suite once to learn which tests touch which lines, then uses
that map to run just the affected ones. When it can't be sure, it runs
everything and tells you exactly why.

```console
$ tia select --explain

src/attr/_funcs.py line 377
  -> SELECTED: project source present in a fresh map; tests chosen by line
     tests/test_funcs.py::TestAsDict::test_dicts
     tests/test_funcs.py::TestAsDict::test_nested_lists
     tests/test_hooks.py::TestAsDictHook::test_asdict
     ... and 28 more

tia: selected 31 of 1,334 tests
```

```console
$ tia run
31 passed, 1381 deselected in 0.98s        # the full suite takes 3.93s
```

## Quick start

```bash
pip install tia-select
```

```bash
tia init     # create .tia.toml
tia build    # watch the suite once, build the map
tia run      # from now on, run only what matters
```

In CI, use the pytest plugin directly:

```bash
pytest --tia --tia-base=origin/main
```

That's it. Python 3.11+, works with any pytest suite.

## Does it actually work?

Fair question — that's the whole point of this project, so here are the
numbers rather than adjectives.

| | attrs | scrapy |
|---|---|---|
| Suite | 1,334 tests, 3.9 s | 4,371 tests, 62 s |
| Defects deliberately injected | 184 | 27 |
| **Defects it let through** | **0** | **0** |
| Test time saved | 58.4% | **65.2%** |
| Changes where it gave up and ran everything | 50.5% | 29.6% |

**It helps most where your suite is slow.** On scrapy's 62-second suite it
saves two thirds of the time. On a four-second suite it saves almost nothing,
because starting pytest at all is most of the cost. If your suite finishes in
seconds, you don't need this.

## It has let defects through before

Twice. Both were caught by its own evaluation harness, and both are written up
in full:

- **[D-0009](docs/DECISIONS.md)** — a test created its fixtures at import time,
  so coverage attributed the line to no test at all and six dependent tests
  were never selected.
- **[D-0014](docs/DECISIONS.md)** — the fix for D-0009 was itself too slow, so
  we added an import graph; the graph then re-opened the same hole. Found only
  when the sample went from 50 injected defects to 200.

That's why there's a fallback rate in the table above, and why ten of the
eighteen possible outcomes deliberately give up the speed benefit. A tool that is
fast but occasionally lets a bug through is worse than no tool, because it
manufactures confidence.

**[docs/SAFETY.md](docs/SAFETY.md)** says exactly what is and isn't guaranteed.
Please read it before using tia as a merge gate.

## How it works

**Watch once.** `tia build` runs your suite under `coverage.py` with dynamic
contexts, recording which tests executed which lines, and inverts that into a
map in `.tia/map.db`.

**Then ask.** On each change, git reports the changed lines, twelve rules
decide what can be trusted, and the map answers the rest. Anything uncertain —
a changed dependency, a config file, a stale map, a line that ran at import
time — runs the whole suite with a reason code you can read.

**Plus an import graph.** A line that executed during import belongs to no
test, so the map can't resolve it. The static import graph names the modules
that import the changed file and selects their tests instead — unless the
closure grows past 60% of the suite, at which point running everything is
cheaper than being clever.

## Commands

| | |
|---|---|
| `tia init` | write `.tia.toml`, create `.tia/` |
| `tia build` | watch the suite, build the map |
| `tia select` | show what would run — `--explain`, `--format json` |
| `tia run` | select, then run |
| `tia status` | map freshness, size, test count |
| `tia explain PATH:LINE` | which tests cover this line, and why |
| `pytest --tia` | the plugin form, for CI |

Exit codes: `0` success, `1` test failure, `2` usage error, `3` map unusable —
and `tia run` falls back to the full suite rather than failing, because a
broken map must never mean "no tests ran".

## The evidence

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

## Reproduce it yourself

```bash
git clone https://github.com/Tanmay-Singh-24/tia && cd tia
pip install -e ".[dev,eval]"
make reproduce
```

That clones the pinned corpus, rebuilds both maps and re-runs every experiment.
The repositories are pinned to exact commits, so the numbers above are the
numbers you get.

## Reading the repository

| | |
|---|---|
| **[docs/SAFETY.md](docs/SAFETY.md)** | what is guaranteed, what is not, how the risk is measured |
| **[docs/DECISIONS.md](docs/DECISIONS.md)** | 14 dated decisions, each with what would prove it wrong |
| **[docs/SPEC.md](docs/SPEC.md)** | the specification this implements |
| **[eval/results/](eval/results/)** | raw JSON behind every number published here |
| **[src/tia/classifier.py](src/tia/classifier.py)** | the twelve rules, in one readable file |

## Licence

MIT. Built as a B.Tech capstone project at VIT Bhopal.
