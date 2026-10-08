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
  <img alt="Misses" src="https://img.shields.io/badge/missed%20defects-0%20of%20213-2E7D62">
  <img alt="Suite time" src="https://img.shields.io/badge/test%20time-%E2%88%9266.9%25%20on%20scrapy-2E7D62">
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
tia init     # create .tia.toml, then commit it
tia build    # watch the suite once, build the map
tia run      # from now on, run only what matters
```

A map is valid for the exact commit and environment it was built in, so rebuild
it when your main branch moves; `tia status` tells you when it is stale, and
tia runs the whole suite rather than trust a stale one.

### In CI

Build the map once per commit on main, and let each pull request restore the
map for the commit it branches from:

```yaml
- uses: Tanmay-Singh-24/tia@v0.2.0
  with:
    mode: build        # on pushes to main
```

```yaml
- uses: Tanmay-Singh-24/tia@v0.2.0
  with:
    mode: test         # on pull requests; needs fetch-depth: 0
```

**[docs/CI.md](docs/CI.md)** has the complete workflow and the three things that
must line up. Python 3.11+, any pytest suite, tested on Linux, macOS and Windows.

## Does it actually work?

Fair question — that's the whole point of this project, so here are the
numbers rather than adjectives.

| | attrs | scrapy |
|---|---|---|
| Suite (full run, median) | 1,334 tests, 3.9 s | 4,371 tests, 53.5 s |
| Defects deliberately injected, detectable | 185 | 28 |
| **Defects it let through** | **0** | **0** |
| Test time saved, per change | 42.7% | **66.9%** |
| Changes where it gave up and ran everything | 50.3% | 28.6% |

**It helps most where your suite is slow.** The percentages look similar; the
seconds do not. On scrapy's 53-second suite, two-thirds saved is roughly half a
minute per change. On attrs' 4-second suite, 43% saved is under two seconds,
because starting pytest at all is a large part of the cost. If your suite
finishes in seconds, you don't need this.

## It has let defects through before

Twice. Both were caught by its own evaluation harness, and both are written up
in full:

- **[D-0009](docs/DECISIONS.md)** — a test created its fixtures at import time,
  so coverage attributed the line to no test at all and six dependent tests
  were never selected.
- **[D-0014](docs/DECISIONS.md)** — the fix for D-0009 was itself too slow, so
  we added an import graph; the graph then re-opened the same hole. Found only
  when the sample went from 50 injected defects to 200.

**And before calling it shippable, we went looking for more.** The published
experiment always built the map at exactly the commit it compared against, so
it could not see how tia behaves in real use. Auditing for that turned up ten
further ways it could silently skip a test that mattered — none of them
reachable by the experiment, all fixed in 0.2.0 with a test that failed on the
old code:

- a map built before `main` moved, looked up with shifted line numbers
  ([D-0016](docs/DECISIONS.md)) — reproduced as a real miss;
- a new test added in a pull request, never run ([D-0017](docs/DECISIONS.md));
- a changed test helper, whose users were dropped ([D-0017](docs/DECISIONS.md));
- new parametrisations, new doctests, and untracked test files
  ([D-0018](docs/DECISIONS.md));
- a map built under a different Python, platform or package version
  ([D-0019](docs/DECISIONS.md)).

That's why there's a fallback rate in the table above, and why eleven of the
nineteen possible outcomes deliberately give up the speed benefit. A tool that is
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
at 200 mutants (seed 2026), scrapy at 30 (seed 1234). Each pair replays one
fixed list of mutations and differs only in whether the import closure is
consulted. These are 0.2.0 measurements: the selection runs exactly what the
shipped tool runs.

| | attrs, no graph | attrs, graph | scrapy, no graph | scrapy, graph |
|---|---|---|---|---|
| Non-equivalent defects | 185 | 185 | 28 | 28 |
| **Misses** | **0** | **0** | **0** | **0** |
| Fallback frequency | 52.4% | 50.3% | 57.1% | 28.6% |
| Time saved per change | 41.9% | **42.7%** | 44.2% | **66.9%** |
| Selection precision, median | 50.0% | 50.0% | 31.2% | 11.2% |
| Selections holding every failing test | 84 / 87 | 88 / 91 | 11 / 12 | 15 / 20 |

**Zero misses in 213 non-equivalent injected defects** across two real
codebases — after the import graph was caught letting one through at 200
mutants and repaired (D-0014).

**Time saved is the mean share of the suite's time saved per change.** Each
change counts once, whether its suite run took 4 seconds or 291. An earlier
version of this table summed seconds instead, and one mutant that hung the
suite for 291 seconds inflated the attrs figure to 58.4%; the real figure is
about 43%. [D-0020](docs/DECISIONS.md) has the whole account.

**The import graph pays off in proportion to suite duration, not test count.**
On scrapy it halves the fallback rate and lifts the saving from 44.2% to 66.9%.
On attrs it is worth almost nothing — 42.7% against 41.9% — because the suite
takes four seconds and pytest's own startup is the floor.

**Precision is the honest cost of conservatism.** Of the tests tia selects, a
median of 50.0% actually fail on attrs and 11.2% on scrapy: it selects broadly
— every parametrisation of a chosen test, every test that imports a changed
module — and that breadth is what keeps the miss rate at zero. "No miss" is not
complete recall either: some selections held only some of the failing tests,
and still caught the defect.

Results: [`safety_attrs_2026-10-08T110119Z_seed2026_nograph_replay.json`](eval/results/safety_attrs_2026-10-08T110119Z_seed2026_nograph_replay.json), [`safety_attrs_2026-10-08T101628Z_seed2026_graph_replay.json`](eval/results/safety_attrs_2026-10-08T101628Z_seed2026_graph_replay.json),
[`safety_scrapy_2026-10-08T122932Z_seed1234_nograph_replay.json`](eval/results/safety_scrapy_2026-10-08T122932Z_seed1234_nograph_replay.json), [`safety_scrapy_2026-10-08T114237Z_seed1234_graph_replay.json`](eval/results/safety_scrapy_2026-10-08T114237Z_seed1234_graph_replay.json).

**Still unmeasured:** fallback frequency over real historical commits, a third
codebase, and whether 0.6 is the right closure limit. No published number moves
without the JSON that produced it.

## Reproduce it yourself

```bash
git clone https://github.com/Tanmay-Singh-24/tia && cd tia
python -m venv .venv && .venv/bin/pip install -e ".[dev,eval]"
make reproduce
```

That clones the pinned corpus, installs tia into it, rebuilds both maps,
**replays the exact injected defects** behind every row of the table above, and
checks the outcome against the published results. About 2.5 hours on an Apple
M4; `make reproduce-attrs` does attrs alone in about an hour.

It replays rather than re-sampling on purpose: sampling draws from the lines
the map records as covered, and a rebuilt map covers a slightly different set,
so the same seed would pick different mutants ([D-0013](docs/DECISIONS.md)).
What must match is whether each defect was caught — the miss count. Wall-clock
figures will differ on other hardware, and `make reproduce` says which is which
rather than leaving you to guess.

```console
$ make published          # the table as published, from eval/published.json
```

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
