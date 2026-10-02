# Decision log

Every non-obvious decision gets an entry here, dated, in the form:
**context → options considered → decision → how we would know it was wrong.**

This file is the primary review-defence artefact. A decision without a
falsification condition is an opinion, not an engineering decision.

---

## D-0000 — Template (copy this, do not delete it)

**Date:** YYYY-MM-DD · **Area:** subsystem · **Status:** proposed | accepted | superseded by D-XXXX

**Context.** What forced a choice. What was true at the time. Include the
measurement that prompted it, if there was one.

**Options considered.**
1. *Option A* — what it buys, what it costs.
2. *Option B* — what it buys, what it costs.
3. *Option C* — what it buys, what it costs.

**Decision.** What we did, in one sentence, and the single reason that decided it.

**How we would know this was wrong.** The concrete observation that would send
us back here — a measured threshold, a failure mode, a corpus result. Not
"if it turns out badly".

**Evidence.** Command output, or a path under `eval/results/`. `TBD` if the
decision was made ahead of measurement, in which case say when it gets measured.

---

## D-0001 — Packaging and toolchain for the skeleton

**Date:** 2026-09-08 · **Area:** repo/build · **Status:** accepted

**Context.** D1 needs a repository layout that survives to PyPI publication in
week 15 without a rename or a restructure. Two things had to be settled before
any code: the distribution name (the import name `tia` is taken on PyPI by an
unrelated package, and the Review 2 deliverable text already says
`pip install tia-select`), and the build backend.

**Options considered.**
1. *setuptools + setup.cfg* — universally understood, but needs explicit
   package-discovery configuration for a src-layout and a separate version
   declaration.
2. *hatchling* — PEP 621 only, reads the version straight out of
   `src/tia/__init__.py`, one-line src-layout config, no plugins needed.
3. *poetry* — good dependency resolution, but a non-standard `[tool.poetry]`
   table and a lockfile we do not need for a library-shaped CLI.

**Decision.** hatchling, distribution name `tia-select`, import name and console
script `tia`. Version is single-sourced from `src/tia/__init__.py`, so the
`tia --version` output, the wheel metadata and the `tia_version` key written
into the map (SPEC B.4 `meta`) cannot drift apart.

**How we would know this was wrong.** If `pip install tia-select` from a clean
venv fails in week 15, or if the console script and the wheel report different
versions, or if hatchling forces a plugin dependency for something we later
need (e.g. shipping data files with the wheel). Any of those sends us back to
setuptools, which is a mechanical change to one file.

**Evidence.** `pip install -e ".[dev,eval]"` and `tia --version` both run in
this repo; see the D1 session output. PyPI names checked 2026-09-08:

```
$ curl -s -o /dev/null -w "%{http_code}" https://pypi.org/pypi/tia/json
200                     # taken by an unrelated package
$ curl -s -o /dev/null -w "%{http_code}" https://pypi.org/pypi/tia-select/json
404                     # free
```

`tia-select` is unclaimed as of today but is **not reserved**; a placeholder
release is uploaded well before week 15 rather than assuming it stays free.

---

## D-0002 — Unimplemented commands exit 2, and the plugin stays inert

**Date:** 2026-09-08 · **Area:** CLI/plugin · **Status:** accepted

**Context.** The full CLI surface (SPEC B.7) is declared in D1, weeks before
most of it works. Stubs can behave in three ways, and the choice interacts
directly with invariant 1 (silent misses are the only unacceptable failure).

**Options considered.**
1. *Do not declare a command until it works* — no misleading surface, but the
   option names churn as subsystems land, and CI integration cannot be written
   against a moving target.
2. *Stub exits 0 with a message* — friendly, but a stubbed `tia run` exiting 0
   is a tool reporting success without running tests. That is exactly the
   failure mode this project exists to prevent, and it would be dishonest in
   a script.
3. *Stub exits 2 (usage error) with a message naming the milestone.*

**Decision.** Option 3 for the CLI. For the pytest plugin the rule is
different and stricter: `pytest --tia` registers the flags but filters nothing,
prints a one-line notice on stderr, and runs the **entire** suite. A tia that
cannot select must never reduce what is executed.

**How we would know this was wrong.** If a stub ever exits 0, or if
`pytest --tia` collects fewer tests than plain `pytest` before D7 lands, this
decision has been violated. `tests/test_plugin.py` asserts both.

**Evidence.** `tests/test_cli.py::test_command_is_a_stub_that_exits_two` and
`tests/test_plugin.py::test_tia_flag_runs_the_full_suite_for_now`.

---

## D-0003 — Corpus checkouts are blobless partial clones, not shallow clones

**Date:** 2026-09-08 · **Area:** eval/corpus · **Status:** accepted

**Context.** D2 says "shallow-clone at a pinned SHA". A `--depth 1` clone is the
cheapest way to get a working tree, but it discards history — and two later
milestones need history on these same checkouts: D5 resolves `git merge-base`
against an upstream branch, and the fallback-frequency experiment (SPEC B.9,
metric 5) samples N real historical commits per repo. Re-cloning the corpus at
week 10 would break the pinning story, because the repositories will have moved
and the results already published would no longer be reproducible from the
committed `corpus.yaml`.

