# tia — Technical specification

## B.1 Fixed technology choices

| Component | Role | Why this and not something else |
|---|---|---|
| Python 3.11+ | Implementation and target | Target ecosystem; `tomllib` in stdlib |
| `coverage.py` ≥ 7.4 dynamic contexts | Per-test line attribution | Removes the need to write a custom `sys.settrace` tracer — this single capability is what makes the project feasible in one semester |
| `pytest-cov` ≥ 4.1 | Wires `--cov-context=test` into a pytest run | Standard path to per-test contexts |
| SQLite (stdlib `sqlite3`) | Map storage | One file, no server. A CLI tool that demands database infrastructure will not be adopted |
| `git` (subprocess, not a library) | Changed-line source | No binding to keep current; plumbing commands are stable |
| pytest plugin API | Selection enforcement | Filter collected tests; integrate with the runner rather than wrapping it |
| `ast` (stdlib) | Import graph | Phase 2, indirect dependencies |
| Typer | CLI | Type-hint driven, minimal boilerplate |

Runtime dependencies are exactly: `typer`, `coverage`, `pytest`, `pytest-cov`.
Nothing else without discussion. Eval-only extras (`pytest-xdist`, `rich`,
`pyyaml`) live in an `[eval]` optional group.

## B.2 The two phases

**Phase 1 — learning (run once, then incrementally).** The full suite runs with
coverage instrumentation and dynamic contexts enabled. For each test, coverage
records the exact set of lines that executed while that test was running. We
read that out and persist an inverted relation: for each source line, the set of
tests that touched it. Stored in `.tia/map.db`, keyed to the git commit it was
built at.

**Phase 2 — selection (every change).** Ask git which lines changed between the
merge base and HEAD. Classify each changed path. For paths where the map is
trustworthy, look up the changed lines and union the tests. Hand pytest that
list. For everything else, fall back.

## B.3 The coverage integration — known gotchas

These will cost you a day each if you discover them yourself.

1. **Enabling contexts.** Either `pytest --cov=<pkg> --cov-context=test` or
   `dynamic_context = test_function` under `[run]` in `.coveragerc`. Prefer the
   pytest-cov route: contexts come out as pytest **nodeids**, which is exactly
   what we need to feed back to `pytest`. The `dynamic_context` route gives you
   dotted Python paths that you then have to translate back to nodeids — avoid.

2. **Context strings carry a phase suffix.** pytest-cov emits
   `tests/test_api.py::test_login|run`, plus separate `|setup` and `|teardown`
   contexts. Strip the suffix at the `|`, and **keep setup/teardown coverage** —
   a fixture touching a line is a genuine dependency. There is also an empty
   context `""` for lines executed at import time, outside any test. Import-time
   lines belong to *every* test in the importing module's dependency closure —
   handle explicitly, do not silently drop.

3. **Reading the data.** Do not parse `.coverage` by hand. Use the API:
   ```python
   from coverage import CoverageData
   data = CoverageData(basename=".coverage")
   data.read()
   for path in data.measured_files():
       for lineno, contexts in data.contexts_by_lineno(path).items():
           ...
   ```

4. **Parallel map building.** With `pytest-xdist`, coverage writes
   `.coverage.<host>.<pid>.<rand>` files that must be `coverage combine`d.
   Contexts survive combining. **Verify this on the corpus in week 1** — the
   proposal already flags it as a risk, and the documented fallback is
   sequential map construction (slow, but done once).

5. **Instrumentation cost.** The learning run is roughly 2–5× slower than a
   normal run. That is acceptable because it is amortised, but say so out loud
   in the report — a reviewer who has used coverage will ask.

6. **Path normalisation.** Store all paths as POSIX-style, relative to the repo
   root, resolved through `os.path.realpath` first. Absolute paths and symlinked
   checkouts are the classic source of "the map matches nothing" bugs.

## B.4 SQLite schema

Start here. Do not pre-optimise.

```sql
CREATE TABLE meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
-- keys: schema_version, tia_version, built_at_commit, repo_root,
--       built_at_utc, suite_command, total_tests, build_duration_s

CREATE TABLE file (
    id   INTEGER PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,        -- POSIX, relative to repo root
    kind TEXT NOT NULL                -- 'source' | 'test' | 'config' | 'other'
);

CREATE TABLE test (
    id           INTEGER PRIMARY KEY,
    nodeid       TEXT NOT NULL UNIQUE,
    file_id      INTEGER NOT NULL REFERENCES file(id),
    duration_ms  REAL,                -- for cost-aware ordering later
    fingerprint  TEXT NOT NULL        -- sha256 of the test function source
);

CREATE TABLE coverage_line (
    file_id INTEGER NOT NULL REFERENCES file(id),
    lineno  INTEGER NOT NULL,
    test_id INTEGER NOT NULL REFERENCES test(id),
    PRIMARY KEY (file_id, lineno, test_id)
) WITHOUT ROWID;

CREATE INDEX idx_cov_by_test ON coverage_line(test_id);

CREATE TABLE import_edge (              -- Phase 2
    importer_file_id INTEGER NOT NULL REFERENCES file(id),
    imported_file_id INTEGER NOT NULL REFERENCES file(id),
    PRIMARY KEY (importer_file_id, imported_file_id)
) WITHOUT ROWID;
```

