"""The pytest plugin form: `pytest --tia [--tia-base=REV]`. See SPEC B.7.

This is how tia is used in CI: no wrapper process, no reimplementation of the
runner, just a collection filter.

The invariant, stated once and enforced by every branch below: if selection
cannot be established, the plugin removes nothing. A tia that fails must cost
time, never coverage.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register the tia options on the pytest command line."""
    group = parser.getgroup("tia", "test impact analysis")
    group.addoption(
        "--tia",
        action="store_true",
        default=False,
        help="Run only the tests affected by the change (falls back to all).",
    )
    group.addoption(
        "--tia-base",
        action="store",
        default=None,
        metavar="REV",
        help="Revision to diff against when selecting (default: .tia.toml upstream).",
    )


def _banner(config: pytest.Config, message: str) -> None:
    """Write one tia line into the pytest report."""
    reporter = config.pluginmanager.get_plugin("terminalreporter")
    if reporter is None:
        print(message, file=sys.stderr)
        return
    reporter.write_line(message)


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Filter collected tests down to the selection."""
    if not config.getoption("--tia"):
        return

    # Imported lazily so that merely having tia installed costs a plain pytest
    # run nothing.
    from tia import diff
    from tia.config import Config
    from tia.selector import select

    try:
        root = diff.repo_root(Path(str(config.rootpath)))
        settings = Config.load(root)
        decision = select(root, settings, base=config.getoption("--tia-base"))
    except Exception as exc:  # noqa: BLE001 - never let tia break a test run
        _banner(
            config,
            f"tia: selection failed ({type(exc).__name__}: {exc}); "
            f"running all {len(items)} tests",
        )
        return

    if decision.full_suite:
        _banner(
            config,
            f"tia: full suite ({decision.primary_reason.value}) — "
            f"running all {len(items)} tests",
        )
        return

    selected = decision.selected
    keep = [item for item in items if item.nodeid in selected]
    removed = [item for item in items if item.nodeid not in selected]

    if not keep:
        _banner(
            config,
            f"tia: selection matched no collected test; running all {len(items)} "
            f"tests rather than none",
        )
        return

    items[:] = keep
    if removed:
        config.hook.pytest_deselected(items=removed)
    _banner(
        config,
        f"tia: selected {len(keep)} of {len(keep) + len(removed)} tests "
        f"(reason: {decision.primary_reason.value}, "
        f"map @ {diff.short(decision.map_commit)})",
    )