**Options considered.**
1. *`--depth 1`* — smallest and fastest, but no merge-base, no historical
   commits, and unshallowing later is a second full network fetch.
2. *Full clone* — everything works, but pays for every blob of every revision
   on six repositories, on a machine with 10 GiB free.
3. *Blobless partial clone* (`--filter=blob:none`) — every commit and tree,
   file contents fetched on demand at checkout.

**Decision.** Option 3. `git clone --filter=blob:none --no-checkout` followed by
`git checkout --detach <pinned sha>`. History is intact for D5 and for commit
sampling; only the blobs actually checked out are transferred.

**How we would know this was wrong.** If a partial clone makes later git
operations pay repeated network round trips (a `git log -p` over sampled
commits would), or if the corpus directory grows past what the disk allows, we
switch to full clones of a smaller corpus. The check is cheap: time the
historical-commit sampling in week 10 and compare against a full clone of one
repo.

**Evidence.** Corpus disk usage after preparation is recorded in the D2 session
output and in `eval/results/baseline_*.json`.

---

## D-0004 — Corpus selection: scrapy and attrs

**Date:** 2026-09-09 · **Area:** eval/corpus · **Status:** accepted

**Context.** SPEC B.9 lists six candidates and four criteria: pure Python,
1,000+ tests, green at a pinned SHA, and a suite short enough to iterate on.
All six were cloned, installed and measured on this machine (Apple M4, 10
cores, 16 GB, macOS 15.6, Python 3.12.10) before anything was chosen. Every
figure below is from `eval/results/baseline_<repo>_2026-09-08.json`.

| repo | tests | green | `-n auto` median | serial median | note |
|---|---|---|---|---|---|
| scrapy | 5000 | yes | 49.85 s | 204.85 s | 5 live-network tests deselected |
| httpx | 1418 | **no** | **deadlocks** | 5.17 s | stalls at ~86% under xdist |
| attrs | 1412 | yes | 2.30 s | 3.93 s | |
| rich | 981 | **no** | 3.06 s | 3.76 s | 8 failures, Pygments drift |
| black | 558 | yes | 6.48 s | 22.76 s | |
| flask | 494 | yes | 1.00 s | 0.66 s | parallel is *slower* |

**Options considered.**
1. *attrs + httpx* — the two repos with ~1,400 tests each. Rejected: httpx is
   red at the pinned SHA (one `PytestUnraisableExceptionWarning` promoted to an
   error by its own `filterwarnings = error`) and, more seriously, deadlocks
   under `-n auto`, so it cannot supply the parallel baseline SPEC B.9 requires.
2. *attrs + rich* — both small and fast. Rejected: rich is red (8 failures in
   syntax/markdown rendering, caused by a newer Pygments than the pinned commit
   expects), and neither suite exceeds four seconds.
3. *scrapy + attrs* — one large, realistic suite and one small, fast one.

**Decision.** scrapy as the primary corpus repository and attrs as the
secondary, for complementary reasons rather than similar ones:

- **scrapy** is the only candidate whose suite is long enough for absolute
  savings to mean anything (204.85 s serial, 49.85 s under `-n auto`). At 5,000 tests it also exercises the
  scale question in SPEC B.4 — millions of `coverage_line` rows — which no
  other candidate reaches.
- **attrs** is the development corpus. The safety experiment runs the suite
  twice per mutant; at 3.9 s that is roughly 30 minutes for 200 mutants, against
  something like 14 hours on scrapy. Iterating on scrapy alone would make the
  evaluation harness unusable during development.

black is held in reserve as a third repo for Review 2.

**How we would know this was wrong.** If scrapy's map turns out not to build
under instrumentation within a tolerable time (SPEC B.3 warns of a 2–5×
slowdown, so expect roughly 10–17 minutes), or if its heavy use of Twisted and
deferred execution makes per-test coverage contexts unreliable, scrapy is
replaced by black and the corpus loses its large repo. That check happens in D4
and is the first thing to run there, not the last.

**Evidence.** `eval/results/baseline_*.json`, all committed.

---

## D-0005 — `-n auto` is not automatically the optimised baseline

**Date:** 2026-09-09 · **Area:** eval/methodology · **Status:** accepted

**Context.** SPEC B.9 requires that the baseline be "properly optimised" and
names `pytest -n auto`, on the reasoning that beating a deliberately slow
baseline is the cheapest way to lose credibility. The measurements contradict
that rule at small suite sizes. On flask, `-n auto` takes 1.00 s against 0.66 s
serial — the parallel baseline is **1.5× slower**, because ten worker processes
cost more to start than the work they remove. attrs shows the same effect
weakly (1.71× rather than the ~8× the core count would suggest), while black,
whose tests are genuinely CPU-bound, gets 3.51×.

