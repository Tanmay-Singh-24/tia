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
