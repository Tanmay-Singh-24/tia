# Using tia in CI

tia runs only the tests a change can affect. To do that safely it needs a
**map** — which tests run which lines — built at the **exact commit your change
branches from**, in the **same environment** your tests run in. A map built at
any other commit, or under a different Python, platform or set of packages, is
refused and the whole suite runs instead. That is what keeps it from missing a
defect; this guide is about arranging for the right map to exist.

The pattern is:

1. **Every push to your main branch** builds the map once and caches it, keyed by
   that commit.
2. **Every pull request** finds the commit it branches from, restores that
   commit's map, and runs only the tests it selects. No map means the whole
   suite runs — slower, never wrong.

## GitHub Actions

tia ships an action that does both halves.

```yaml
name: tests

on:
  push:
    branches: [main]
  pull_request:

jobs:
  map:
    if: github.event_name == 'push'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -e ".[test]"        # however you install your project
      - uses: Tanmay-Singh-24/tia@v0.2.0
        with:
          mode: build

  selective:
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0                     # required: tia uses git merge-base
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"             # must match the map job
      - run: pip install -e ".[test]"        # must install the same versions
      - uses: Tanmay-Singh-24/tia@v0.2.0
        with:
          mode: test
          pytest-args: "-n auto"             # anything else you pass to pytest
```

The log says, every time, whether a map was found and what tia selected:

```
tia: map restored for branch point 5960308ea686...
tia: selected 2 of 162 tests (reason: SELECTED, map @ 5960308)
```

### Inputs

| Input | Default | |
|---|---|---|
| `mode` | — | `build` on pushes to main; `test` everywhere else |
| `base-ref` | `main` | the branch changes are compared against |
| `pytest-args` | | extra arguments for pytest in `test` mode |
| `tia-version` | | pin a tia version. Otherwise an already-installed tia is kept, or the release matching the action's tag is installed (`@v0.2.0` means tia 0.2.0) |

## The three things that must line up

**The commit.** The map is used only when it was built at the branch point
itself — `git merge-base` of your change and the base branch. A map from an
older commit is refused (`MAP_STALE`), because once `main` has moved, the same
line number can name different code. Building on every push to `main` keeps a
map available for every commit a pull request can branch from. If a pull
request runs before its base commit's map has finished building, the whole
suite runs for that run.

**The environment.** The map records the Python version, the platform and every
installed package's version. If any differs in the pull-request job, tia refuses
the map (`ENVIRONMENT_CHANGED`) and says which one, for example
`attrs 23.1.0 -> 23.2.0`. Install from a lockfile in both jobs. Newly installed
packages that are not pytest plugins are tolerated, and your own project's
version is ignored — a project versioned from git reports a new version on every
commit.

**The checkout.** `fetch-depth: 0`, so `git merge-base` can find the branch
point. Commit your `.tia.toml`.

## Keep running the full suite somewhere

Until you have measured tia's miss rate on your own codebase, keep a full run —
nightly, or on merge to main. That is what earns the right to drop it.
`docs/SAFETY.md` lists what tia guarantees and what it does not.

## Other CI systems

The action is a thin wrapper. Anywhere else:

```bash
# on each commit to main, in the test environment:
tia build                                  # writes .tia/map.db
# store .tia/map.db in your CI cache, keyed by the commit SHA

# on a change:
BASE=$(git merge-base HEAD origin/main)
# restore the cache entry for $BASE to .tia/map.db, if one exists
python -m pytest --tia --tia-base="$BASE"
```

`tia select --base "$BASE" --format json` prints the decision without running
anything, including every reason code and the exact `pytest_args`.
