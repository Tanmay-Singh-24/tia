# Project: tia — Test Impact Analysis for Python

## What this is

A command-line tool that, given a git change, runs only the tests that could
possibly be affected by that change — and falls back to running everything
whenever it cannot prove that is safe.

This is a capstone project in **developer tooling and build infrastructure**.
It is not a software-testing-practice project. The engineering questions are:
how program execution is traced, how dependency relationships are inferred in a
dynamically typed language, how storage is structured for fast lookup, and how
a correctness guarantee is defended under uncertainty.

## The thesis this project must defend

Selective test execution already exists (pytest-testmon, Bazel, Launchable).
What does not exist publicly is **an open tool whose selection logic is
inspectable, paired with a reproducible safety evaluation on real codebases.**

Every design decision must serve that thesis. Speed alone is not the
contribution; *measured* speed with *measured* safety is.

## Non-negotiable invariants

1. **Silent misses are the only unacceptable failure.** A tool that is fast but
   occasionally lets a defect through is worse than no tool, because it
   manufactures false confidence. When in doubt, run everything.
2. **Fallback is a feature, not a bug.** Every fallback path is logged with a
   machine-readable reason code and counted. Fallback frequency is a headline
   metric we publish, not something we hide.
3. **No fabricated numbers, ever.** Benchmark results come from the harness or
   they do not exist. Never write a plausible-looking figure into a README, a
   report, or a docstring. If a number is not yet measured, write `TBD`.
4. **The evaluation harness is built before the tool is finished.** Week 1—2.
   Every subsequent decision gets assessed against evidence.
5. **The week-8 file-level version is the minimum shippable result.** Nothing
   after week 8 is allowed to destabilise it. Line-level precision, import
   graphs and everything else are enhancements behind flags.

## Working agreements for the AI assistant

- **Ask before adding any third-party dependency.** The runtime dependency list
  is fixed (see SPEC). Dev/eval dependencies need a one-line justification.
- **Small, reviewable commits.** One logical change per commit. Conventional
  commit messages (`feat:`, `fix:`, `perf:`, `test:`, `docs:`, `chore:`).
- **Tests before or alongside implementation.** This project cannot ship an
  untested test tool. That is the joke the panel will make; do not hand it to
  them.
- **Every non-obvious decision gets a dated entry in `docs/DECISIONS.md`** in the
  form: context → options considered → decision → how we would know it was wrong.
  This file is the single richest source of review-defence material. Treat
  writing it as part of the task, not as documentation overhead.
- **Never claim a behaviour works without running it.** Run the command, paste
  the real output.
- **Prefer boring, inspectable code.** Someone on the panel will ask you to read
  a function aloud and explain it. Optimise for that.
- **Type hints on all public functions.** `mypy --strict` on `src/tia/` must pass.
- **If a task is ambiguous, ask one question rather than guessing.** Wrong
  assumptions compound.

## Repository layout

```
src/tia/
  __init__.py       version
  cli.py            Typer entry point
  config.py         .tia.toml loading, defaults
  db.py             SQLite schema, migrations, all queries
  mapper.py         builds the line→test map from coverage data
  diff.py           git integration, hunk parsing
  classifier.py     safety classifier — the heart of the guarantee
  importgraph.py    ast-based module dependency graph (Phase 2)
  selector.py       orchestration: diff → classify → query → decision
  plugin.py         pytest plugin (collection filtering)
  reasons.py        fallback reason codes, single source of truth
tests/              our own tests
eval/
  harness.py        benchmark runner
  mutate.py         defect injection
  corpus.py         corpus checkout/setup
  corpus.yaml       pinned repos + commits
  results/          raw JSON, committed
docs/
  SPEC.md           the specification
  DECISIONS.md      decision log
  SAFETY.md         what we guarantee and what we do not
```

## Vocabulary — use these terms consistently everywhere

- **map** — the persisted line→test relation. Never "cache", never "index".
- **selection** — the subset of tests chosen for a change.
- **fallback** — abandoning selection and running the full suite.
- **reason code** — the enum value explaining a fallback or a forced inclusion.
- **corpus** — the set of real open-source repos we evaluate against.
- **miss** — a defect that the full suite catches but the selection does not.
  This is the failure mode that matters.