**Options considered.**
1. *Always report `-n auto`, as written.* Simple, but on flask it would let tia
   claim a speedup that is partly just the baseline being handicapped.
2. *Always report serial.* Would inflate every speedup number — precisely the
   credibility problem SPEC B.9 warns about.
3. *Report both, and define the baseline per repo as the faster of the two.*

**Decision.** Option 3. Both modes are measured and both are stored in every
results JSON. The headline reduction for a repo is computed against whichever
mode is faster on that repo, and the report names which one it was.

**How we would know this was wrong.** If a reviewer can point to a repo where
the faster-of-two rule flatters tia — for example if selection interacts badly
with xdist scheduling so that a selected run is slower in parallel while the
baseline is taken from the parallel mode. The guard is that the selected run
must be timed in the same mode as the baseline it is compared against, and the
harness will enforce that rather than leaving it to whoever writes the table.

**Evidence.** flask 1.002 s (`-n auto`) vs 0.661 s (serial); attrs 2.299 vs
3.930; black 6.484 vs 22.759. All in `eval/results/baseline_*.json`.

---

## D-0006 — Test count is a poor proxy for suite substance

**Date:** 2026-09-09 · **Area:** eval/methodology · **Status:** accepted

**Context.** SPEC B.9's corpus criterion is "1,000+ tests". The measurements
show that number does not track what this project actually reduces. black has
558 tests and a 22.76 s serial suite; attrs has 1,412 tests and a 3.93 s one.
By test count black is disqualified and attrs is comfortable; by the thing tia
exists to shorten, black is nearly six times the target.

**Options considered.**
1. *Keep the test-count criterion as the gate.* Consistent with the SPEC, but
   selects on a number that does not correspond to the benefit.
2. *Replace it with baseline runtime.* Better aligned, but drops the scale
   pressure that a large test count puts on the map (row counts, lookup
   latency).
3. *Keep both, and say which one each repo satisfies.*

**Decision.** Option 3. Test count is retained because SPEC B.4's scale
question is about rows in `coverage_line`, which scales with tests × covered
lines. Baseline runtime is added as a separate, equally binding criterion,
because it is what the runtime-reduction metric is computed from. A repo is
described as satisfying one, the other, or both — never as simply "qualifying".

**How we would know this was wrong.** If the eventual runtime reduction turns
out to correlate with test count rather than with baseline runtime across the
corpus, this framing is backwards and the report should say so. That
correlation is checkable once the tool works, and is worth checking: "which
codebase properties predict the benefit" is exactly the characterisation the
proposal commits to producing.

**Evidence.** black 558 tests / 22.76 s vs attrs 1412 tests / 3.93 s, in
`eval/results/baseline_black_2026-09-08.json` and
`eval/results/baseline_attrs_2026-09-08.json`.

---

## D-0007 — Coverage spike: contexts, phases, import-time lines, xdist

**Date:** 2026-09-09 · **Area:** instrumentation · **Status:** accepted

**Context.** Everything downstream assumes coverage.py's dynamic contexts give
us per-test line attribution in a form we can feed back to pytest. The proposal
flags parallel instrumentation as a risk. Run on attrs (1412 tests) at the
pinned SHA before any mapper code was written.

**What was measured.**

1. **Context format.** `pytest --cov=attr --cov=attrs --cov-context=test`
   produces contexts that are pytest nodeids with a phase suffix:

   ```
   'tests/test_abc.py::TestUpdateAbstractMethods::test_abc_implementation[True]|run'
   'tests/test_funcs.py::TestAsDict::test_shallow|setup'
   'tests/test_make.py::TestAttributes::test_pre_post_init_order[True]|teardown'
   ```

   Over 1367 contexts: 1333 `|run`, 17 `|setup`, 16 `|teardown`, and exactly
   one empty context `''`. Parametrised ids survive intact, so the strings feed
   straight back to pytest with no translation. This confirms the SPEC's
   preference for the pytest-cov route over `dynamic_context`.

2. **xdist.** Under `-n auto`, pytest-cov combines the per-worker data files
   automatically and **contexts survive**: 1368 contexts with the same suffix
   distribution (one extra `|setup`, from a fixture that runs once per worker).
   The documented fallback to sequential map construction is not needed.

3. **Instrumented slowdown.** attrs serial 3.93 s → 8.55 s (**2.2×**); `-n auto`
   2.30 s → 5.13 s (**2.2×**). Within the SPEC's predicted 2–5×. On scrapy this
   projects to roughly 110 s parallel for a map build, which is acceptable for a
   once-per-map cost.

4. **Paths.** `CoverageData.measured_files()` returns absolute, fully resolved
   paths (`/Users/.../repo/src/attr/_make.py`). They must be made relative to
   the repo root and POSIX-normalised on the way into the map, exactly as SPEC
   B.3 warns.

5. **Import-time lines.** In `src/attr/_make.py`, 371 of 1700 covered lines
   appear **only** in the empty context — executed at import, attributable to no
   single test.