**Anticipate the scale question.** 3,000 tests × ~1,500 covered lines each is on
the order of 4–5 million rows. Measure the real file size and the p95 lookup
latency on the corpus in week 5 and record it in `DECISIONS.md`. If it is a
problem, the documented upgrade is to replace `coverage_line` with
`(file_id, test_id, line_bits BLOB)` — a per-file line bitmap, the same
representation `coverage.py` itself uses internally. **Do not do this
speculatively.** "We measured it at X MB and Y ms, which was acceptable, and
here is the design we had ready if it had not been" is a far stronger review
answer than a premature optimisation.

## B.5 Change detection (`diff.py`)

```
base = git merge-base HEAD <upstream>        # default upstream: origin/main
git diff --unified=0 --no-color --find-renames <base> HEAD
```

Parse hunk headers `@@ -old_start,old_count +new_start,new_count @@`.

**The subtlety that matters, and that a panel will probe:** the map was built at
some commit. Changed lines must be looked up using the **old-side** line numbers
if the map is older than the change, because those are the coordinates the map
speaks. Concretely:

- **Modified or deleted lines** — `old_start .. old_start + old_count - 1`.
  Look these up directly.
- **Pure insertions** (`old_count == 0`) — the new lines have no old-side
  coordinates and therefore *cannot* be looked up. Conservative rule: select the
  tests covering the two straddling old lines (`old_start` and `old_start + 1`)
  **and** fall back to file-level selection for that file. Record reason code
  `INSERTION_NO_HISTORY`. Do not pretend an inserted line can be resolved.
- **Renames** — treat as delete + add unless the content hash is unchanged, in
  which case rewrite the path in the map.
- **New files** — no map coverage; reason code `UNMAPPED_FILE`.

Also record: `git status --porcelain` for uncommitted work, since developers run
this locally on dirty trees. Uncommitted changes are diffed against the index
and treated identically.

## B.6 The safety classifier (`classifier.py`) — the heart of the project

Every changed path is routed to exactly one outcome. This table *is* the
guarantee; it belongs in `docs/SAFETY.md` verbatim and on a slide in both reviews.

| Changed path | Outcome | Reason code |
|---|---|---|
| Test file, new or modified | Always run those tests, without consulting the map | `TEST_CHANGED` |
| `conftest.py` | Run every test at or below that directory | `CONFTEST_CHANGED` |
| Project Python source, present in map, map fresh | **Line-level selection** | `SELECTED` |
| Project Python source, absent from map | Full suite | `UNMAPPED_FILE` |
| `__init__.py` | File-level selection over the whole package, never line-level | `PACKAGE_INIT` |
| `pyproject.toml`, `setup.cfg`, `setup.py`, `tox.ini`, `pytest.ini`, `.coveragerc` | Full suite | `BUILD_CONFIG_CHANGED` |
| `requirements*.txt`, `poetry.lock`, `uv.lock`, `Pipfile.lock` | Full suite | `DEPENDENCY_CHANGED` |
| Data, fixtures, templates, `.json`, `.yaml`, `.sql`, `.html`, `.csv` | Full suite | `NON_SOURCE_ASSET` |
| Anything under a configured `always_full` glob | Full suite | `USER_CONFIGURED` |
| Map commit is not an ancestor of the diff base | Full suite | `MAP_STALE` |
| No map exists | Full suite | `NO_MAP` |
| Classifier raised an exception | Full suite | `CLASSIFIER_ERROR` |

Two of the three problems the proposal identifies are answered by *deliberately
forgoing the speed benefit*. Say that in the review as a strength. The design is
conservative by construction; the empirical question is how often conservatism
fires, and that is precisely what `fallback frequency` measures.

Reason codes live in `reasons.py` as a single enum with human-readable
descriptions attached. `tia select --explain` prints, per selected test, the
chain: changed line → covering test → why included. **Build `--explain` early.**
It is your debugger, your demo centrepiece, and the concrete embodiment of
"inspectable selection logic" — which is the whole differentiator.

## B.7 CLI surface

```
tia init                     write .tia.toml, create .tia/, add to .gitignore
tia build [--suite "pytest"] [--jobs N]
                             run the instrumented suite, build the map
tia select [--base origin/main] [--format nodeids|json] [--explain]
                             print the selection and exit; no tests run
tia run [--base ...] -- <extra pytest args>
                             select, then run
tia status                   map freshness, commit, size, test count, age
tia explain <path>:<line>    which tests cover this line, and why
pytest --tia [--tia-base=origin/main]      plugin form, for CI
```

