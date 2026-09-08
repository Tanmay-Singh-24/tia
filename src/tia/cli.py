"""The tia command line. Surface and exit codes are fixed by docs/SPEC.md B.7.

Exit codes
    0  success
    1  test failure
    2  usage error (and, for now, "not implemented")
    3  map unusable

Every command here is a stub. Each one names the milestone that implements it,
so `tia --help` doubles as an honest progress report.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, NoReturn

import typer

from tia import __version__

EXIT_USAGE = 2
"""Usage error. Unimplemented commands exit with this until they land."""


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


def _not_implemented(command: str, milestone: str, **parsed: object) -> NoReturn:
    """Report a command as unimplemented, echo what it parsed, and exit.

    Echoing the parsed arguments keeps the stubs useful: the CLI contract in
    SPEC B.7 can be checked end to end before any of it is wired up.
    """
    typer.secho(
        f"tia {command}: not implemented (lands in {milestone})",
        err=True,
        fg=typer.colors.YELLOW,
    )
    if parsed:
        rendered = ", ".join(
            f"{key}={value!r}" for key, value in sorted(parsed.items())
        )
        typer.secho(f"  parsed: {rendered}", err=True, dim=True)
    raise typer.Exit(code=EXIT_USAGE)


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    version: Annotated[
        bool,
        typer.Option("--version", help="Show the tia version and exit."),
    ] = False,
) -> None:
    """Entry callback: handles --version and bare `tia`."""
    if version:
        typer.echo(f"tia {__version__}")
        raise typer.Exit(code=0)
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit(code=0)


@app.command()
def init() -> None:
    """Write .tia.toml, create .tia/, and add it to .gitignore."""
    _not_implemented("init", "D6")


@app.command()
def build(
    suite: Annotated[
        str,
        typer.Option("--suite", help="Command used to run the full suite."),
    ] = "pytest",
    jobs: Annotated[
        int | None,
        typer.Option("--jobs", "-j", help="Parallel workers for the learning run."),
    ] = None,
) -> None:
    """Run the instrumented suite and build the map."""
    _not_implemented("build", "D4", suite=suite, jobs=jobs)


@app.command()
def select(
    base: Annotated[
        str,
        typer.Option("--base", help="Revision to diff against."),
    ] = "origin/main",
    output_format: Annotated[
        SelectionFormat,
        typer.Option("--format", help="Output format for the selection."),
    ] = SelectionFormat.NODEIDS,
    explain: Annotated[
        bool,
        typer.Option(
            "--explain", help="Print changed line -> covering test -> reason."
        ),
    ] = False,
) -> None:
    """Print the selection and exit. Runs no tests."""
    _not_implemented(
        "select", "D6", base=base, format=output_format.value, explain=explain
    )


@app.command(
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def run(
    ctx: typer.Context,
    base: Annotated[
        str,
        typer.Option("--base", help="Revision to diff against."),
    ] = "origin/main",
) -> None:
    """Select, then run. Extra arguments after `--` are passed to pytest."""
    _not_implemented("run", "D7", base=base, pytest_args=ctx.args)


@app.command()
def status() -> None:
    """Report map freshness: commit, size, test count, age."""
    _not_implemented("status", "D4")


@app.command()
def explain(
    target: Annotated[
        str,
        typer.Argument(
            metavar="PATH:LINE", help="Source location, e.g. src/app.py:42."
        ),
    ],
) -> None:
    """Show which tests cover a line, and why."""
    _not_implemented("explain", "D6", target=target)


def main() -> None:
    """Console-script entry point."""
    app()


if __name__ == "__main__":
    main()
