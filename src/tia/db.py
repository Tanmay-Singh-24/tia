"""The map: SQLite schema, migrations, and every query that touches it.

The map is the persisted line-to-test relation. One file, no server, so that
using tia never means running database infrastructure. Schema is SPEC B.4.

Every query in the project lives here. Nothing else opens the database.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

MAP_DIRNAME = ".tia"
MAP_FILENAME = "map.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS file (
    id   INTEGER PRIMARY KEY,
    path TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS test (
    id           INTEGER PRIMARY KEY,
    nodeid       TEXT NOT NULL UNIQUE,
    file_id      INTEGER NOT NULL REFERENCES file(id),
    duration_ms  REAL,
    fingerprint  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS coverage_line (
    file_id INTEGER NOT NULL REFERENCES file(id),
    lineno  INTEGER NOT NULL,
    test_id INTEGER NOT NULL REFERENCES test(id),
    PRIMARY KEY (file_id, lineno, test_id)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_cov_by_test ON coverage_line(test_id);

CREATE TABLE IF NOT EXISTS import_edge (
    importer_file_id INTEGER NOT NULL REFERENCES file(id),
    imported_file_id INTEGER NOT NULL REFERENCES file(id),
    PRIMARY KEY (importer_file_id, imported_file_id)
) WITHOUT ROWID;
"""

# File kinds. 'source' is project code the map can speak about; 'test' holds
# tests; 'config' and 'other' exist so the classifier can explain itself.
KIND_SOURCE = "source"
KIND_TEST = "test"
KIND_CONFIG = "config"
KIND_OTHER = "other"


def map_path(repo_root: Path) -> Path:
    """Where the map lives for a given repository."""
    return repo_root / MAP_DIRNAME / MAP_FILENAME