**Decision.** Strip at the `|`, and keep setup and teardown coverage: a fixture
touching a line is a genuine dependency. Store paths relative to the repo root.
Import-time-only lines are the interesting case: a change to one cannot be
attributed to any test, and a test may import a module without executing any
other line in it, so selecting "tests that touched this file" would be unsound.
Such a change therefore falls back to the full suite under a dedicated reason
code, `IMPORT_TIME_LINE`.

**How we would know this was wrong.** If `IMPORT_TIME_LINE` turns out to
dominate the fallback-frequency breakdown — plausible, since a third of covered
lines in this module are import-time — the conservatism is too expensive and the
Phase 2 import graph becomes load-bearing rather than an enhancement. The
measurement that decides it is the fallback breakdown in D8, and the number to
watch is what fraction of real commits touch only import-time lines.

**Evidence.** Commands and their real output are in this session; the
instrumented timings are reproducible with
`pytest --cov=attr --cov=attrs --cov-context=test` in the attrs corpus checkout.

---

## D-0008 — Mutants must explicitly invalidate bytecode caches

**Date:** 2026-09-09 · **Area:** eval/safety · **Status:** accepted

**Context.** Found while writing the end-to-end test that injects a defect and
checks the selection catches it. The test failed: the full suite passed on a
mutated file. The mutation had been written correctly — reading the file back
showed `return a - b` — and the tests still passed.

CPython validates a cached `.pyc` against two properties of the source: its
**mtime in whole seconds** and its **size in bytes**. A mutation that changes
neither is invisible. Single-site mutation operators produce exactly this case
constantly: `==` → `!=`, `+` → `-`, `<` → `>` all preserve length, and a
harness generating mutants in a loop writes them well inside one second.

Measured, with the mutation applied immediately after a warm `.pyc`:

| mutation | outcome |
|---|---|
| same size, same second | **missed** — stale bytecode, suite passes |
| different size (padded) | caught |
| same size, mtime bumped +10s | caught |
| same size, after a 1.1 s wait | caught |

**Why this is dangerous rather than merely annoying.** The safety experiment
(SPEC B.9 metric 4) runs the full suite on each mutant and **excludes the
mutant from the denominator when the full suite passes**, on the grounds that
it must be equivalent. A mutant that never took effect is indistinguishable
from an equivalent one. Every silently-ineffective mutant would therefore be
quietly dropped, and the reported miss rate would be computed over mutations
that never happened. The metric would look perfect and mean nothing — the exact
failure this project exists to argue against.

**Options considered.**
1. *`PYTHONDONTWRITEBYTECODE=1`* — necessary but **not sufficient**: it stops
   Python writing caches, not reading a stale one that already exists.
2. *Pad mutants to change file size* — corrupts the experiment: the mutation is
   no longer the only difference.
3. *Sleep or bump mtime* — works, but relies on a side effect rather than
   saying what is meant, and a bumped mtime is still only second-granular.
4. *Delete the cached `.pyc` explicitly after writing each mutant.*

**Decision.** Option 4, with option 1 alongside. Every write of a mutant
unlinks `importlib.util.cache_from_source(path)`, and every subprocess in the
evaluation runs with `PYTHONDONTWRITEBYTECODE=1` so no fresh stale cache can
appear mid-experiment. `eval/mutate.py` must use this when it is written in D8;
it is not optional, and it is not a detail.

**How we would know this was wrong.** If the D8 safety run reports an
implausibly high equivalent-mutant rate, suspect this first. A cheap standing
check: for a sample of mutants, assert that at least one test *changes outcome*
between the clean tree and the mutant. A mutant that changes nothing anywhere
should be rare, not common.

