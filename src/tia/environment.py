"""The environment a map was built in, and whether it still holds (D-0019).

Coverage records the code paths that actually ran. Those depend on the Python
version, the platform, and the version of every installed package: a branch
taken only on Windows, or only under a newer release of a dependency, is absent
from a map built elsewhere. Selecting from such a map can miss the one test that
reaches the changed line, so a map is trusted only in a compatible environment.

Compatible means: the same Python major.minor, the same platform, every package
installed at build time still installed at the same version, and no new pytest
plugin. A newly installed package that is *not* a pytest plugin is allowed — it
changes no code path the suite exercised, and refusing the map every time a
developer installs a tool would make tia exhausting to use.
"""

from __future__ import annotations

import json
import sys
from importlib import metadata
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

#: tia's own distribution. Upgrading tia does not change the code under test;
#: the map's schema version guards against tia changing what a map means.
SELF = "tia-select"


def _normalise(name: str) -> str:
    return name.lower().replace("_", "-").replace(".", "-")


def installed_from_inside(direct_url_json: str | None, root: Path) -> bool:
    """Was this distribution installed from a directory inside `root`?

    That is the project under test itself, and its version must not count: a
    project versioned from git (setuptools-scm, hatch-vcs) reports a version
    containing the commit hash, so it differs on every commit, and counting it
    would make every CI selection fall back.
    """
    if not direct_url_json:
        return False
    try:
        url = json.loads(direct_url_json).get("url", "")
    except ValueError:
        return False
    parsed = urlparse(url)
    if parsed.scheme != "file":
        return False
    location = Path(unquote(parsed.path)).resolve()
    return location == root.resolve() or root.resolve() in location.parents


def installed_packages(root: Path | None = None) -> dict[str, str]:
    """Every installed distribution, normalised name to version — excluding tia
    itself and anything installed from inside `root`, the project under test."""
    found: dict[str, str] = {}
    for dist in metadata.distributions():
        name = dist.metadata["Name"]
        if not name:
            continue
        if root is not None and installed_from_inside(
            dist.read_text("direct_url.json"), root
        ):
            continue
        found[_normalise(name)] = dist.version
    found.pop(SELF, None)
    return found


def pytest_plugins() -> set[str]:
    """Distributions that register a pytest plugin through an entry point."""
    plugins: set[str] = set()
    for dist in metadata.distributions():
        if any(ep.group == "pytest11" for ep in dist.entry_points):
            name = dist.metadata["Name"]
            if name:
                plugins.add(_normalise(name))
    return plugins


def fingerprint(root: Path | None = None) -> dict[str, Any]:
    """This interpreter's environment, in the form a map records."""
    return {
        "python": f"{sys.version_info.major}.{sys.version_info.minor}",
        "platform": sys.platform,
        "packages": installed_packages(root),
    }


def differences(
    recorded: dict[str, Any] | None,
    current: dict[str, Any],
    *,
    plugins: set[str] | None = None,
) -> list[str]:
    """Why a map built in `recorded` cannot be trusted in `current`.

    An empty list means it can. Each entry is a short human-readable reason,
    because whoever sees tia fall back deserves to know what to fix.
    """
    if not recorded:
        return ["the map records no environment"]
    reasons: list[str] = []
    if recorded.get("python") != current.get("python"):
        reasons.append(f"Python {recorded.get('python')} -> {current.get('python')}")
    if recorded.get("platform") != current.get("platform"):
        reasons.append(
            f"platform {recorded.get('platform')} -> {current.get('platform')}"
        )

    before: dict[str, str] = recorded.get("packages") or {}
    now: dict[str, str] = current.get("packages") or {}
    for name in sorted(before):
        if name not in now:
            reasons.append(f"{name} {before[name]} removed")
        elif now[name] != before[name]:
            reasons.append(f"{name} {before[name]} -> {now[name]}")

    known_plugins = pytest_plugins() if plugins is None else plugins
    for name in sorted(set(now) - set(before)):
        if name in known_plugins:
            reasons.append(f"new pytest plugin {name} {now[name]}")
    return reasons