def connect(path: Path, *, create: bool = False) -> sqlite3.Connection:
    """Open the map. With create=True the directory and schema are made."""
    if create:
        path.parent.mkdir(parents=True, exist_ok=True)
    elif not path.exists():
        raise FileNotFoundError(path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    if create:
        conn.executescript(SCHEMA)
        set_meta(conn, "schema_version", str(SCHEMA_VERSION))
        conn.commit()
    return conn


@contextmanager
def bulk_write(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Relax durability for the one-shot build. The map is rebuildable."""
    conn.execute("PRAGMA journal_mode = MEMORY")
    conn.execute("PRAGMA synchronous = OFF")
    try:
        yield conn
        conn.commit()
    finally:
        conn.execute("PRAGMA synchronous = FULL")


def migrate(conn: sqlite3.Connection) -> None:
    """Forward migration hook.

    There is exactly one schema version so far. When a second arrives, this is
    where the step from 1 to 2 goes. A map whose version we do not recognise is
    refused rather than guessed at — the caller treats that as an unusable map
    and runs the full suite.
    """
    found = get_meta(conn, "schema_version")
    if found is None:
        raise ValueError("map has no schema_version")
    version = int(found)
    if version > SCHEMA_VERSION:
        raise ValueError(
            f"map schema v{version} is newer than this tia understands "
            f"(v{SCHEMA_VERSION}); upgrade tia or rebuild the map"
        )


# --------------------------------------------------------------------------
# meta
# --------------------------------------------------------------------------


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return None if row is None else str(row["value"])


def all_meta(conn: sqlite3.Connection) -> dict[str, str]:
    return {
        str(row["key"]): str(row["value"])
        for row in conn.execute("SELECT key, value FROM meta")
    }


# --------------------------------------------------------------------------
# writing
# --------------------------------------------------------------------------


def upsert_file(conn: sqlite3.Connection, path: str, kind: str) -> int:
    """Get the id for a repo-relative POSIX path, inserting it if new."""
    conn.execute(
        "INSERT INTO file(path, kind) VALUES(?, ?) "
        "ON CONFLICT(path) DO UPDATE SET kind = excluded.kind",
        (path, kind),
    )
    row = conn.execute("SELECT id FROM file WHERE path = ?", (path,)).fetchone()
    return int(row["id"])


def insert_test(
    conn: sqlite3.Connection,
    nodeid: str,
    file_id: int,
    fingerprint: str,
    duration_ms: float | None = None,
) -> int:
    conn.execute(
        "INSERT INTO test(nodeid, file_id, fingerprint, duration_ms) "
        "VALUES(?, ?, ?, ?) ON CONFLICT(nodeid) DO UPDATE SET "
        "fingerprint = excluded.fingerprint, duration_ms = excluded.duration_ms",
        (nodeid, file_id, fingerprint, duration_ms),
    )
    row = conn.execute("SELECT id FROM test WHERE nodeid = ?", (nodeid,)).fetchone()
    return int(row["id"])


def insert_coverage(
    conn: sqlite3.Connection, rows: Iterable[tuple[int, int, int]]
) -> None:
    """Bulk-insert (file_id, lineno, test_id) triples."""
    conn.executemany(
        "INSERT OR IGNORE INTO coverage_line(file_id, lineno, test_id) VALUES(?, ?, ?)",
        rows,
    )


# --------------------------------------------------------------------------
# reading — the selection path
# --------------------------------------------------------------------------


def file_id_for(conn: sqlite3.Connection, path: str) -> int | None:
    row = conn.execute("SELECT id FROM file WHERE path = ?", (path,)).fetchone()
    return None if row is None else int(row["id"])


def tests_for_lines(
    conn: sqlite3.Connection, path: str, linenos: Iterable[int]
) -> set[str]:
    """Every test that executed any of these lines of this file."""
    numbers = list(linenos)
    if not numbers:
        return set()
    file_id = file_id_for(conn, path)
    if file_id is None:
        return set()
    found: set[str] = set()
    # Chunked to stay under SQLite's variable limit on large hunks.
    for start in range(0, len(numbers), 500):
        chunk = numbers[start : start + 500]
        placeholders = ",".join("?" * len(chunk))
        rows = conn.execute(
            f"SELECT DISTINCT t.nodeid FROM coverage_line c "  # noqa: S608
            f"JOIN test t ON t.id = c.test_id "
            f"WHERE c.file_id = ? AND c.lineno IN ({placeholders})",
            (file_id, *chunk),
        )
        found.update(str(row["nodeid"]) for row in rows)
    return found


def tests_for_file(conn: sqlite3.Connection, path: str) -> set[str]:
    """Every test that executed any line of this file."""
    file_id = file_id_for(conn, path)
    if file_id is None:
        return set()
    rows = conn.execute(
        "SELECT DISTINCT t.nodeid FROM coverage_line c "
        "JOIN test t ON t.id = c.test_id WHERE c.file_id = ?",
        (file_id,),
    )
    return {str(row["nodeid"]) for row in rows}


def tests_in_files(conn: sqlite3.Connection, paths: Iterable[str]) -> set[str]:
    """Every test defined in these test files."""
    found: set[str] = set()
    for path in paths:
        rows = conn.execute(
            "SELECT t.nodeid FROM test t JOIN file f ON f.id = t.file_id "
            "WHERE f.path = ?",
            (path,),
        )
        found.update(str(row["nodeid"]) for row in rows)
    return found


def tests_under_directory(conn: sqlite3.Connection, directory: str) -> set[str]:
    """Every test whose file lives at or below a directory (for conftest.py)."""
    prefix = "" if directory in {"", "."} else directory.rstrip("/") + "/"
    rows = conn.execute(
        "SELECT t.nodeid FROM test t JOIN file f ON f.id = t.file_id "
        "WHERE f.path LIKE ? ESCAPE '\\'",
        (prefix.replace("_", r"\_").replace("%", r"\%") + "%",),
    )
    return {str(row["nodeid"]) for row in rows}


def tests_covering_line(conn: sqlite3.Connection, path: str, lineno: int) -> list[str]:
    """For `tia explain`: which tests executed this exact line."""
    return sorted(tests_for_lines(conn, path, [lineno]))


def all_test_nodeids(conn: sqlite3.Connection) -> set[str]:
    return {str(row["nodeid"]) for row in conn.execute("SELECT nodeid FROM test")}


def mapped_source_files(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT DISTINCT f.path FROM file f JOIN coverage_line c ON c.file_id = f.id"
    )
    return {str(row["path"]) for row in rows}


def stats(conn: sqlite3.Connection, path: Path | None = None) -> dict[str, Any]:
    """Counts and size, for `tia status`."""

    def count(table: str) -> int:
        row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()  # noqa: S608
        return int(row["n"])

    return {
        "files": count("file"),
        "tests": count("test"),
        "coverage_rows": count("coverage_line"),
        "size_bytes": path.stat().st_size if path and path.exists() else None,
    }
