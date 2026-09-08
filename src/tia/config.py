""".tia.toml loading and defaults.

Configuration is deliberately small. Anything that changes what tia *selects*
must be visible in one short file that a reviewer can read in full.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_FILENAME = ".tia.toml"

DEFAULT_UPSTREAM = "origin/main"
DEFAULT_SUITE = "pytest"


@dataclass(frozen=True)
class Config:
    """Everything tia needs to know about a repository."""

    packages: list[str] = field(default_factory=list)
    """Import names to measure, e.g. ["attr", "attrs"]. Empty means measure all."""

    suite: str = DEFAULT_SUITE
    """Command used to run the full suite during a build."""

    upstream: str = DEFAULT_UPSTREAM
    """Default revision to diff against."""

    always_full: list[str] = field(default_factory=list)
    """Globs that always force the full suite (SPEC B.6, USER_CONFIGURED)."""

    source_roots: list[str] = field(default_factory=list)
    """Directories holding project source, e.g. ["src"]. Informational."""

    @staticmethod
    def load(repo_root: Path) -> Config:
        """Read .tia.toml if present; otherwise return defaults."""
        path = repo_root / CONFIG_FILENAME
        if not path.exists():
            return Config()
        with path.open("rb") as handle:
            raw = tomllib.load(handle)
        table = raw.get("tia", raw)
        return Config(
            packages=list(table.get("packages", [])),
            suite=str(table.get("suite", DEFAULT_SUITE)),
            upstream=str(table.get("upstream", DEFAULT_UPSTREAM)),
            always_full=list(table.get("always_full", [])),
            source_roots=list(table.get("source_roots", [])),
        )


TEMPLATE = """\
# tia configuration. See https://github.com/tanmaysingh/tia
[tia]
# Import names to measure while building the map. Leave empty to measure
# everything the suite imports from this repository.
packages = [{packages}]

# Command that runs the full suite.
suite = "{suite}"

# Revision changes are compared against by default.
upstream = "{upstream}"

# Globs that always force the full suite, whatever the map says.
always_full = []
"""


def render_template(
    packages: list[str], suite: str = DEFAULT_SUITE, upstream: str = DEFAULT_UPSTREAM
) -> str:
    """The .tia.toml written by `tia init`."""
    return TEMPLATE.format(
        packages=", ".join(f'"{name}"' for name in packages),
        suite=suite,
        upstream=upstream,
    )
