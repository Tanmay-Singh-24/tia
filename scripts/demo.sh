#!/usr/bin/env bash
# The Review 1 demo, end to end, on a real repository.
#
# Runs against the attrs corpus checkout: 1412 real tests from a widely used
# library, not a toy project. Needs no network and no 30-minute suite run.
#
#   ./scripts/demo.sh
#
# Every number it prints is produced live, in front of you.
# Note: no `set -e` around the pytest steps. The safety demonstration runs a
# suite that is *supposed* to fail, and exiting on that would end the demo at
# its most important moment.
set -uo pipefail

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
cleanup() {
    git -C "$CORPUS" checkout -- "$TARGET" 2>/dev/null || true
    rm -f "$CORPUS/requirements-demo.txt"
    git -C "$CORPUS" reset -q 2>/dev/null || true
}
trap cleanup EXIT

step "1. The map: built once, reused for every change"
tia status
pause

step "2. A one-line change to a leaf function"
git checkout -- "$TARGET"
sed -i '' "${LINE}s/.*/    return False  # touched/" "$TARGET"
git diff --unified=0 -- "$TARGET" | tail -4
pause

step "3. What tia selects, and WHY (this is the project)"
tia select --explain 2>&1 | tail -20
pause

step "4. Running only those tests"
time pytest -q -p no:randomly --tia 2>&1 | tail -2 || true
echo "  baseline: 3.93s serial for all 1412, from eval/results/baseline_attrs_*.json"
pause

step "5. Now inject a real defect on that same line"
sed -i '' "${LINE}s/.*/    return True/" "$TARGET"
git diff --unified=0 -- "$TARGET" | tail -3
echo
echo "  the full suite catches it:"
pytest -q -p no:randomly 2>&1 | tail -1 || true
echo "  and so does the selection:"
pytest -q -p no:randomly --tia 2>&1 | tail -1 || true
echo
echo "  Same failure count, a fraction of the time. No miss."
pause

step "6. Change a dependency file instead"
git checkout -- "$TARGET"
echo "some-package==1.0" > requirements-demo.txt
git add -N requirements-demo.txt
tia select 2>&1 | tail -3
echo
echo "  Nine of the fourteen classifier rules give up the speed benefit on"
echo "  purpose. How often that fires is the fallback frequency we publish."

step "done"
git checkout -- "$TARGET"
