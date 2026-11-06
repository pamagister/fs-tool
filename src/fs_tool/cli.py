"""Command-line interface for fs-tool.

Console script entry point: ``fs_tool.cli:main`` (``fs-tool``).
The package is also runnable as ``python -m fs_tool``.
"""

from __future__ import annotations

import sys

import typer
from click.exceptions import ClickException
from click.exceptions import Exit as ClickExit

from fs_tool.core.errors import ErrorCode, FsToolError

try:
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as _distribution_version
except ImportError:  # pragma: no cover - Python < 3.8, out of support
    __version__ = "0.1.0"
else:
    try:
        __version__ = _distribution_version("fs-tool")
    except PackageNotFoundError:
        # Running from source without installation.
        __version__ = "0.1.0"

# Process exit codes (plan.md section 4.3).
EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_INVALID_ARGS = 2
EXIT_ACCESS_DENIED = 3
EXIT_CONFLICT = 4
EXIT_INCOMPLETE = 5

app = typer.Typer(
    name="fs-tool",
    help="Inspect, analyze, compare and organize local filesystems.",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
)


class CliContext:
    """Shared CLI context populated by the root callback."""

    def __init__(
        self,
        allow_root: list[str],
        config: str | None,
        output_format: str,
        json_output: bool,
        plain_output: bool,
    ) -> None:
        self.allow_root = allow_root
        self.config = config
        self.output_format = output_format
        self.json_output = json_output
        self.plain_output = plain_output


def _resolve_format(
    format_value: str,
    json_output: bool,
    plain_output: bool,
    is_tty: bool,
) -> str:
    """Resolve the effective output format (plan.md decision D7).

    Precedence: explicit --json/--plain > --format > auto (TTY -> plain,
    otherwise JSON). ``--json`` and --plain`` are mutually exclusive.
    """
    if json_output and plain_output:
        raise FsToolError(
            "--json and --plain are mutually exclusive.",
            code=ErrorCode.INVALID_ARGUMENT,
        )
    if json_output:
        return "json"
    if plain_output:
        return "plain"
    if format_value not in ("auto", "json", "plain"):
        raise FsToolError(
            f"Unknown --format value {format_value!r}; use auto, json or plain.",
            code=ErrorCode.INVALID_ARGUMENT,
        )
    if format_value == "auto":
        return "plain" if is_tty else "json"
    return format_value


@app.callback()
def _root(
    ctx: typer.Context,
    allow_root: list[str] = typer.Option(
        [],
        "--allow-root",
        help="Explicitly allow an additional filesystem root (repeatable).",
    ),
    config: str | None = typer.Option(None, "--config", help="Path to TOML configuration file."),
    format_value: str = typer.Option(
        "auto", "--format", help="Output format: auto, json or plain."
    ),
    json_output: bool = typer.Option(False, "--json", help="Explicitly request JSON output."),
    plain_output: bool = typer.Option(
        False, "--plain", help="Human-readable output instead of JSON."
    ),
    version: bool = typer.Option(False, "--version", help="Show application version and exit."),
) -> None:
    """Root callback: global options and version information.

    ``--help``/``--version`` are documented exceptions to the JSON
    envelope (plan.md section 4.3).
    """
    if version:
        typer.echo(f"fs-tool {__version__}")
        raise typer.Exit(EXIT_SUCCESS)

    ctx.obj = CliContext(
        allow_root=list(allow_root),
        config=config,
        output_format=_resolve_format(format_value, json_output, plain_output, sys.stdout.isatty()),
        json_output=json_output,
        plain_output=plain_output,
    )


# Command groups are registered without commands in Phase 0; commands
# are implemented in later phases.
inspect_group = typer.Typer(name="inspect", help="Inspect the filesystem.")
find_group = typer.Typer(name="find", help="Find filesystem entries.")
duplicates_group = typer.Typer(name="duplicates", help="Find duplicate files.")
compare_group = typer.Typer(name="compare", help="Compare directory trees.")
verify_group = typer.Typer(name="verify", help="Verify filesystem state.")
write_group = typer.Typer(name="write", help="Write operations.")

for group in (
    inspect_group,
    find_group,
    duplicates_group,
    compare_group,
    verify_group,
    write_group,
):
    app.add_typer(group)


def main(argv: list[str] | None = None) -> int:
    """Application entry point.

    Returns a process exit code (plan.md section 4.3):

    * 0 - success
    * 1 - operation failed or verification discrepancies
    * 2 - invalid arguments or incomplete analysis
    * 3 - access denied or safety restriction
    * 4 - operation conflict
    * 5 - incomplete scan or verification
    """
    args = list(sys.argv[1:] if argv is None else argv)

    # ``--version`` is handled up front: typer only invokes the root
    # callback when a subcommand is selected
    # (invoke_without_command=False), so the option callback would never
    # run for ``fs-tool --version``. --help/--version are documented
    # exceptions to the JSON envelope (plan.md section 4.3).
    if "--version" in args:
        print(f"fs-tool {__version__}")
        return EXIT_SUCCESS

    try:
        result = app(args=args, standalone_mode=False)
    except FsToolError as exc:
        print(f"Error: {exc.message}", file=sys.stderr)
        return exc.exit_code
    except ClickExit as exc:
        return exc.exit_code if isinstance(exc.exit_code, int) else EXIT_SUCCESS
    except ClickException as exc:
        # Invalid usage (unknown command, bad option, ...): exit 2.
        return exc.exit_code if isinstance(exc.exit_code, int) else EXIT_FAILURE
    except Exception as exc:  # CLI boundary: report, do not swallow silently
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return EXIT_FAILURE
    return result if isinstance(result, int) else EXIT_SUCCESS