Exit codes: `0` success, `1` test failure, `2` usage error, `3` map unusable
(and, in `run`, this must have already fallen back to the full suite rather than
failing — a broken map must never mean "no tests ran").

Plugin implementation: `pytest_addoption` for the flags, and filter in
`pytest_collection_modifyitems(session, config, items)` by mutating `items` in
place. Report the removed ones through `config.hook.pytest_deselected(items=...)`
so pytest's own summary line shows the deselection honestly. Print a one-line
banner: `tia: selected 12 of 3,041 tests (reason: SELECTED, map @ a3f9c21)`.

## B.8 Import graph (Phase 2, `importgraph.py`)

Walk every project `.py` with `ast`, collect `Import` / `ImportFrom`, resolve
relative imports against the package root, build the reverse edge set
(imported → importers). When file `M` changes, additionally select tests covering
files that transitively import `M`.

Guard against closure explosion: a change to a widely-imported utility module
will pull in nearly everything. Measure the median and p95 closure size on the
corpus. If the closure exceeds a configurable fraction of the suite (default
60%), stop and run everything instead — reason code `CLOSURE_TOO_LARGE` — because
selecting 80% of the suite costs more to compute than it saves.

The honest framing for the report: the import graph catches *static* indirect
dependencies. Dynamic loading (`importlib`, `getattr` dispatch, monkeypatching,
entry points, plugin registries) remains unobservable. The line-level map partly
compensates because it records what *actually executed* rather than what the
source appears to say. Neither is complete. `docs/SAFETY.md` must state this
plainly — a reviewer who catches you overclaiming will spend the rest of the
session there.

## B.9 Evaluation harness (`eval/`) — build this first

### Corpus

Two to three real open-source Python projects with substantial pytest suites.
Selection criteria: pure Python, 1,000+ tests, installable dev dependencies,
suite green at a pinned commit, total runtime under ~15 minutes so you can
iterate. Candidates to evaluate in week 1 (verify counts and green status
yourself, do not trust any number you have not run): `pallets/flask`,
`Textualize/rich`, `psf/black`, `encode/httpx`, `scrapy/scrapy`,
`python-attrs/attrs`. Pin exact commit SHAs in `corpus.yaml` and never move them
without a `DECISIONS.md` entry — reproducibility is the contribution.

### Metrics

1. **Runtime reduction.** Median wall-clock across ≥5 repetitions, selected vs.
   full. **The baseline must be a properly optimised one** — same machine, same
   `pytest -n auto` parallelism, caches warm, `-p no:randomly`. Beating a
   deliberately slow baseline is the cheapest way to lose credibility. Report
   median and interquartile range, never a single run.
2. **Selection ratio.** `|selected| / |total|`, distribution over sampled commits.
3. **Selection precision.** Under a single injected defect at line `L`, let
   `F` = tests that fail on the full suite, `S` = tests selected. Precision is
   `|F ∩ S| / |S|`. State the limitation openly: this proxies "genuinely
   related" as "actually fails", which understates precision for tests that
   exercise the line without asserting on it.
4. **Safety validation — the critical metric.** For each injected defect:
   run the full suite (must fail — otherwise the mutant is *equivalent* and is
   excluded from the denominator), then run only the selection. If the selection
   passes, that is a **miss**. Report `misses / non-equivalent mutants`. A single
   miss is a failure of the core guarantee and must be root-caused in the
   report, not averaged away.
5. **Fallback frequency.** Over N sampled real historical commits from each
   corpus repo, how often does the classifier abandon selection, broken down by
   reason code. This is the honest cost of the conservative design and it is a
   headline result, not an appendix.
6. **Map build cost and size.** Instrumented-run slowdown factor, database size,
   p95 lookup latency.

### Defect injection (`mutate.py`)

Write your own AST mutator rather than using `mutmut` or `cosmic-ray`. You need
line-precise, deterministic, single-site mutation so that you know exactly which
line to feed the selector — off-the-shelf tools optimise for coverage of the
mutation space, not for controlled experiments. Roughly 200 lines. Operators:

- comparison flip (`<` ↔ `<=`, `==` ↔ `!=`, `>` ↔ `>=`)
- arithmetic swap (`+` ↔ `-`, `*` ↔ `/`)
- boolean negation (`and` ↔ `or`, insert `not`)
- constant perturbation (`n` → `n+1`, `""` → `"x"`, `True` ↔ `False`)
- return value replacement (`return X` → `return None`)
- conditional forcing (`if cond` → `if True` / `if False`)

Sample mutation sites uniformly across covered lines. Emit each mutant as a real
git commit on a scratch branch so the tool's normal git path is exercised — do
not special-case the harness. Record every run as JSON under `eval/results/`,
committed to the repo, with the tool version, corpus SHA, machine spec and
timestamp. **Every number in either review must be traceable to a committed
JSON file.**

### Reproducibility

`eval/harness.py --repo flask --experiment safety --n 200` reproduces a published
table end to end. A `make reproduce` target that runs the full published
evaluation is a strong closing slide for Review 2.
