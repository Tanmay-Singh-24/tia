# Changelog

All notable changes. Each entry links to the decision record that explains it;
the decision records say what was considered and what would prove each choice
wrong.

## 0.2.0 — the first release meant for real use

0.1.0 was measured with zero misses, but only in the setting the experiment
used: a map built at exactly the commit being compared against. Auditing how
tia behaves in real use found ten ways it could silently skip a test that
mattered. None was reachable by the published experiment, and every one is now
pinned by a test that failed on the old code.

### Fixed — silent misses

- **A map from an earlier commit was trusted.** If `main` moved after the map was
  built, changed lines were looked up with shifted line numbers, and the wrong
  tests were selected — reproduced as a real miss. The map is now used only at
  the exact branch point. ([D-0016](docs/DECISIONS.md))
- **`tia build` accepted uncommitted edits**, stamping HEAD's commit on another
  version of the code. It now refuses when Python files differ from HEAD.
  ([D-0016](docs/DECISIONS.md))
- **`--base` / `--tia-base` compared against a branch's tip**, describing every
  upstream commit the branch lacked. Every base now resolves to the branch
  point. ([D-0016](docs/DECISIONS.md))
- **A new test added in a pull request never ran.** Changed test files now run
  whole, including tests the map has never seen. ([D-0017](docs/DECISIONS.md))
- **A changed test helper reached none of its users.** Only `test_*.py` /
  `*_test.py` count as test modules; helpers take the ordinary rules.
  ([D-0017](docs/DECISIONS.md))
- **A rule could return an empty selection as an answer.** Any rule that reaches
  no recorded test now widens or falls back. ([D-0017](docs/DECISIONS.md))
- **New parametrisations, new doctests and untracked test files were dropped.**
  Selection is now by test function; doctests in changed files are kept;
  untracked test modules and `conftest.py` join the change.
  ([D-0018](docs/DECISIONS.md))
- **A map built in another environment was trusted.** The Python version,
  platform and installed package versions are recorded; a mismatch falls back
  with `ENVIRONMENT_CHANGED`, naming what differed. ([D-0019](docs/DECISIONS.md))

### Corrected — a published figure

- **The attrs time saving was overstated.** Published as 58.4%, it was set by
  one mutant that hung the suite for 291 seconds and finished just under the
  timeout, crediting tia with about 290 seconds of savings by itself. The time
  metric is now the mean share of the suite saved per change, which no single
  change can dominate. attrs: **42.7%**. scrapy, which had no such hangs:
  **66.9%** (was 65.2%). Every miss count stands. ([D-0020](docs/DECISIONS.md))

### Added

- **Import graph** (Phase 2): a changed line that ran at import time selects the
  tests of every file that imports it, instead of the whole suite. New reasons
  `IMPORT_CLOSURE` and `CLOSURE_TOO_LARGE`. ([D-0012](docs/DECISIONS.md),
  [D-0014](docs/DECISIONS.md))
- **GitHub Action** (`uses: Tanmay-Singh-24/tia@v0.2.0`): build the map once per
  `main` commit, restore it on pull requests. See [docs/CI.md](docs/CI.md).
- Fallbacks carry a **detail** line saying what to fix, shown by `tia select` and
  in the pytest banner.
- `tia select --format json` includes `forced_paths` and `pytest_args`;
  `pytest $(tia select)` runs exactly what tia would.
- Evaluation: selection precision ([SPEC B.9](docs/SPEC.md)), replay of the exact
  recorded defects, and `make reproduce`. ([D-0015](docs/DECISIONS.md))

### Changed

- `tia status` reports a map as fresh only if selection would use it.
- All of tia's output is ASCII; a Windows console code page can no longer break
  or crash it.
- Tested on Linux, macOS and Windows, Python 3.11, 3.12 and 3.13.

### Upgrading from 0.1.0

Rebuild your map with `tia build`. Maps from 0.1.0 recorded no environment and
are not trusted. In CI, move to building the map on every `main` commit — see
[docs/CI.md](docs/CI.md).

## 0.1.0 — 2026-10-03

First release. Line-level selection from a coverage map, a twelve-rule safety
classifier, the pytest plugin, and the evaluation harness behind the published
results.