**Evidence.**
`tests/test_end_to_end.py::test_same_size_mutation_is_invisible_without_invalidation`
forces the stale condition deterministically (writing the mutant at the
original file's exact mtime) and asserts both halves: missed while the cache
stands, caught once it is invalidated.

---

## D-0009 — A measured miss: lines that execute both at import time and inside tests

**Date:** 2026-09-09 · **Area:** classifier/mapper · **Status:** accepted

**Context.** The first safety run on attrs (50 mutants, seed 1234) produced
**one miss in 46 non-equivalent mutants**. This entry is the root cause of that
single miss, written out in full because a miss is a failure of the core
guarantee and averaging it into a rate would be exactly the dishonesty this
project exists to avoid.

**The mutant.** `src/attr/_cmp.py:88`, `if ge is not None:` forced to
`if True:`. The full suite caught it — six failures, all in `tests/test_cmp.py`:

```
FAILED tests/test_cmp.py::TestEqOrder::test_ge_same_type[PartialOrderCSameType]
FAILED tests/test_cmp.py::TestEqOrder::test_ge_same_type[PartialOrderCAnyType]
FAILED tests/test_cmp.py::TestEqOrder::test_ge_different_type[PartialOrderCAnyType]
FAILED tests/test_cmp.py::TestEqOrder::test_not_lt_same_type[PartialOrderCSameType]
FAILED tests/test_cmp.py::TestEqOrder::test_not_lt_same_type[PartialOrderCAnyType]
FAILED tests/test_cmp.py::TestDundersPartialOrdering::test_ge
```

tia selected **two** tests, and neither was among them:

```
$ tia explain src/attr/_cmp.py:88
src/attr/_cmp.py:88 — 2 tests executed this line:
  tests/test_cmp.py::TestNotImplementedIsPropagated::test_not_implemented_is_propagated
  tests/test_cmp.py::TestTotalOrderingException::test_eq_must_specified
```

**Root cause.** Line 88 lives inside `cmp_using()`, and `tests/test_cmp.py`
calls that function **at module level**:

```python
# tests/test_cmp.py:15
PartialOrderCSameType = cmp_using(..., class_name="PartialOrderCSameType")
```

That call runs during collection, before any test starts, so coverage.py
attributes the execution to the empty import-time context and to no test. The
only executions attributed to tests were the two that call `cmp_using` inside a
test body. The six tests that genuinely depend on the line established that
dependency at import time and therefore never appear as covering it.

D-0007 had already identified import-time lines as unattributable and added the
`IMPORT_TIME_LINE` fallback — but the rule only fired for lines with **no** test
contexts at all. A line executed both at import time *and* inside a couple of
tests looked perfectly mappable, and was not. The gap was the word "only".

**Options considered.**
1. *Attribute import-time lines to every test in the module that imported them.*
   Unsound in the other direction: a test can import a module without executing
   any other line of it, so this both over-selects and still misses.
2. *Treat any line with an import-time execution as unresolvable and fall back.*
   Conservative, cheap to implement, costs speed on genuinely shared lines.
3. *Wait for the Phase 2 import graph to resolve it properly.* Leaves a known
   miss in place for weeks, on a guarantee that is the whole thesis.

**Decision.** Option 2. The map now records import-time lines in their own table
(`import_time_line`, schema v2), and the classifier falls back with
`IMPORT_TIME_LINE` when **any** changed line ever executed at import time —
whether or not tests also covered it. Because a v1 map cannot answer that
question, `migrate()` refuses it outright rather than using it with a silent
hole; the caller treats that as an unusable map and runs everything.

**How we would know this was wrong.** If `IMPORT_TIME_LINE` comes to dominate
the fallback breakdown, the rule is too blunt and costs more speed than the
safety is worth on that codebase. attrs records 1,704 import-time line
executions, so the pressure is real. The number to watch is the share of
`IMPORT_TIME_LINE` in fallback frequency; the escape hatch, if it is too high,
is the Phase 2 import graph, which can name the modules that imported a file
and select their tests rather than everything.

**Evidence.** The post-fix run is committed under `eval/results/`. The rule is
pinned by four cases in `tests/test_classifier.py`, including one asserting
that import-time lines *elsewhere* in the file do not block selection.

**A missing artefact, stated plainly.** The pre-fix run's JSON no longer
exists. Results were keyed on the date alone, so re-running the experiment on
the same day overwrote the very file it was meant to be compared against. That
harness bug is fixed — filenames now carry a timestamp and the seed, and each
payload records the tia version and commit — but the original file is gone, and
this project does not get to cite evidence it cannot produce. The miss is
reproducible from source: check out the parent of the commit that introduced
this rule, rebuild the map, and apply the mutation quoted above. The command
output in this entry was captured from that reproduction, not reconstructed.

**The cost, measured immediately.** The re-run at seed 1234 gives 0 misses in
47 non-equivalent mutants — and **28 of those 47 (59.6%) fall back, every one
of them `IMPORT_TIME_LINE`**. The falsification condition written above fired on
the very next run. The rule is correct and it is expensive; on attrs it is now
the only thing preventing line-level selection in the majority of cases. This
is the strongest argument yet that the Phase 2 import graph is load-bearing
rather than an enhancement, and it should be presented as a finding, not
buried: a conservative tool that gives up 60% of the time has an honest cost,
and that cost is the headline of this experiment.

---

## D-0010 — Insertion handling: inserted lines are not resolvable, and we say so

**Date:** 2026-09-09 · **Area:** diff/classifier · **Status:** accepted

**Context.** The map speaks the line numbers of the commit it was built at. A
diff hunk header `@@ -old_start,old_count +new_start,new_count @@` with
`old_count == 0` describes lines that exist only on the new side. They have no
old-side coordinate, so there is nothing to look up. This is the case a panel
will probe, because getting it wrong is invisible: the lookup returns an empty
set and the tool cheerfully selects nothing.

**Options considered.**
1. *Look up the new-side line numbers.* Wrong in a way that produces confident
   nonsense: after an insertion the new numbers refer to different code in the
   map, so tests get selected for lines that have nothing to do with the change.
2. *Select the tests covering the straddling old lines* (`old_start` and
   `old_start + 1`) and treat that as the answer. Plausible and unsound —
   inserted code can call anything, and its dependencies need not resemble
   those of its neighbours.
3. *Straddling lines as a hint, plus file-level selection for that file.*
4. *Full suite for any file containing an insertion.* Safest, and expensive:
   almost every real commit inserts a line somewhere.

**Decision.** Option 3, matching SPEC B.5. `diff.py` records
`FileChange.insertions` whenever any hunk has `old_count == 0` and takes the two
straddling old lines as a weak signal. The classifier then returns
`INSERTION_NO_HISTORY` with file-level scope, so every test that has ever
touched that file runs. New files, which are all insertion, take a different
path: they are absent from the map entirely and fall back with `UNMAPPED_FILE`.

A detail worth recording because it was wrong first: a newly added file's diff
reads `@@ -0,0 +1,N @@`, and the straddling rule would invent old-side "lines"
0 and 1 of a file that did not exist. Added files now carry an empty line set.
`tests/test_diff.py::test_new_file_has_no_old_lines` pins it.

**How we would know this was wrong.** If `INSERTION_NO_HISTORY` turns out to
fire on nearly every commit, file-level selection is doing most of the work and
the line-level machinery is not earning its complexity — in which case the
honest report says the file-level tool is the product. The number to watch is
the share of `INSERTION_NO_HISTORY` in the fallback breakdown over real
historical commits.

**Evidence.** `tests/test_diff.py` covers single-line edits, pure insertions,
pure deletions, renames with edits, new files, binaries and merge commits
against real repositories built in `tmp_path`.

---

## D-0011 — Map storage: measured before optimising

**Date:** 2026-09-09 · **Area:** db · **Status:** accepted

**Context.** SPEC B.4 anticipates the scale question — 3,000 tests × ~1,500
covered lines each is on the order of 4–5 million rows — and explicitly says not
to pre-optimise. The alternative design, held in reserve, replaces
`coverage_line` with `(file_id, test_id, line_bits BLOB)`: a per-file line
bitmap, the representation `coverage.py` uses internally.

**Options considered.**
1. *Row per (file, line, test)*, `WITHOUT ROWID`, indexed by test. Simple, and
   every query in `db.py` is one readable SQL statement.
2. *Per-file line bitmaps.* Far smaller and faster to union, but every query
   becomes bit arithmetic, and `tia explain` — the feature that makes the
   selection inspectable, which is the entire differentiator — turns into
   decoding a blob.
3. *A different store entirely* (LMDB, a columnar file). Rejected: a CLI tool
   that demands database infrastructure will not be adopted, and stdlib
   `sqlite3` is already there.

**Decision.** Option 1 until measurement says otherwise. Measured on attrs
(1,412 tests): **508,939 rows, 13.2 MB, built in about 10 seconds.** Selection
against that map is fast enough that the wall-clock figures in the safety
experiment are dominated by pytest startup, not by lookup.

**How we would know this was wrong.** The reserve design becomes necessary if
the map on the largest corpus repository exceeds roughly 500 MB, or if p95
lookup latency for one changed file exceeds ~50 ms — at which point selection
would start costing more than it saves on a fast suite.

**Measured on scrapy, the largest corpus repository (4,371 tests, 328 files):**

| | attrs | scrapy |
|---|---|---|
| Tests in the map | 1,334 | 4,371 |
| `coverage_line` rows | 508,939 | **1,723,636** |
| Map size | 13.2 MB | **47.5 MB** |
| Map build (instrumented suite + write) | ~10 s | 81.4 s + 10.3 s |
| Instrumentation slowdown | 2.2× | **1.63×** (49.85 s → 81.4 s) |
| Lookup latency, median | — | **0.04 ms** |
| Lookup latency, **p95** | — | **1.41 ms** |
| Lookup latency, max | — | 2.51 ms |

Latency was measured over 200 simulated five-line hunks sampled uniformly from
covered lines across the map.

Both thresholds are missed by more than an order of magnitude: 47.5 MB against
a 500 MB budget, and 1.41 ms against 50 ms. The simple schema stands and the
bitmap design stays on the shelf. Selection cost is irrelevant next to pytest's
own startup, which is the real floor on these suites (D-0005).

**A note on the slowdown.** attrs pays 2.2× under instrumentation while scrapy
pays only 1.63×. That is the expected direction: scrapy's suite spends much of
its time in I/O and Twisted's reactor rather than executing Python lines, and
coverage only taxes the latter. A codebase whose tests are CPU-bound pays more
to be mapped.

**Evidence.** `tia status` in both corpus checkouts; the latency figures are
reproducible with the sampling loop recorded in this session against
`eval/.corpus/scrapy/repo/.tia/map.db`.

---

## D-0012 — The import graph replaces a fallback with a cheaper fallback

**Date:** 2026-10-02 · **Area:** importgraph/classifier · **Status:** accepted

**Context.** D-0009 added the rule that any change touching a line which ever
executed at import time runs the whole suite, because coverage attributes
import-time execution to no test. It removed the only miss the harness has ever
found. It also became the single largest cost in the system: at Review 1 it
caused **every** fallback on attrs and fired on 59.6% of mutants. SPEC B.8's
import graph was written as a Phase 2 enhancement; the measurement turned it
into the thing that makes D-0009 affordable.

**Options considered.**
1. *Leave it.* Safe, and roughly three in five changes get no benefit at all.
2. *Attribute import-time lines to every test in the importing module.* Cheap
   to implement and wrong in the unsafe direction: it guesses at a dependency
   the map did not observe.
3. *Static import graph.* When a changed line ran at import time, select the
   tests covering every module that transitively imports the changed file.
   Strictly more information than "run everything", and conservative: the
   closure is a superset of what an import-time dependency can reach *through
   imports*.

**Decision.** Option 3, guarded. `importgraph.py` resolves `import` and
`from ... import` with `ast`, maps module names back to project files, and
walks the reverse edges breadth-first. A changed import-time line yields
`IMPORT_CLOSURE`; once the closure exceeds `closure_max_fraction` of the suite
(default 0.6) it yields `CLOSURE_TOO_LARGE` and the whole suite runs, because
selecting most of a suite costs more to compute than it saves.

**Measured on both corpus repositories.** Each pair is one map, one seed and
one set of mutation sites, differing only in whether the closure is consulted.
**These figures supersede the ones first recorded here**, which were produced
by a graph that was letting a defect through — see D-0014.

| | attrs, no graph | attrs, graph | scrapy, no graph | scrapy, graph |
|---|---|---|---|---|
| Non-equivalent defects | 184 | 184 | 27 | 27 |
| Misses | 0 | 0 | 0 | 0 |
| Fallback frequency | 52.7% | 50.5% | 59.3% | **29.6%** |
| Net time reduction | 57.0% | 58.4% | 40.4% | **65.2%** |
| Precision, median | 62.5% | 55.2% | 25.0% | 9.8% |

The honest reading, repository by repository. On **scrapy** the graph earns its
place: it halves the fallback rate and lifts the saving from 40.4% to 65.2%. On
**attrs** it is worth almost nothing — 58.4% against 57.0%, with the fallback
rate barely moving — because a 3.9-second suite has nothing left to give once
pytest's startup is paid (D-0005). The dominant fallback reason changes from
`IMPORT_TIME_LINE` to `CLOSURE_TOO_LARGE` in both: we replaced a rule that gave
up immediately with one that tries first and, on a tightly coupled codebase,
still usually gives up.

Precision falls when the graph is on (62.5% to 55.2% on attrs, 25.0% to 9.8% on
scrapy), which is expected and is the price of the recall that keeps misses at
zero: the closure deliberately selects more than can fail.

**Closure size is the thing that decides it**, and it is a property of the
codebase, not of tia:

| | attrs | scrapy |
|---|---|---|
| Source files in the graph | 16 | 144 |
| Import edges | 37 | 599 |
| Closure as a share of the suite, median | **9.4%** | **42.9%** |
| p95 | 99.7% | 87.7% |
| Files whose closure exceeds the 60% limit | 5 of 16 | 62 of 144 |

A library with leaf modules gets most of its changes selected; a framework
whose core is imported by everything abandons the attempt more often. But the
benefit does not follow that ordering — see above. The property that predicts
the benefit is **baseline suite duration**, with closure share deciding only how
frequently selection is attempted at all. This is the "which codebase
properties predict the benefit" characterisation the proposal committed to
producing, and it is a more useful result than the speedup itself.

**How we would know this was wrong.** If a miss ever appears on a mutant whose
verdict was `IMPORT_CLOSURE`, the closure is not the superset we claim and the
rule must revert to the full suite. The experiment that would show it is the
one already in place, which is why the arms are run on the same sites. The
default limit of 0.6 is SPEC B.8's suggestion, not a measured optimum; the
measurement that would set it is a sweep of the limit against net reduction,
and it has not been run.

**Evidence.** `eval/results/safety_attrs_2026-10-02T132005Z_seed1234_nograph.json`
and `..._133350Z_seed1234_graph.json`.

---

## D-0013 — Two ways our own measurements lied, and what now prevents them

**Date:** 2026-10-02 · **Area:** eval/methodology · **Status:** accepted

**Context.** Both of these produced numbers we believed before we caught them.
They are recorded because a project whose contribution is *reproducible
measurement* has to be hardest on its own measurements.

**Fault 1 — a before/after across a map rebuild is not a controlled
comparison.** Mutation sites are sampled from the lines the map records as
covered. Rebuilding the map changes that set slightly (508,939 rows against
508,929 on the same commit, because coverage of a parallel run is not
bit-identical), so the same seed selects *different mutants*. The first
import-graph comparison looked like fallback dropping 59.6% → 51.1% and net
reduction collapsing 46.1% → 11.8%, and neither half was comparing like with
like.

*Fix:* `--no-import-graph` selects the Phase 1 arm at selection time, so both
arms run against one map and one site list and differ in exactly one variable.
The arm is recorded in the payload and in the filename. The no-graph arm
reproduces the Review 1 figure exactly (59.6% fallback, n=19), which is the
check that the sampling is reproducible when the map is held fixed.

**Fault 2 — an exclusion threshold chosen by hand changes the answer.** Net
time reduction was computed outside the harness, excluding runs slower than
800s to drop a mutant that hangs the suite. When the timeout setting moved from
900s to 600s, that same hung mutant fell on the other side of the threshold:
included, it turned a 46% reduction into 11%. The tool had not changed at all.

*Fix:* `net_reduction` is computed inside `eval/harness.py` and lands in every
results JSON, excluding runs by **exit code** — a timeout measures a hang, not a
suite — rather than by any duration. Recomputed under that definition the
published figure stands: 46.1% then, 46.2% on the reproduction arm today.

**How we would know this was wrong.** If two runs of the same arm, same seed and
same map ever disagree on fallback frequency, sampling is not deterministic and
every comparison in the report is void. Cheap to check and worth checking before
the final numbers are frozen.

**Evidence.** The two arm files above, and the `net_reduction` block now present
in every safety result.

---

## D-0014 — The import graph let a defect through, twice, and scale is what found it

**Date:** 2026-10-02 · **Area:** importgraph/selector · **Status:** accepted

**Context.** At 50 mutants the import graph showed 0 misses on both corpus
repositories. At 200 mutants on attrs it showed **1 miss in 184**, against 0 for
the arm that ignored the closure. The defect was `conditional_forcing` on
`src/attr/_cmp.py:88` — the same line as D-0009's miss. The rule written to
close that hole had re-opened it.

This is the falsification condition D-0012 was written with: *"if a miss ever
appears on a mutant whose verdict was `IMPORT_CLOSURE`, the closure is not the
superset we claim."* It appeared. The verdict was `IMPORT_CLOSURE`, 70 tests
were selected, one test failed under the full suite, and none of the 70 was it.

**Two independent faults, and the first fix was not enough.**

*Fault 1 — the graph had no test files in it.* It was built from
`mapped_source_files()`, which returns files carrying coverage rows. attrs runs
coverage as `--cov=attr --cov=attrs`, so its test files have no coverage rows
and were not nodes in the graph at all. The edge `tests/test_cmp.py -> attr`
was never recorded, and the closure of `_cmp.py` was three source files. Fixed
by building over `all_known_files()`: edges went 37 -> 104 and the closure
reached `tests/test_cmp.py`.

*Fault 2 — the closure then asked the wrong question.* `tests_for_file()`
returns tests that **executed** a file. For a test file with no coverage rows it
returns nothing, so reaching `tests/test_cmp.py` still yielded zero tests from
it, while the 61 tests **defined** there sat in the `test` table untouched. The
closure now unions `tests_for_file` with `tests_in_files`.

**Measured, attrs, 200 mutants, seed 2026, one map and one site list per arm:**

| | no graph | graph (faulty) | graph (fixed) |
|---|---|---|---|
| **Misses** | **0 / 184** | **1 / 184** | **0 / 184** |
| Fallback frequency | 52.7% | 47.8% | 50.5% |
| Net time reduction | 57.0% | 35.4% | 58.4% |
| Selection precision, median | 62.5% | 50.0% | 55.2% |
| Selections containing every failing test | 85 / 87 | 88 / 95 | 87 / 91 |

**What this costs the Phase 2 story.** With the fault repaired, the import graph
is worth almost nothing on attrs: 58.4% against 57.0%, and a fallback rate that
barely moves. The earlier attrs result (51.1% fallback, 50.7% reduction) and
the scrapy result (29.6%, 66.3%) were both produced by the faulty graph and
were withdrawn. Both repositories have since been re-measured on rebuilt maps:
attrs 50.5% / 58.4%, scrapy 29.6% / **65.2%**, both with zero misses. The
scrapy benefit survives the repair; the attrs benefit does not.

**Three things worth taking from this.**

1. **50 mutants was not enough.** The missed mutant is index 80 of 200. Every
   safety claim this project made before today rested on a sample too small to
   see it.
2. **The first fix was convincing and insufficient.** Edges tripled, and the
   closure visibly reached the right file. Only re-running the experiment showed
   the defect still escaping. A fix verified by reasoning is not verified.
3. **"No miss" is not "complete recall".** 4 of 91 selections contained only
   some of the failing tests. They still caught the defect, so they are not
   misses, but a selection holding one of five failing tests is fragile. The
   `selections_containing_every_failing_test` figure is reported alongside the
   miss rate for that reason.

**How we would know this was wrong.** The regression test
`test_import_closure_reaches_tests_defined_in_a_closure_file` builds a
module-level dependency, injects a defect on that line, and asserts the
dependent test is selected. If the miss rate on any repository is ever
non-zero for an `IMPORT_CLOSURE` verdict again, the rule reverts to a
full-suite fallback and the import graph is reported as measured and rejected.

**Evidence.** `eval/results/safety_attrs_*_seed2026_*.json` — the no-graph arm,
the faulty graph arm carrying the miss, and the fixed arm.
