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
