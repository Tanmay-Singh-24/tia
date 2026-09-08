"""The tia command line. Surface and exit codes are fixed by docs/SPEC.md B.7.

Exit codes
    0  success
    1  test failure
    2  usage error
    3  map unusable

`tia run` never exits 3: a broken map falls back to the full suite instead,
because "no tests ran" must never be the result of tia failing.
"""

from __future__ import annotations

import json
import subprocess
import sys
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer

from tia import __version__, db, diff, mapper
from tia.config import CONFIG_FILENAME, Config, render_template
from tia.reasons import Reason
from tia.selector import Decision, select

EXIT_OK = 0
EXIT_TEST_FAILURE = 1
EXIT_USAGE = 2
EXIT_MAP_UNUSABLE = 3


class SelectionFormat(StrEnum):
    """Output format for `tia select`."""

    NODEIDS = "nodeids"
    JSON = "json"


app = typer.Typer(
    name="tia",
    help=(
        "Run only the tests a change can affect — and the full suite whenever "
        "that cannot be established."
    ),
    add_completion=False,
)


def _root() -> Path:
    try:
        return diff.repo_root()
    except diff.GitError as exc:
        typer.secho(f"tia: not a git repository ({exc})", err=True, fg="red")
        raise typer.Exit(code=EXIT_USAGE) from exc


def _echo_err(message: str, colour: str | None = None) -> None:
    typer.secho(message, err=True, fg=colour)


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    version: Annotated[
        bool, typer.Option("--version", help="Show the tia version and exit.")
    ] = False,
) -> None:
    """Entry callback: handles --version and bare `tia`."""
    if version:
        typer.echo(f"tia {__version__}")
        raise typer.Exit(code=EXIT_OK)
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit(code=EXIT_OK)


@app.command()
def init(
    packages: Annotated[
        list[str] | None,
        typer.Option("--package", "-p", help="Import name to measure. Repeatable."),
    ] = None,
) -> None:
    """Write .tia.toml, create .tia/, and add it to .gitignore."""
    root = _root()
    config_path = root / CONFIG_FILENAME
    if config_path.exists():
        _echo_err(f"tia: {CONFIG_FILENAME} already exists, leaving it alone", "yellow")
    else:
        config_path.write_text(render_template(packages or []))
        typer.echo(f"wrote {CONFIG_FILENAME}")

    (root / db.MAP_DIRNAME).mkdir(exist_ok=True)
    typer.echo(f"created {db.MAP_DIRNAME}/")

    gitignore = root / ".gitignore"
    entry = f"{db.MAP_DIRNAME}/"
    existing = gitignore.read_text() if gitignore.exists() else ""
    if entry not in existing:
        with gitignore.open("a") as handle:
            handle.write(
                ("" if existing.endswith("\n") or not existing else "\n")
                + f"\n# tia's map is a build artefact\n{entry}\n"
            )
        typer.echo(f"added {entry} to .gitignore")


@app.command()
def build(
    suite: Annotated[
        str | None, typer.Option("--suite", help="Command used to run the suite.")
    ] = None,
    jobs: Annotated[
        int | None,
        typer.Option("--jobs", "-j", help="Parallel workers for the learning run."),
    ] = None,
) -> None:
    """Run the instrumented suite and build the map."""
    root = _root()
    config = Config.load(root)
    if suite:
        config = Config(
            packages=config.packages,
            suite=suite,
            upstream=config.upstream,
            always_full=config.always_full,
            source_roots=config.source_roots,
        )

    typer.echo(f"tia: building the map with: {config.suite} (--cov-context=test)")
    try:
        result = mapper.build(root, config, jobs=jobs, commit=diff.head_commit(root))
    except (RuntimeError, diff.GitError) as exc:
        _echo_err(f"tia build: {exc}", "red")
        raise typer.Exit(code=EXIT_MAP_UNUSABLE) from exc

    if result.suite_exit_code != EXIT_OK:
        _echo_err(
            f"tia: the suite exited {result.suite_exit_code}. The map was still "
            f"built, but a map from a red suite describes a red suite.",
            "yellow",
        )
    typer.echo(
        f"tia: mapped {result.tests} tests across {result.files} files, "
        f"{result.coverage_rows:,} line-to-test rows, "
        f"{result.db_bytes / 1_048_576:.1f} MB"
    )
    typer.echo(
        f"tia: suite {result.suite_duration_s:.1f}s under instrumentation, "
        f"map written in {result.build_duration_s - result.suite_duration_s:.1f}s"
    )
    if result.import_time_lines:
        typer.echo(
            f"tia: {result.import_time_lines:,} import-time line executions "
            f"belong to no test (see reason IMPORT_TIME_LINE)"
        )


def _print_explanations(decision: Decision) -> None:
    """The chain: changed path -> reason -> the tests it pulled in."""
    typer.echo("")
    for verdict in decision.verdicts:
        change = verdict.change
        lines = sorted(change.old_lines)
        where = (
            f" lines {lines[0]}-{lines[-1]}"
            if len(lines) > 1
            else f" line {lines[0]}"
            if lines
            else ""
        )
        typer.secho(f"{change.path}{where}", bold=True)
        typer.echo(f"  -> {verdict.reason.value}: {verdict.reason.description}")
        chosen = [e for e in decision.explanations if e.reason == verdict.reason]
        for explanation in chosen[:10]:
            typer.echo(f"     {explanation.nodeid}")
        if len(chosen) > 10:
            typer.echo(f"     ... and {len(chosen) - 10} more")


