"""Command-line interface for fs-tool.

Console script entry point: ``fs_tool.cli:main`` (``fs-tool``).
The package is also runnable as ``python -m fs_tool``.
"""

from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path

import typer
from click.exceptions import ClickException
from click.exceptions import Exit as ClickExit

from fs_tool import __version__
from fs_tool.core.config import load_config
from fs_tool.core.errors import ErrorCode, FsToolError
from fs_tool.core.traversal import traverse
from fs_tool.output.json import SCHEMA_VERSION, Envelope, Error
from fs_tool.safety.validation import validate_path

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


def merge_globals(
    ctx: typer.Context,
    *,
    allow_root: list[str] | None = None,
    config: str | None = None,
    format_value: str | None = None,
    json_output: bool | None = None,
    plain_output: bool | None = None,
    version: bool = False,
) -> None:
    """Merge subcommand-level global options into the CLI context.

    The root callback has already populated the context from root-level
    options; subcommand-level options override them. The configuration
    may only restrict allowed roots, never expand them (decision D4).
    """
    if version:
        typer.echo(f"fs-tool {__version__}")
        raise typer.Exit(EXIT_SUCCESS)

    if config is not None:
        ctx.obj.config = config
    if allow_root is not None:
        # Re-resolve the config with the subcommand's CLI roots.
        config_obj = load_config(
            config_path=ctx.obj.config, cli_roots=tuple(Path(root) for root in allow_root)
        )
        ctx.obj.allow_root = [str(root) for root in config_obj.allowed_roots]
    if format_value is not None:
        ctx.obj.output_format = format_value
    if json_output is not None:
        ctx.obj.json_output = json_output
    if plain_output is not None:
        ctx.obj.plain_output = plain_output

    if ctx.obj.json_output and ctx.obj.plain_output:
        raise FsToolError(
            "--json and --plain are mutually exclusive.",
            code=ErrorCode.INVALID_ARGUMENT,
        )
    ctx.obj.output_format = _resolve_format(
        ctx.obj.output_format,
        ctx.obj.json_output,
        ctx.obj.plain_output,
        sys.stdout.isatty(),
    )


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
    ctx.obj = CliContext(
        allow_root=[],
        config=None,
        output_format="auto",
        json_output=False,
        plain_output=False,
    )
    merge_globals(
        ctx,
        allow_root=list(allow_root),
        config=config,
        format_value=format_value,
        json_output=json_output,
        plain_output=plain_output,
        version=version,
    )


# Command groups are registered without commands in Phase 0; commands
# are implemented in later phases.
inspect_group = typer.Typer(name="inspect", help="Inspect the filesystem.", no_args_is_help=True)
find_group = typer.Typer(name="find", help="Find filesystem entries.", no_args_is_help=True)
duplicates_group = typer.Typer(
    name="duplicates", help="Find duplicate files.", no_args_is_help=True
)
compare_group = typer.Typer(name="compare", help="Compare directory trees.", no_args_is_help=True)
verify_group = typer.Typer(name="verify", help="Verify filesystem state.", no_args_is_help=True)
write_group = typer.Typer(name="write", help="Write operations.", no_args_is_help=True)

for group in (
    inspect_group,
    find_group,
    duplicates_group,
    compare_group,
    verify_group,
    write_group,
):
    app.add_typer(group)


@inspect_group.command(name="tree")
def inspect_tree(
    ctx: typer.Context,
    source: Path = typer.Argument(..., help="Directory to traverse."),
    max_depth: int | None = typer.Option(None, "--max-depth", help="Maximum recursion depth."),
    max_entries: int | None = typer.Option(
        None, "--max-entries", help="Maximum number of entries."
    ),
    dirs_only: bool = typer.Option(False, "--dirs-only", help="Directory entries only."),
    ignore_dir: list[str] = typer.Option(
        [],
        "--ignore-dir",
        help="Ignore a directory by name (repeatable).",
    ),
    ignore_pattern: list[str] = typer.Option(
        [],
        "--ignore-pattern",
        help="Ignore names matching a pattern (repeatable).",
    ),
) -> int:
    """Display a directory tree (JSON by default, plain with --plain).

    Global options such as ``--plain`` and ``--allow-root`` precede
    the command, e.g. ``fs-tool --plain tree /tmp``.
    """
    root = validate_path(source, tuple(ctx.obj.allow_root))
    result = traverse(
        root,
        max_depth=max_depth,
        max_entries=max_entries,
        dirs_only=dirs_only,
        ignore_dirs=frozenset(ignore_dir),
        ignore_patterns=tuple(ignore_pattern),
    )

    if ctx.obj.output_format == "plain":
        from fs_tool.output.plain import render_tree

        typer.echo(render_tree(result.entries, root))
        for error in result.errors:
            print(
                f"fs-tool: error: {error.message} ({error.path})",
                file=sys.stderr,
            )
        return EXIT_INCOMPLETE if not result.complete else EXIT_SUCCESS

    entry_dicts = [asdict(entry) for entry in result.entries]
    errors = tuple(
        Error(code="INACCESSIBLE_ENTRY", message=error.message, path=error.path)
        for error in result.errors
    )
    envelope = Envelope(
        schema_version=SCHEMA_VERSION,
        success=True,
        command="inspect.tree",
        result={
            "root": str(root),
            "entries": entry_dicts,
            "count": len(entry_dicts),
        },
        errors=errors,
        complete=result.complete,
    )
    typer.echo(envelope.to_json())
    return EXIT_INCOMPLETE if not result.complete else EXIT_SUCCESS


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
