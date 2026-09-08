"""The pytest plugin form: `pytest --tia [--tia-base=REV]`. See SPEC B.7.

The options are registered from day one so the CI-facing surface is stable.
Collection filtering lands in D7. Until then the plugin is deliberately inert:
it announces itself and leaves every collected test in place. A tia that cannot
select must never mean "no tests ran".

The banner goes through pytest's terminal reporter rather than a bare print, so
it lands in the report in collection order instead of racing pytest's buffered
stdout. Bare stderr is kept only as a fallback for runs with no terminal
plugin (`-p no:terminal`).
"""

from __future__ import annotations

import sys

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
        default="origin/main",
        metavar="REV",
        help="Revision to diff against when selecting (default: origin/main).",
    )


def _banner(config: pytest.Config, message: str) -> None:
    """Write one tia line into the pytest report."""
    reporter = config.pluginmanager.get_plugin("terminalreporter")
    if reporter is None:
        print(message, file=sys.stderr)
        return
    reporter.write_line(message)


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    """Filter collected tests down to the selection. Inert until D7."""
    if not config.getoption("--tia"):
        return
    _banner(
        config,
        f"tia: selection not implemented (lands in D7); "
        f"running all {len(items)} collected tests",
    )