@app.command(name="select")
def select_cmd(
    base: Annotated[
        str | None, typer.Option("--base", help="Revision to diff against.")
    ] = None,
    output_format: Annotated[
        SelectionFormat, typer.Option("--format", help="Output format.")
    ] = SelectionFormat.NODEIDS,
    explain: Annotated[
        bool,
        typer.Option("--explain", help="Print changed line -> covering test -> why."),
    ] = False,
) -> None:
    """Print the selection and exit. Runs no tests."""
    root = _root()
    decision = select(root, Config.load(root), base=base)

    if output_format is SelectionFormat.JSON:
        typer.echo(json.dumps(decision.as_dict(), indent=2))
        raise typer.Exit(code=EXIT_OK)

    if decision.full_suite:
        reasons = ", ".join(sorted({r.value for r in decision.fallback_reasons}))
        _echo_err(
            f"tia: full suite ({reasons or decision.primary_reason.value})", "yellow"
        )
        for reason in dict.fromkeys(decision.fallback_reasons):
            _echo_err(f"  {reason.value}: {reason.description}")
        if explain:
            _print_explanations(decision)
        raise typer.Exit(code=EXIT_OK)

    for nodeid in sorted(decision.selected):
        typer.echo(nodeid)
    _echo_err(f"tia: selected {len(decision.selected)} of {decision.total_tests} tests")
    if explain:
        _print_explanations(decision)


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True}
)
def run(
    ctx: typer.Context,
    base: Annotated[
        str | None, typer.Option("--base", help="Revision to diff against.")
    ] = None,
) -> None:
    """Select, then run. Extra arguments after `--` are passed to pytest."""
    root = _root()
    config = Config.load(root)
    decision = select(root, config, base=base)
    extra = list(ctx.args)

    if decision.full_suite:
        _echo_err(
            f"tia: full suite ({decision.primary_reason.value}) — "
            f"{decision.primary_reason.description}",
            "yellow",
        )
        command = [sys.executable, "-m", "pytest", *extra]
    elif not decision.selected:
        _echo_err("tia: no tests affected by this change", "green")
        raise typer.Exit(code=EXIT_OK)
    else:
        _echo_err(
            f"tia: selected {len(decision.selected)} of {decision.total_tests} "
            f"tests (map @ {diff.short(decision.map_commit)})",
            "green",
        )
        command = [sys.executable, "-m", "pytest", *extra, *sorted(decision.selected)]

    proc = subprocess.run(command, cwd=root, check=False)  # noqa: S603
    raise typer.Exit(code=proc.returncode)


@app.command()
def status() -> None:
    """Report map freshness: commit, size, test count, age."""
    root = _root()
    map_file = db.map_path(root)
    if not map_file.exists():
        _echo_err(f"tia: no map at {map_file.relative_to(root)} — run `tia build`")
        raise typer.Exit(code=EXIT_MAP_UNUSABLE)

    conn = db.connect(map_file)
    try:
        meta = db.all_meta(conn)
        counts = db.stats(conn, map_file)
    finally:
        conn.close()

    commit = meta.get("built_at_commit", "")
    fresh = (
        "fresh"
        if commit and diff.is_ancestor(root, commit, diff.head_commit(root))
        else "STALE — the map's commit is not an ancestor of HEAD"
    )
    size_mb = (counts["size_bytes"] or 0) / 1_048_576
    typer.echo(f"map          {map_file.relative_to(root)}")
    typer.echo(f"built at     {diff.short(commit)}  ({meta.get('built_at_utc', '?')})")
    typer.echo(f"freshness    {fresh}")
    typer.echo(f"tests        {counts['tests']:,}")
    typer.echo(f"files        {counts['files']:,}")
    typer.echo(f"rows         {counts['coverage_rows']:,}")
    typer.echo(f"size         {size_mb:.1f} MB")
    typer.echo(f"suite        {meta.get('suite_command', '?')}")


@app.command()
def explain(
    target: Annotated[
        str, typer.Argument(metavar="PATH:LINE", help="e.g. src/app.py:42")
    ],
) -> None:
    """Show which tests cover a line, and why."""
    root = _root()
    if ":" not in target:
        _echo_err("tia explain: expected PATH:LINE, e.g. src/app.py:42", "red")
        raise typer.Exit(code=EXIT_USAGE)
    path, _, raw_line = target.rpartition(":")
    try:
        lineno = int(raw_line)
    except ValueError as exc:
        _echo_err(f"tia explain: {raw_line!r} is not a line number", "red")
        raise typer.Exit(code=EXIT_USAGE) from exc

    map_file = db.map_path(root)
    if not map_file.exists():
        _echo_err(f"tia: no map — run `tia build` ({Reason.NO_MAP.value})")
        raise typer.Exit(code=EXIT_MAP_UNUSABLE)

    conn = db.connect(map_file)
    try:
        covering = db.tests_covering_line(conn, path, lineno)
        known = db.file_id_for(conn, path) is not None
    finally:
        conn.close()

    if not known:
        typer.echo(f"{path} is not in the map ({Reason.UNMAPPED_FILE.value})")
        typer.echo(f"  {Reason.UNMAPPED_FILE.description}")
        return
    if not covering:
        typer.echo(f"{path}:{lineno} is in the map but no test executed it.")
        typer.echo("  A change here selects nothing by line.")
        return
    typer.echo(f"{path}:{lineno} — {len(covering)} tests executed this line:")
    for nodeid in covering:
        typer.echo(f"  {nodeid}")


def main() -> None:
    """Console-script entry point."""
    app()


if __name__ == "__main__":
    main()
