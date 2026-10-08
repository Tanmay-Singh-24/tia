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

**4. Tests the map has never seen still run.**
A test written in this change has never been observed, so the map is never
asked about it. A changed test file runs whole, including tests added to it; a
changed `conftest.py` runs everything at or below its directory; a new
parametrisation of a selected test runs, because selection is by test function;
a new doctest in a changed file runs; and a test file not yet `git add`-ed is
part of the change.

**5. The map is used only where it is valid.**
A map describes one commit in one environment. It is used only when it was
built at *exactly* the commit this change branches from — not merely an earlier
one, because once `main` moves the same line number can name different code —
and under the same Python version, platform and installed package versions.
Otherwise it is refused, and the reason names what differed. `tia build`
refuses to build from uncommitted Python edits, which would stamp HEAD's commit
on someone else's line numbers.

**6. An empty answer is never a selection.**
Any rule that resolves to no recorded test — a line the map holds nothing for,
a package whose files were never measured — widens or falls back. "No test
reaches this" is ignorance, not proof that nothing needs to run.

## The classifier — the guarantee in full

The map must first pass two checks: built at exactly this change's branch point
(`MAP_STALE` otherwise), and in this environment (`ENVIRONMENT_CHANGED`
otherwise). Then every changed path is routed to exactly one outcome.

| Changed path | Outcome | Reason code |
|---|---|---|
| Matches an `always_full` glob | Full suite | `USER_CONFIGURED` |
| `conftest.py` | Everything at or below that directory, including unseen tests | `CONFTEST_CHANGED` |
| Test module (`test_*.py`, `*_test.py`), new or modified | That whole file, including unseen tests | `TEST_CHANGED` |
| `requirements*.txt`, `poetry.lock`, `uv.lock`, `Pipfile.lock` | Full suite | `DEPENDENCY_CHANGED` |
| `pyproject.toml`, `setup.cfg`, `setup.py`, `tox.ini`, `pytest.ini`, `.coveragerc` | Full suite | `BUILD_CONFIG_CHANGED` |
| Anything that is not a `.py` file | Full suite | `NON_SOURCE_ASSET` |
| `__init__.py` | File-level over the package | `PACKAGE_INIT` |
| Python file absent from the map, or deleted | Full suite | `UNMAPPED_FILE` |
| Lines inserted (no old-side coordinates) | File-level for that file | `INSERTION_NO_HISTORY` |
| Changed line also ran at import time | Tests of every file that imports it | `IMPORT_CLOSURE` |
| ...and that set exceeds 60% of the suite | Full suite | `CLOSURE_TOO_LARGE` |
| ...and the map has no import graph | Full suite | `IMPORT_TIME_LINE` |
| Changed line the map holds nothing for | File-level for that file | `LINE_NOT_IN_MAP` |
| Project source in the map | Line-level selection | `SELECTED` |
| Any of the above that reaches no recorded test | Full suite | `UNMAPPED_FILE` |
| Map built at a different commit | Full suite | `MAP_STALE` |
| Map built in a different environment | Full suite | `ENVIRONMENT_CHANGED` |
| No map exists | Full suite | `NO_MAP` |
| Classifier raised | Full suite | `CLASSIFIER_ERROR` |

Eleven of the nineteen outcomes deliberately give up the speed benefit. That is
the design, not a shortfall in it. How often each fires is measured and
published as **fallback frequency**, because the honest cost of a conservative
tool is part of its description.

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
  variables, clock, network, database contents. (Python version, platform and
  installed package versions *are* checked — see guarantee 5.)

- **A test was skipped during the learning run.** A skipped test executes no
  lines, so it contributes nothing to the map and cannot be selected by line.
  It is still run whenever its own file changes.

- **Coverage did not observe the relationship.** Code executed in a subprocess
  the coverage run did not instrument, or in a C extension, is invisible.

- **The map was built from a suite in a state the change does not share.**
  The map is pinned to a commit and an environment, but not to environment
  variables, the clock, or a suite that was already failing when it was built.

- **A test module has a non-default name.** Only `test_*.py` and `*_test.py`
  are recognised as test modules. A project that collects tests from other
  names (a custom `python_files`) has them treated as source — which falls
  back to the full suite rather than missing anything, at the cost of speed.

- **An untracked file other than a test module or `conftest.py` matters.**
  Locally, untracked test files are part of the change; other untracked files
  are not, because counting every stray file would make tia run everything. A
  test that discovers files by globbing a directory can be affected by one.

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

**Current status — both corpus repositories**

| | attrs, no graph | attrs, graph | scrapy, no graph | scrapy, graph |
|---|---|---|---|---|
| Non-equivalent defects | 184 | 184 | 27 | 27 |
| **Misses** | **0** | **0** | **0** | **0** |
| Fallback frequency | 52.7% | 50.5% | 59.3% | 29.6% |
| Net time reduction | 57.0% | **58.4%** | 40.4% | **65.2%** |
| Selection precision, median | 62.5% | 55.2% | 25.0% | 9.8% |
| Selections holding every failing test | 85/87 | 87/91 | 11/11 | 14/19 |

Zero misses in 211 non-equivalent injected defects. That is the result the tool
exists for, and it is worth saying what it cost: on roughly three changes in ten
to scrapy and one in two to attrs, tia runs the whole suite and saves nothing.

**An earlier version of the import graph let a defect through** — 1 miss in 184,
found only when the sample was raised from 50 to 200. Two independent faults,
the first fix insufficient. D-0014 has the full account. It is the clearest
evidence in this project that a safety claim is worth exactly as much as the
experiment that could have falsified it.

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
