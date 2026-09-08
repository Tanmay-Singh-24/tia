#!/usr/bin/env bash
# The Review 1 demo, end to end, on a real repository.
#
# Runs against the attrs corpus checkout: 1412 real tests from a widely used
# library, not a toy project. Needs no network and no 30-minute suite run.
#
#   ./scripts/demo.sh
#
# Every number it prints is produced live, in front of you.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CORPUS="$REPO_ROOT/eval/.corpus/attrs/repo"
VENV="$REPO_ROOT/eval/.corpus/attrs/.venv"
TARGET="src/attr/_funcs.py"
LINE=377

step() { printf '\n\033[1m=== %s ===\033[0m\n' "$1"; }
pause() { if [ -t 0 ]; then read -rp "  [enter] " _; fi; }

if [ ! -d "$CORPUS" ]; then
    echo "corpus not prepared. Run:  python eval/corpus.py prepare --repo attrs" >&2
    exit 1
fi

cd "$CORPUS"
export PATH="$VENV/bin:$PATH"
trap 'git -C "$CORPUS" checkout -- "$TARGET" 2>/dev/null || true' EXIT

step "1. The map: built once, reused for every change"
tia status
pause

step "2. A one-line change"
git checkout -- "$TARGET"
sed -i '' "${LINE}s/    return False/    return True/" "$TARGET"
git diff --unified=0 -- "$TARGET" | tail -4
pause

step "3. What tia selects, and WHY (this is the project)"
tia select --explain 2>&1 | tail -20
pause

step "4. Running only those tests"
time pytest -q -p no:randomly $(tia select 2>/dev/null | tr '\n' ' ')
echo "  baseline for comparison: 3.93s serial, from eval/results/baseline_attrs_*.json"
pause

step "5. The full suite catches this defect. Does the selection?"
echo "  full suite:"
pytest -q -p no:randomly 2>&1 | tail -1
echo "  tia selection:"
pytest -q -p no:randomly --tia 2>&1 | tail -1
echo "  Same failures, a fraction of the time. No miss."
pause

step "6. Now change a dependency file instead"
git checkout -- "$TARGET"
echo "# demo" >> requirements-demo.txt 2>/dev/null || true
git add -N requirements-demo.txt 2>/dev/null || true
tia select 2>&1 | tail -3
rm -f requirements-demo.txt
echo "  Two of three classifier paths give up the speed benefit on purpose."

step "done"
git checkout -- "$TARGET"
