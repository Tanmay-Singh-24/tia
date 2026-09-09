# What tia guarantees, and what it does not

This document exists because the honest version of this project's claim is
narrower than "tia is safe". Read the limitations section before relying on it.

## The failure that matters

A **miss** is a defect that the full suite catches and tia's selection does
not. Missing is the only unacceptable failure mode, because a tool that is fast
but occasionally lets a defect through is worse than no tool at all: it
manufactures confidence that is not warranted. Being slow is a cost. Being
wrong is a betrayal.

Everything below follows from that ordering.

## What is guaranteed

**1. tia never reduces what runs unless it can say why.**
Every decision carries a machine-readable reason code. There is no path through
`selector.select()` that returns a smaller set of tests without recording the
rule that permitted it. `tia select --explain` prints the chain from changed
line to covering test to reason.

**2. Uncertainty always resolves to the full suite.**
No map, a stale map, an unreadable map, a file the map has never seen, a git
command that fails, an unexpected exception in the classifier — every one of
these runs everything. The classifier is wrapped so that even a crash inside it
produces `CLASSIFIER_ERROR` and the full suite rather than a smaller selection.

**3. A broken tia costs time, never coverage.**
`pytest --tia` removes nothing if selection fails for any reason. If the
selection matches no collected test, the plugin runs the whole suite rather
than nothing — "0 tests passed" must never be the output of a tool whose job is
deciding what to skip.

**4. Changed tests always run.**
A new or edited test has never been observed by the map, so the map is not
consulted about it.

## The classifier — the guarantee in full

Every changed path is routed to exactly one outcome.

| Changed path | Outcome | Reason code |
|---|---|---|
| Test file, new or modified | Run those tests, without consulting the map | `TEST_CHANGED` |
| `conftest.py` | Run every test at or below that directory | `CONFTEST_CHANGED` |
| Project Python source, in the map, map fresh | Line-level selection | `SELECTED` |
| Project Python source, absent from the map | Full suite | `UNMAPPED_FILE` |
| `__init__.py` | File-level over the package, never line-level | `PACKAGE_INIT` |
| Lines inserted (no old-side coordinates) | File-level for that file | `INSERTION_NO_HISTORY` |
| Changed line only ever ran at import time | Full suite | `IMPORT_TIME_LINE` |
| `pyproject.toml`, `setup.cfg`, `setup.py`, `tox.ini`, `pytest.ini`, `.coveragerc` | Full suite | `BUILD_CONFIG_CHANGED` |
| `requirements*.txt`, `poetry.lock`, `uv.lock`, `Pipfile.lock` | Full suite | `DEPENDENCY_CHANGED` |
| Anything that is not a `.py` file | Full suite | `NON_SOURCE_ASSET` |
| Matches an `always_full` glob | Full suite | `USER_CONFIGURED` |
| Map commit is not an ancestor of the diff base | Full suite | `MAP_STALE` |
| No map exists | Full suite | `NO_MAP` |
| Classifier raised | Full suite | `CLASSIFIER_ERROR` |

Nine of these fourteen rows deliberately give up the speed benefit. That is the
design, not a shortfall in it. How often each fires is measured and published
as **fallback frequency**, because the honest cost of a conservative tool is
part of its description.

Note one deliberate deviation from the specification: SPEC B.6 enumerates asset
suffixes (`.json`, `.yaml`, `.sql`, `.html`, `.csv`). tia is stricter and
treats *every* non-`.py` path as an asset. Enumerating means the first unlisted
suffix — `.proto`, a `Makefile`, a `.pyx` — silently takes the fast path, and
that is precisely the shape of a silent miss.

## What is NOT guaranteed

**Complete certainty is not attainable in a dynamically typed language, and is
not claimed.** Python can load code by name at run time, replace behaviour
during execution, and dispatch through registries no analysis can see.

Specifically, tia can miss a defect when:

- **A dependency exists only through dynamic loading.** `importlib`, `getattr`
  dispatch, monkeypatching, entry points and plugin registries create real
  relationships that neither the map nor a static import graph observes. The
  map is built from lines that *actually executed*, which covers much of this
  in practice — but only for the paths that executed during the learning run.

- **A test's behaviour depends on state outside the repository.** Environment
  variables, clock, network, database contents, installed package versions.

- **A test was skipped during the learning run.** A skipped test executes no
  lines, so it contributes nothing to the map and cannot be selected by line.
  It is still run whenever its own file changes.

- **Coverage did not observe the relationship.** Code executed in a subprocess
  the coverage run did not instrument, or in a C extension, is invisible.

- **The map is out of date in a way `MAP_STALE` does not catch.** The staleness
  check is an ancestry test on commits. It does not detect a map built from a
  suite that was already failing, or one built with different environment
  variables than the selection run uses.

- **Test ordering or inter-test state matters.** tia selects a subset, which
  changes execution order. A suite with order-dependent tests can behave
  differently under selection. This is a property of the suite, but tia
  exposes it.

## How the residual risk is measured, not asserted

The claim "tia is safe" is not made. What is made is a measurement:

- Defects are injected one at a time at known lines.
- The full suite is run. If it passes, the mutant is *equivalent* and excluded.
- The selection is run. If it passes where the full suite failed, that is a
  **miss**.
- The reported figure is `misses / non-equivalent mutants`, per repository.

A single miss is a failure of the core guarantee and is root-caused
individually in the report rather than averaged away.

**Current status — attrs, 50 mutants, seed 1234**
([`eval/results/safety_attrs_2026-09-08T231235Z_seed1234.json`](../eval/results/safety_attrs_2026-09-08T231235Z_seed1234.json)):

| | |
|---|---|
| Mutants generated | 50 |
| Equivalent (excluded) | 3 |
| Non-equivalent | 47 |
| **Misses** | **0** |
| Fell back to the full suite | 28 of 47 (59.6%), all `IMPORT_TIME_LINE` |
| Selection ratio, when selecting | median 0.7% (min 0.08%, max 99.9%) |
| Full suite / selected, median | 3.97 s / 0.30 s |

Read those two middle rows together. Zero misses is the result that matters,
but it is bought by giving up line-level selection on **60% of changes** to this
codebase. tia is safe here and, on well over half of these changes, no faster
than simply running everything.

**Second repository — scrapy, 17 mutants** (a partial run, stopped early;
`complete: false` in the JSON): 14 non-equivalent, **0 misses**, and **7 of 14
(50%) fell back**, again every one `IMPORT_TIME_LINE`. Median selection ratio
0.39%; full suite 45.95 s against 2.62 s for the selection. The fallback rate
is the same story at 5,000 tests as at 1,400.

**These figures are two repositories, one run each, and one of them partial.** It is not a claim about
your codebase, and it is not enough mutants to put a confidence interval on.
The corpus-wide result at 200+ mutants per repository is not yet measured.

**An earlier run of this same experiment found a real miss** — one in 46 — and
the fallback rule above is what fixes it. The root cause is written out in full
in `docs/DECISIONS.md` under D-0009. It is worth reading before trusting any of
this: it is a concrete example of a dependency that the map genuinely could not
see.

## If you are deciding whether to use this

Use `tia run` locally to shorten the edit-test loop, where a miss costs you one
extra CI cycle. Before relying on it as a merge gate, read the published
fallback frequency and miss rate for a codebase resembling yours, and keep a
full-suite run somewhere in your pipeline — nightly, or on the merge commit.
tia is a way to get feedback sooner, not a replacement for having run your
tests.
