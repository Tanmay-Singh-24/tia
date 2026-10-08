"""Print the published safety table, or check a reproduction against it.

    python eval/report.py             the published table, from eval/published.json
    python eval/report.py --compare   published vs the newest replay of each arm

The comparison separates what a reproduction must match from what it may not.
The mutation list is replayed exactly, so whether each defect was caught —
the miss count — must agree. Wall-clock time depends on the machine, so net
reduction will move on other hardware; that is reported, not checked.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from metrics import time_saved_per_change

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "eval" / "results"
MANIFEST = ROOT / "eval" / "published.json"


def load(name: str) -> dict[str, Any]:
    return json.loads((RESULTS / name).read_text())


def newest_replay(repo: str, arm: str) -> dict[str, Any] | None:
    best: tuple[str, dict[str, Any]] | None = None
    for path in RESULTS.glob(f"safety_{repo}_*_{arm}_replay.json"):
        payload = json.loads(path.read_text())
        if payload.get("complete") and (best is None or path.name > best[0]):
            best = (path.name, payload)
    return best[1] if best else None


def figures(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload["summary"]
    precision = summary.get("precision", {})
    return {
        "mutants": summary["non_equivalent"],
        "misses": summary["misses"],
        "fallback": summary["fallback_frequency"],
        # Computed from the per-mutant records, so files written before the
        # metric existed are judged by the same definition as new ones.
        "net": time_saved_per_change(payload["mutants"]),
        "precision": precision.get("median"),
    }


def pct(value: float | None) -> str:
    return "-" if value is None else f"{value:.1%}"


def published_table(manifest: dict[str, Any]) -> None:
    print("| | misses | fallback | time saved per change | precision |")
    print("|---|---|---|---|---|")
    for repo, entry in manifest.items():
        if repo.startswith("_"):
            continue
        for arm in ("nograph", "graph"):
            f = figures(load(entry[arm]))
            label = f"{repo}, {'import graph' if arm == 'graph' else 'no graph'}"
            print(
                f"| {label} | {f['misses']} / {f['mutants']} | {pct(f['fallback'])} "
                f"| {pct(f['net'])} | {pct(f['precision'])} |"
            )


def compare(manifest: dict[str, Any]) -> int:
    """Return non-zero if anything that must reproduce did not."""
    failures = 0
    print(
        f"{'arm':<22}{'':<11}{'misses':>10}{'fallback':>10}{'net':>9}{'precision':>11}"
    )
    for repo, entry in manifest.items():
        if repo.startswith("_"):
            continue
        for arm in ("nograph", "graph"):
            label = f"{repo} {'graph' if arm == 'graph' else 'no graph'}"
            pub = figures(load(entry[arm]))
            rep_payload = newest_replay(repo, arm)
            print(
                f"{label:<22}{'published':<11}"
                f"{pub['misses']:>4} / {pub['mutants']:<3}{pct(pub['fallback']):>10}"
                f"{pct(pub['net']):>9}{pct(pub['precision']):>11}"
            )
            if rep_payload is None:
                print(f"{'':<22}{'reproduced':<11}  not run yet")
                failures += 1
                continue
            rep = figures(rep_payload)
            verdict = "OK" if rep["misses"] == pub["misses"] else "MISS COUNT DIFFERS"
            if verdict != "OK":
                failures += 1
            print(
                f"{'':<22}{'reproduced':<11}"
                f"{rep['misses']:>4} / {rep['mutants']:<3}{pct(rep['fallback']):>10}"
                f"{pct(rep['net']):>9}{pct(rep['precision']):>11}   {verdict}"
            )
    print(
        "\nMust match: the miss count (the mutation list is replayed exactly).\n"
        "May differ: net reduction, which is wall-clock time and depends on the\n"
        "machine; and fallback or precision by a mutant or two if a rebuilt map\n"
        "records slightly different coverage (D-0013)."
    )
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--compare", action="store_true", help="check the newest replays"
    )
    args = parser.parse_args(argv)
    manifest = json.loads(MANIFEST.read_text())
    if args.compare:
        return compare(manifest)
    published_table(manifest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
