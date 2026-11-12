"""Command-line interface for fs-tool.

Console script entry point: ``fs_tool.cli:main`` (``fs-tool``).
The package is also runnable as ``python -m fs_tool``.
"""

from __future__ import annotations

import hashlib
import json
import stat
import sys
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import typer
from click.exceptions import ClickException
from click.exceptions import Exit as ClickExit

from fs_tool import __version__
from fs_tool.core.analysis.search import find_entries, matches_extension, parse_size
from fs_tool.core.capabilities.models import CapabilityResult
from fs_tool.core.config import load_config
from fs_tool.core.errors import ErrorCode, FsToolError
from fs_tool.core.hashing import sha256_of_file
from fs_tool.core.models import EntryType, FilesystemEntry
from fs_tool.core.providers.inspection import analyze_file, inspect_metadata, read_file
from fs_tool.core.traversal import SortBy, TraversalError, build_entry, traverse
from fs_tool.operations.common import OperationReport
from fs_tool.operations.copy import copy_path
from fs_tool.operations.mkdir import make_directory
from fs_tool.operations.move import move_path
from fs_tool.output.entries import (
    INVENTORY_COMPACT_FIELDS,
    find_entry_dict,
    inventory_entry_dict,
    tree_entry_dict,
)
from fs_tool.output.json import SCHEMA_VERSION, Envelope, Error, Warning
from fs_tool.output.results import capability_result_to_dict
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
        verbose: bool = False,
    ) -> None:
        self.allow_root = allow_root
        self.config = config
        self.output_format = output_format
        self.json_output = json_output
        self.plain_output = plain_output
        self.verbose = verbose


def _resolve_format(
    format_value: str,
    json_output: bool,
    plain_output: bool,
    is_tty: bool,
) -> str:
    """Resolve the effective output format (plan.md decision D7).

    Precedence: explicit --json/--plain > --format > auto (TTY -> plain,
    otherwise JSON). ``--json`` and ``--plain`` are mutually exclusive.
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
    if format_value not in ("auto", "json", "plain", "csv", "tsv"):
        raise FsToolError(
            f"Unknown --format value {format_value!r}; use auto, json, plain, csv or tsv.",
            code=ErrorCode.INVALID_ARGUMENT,
        )
    if format_value == "auto":
        return "plain" if is_tty else "json"
    return format_value


SORT_BY_CHOICES = ("name", "size", "modified", "extension")


def _validate_sort_by(value: str) -> SortBy:
    """Validate a ``--sort-by`` value and return it unchanged."""
    if value not in SORT_BY_CHOICES:
        raise FsToolError(
            f"Invalid --sort-by value {value!r}; use name, size, modified or extension.",
            code=ErrorCode.INVALID_ARGUMENT,
        )
    return cast(SortBy, value)


def _reject_tabular(ctx: typer.Context) -> None:
    """Reject CSV/TSV output for commands that do not support it."""
    if ctx.obj.output_format in ("csv", "tsv"):
        raise FsToolError(
            f"{ctx.obj.output_format.upper()} output is only supported by inspect inventory.",
            code=ErrorCode.INVALID_ARGUMENT,
        )


def merge_globals(
    ctx: typer.Context,
    *,
    allow_root: list[str] | None = None,
    config: str | None = None,
    format_value: str | None = None,
    json_output: bool | None = None,
    plain_output: bool | None = None,
    verbose: bool | None = None,
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
    if verbose is not None:
        ctx.obj.verbose = verbose

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
        help="Set an allowed root, replacing the default Home and CWD roots (repeatable).",
    ),
    config: str | None = typer.Option(None, "--config", help="Path to TOML configuration file."),
    format_value: str = typer.Option(
        "auto",
        "--format",
        help="Output format: auto, json, plain, csv or tsv (csv/tsv inventory only).",
    ),
    json_output: bool = typer.Option(False, "--json", help="Explicitly request JSON output."),
    plain_output: bool = typer.Option(
        False, "--plain", help="Human-readable output instead of JSON."
    ),
    verbose: bool = typer.Option(
        False,
        "-v",
        "--verbose/--no-verbose",
        help=(
            "Include all available entry fields for entry collections "
            "(tree, inventory, find). Other commands are unchanged."
        ),
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
        verbose=False,
    )
    merge_globals(
        ctx,
        allow_root=list(allow_root),
        config=config,
        format_value=format_value,
        json_output=json_output,
        plain_output=plain_output,
        verbose=verbose,
        version=version,
    )


# Command groups are registered without commands in Phase 0; commands
# are implemented in later phases.
inspect_group = typer.Typer(name="inspect", help="Inspect the filesystem.", no_args_is_help=True)
verify_group = typer.Typer(name="verify", help="Verify filesystem state.", no_args_is_help=True)
write_group = typer.Typer(name="write", help="Write operations.", no_args_is_help=True)

for group in (inspect_group, verify_group, write_group):
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
    sort_by: str = typer.Option(
        "name",
        "--sort-by",
        help="Sort entries by name, size, modified or extension.",
    ),
    no_default_ignore: bool = typer.Option(
        False,
        "--no-default-ignore",
        help="Include directories from the default ignore list.",
    ),
) -> int:
    """Display a directory tree (JSON by default, plain with --plain).

    Global options such as ``--plain`` and ``--allow-root`` precede
    the command, e.g. ``fs-tool --plain inspect tree /tmp``.
    """
    _reject_tabular(ctx)
    root = validate_path(source, tuple(ctx.obj.allow_root))
    result = traverse(
        root,
        max_depth=max_depth,
        max_entries=max_entries,
        dirs_only=dirs_only,
        ignore_dirs=frozenset(ignore_dir),
        ignore_patterns=tuple(ignore_pattern),
        sort_by=_validate_sort_by(sort_by),
        use_default_ignores=not no_default_ignore,
    )

    if ctx.obj.output_format == "plain":
        from fs_tool.output.plain import render_tree

        typer.echo(render_tree(result.entries, root, verbose=ctx.obj.verbose))
        if not result.complete:
            print("fs-tool: error: scan incomplete", file=sys.stderr)
        for error in result.errors:
            print(
                f"fs-tool: error: {error.message} ({error.path})",
                file=sys.stderr,
            )
        return EXIT_INCOMPLETE if not result.complete else EXIT_SUCCESS

    entry_dicts = [tree_entry_dict(entry, verbose=ctx.obj.verbose) for entry in result.entries]
    errors = tuple(
        Error(code="INACCESSIBLE_ENTRY", message=error.message, path=error.path)
        for error in result.errors
    )
    envelope = Envelope(
        schema_version=SCHEMA_VERSION,
        success=result.complete,
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


def _info_result_dict(
    entry: FilesystemEntry,
    metadata_result: CapabilityResult | None,
) -> dict[str, Any]:
    """Serialize a filesystem entry and its metadata status for ``inspect info``."""
    entry_dict = asdict(entry)
    entry_dict["metadata_result"] = (
        capability_result_to_dict(metadata_result) if metadata_result is not None else None
    )
    return entry_dict


@inspect_group.command(name="info")
def inspect_info(
    ctx: typer.Context,
    source: Path = typer.Argument(..., help="File or directory to inspect."),
    metadata: bool = typer.Option(
        False,
        "--metadata",
        help="Deprecated compatibility flag; format metadata is extracted automatically.",
    ),
    hash_file: bool = typer.Option(
        False, "--hash", help="Calculate the SHA-256 hash of a regular file."
    ),
) -> int:
    """Inspect filesystem and format metadata for a single file or directory.

    Format metadata (PDF, ODF, OOXML) is extracted automatically when a
    provider supports the format. Content analysis belongs to
    ``inspect analyze``.

    Global options such as ``--plain`` and ``--allow-root`` precede
    the command, e.g. ``fs-tool --plain inspect info /tmp/notes.txt``.
    """
    _reject_tabular(ctx)
    del metadata  # retained as a compatibility flag; extraction is automatic
    root = validate_path(source, tuple(ctx.obj.allow_root))
    try:
        entry = build_entry(root, root)
    except FsToolError as exc:
        envelope = Envelope(
            schema_version=SCHEMA_VERSION,
            success=False,
            command="inspect.info",
            result=None,
            errors=(Error(code=exc.code, message=exc.message, path=exc.path),),
            complete=False,
        )
        typer.echo(envelope.to_json())
        return exc.exit_code

    inspection = inspect_metadata(root) if entry.type is EntryType.FILE else None
    if inspection is not None and inspection.metadata is not None:
        entry = replace(entry, metadata=inspection.metadata)

    if hash_file:
        digest = sha256_of_file(root) if entry.type is EntryType.FILE else None
        entry = replace(entry, sha256=digest)
        if entry.type is EntryType.FILE and digest is None:
            message = f"Cannot hash {root}"
            result = _info_result_dict(entry, inspection.result if inspection is not None else None)
            if ctx.obj.output_format == "plain":
                print(f"fs-tool: error: {message}", file=sys.stderr)
                return EXIT_INCOMPLETE
            envelope = Envelope(
                schema_version=SCHEMA_VERSION,
                success=False,
                command="inspect.info",
                result=result,
                errors=(
                    Error(
                        code=ErrorCode.INCOMPLETE_SCAN.value,
                        message=message,
                        path=str(root),
                    ),
                ),
                complete=False,
            )
            typer.echo(envelope.to_json())
            return EXIT_INCOMPLETE

    metadata_result = inspection.result if inspection is not None else None
    if ctx.obj.output_format == "plain":
        from fs_tool.output.plain import render_info

        typer.echo(render_info(entry, metadata_result))
        return EXIT_SUCCESS

    envelope = Envelope(
        schema_version=SCHEMA_VERSION,
        success=True,
        command="inspect.info",
        result=_info_result_dict(entry, metadata_result),
        complete=True,
    )
    typer.echo(envelope.to_json())
    return EXIT_SUCCESS


@inspect_group.command(name="analyze")
def inspect_analyze(
    ctx: typer.Context,
    source: Path = typer.Argument(..., help="Regular file to analyze."),
    hash_file: bool = typer.Option(
        False, "--hash", help="Calculate the SHA-256 hash of the source file."
    ),
) -> int:
    """Run all applicable structured content analyses for a regular file.

    Analyses return structure without complete file content. The result
    contains one entry per applicable capability with an explicit
    ``available``, ``unavailable`` or ``failed`` status. Hashes always
    identify the original source file.

    Global options such as ``--plain`` and ``--allow-root`` precede
    the command, e.g. ``fs-tool --plain inspect analyze /tmp/source.py``.
    """
    _reject_tabular(ctx)
    root = validate_path(source, tuple(ctx.obj.allow_root))

    try:
        lst = root.lstat()
    except OSError as exc:
        envelope = Envelope(
            schema_version=SCHEMA_VERSION,
            success=False,
            command="inspect.analyze",
            result=None,
            errors=(
                Error(
                    code=ErrorCode.INVALID_ARGUMENT,
                    message=f"Cannot stat {root}: {exc.strerror or exc}",
                    path=str(root),
                ),
            ),
            complete=False,
        )
        typer.echo(envelope.to_json())
        return EXIT_INVALID_ARGS

    if stat.S_ISLNK(lst.st_mode):
        envelope = Envelope(
            schema_version=SCHEMA_VERSION,
            success=False,
            command="inspect.analyze",
            result=None,
            errors=(
                Error(
                    code=ErrorCode.INVALID_ARGUMENT,
                    message="Refusing to analyze a symbolic link.",
                    path=str(root),
                ),
            ),
            complete=False,
        )
        typer.echo(envelope.to_json())
        return EXIT_INVALID_ARGS

    if not stat.S_ISREG(lst.st_mode):
        envelope = Envelope(
            schema_version=SCHEMA_VERSION,
            success=False,
            command="inspect.analyze",
            result=None,
            errors=(
                Error(
                    code=ErrorCode.INVALID_ARGUMENT,
                    message="inspect analyze requires a regular file.",
                    path=str(root),
                ),
            ),
            complete=False,
        )
        typer.echo(envelope.to_json())
        return EXIT_INVALID_ARGS

    report = analyze_file(root)
    result: dict[str, Any] = {
        "path": str(root),
        "name": root.name,
        "extension": root.suffix.lower() or None,
        "size": lst.st_size,
        "sha256": None,
        "supported": report.supported,
        "analyses": [capability_result_to_dict(item) for item in report.results],
    }

    if hash_file:
        digest = sha256_of_file(root)
        result["sha256"] = digest
        if digest is None:
            message = f"Cannot hash {root}"
            if ctx.obj.output_format == "plain":
                from fs_tool.output.plain import render_analyze

                typer.echo(render_analyze(result))
                print(f"fs-tool: error: {message}", file=sys.stderr)
                return EXIT_INCOMPLETE
            envelope = Envelope(
                schema_version=SCHEMA_VERSION,
                success=False,
                command="inspect.analyze",
                result=result,
                errors=(
                    Error(
                        code=ErrorCode.INCOMPLETE_SCAN.value,
                        message=message,
                        path=str(root),
                    ),
                ),
                complete=False,
            )
            typer.echo(envelope.to_json())
            return EXIT_INCOMPLETE

    if ctx.obj.output_format == "plain":
        from fs_tool.output.plain import render_analyze

        typer.echo(render_analyze(result))
        return EXIT_SUCCESS

    envelope = Envelope(
        schema_version=SCHEMA_VERSION,
        success=True,
        command="inspect.analyze",
        result=result,
        complete=True,
    )
    typer.echo(envelope.to_json())
    return EXIT_SUCCESS


# Tree-hash algorithm version 2: only structure- and content-related fields
# are hashed. Environment-specific fields (permissions, ownership, MIME type,
# symlink target, timestamps, absolute path, device/inode) are excluded so the
# hash is portable across machines and users. Directory and symlink sizes are
# normalized to null because their ``st_size`` is filesystem- or target-path-
# dependent rather than content.
TREE_HASH_FIELDS = ("rel_path", "type", "extension", "size", "sha256")


def _tree_hash_projection(entry: dict[str, Any]) -> dict[str, Any]:
    """Project one entry onto the portable tree-hash field set."""
    entry_type = entry.get("type")
    type_value = entry_type.value if isinstance(entry_type, EntryType) else entry_type
    size = entry.get("size")
    if type_value != EntryType.FILE.value:
        size = None
    return {
        "rel_path": entry.get("rel_path"),
        "type": type_value,
        "extension": entry.get("extension"),
        "size": size,
        "sha256": entry.get("sha256"),
    }


def _compute_tree_hash(entries: list[dict[str, Any]], schema_version: int = SCHEMA_VERSION) -> str:
    """Compute a deterministic, portable tree hash over inventory entries.

    Only :data:`TREE_HASH_FIELDS` are hashed. Entries are sorted by
    ``rel_path``. Fields that are filesystem- or environment-specific
    (absolute ``path``, inode ``dev_ino``, timestamps, ``mode``, ``owner``,
    ``mime_type``, ``target``) are excluded so the hash depends only on
    structure and content, making it portable across machines and
    deterministic across time. ``generated_at`` is never part of the hash
    input. The result is versioned via ``schema_version``.
    """
    ordered = sorted(entries, key=lambda entry: entry.get("rel_path") or "")
    hashable = {
        "schema_version": schema_version,
        "entries": [_tree_hash_projection(entry) for entry in ordered],
    }
    canonical = json.dumps(hashable, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


INVENTORY_ALLOWED_FIELDS = tuple(
    field_name for field_name in FilesystemEntry.__dataclass_fields__ if field_name != "path"
)


def _inventory_output_dict(
    entry: FilesystemEntry,
    digest: str | None,
    *,
    verbose: bool,
    fields: tuple[str, ...] | None,
    include_hash: bool,
) -> dict[str, Any]:
    """Build one inventory entry without materializing every field."""
    if verbose:
        data = inventory_entry_dict(entry, verbose=True)
        data["sha256"] = digest
        return data
    if fields is not None:
        data = {}
        for field_name in fields:
            data[field_name] = digest if field_name == "sha256" else getattr(entry, field_name)
        return data
    data = {field_name: getattr(entry, field_name) for field_name in INVENTORY_COMPACT_FIELDS}
    if include_hash:
        data["sha256"] = digest
    return data


def _inventory_entry_matches(
    entry: FilesystemEntry,
    *,
    extension: str | None,
    min_size: int | None,
    max_size: int | None,
) -> bool:
    """Return whether an entry passes the inventory content filters."""
    if entry.type is not EntryType.FILE:
        return True
    if extension is not None and not matches_extension(entry, extension):
        return False
    if entry.size is None:
        return min_size is None and max_size is None
    if min_size is not None and entry.size < min_size:
        return False
    if max_size is not None and entry.size > max_size:
        return False
    return True


@inspect_group.command(name="inventory")
def inspect_inventory(
    ctx: typer.Context,
    source: Path = typer.Argument(..., help="Directory to inventory."),
    hash_files: bool = typer.Option(False, "--hash", help="Calculate SHA-256 hashes for files."),
    tree_hash: bool = typer.Option(
        False,
        "--tree-hash",
        help="Calculate aggregate tree hash (complete scans only).",
    ),
    max_depth: int | None = typer.Option(None, "--max-depth", help="Maximum recursion depth."),
    max_entries: int | None = typer.Option(
        None, "--max-entries", help="Maximum number of entries."
    ),
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
    dirs_only: bool = typer.Option(False, "--dirs-only", help="Directory entries only."),
    sort_by: str = typer.Option(
        "name",
        "--sort-by",
        help="Sort entries by name, size, modified or extension.",
    ),
    no_default_ignore: bool = typer.Option(
        False,
        "--no-default-ignore",
        help="Include directories from the default ignore list.",
    ),
    extension: str | None = typer.Option(
        None,
        "--extension",
        help="Only include files with this extension.",
    ),
    min_size: str | None = typer.Option(
        None,
        "--min-size",
        help="Minimum file size, for example 1K, 2M or 1G.",
    ),
    max_size: str | None = typer.Option(
        None,
        "--max-size",
        help="Maximum file size, for example 1K, 2M or 1G.",
    ),
    fields: str | None = typer.Option(
        None,
        "--fields",
        help="Comma-separated entry fields to return.",
    ),
    max_hash_bytes: str | None = typer.Option(
        None,
        "--max-hash-bytes",
        help="Skip hashing files larger than SIZE.",
    ),
    progress: bool = typer.Option(
        False,
        "--progress",
        help="Write progress information to stderr.",
    ),
) -> int:
    """Create a deterministic inventory of a directory tree.

    Global options such as ``--plain`` and ``--allow-root`` precede
    the command, e.g. ``fs-tool --plain inspect inventory /tmp``.
    """
    root = validate_path(source, tuple(ctx.obj.allow_root))

    def invalid(message: str) -> int:
        envelope = Envelope(
            schema_version=SCHEMA_VERSION,
            success=False,
            command="inspect.inventory",
            result=None,
            errors=(
                Error(
                    code=ErrorCode.INVALID_ARGUMENT,
                    message=message,
                    path=str(root),
                ),
            ),
            complete=False,
        )
        typer.echo(envelope.to_json())
        return EXIT_INVALID_ARGS

    min_size_value: int | None = None
    if min_size is not None:
        try:
            min_size_value = parse_size(min_size)
        except ValueError as exc:
            return invalid(f"Invalid --min-size value {min_size!r}: {exc}")

    max_size_value: int | None = None
    if max_size is not None:
        try:
            max_size_value = parse_size(max_size)
        except ValueError as exc:
            return invalid(f"Invalid --max-size value {max_size!r}: {exc}")

    max_hash_bytes_value: int | None = None
    if max_hash_bytes is not None:
        try:
            max_hash_bytes_value = parse_size(max_hash_bytes)
        except ValueError as exc:
            return invalid(f"Invalid --max-hash-bytes value {max_hash_bytes!r}: {exc}")

    requested_fields: tuple[str, ...] | None = None
    if fields is not None:
        requested_fields = tuple(part.strip() for part in fields.split(",") if part.strip())
        if not requested_fields:
            return invalid("--fields must list at least one field.")
        unknown = [name for name in requested_fields if name not in INVENTORY_ALLOWED_FIELDS]
        if unknown:
            return invalid(
                f"Invalid --fields value(s): {', '.join(unknown)}. "
                f"Allowed fields: {', '.join(INVENTORY_ALLOWED_FIELDS)}."
            )

    def report_progress(count: int) -> None:
        print(f"fs-tool: scanned {count} entries", file=sys.stderr)

    result = traverse(
        root,
        max_depth=max_depth,
        max_entries=max_entries,
        dirs_only=dirs_only,
        ignore_dirs=frozenset(ignore_dir),
        ignore_patterns=tuple(ignore_pattern),
        sort_by=_validate_sort_by(sort_by),
        use_default_ignores=not no_default_ignore,
        progress=report_progress if progress else None,
    )
    if progress:
        print(f"fs-tool: scan finished: {len(result.entries)} entries", file=sys.stderr)

    warnings_list: list[Warning] = []
    selected_entries: list[FilesystemEntry] = []
    filtered = 0
    for entry in result.entries:
        if _inventory_entry_matches(
            entry,
            extension=extension,
            min_size=min_size_value,
            max_size=max_size_value,
        ):
            selected_entries.append(entry)
        else:
            filtered += 1

    # Filters define the inventory scope. Hashing and tree_hash therefore see
    # only the selected entries; filtered files are never opened.
    digests: list[str | None] = []
    for index, entry in enumerate(selected_entries, start=1):
        digest: str | None = None
        if hash_files and entry.type is EntryType.FILE:
            if max_hash_bytes_value is not None and (entry.size or 0) > max_hash_bytes_value:
                warnings_list.append(
                    Warning(
                        code="HASH_SKIPPED",
                        message=(
                            f"Skipped hashing {entry.path}; size {entry.size} "
                            f"exceeds limit {max_hash_bytes_value}."
                        ),
                        path=entry.path,
                        details={"size": entry.size, "limit": max_hash_bytes_value},
                    )
                )
            else:
                digest = sha256_of_file(entry.path)
                if digest is None:
                    result.complete = False
                    result.errors.append(
                        TraversalError(
                            path=entry.path,
                            message=f"Cannot hash {entry.path}",
                        )
                    )
        digests.append(digest)
        if progress and index % 1000 == 0:
            print(f"fs-tool: hashed {index} files", file=sys.stderr)

    selected: list[tuple[FilesystemEntry, str | None]] = list(zip(selected_entries, digests))

    verbose = ctx.obj.verbose and requested_fields is None
    entry_dicts = [
        _inventory_output_dict(
            entry,
            digest,
            verbose=verbose,
            fields=requested_fields,
            include_hash=hash_files,
        )
        for entry, digest in selected
    ]

    errors = tuple(
        Error(code="INACCESSIBLE_ENTRY", message=error.message, path=error.path)
        for error in result.errors
    )

    tree_hash_value: str | None = None
    if tree_hash and result.complete:
        # Hashing the canonical projection keeps tree_hash stable regardless
        # of the selected output profile.
        hash_entries = [
            {
                "rel_path": entry.rel_path,
                "type": entry.type,
                "extension": entry.extension,
                "size": entry.size,
                "sha256": digest,
            }
            for entry, digest in selected
        ]
        tree_hash_value = _compute_tree_hash(hash_entries)

    inventory: dict[str, Any] = {
        "root": str(root),
        "entries": entry_dicts,
        "count": len(entry_dicts),
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "complete": result.complete,
        "skipped": result.skipped,
        "truncated": result.truncated,
    }
    if filtered:
        inventory["filtered"] = filtered
    if tree_hash_value is not None:
        inventory["tree_hash"] = tree_hash_value

    if ctx.obj.output_format in ("csv", "tsv"):
        from fs_tool.output.tabular import render_inventory_tabular

        delimiter = "\t" if ctx.obj.output_format == "tsv" else ","
        typer.echo(render_inventory_tabular(inventory, delimiter=delimiter), nl=False)
        if not result.complete:
            print("fs-tool: error: scan incomplete", file=sys.stderr)
        for warning in warnings_list:
            print(f"fs-tool: warning: {warning.message} ({warning.path})", file=sys.stderr)
        for error in result.errors:
            print(
                f"fs-tool: error: {error.message} ({error.path})",
                file=sys.stderr,
            )
        return EXIT_INCOMPLETE if not result.complete else EXIT_SUCCESS

    if ctx.obj.output_format == "plain":
        from fs_tool.output.plain import render_inventory

        typer.echo(render_inventory(inventory, root, verbose=verbose))
        if not result.complete:
            print("fs-tool: error: scan incomplete", file=sys.stderr)
        for warning in warnings_list:
            print(f"fs-tool: warning: {warning.message} ({warning.path})", file=sys.stderr)
        for error in result.errors:
            print(
                f"fs-tool: error: {error.message} ({error.path})",
                file=sys.stderr,
            )
        return EXIT_INCOMPLETE if not result.complete else EXIT_SUCCESS

    envelope = Envelope(
        schema_version=SCHEMA_VERSION,
        success=result.complete,
        command="inspect.inventory",
        result=inventory,
        errors=errors,
        warnings=tuple(warnings_list),
        complete=result.complete,
    )
    typer.echo(envelope.to_json())
    return EXIT_INCOMPLETE if not result.complete else EXIT_SUCCESS


@inspect_group.command(name="read")
def inspect_read(
    ctx: typer.Context,
    source: Path = typer.Argument(..., help="Text file to read."),
    max_bytes: int = typer.Option(65536, "--max-bytes", help="Maximum number of bytes to read."),
) -> int:
    """Read bounded textual content from a regular file.

    Plain text is read as UTF-8. PDF files are read through the optional
    ``pypdf`` dependency and return extracted text with page boundaries.
    Symlinks are never followed and binary content is rejected. Content is
    truncated at ``--max-bytes`` with ``truncated`` set in the result.

    Global options such as ``--plain`` and ``--allow-root`` precede
    the command, e.g. ``fs-tool --plain inspect read /tmp/notes.txt``.
    """
    _reject_tabular(ctx)
    root = validate_path(source, tuple(ctx.obj.allow_root))

    try:
        lst = root.lstat()
    except OSError as exc:
        envelope = Envelope(
            schema_version=SCHEMA_VERSION,
            success=False,
            command="inspect.read",
            result=None,
            errors=(
                Error(
                    code=ErrorCode.INVALID_ARGUMENT,
                    message=f"Cannot stat {root}: {exc.strerror or exc}",
                    path=str(root),
                ),
            ),
            complete=False,
        )
        typer.echo(envelope.to_json())
        return EXIT_INVALID_ARGS

    if stat.S_ISLNK(lst.st_mode):
        envelope = Envelope(
            schema_version=SCHEMA_VERSION,
            success=False,
            command="inspect.read",
            result=None,
            errors=(
                Error(
                    code=ErrorCode.INVALID_ARGUMENT,
                    message="Refusing to read a symbolic link.",
                    path=str(root),
                ),
            ),
            complete=False,
        )
        typer.echo(envelope.to_json())
        return EXIT_INVALID_ARGS

    if not stat.S_ISREG(lst.st_mode):
        envelope = Envelope(
            schema_version=SCHEMA_VERSION,
            success=False,
            command="inspect.read",
            result=None,
            errors=(
                Error(
                    code=ErrorCode.INVALID_ARGUMENT,
                    message="Refusing to read a non-regular file.",
                    path=str(root),
                ),
            ),
            complete=False,
        )
        typer.echo(envelope.to_json())
        return EXIT_INVALID_ARGS

    try:
        content = read_file(root, max_bytes=max_bytes)
    except FsToolError as exc:
        envelope = Envelope(
            schema_version=SCHEMA_VERSION,
            success=False,
            command="inspect.read",
            result=None,
            errors=(
                Error(
                    code=exc.code.value,
                    message=exc.message,
                    path=str(root),
                ),
            ),
            complete=False,
        )
        typer.echo(envelope.to_json())
        return exc.exit_code

    result: dict[str, Any] = {
        "path": str(root),
        "name": root.name,
        "size": lst.st_size,
        "content": content.content,
        "truncated": content.truncated,
        "encoding": content.encoding,
        "format": content.format,
        "representation": content.representation,
    }
    if content.page_count is not None:
        result["page_count"] = content.page_count
        result["pages"] = [{"index": page.index, "content": page.content} for page in content.pages]

    if ctx.obj.output_format == "plain":
        typer.echo(content.content)
        if content.truncated:
            print(
                f"fs-tool: warning: content truncated at {max_bytes} bytes",
                file=sys.stderr,
            )
        return EXIT_SUCCESS

    envelope = Envelope(
        schema_version=SCHEMA_VERSION,
        success=True,
        command="inspect.read",
        result=result,
        complete=True,
    )
    typer.echo(envelope.to_json())
    return EXIT_SUCCESS


@app.command(name="capabilities")
def capabilities_cmd(ctx: typer.Context) -> int:
    """List supported capabilities and their current availability.

    Every capability reports its requirements, missing prerequisites and
    actionable next steps. The command only checks the environment; it does
    not analyze files, install packages or download resources.

    Example: ``fs-tool capabilities --plain``.
    """
    _reject_tabular(ctx)
    from fs_tool.core.capabilities.report import capabilities_report

    report = capabilities_report()

    if ctx.obj.output_format == "plain":
        from fs_tool.output.plain import render_capabilities

        typer.echo(render_capabilities(report))
        return EXIT_SUCCESS

    envelope = Envelope(
        schema_version=SCHEMA_VERSION,
        success=True,
        command="capabilities",
        result=report,
        complete=True,
    )
    typer.echo(envelope.to_json())
    return EXIT_SUCCESS


def _emit_setup_error(ctx: typer.Context, message: str) -> int:
    """Emit an invalid setup invocation in the selected output format."""
    if ctx.obj.output_format == "plain":
        print(f"fs-tool: error: {message}", file=sys.stderr)
    else:
        envelope = Envelope(
            schema_version=SCHEMA_VERSION,
            success=False,
            command="setup",
            result=None,
            errors=(
                Error(
                    code=ErrorCode.INVALID_ARGUMENT.value,
                    message=message,
                ),
            ),
            complete=False,
        )
        typer.echo(envelope.to_json())
    return EXIT_INVALID_ARGS


@app.command(name="setup")
def setup_cmd(
    ctx: typer.Context,
    capability: str | None = typer.Argument(
        None,
        help="Capability to prepare: pdf, image or yolo.",
    ),
    all_targets: bool = typer.Option(
        False,
        "--all",
        help="Prepare every setup target (pdf, image and yolo).",
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Replace an existing invalid model file (yolo only).",
    ),
) -> int:
    """Prepare optional capabilities without changing the Python environment.

    ``pdf`` and ``image`` check their Python dependencies and report exact
    installation commands. ``yolo`` additionally downloads and verifies the
    model when it is missing. Use ``--all`` to prepare every target
    independently.

    Example: ``fs-tool setup yolo --plain``.
    """
    _reject_tabular(ctx)
    from fs_tool.setup.service import SETUP_TARGET_NAMES, setup_report

    if all_targets and capability is not None:
        return _emit_setup_error(ctx, "Specify either a capability or --all, not both.")
    if not all_targets and capability is None:
        return _emit_setup_error(
            ctx,
            "Specify a capability (pdf, image or yolo) or use --all.",
        )
    if capability is not None and capability not in SETUP_TARGET_NAMES:
        return _emit_setup_error(
            ctx,
            f"Unknown setup target {capability!r}; use pdf, image or yolo.",
        )

    target_names = SETUP_TARGET_NAMES if capability is None else (capability,)
    report = setup_report(target_names, force=force)
    failed = report["failed_count"] > 0

    if ctx.obj.output_format == "plain":
        from fs_tool.output.plain import render_setup

        typer.echo(render_setup(report))
        return EXIT_FAILURE if failed else EXIT_SUCCESS

    errors = tuple(
        Error(
            code=target.get("error_code") or ErrorCode.SETUP_FAILED.value,
            message=target["message"],
            path=(target.get("resource") or {}).get("path"),
        )
        for target in report["targets"]
        if target["status"] == "failed"
    )
    envelope = Envelope(
        schema_version=SCHEMA_VERSION,
        success=not failed,
        command="setup",
        result=report,
        errors=errors,
        complete=True,
    )
    typer.echo(envelope.to_json())
    return EXIT_FAILURE if failed else EXIT_SUCCESS


@app.command(name="find")
def find_cmd(
    ctx: typer.Context,
    source: Path = typer.Argument(..., help="Directory to search."),
    name: list[str] = typer.Option(
        [], "--name", help="Match filenames against a glob pattern (repeatable)."
    ),
    extension: str | None = typer.Option(
        None, "--extension", help="Filter by file extension (e.g. py, .pdf)."
    ),
    entry_type: str | None = typer.Option(
        None, "--type", help="Filter by entry type: file, directory, symlink, other."
    ),
    min_size: str | None = typer.Option(
        None, "--min-size", help="Minimum file size (e.g. 1K, 2M, 1G)."
    ),
    max_size: str | None = typer.Option(
        None, "--max-size", help="Maximum file size (e.g. 1K, 2M, 1G)."
    ),
    modified_after: str | None = typer.Option(
        None, "--modified-after", help="Entries modified at or after this ISO-8601 timestamp."
    ),
    modified_before: str | None = typer.Option(
        None, "--modified-before", help="Entries modified at or before this ISO-8601 timestamp."
    ),
    max_depth: int | None = typer.Option(None, "--max-depth", help="Maximum recursion depth."),
    max_entries: int | None = typer.Option(
        None, "--max-entries", help="Maximum number of entries to scan."
    ),
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
    sort_by: str = typer.Option(
        "name",
        "--sort-by",
        help="Sort matches by name, size, modified or extension.",
    ),
    no_default_ignore: bool = typer.Option(
        False,
        "--no-default-ignore",
        help="Include directories from the default ignore list.",
    ),
) -> int:
    """Find filesystem entries matching filters.

    Example: ``fs-tool find ~/Documents --name "*.pdf" --plain``.
    """
    _reject_tabular(ctx)
    root = validate_path(source, tuple(ctx.obj.allow_root))

    type_enum: EntryType | None = None
    if entry_type is not None:
        try:
            type_enum = EntryType(entry_type.lower())
        except ValueError:
            envelope = Envelope(
                schema_version=SCHEMA_VERSION,
                success=False,
                command="find",
                result=None,
                errors=(
                    Error(
                        code=ErrorCode.INVALID_ARGUMENT,
                        message=(
                            f"Invalid --type value {entry_type!r}; "
                            "use file, directory, symlink or other."
                        ),
                        path=str(root),
                    ),
                ),
                complete=False,
            )
            typer.echo(envelope.to_json())
            return EXIT_INVALID_ARGS

    min_size_int: int | None = None
    if min_size is not None:
        try:
            min_size_int = parse_size(min_size)
        except ValueError as exc:
            envelope = Envelope(
                schema_version=SCHEMA_VERSION,
                success=False,
                command="find",
                result=None,
                errors=(
                    Error(
                        code=ErrorCode.INVALID_ARGUMENT,
                        message=f"Invalid --min-size value {min_size!r}: {exc}",
                        path=str(root),
                    ),
                ),
                complete=False,
            )
            typer.echo(envelope.to_json())
            return EXIT_INVALID_ARGS

    max_size_int: int | None = None
    if max_size is not None:
        try:
            max_size_int = parse_size(max_size)
        except ValueError as exc:
            envelope = Envelope(
                schema_version=SCHEMA_VERSION,
                success=False,
                command="find",
                result=None,
                errors=(
                    Error(
                        code=ErrorCode.INVALID_ARGUMENT,
                        message=f"Invalid --max-size value {max_size!r}: {exc}",
                        path=str(root),
                    ),
                ),
                complete=False,
            )
            typer.echo(envelope.to_json())
            return EXIT_INVALID_ARGS

    for option_name, timestamp in (
        ("--modified-after", modified_after),
        ("--modified-before", modified_before),
    ):
        if timestamp is None:
            continue
        try:
            datetime.fromisoformat(timestamp)
        except ValueError:
            envelope = Envelope(
                schema_version=SCHEMA_VERSION,
                success=False,
                command="find",
                result=None,
                errors=(
                    Error(
                        code=ErrorCode.INVALID_ARGUMENT,
                        message=(
                            f"Invalid {option_name} value {timestamp!r}; "
                            "expected an ISO-8601 timestamp."
                        ),
                        path=str(root),
                    ),
                ),
                complete=False,
            )
            typer.echo(envelope.to_json())
            return EXIT_INVALID_ARGS

    matching, errors, complete = find_entries(
        root,
        name_patterns=tuple(name),
        extension=extension,
        entry_type=type_enum,
        min_size=min_size_int,
        max_size=max_size_int,
        modified_after=modified_after,
        modified_before=modified_before,
        max_depth=max_depth,
        max_entries=max_entries,
        ignore_dirs=frozenset(ignore_dir),
        ignore_patterns=tuple(ignore_pattern),
        sort_by=_validate_sort_by(sort_by),
        use_default_ignores=not no_default_ignore,
    )

    entry_dicts = [find_entry_dict(entry, verbose=ctx.obj.verbose) for entry in matching]
    error_tuples = tuple(
        Error(code="INACCESSIBLE_ENTRY", message=message, path=str(root)) for message in errors
    )

    result: dict[str, Any] = {
        "root": str(root),
        "entries": entry_dicts,
        "count": len(entry_dicts),
        "complete": complete,
    }

    if ctx.obj.output_format == "plain":
        from fs_tool.output.plain import render_find

        typer.echo(render_find(matching, root, verbose=ctx.obj.verbose))
        if not complete:
            print("fs-tool: error: scan incomplete", file=sys.stderr)
        for message in errors:
            print(f"fs-tool: error: {message}", file=sys.stderr)
        return EXIT_INCOMPLETE if not complete else EXIT_SUCCESS

    envelope = Envelope(
        schema_version=SCHEMA_VERSION,
        success=complete,
        command="find",
        result=result,
        errors=error_tuples,
        complete=complete,
    )
    typer.echo(envelope.to_json())
    return EXIT_INCOMPLETE if not complete else EXIT_SUCCESS


@app.command(name="duplicates")
def duplicates_cmd(
    ctx: typer.Context,
    source: Path = typer.Argument(..., help="Directory to search for duplicates."),
    min_size: str = typer.Option(
        "1", "--min-size", help="Minimum file size (e.g. 1K, 2M). Default 1 byte."
    ),
    include_empty: bool = typer.Option(
        False, "--include-empty", help="Include empty files in duplicate detection."
    ),
    max_entries: int | None = typer.Option(
        None, "--max-entries", help="Maximum number of entries to scan."
    ),
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
    no_default_ignore: bool = typer.Option(
        False,
        "--no-default-ignore",
        help="Include directories from the default ignore list.",
    ),
) -> int:
    """Find files with identical content.

    Uses file size as an initial filter, then SHA-256 hashing for
    same-size candidates. Hardlinks are not counted as duplicates.

    Example: ``fs-tool duplicates ~/Archive --plain``.
    """
    _reject_tabular(ctx)
    root = validate_path(source, tuple(ctx.obj.allow_root))

    try:
        min_size_int = parse_size(min_size)
    except ValueError as exc:
        envelope = Envelope(
            schema_version=SCHEMA_VERSION,
            success=False,
            command="duplicates",
            result=None,
            errors=(
                Error(
                    code=ErrorCode.INVALID_ARGUMENT,
                    message=f"Invalid --min-size value {min_size!r}: {exc}",
                    path=str(root),
                ),
            ),
            complete=False,
        )
        typer.echo(envelope.to_json())
        return EXIT_INVALID_ARGS

    from fs_tool.core.analysis.duplicates import find_duplicates

    dup_result = find_duplicates(
        root,
        min_size=min_size_int,
        include_empty=include_empty,
        max_entries=max_entries,
        ignore_dirs=frozenset(ignore_dir),
        ignore_patterns=tuple(ignore_pattern),
        use_default_ignores=not no_default_ignore,
    )

    groups = [
        {
            "sha256": g.sha256,
            "size": g.size,
            "count": g.count,
            "files": g.files,
        }
        for g in dup_result.groups
    ]

    total_duplicate_files = sum(g.count for g in dup_result.groups)

    result: dict[str, Any] = {
        "root": str(root),
        "duplicate_groups": groups,
        "duplicate_group_count": len(groups),
        "duplicate_file_count": total_duplicate_files,
        "complete": dup_result.complete,
    }

    error_tuples = tuple(
        Error(code="INACCESSIBLE_ENTRY", message=message, path=str(root))
        for message in dup_result.errors
    )

    if ctx.obj.output_format == "plain":
        from fs_tool.output.plain import render_duplicates

        typer.echo(render_duplicates(groups))
        if not dup_result.complete:
            print("fs-tool: error: scan incomplete", file=sys.stderr)
        for message in dup_result.errors:
            print(f"fs-tool: error: {message}", file=sys.stderr)
        return EXIT_INCOMPLETE if not dup_result.complete else EXIT_SUCCESS

    envelope = Envelope(
        schema_version=SCHEMA_VERSION,
        success=dup_result.complete,
        command="duplicates",
        result=result,
        errors=error_tuples,
        complete=dup_result.complete,
    )
    typer.echo(envelope.to_json())
    return EXIT_INCOMPLETE if not dup_result.complete else EXIT_SUCCESS


@app.command(name="compare")
def compare_cmd(
    ctx: typer.Context,
    source: Path = typer.Argument(..., help="Source directory to compare."),
    destination: Path = typer.Argument(..., help="Destination directory to compare."),
    max_entries: int | None = typer.Option(
        None, "--max-entries", help="Maximum number of entries to scan per tree."
    ),
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
    no_default_ignore: bool = typer.Option(
        False,
        "--no-default-ignore",
        help="Include directories from the default ignore list.",
    ),
) -> int:
    """Compare two directory trees.

    Identifies identical, missing, changed, unexpected, type-conflict,
    and unsupported entries using relative paths and SHA-256 hashing.

    Example: ``fs-tool compare ~/Docs ~/Docs_Backup --plain``.
    """
    _reject_tabular(ctx)
    source_root = validate_path(source, tuple(ctx.obj.allow_root))
    dest_root = validate_path(destination, tuple(ctx.obj.allow_root))

    from fs_tool.core.analysis.comparison import compare_trees

    comparison = compare_trees(
        source_root,
        dest_root,
        max_entries=max_entries,
        ignore_dirs=frozenset(ignore_dir),
        ignore_patterns=tuple(ignore_pattern),
        use_default_ignores=not no_default_ignore,
    )

    result: dict[str, Any] = {
        "source": str(source_root),
        "destination": str(dest_root),
        "identical": comparison.identical,
        "missing": comparison.missing,
        "changed": comparison.changed,
        "unexpected": comparison.unexpected,
        "type_conflicts": comparison.type_conflicts,
        "unsupported": comparison.unsupported,
        "complete": comparison.complete,
    }

    error_tuples = tuple(
        Error(code="INACCESSIBLE_ENTRY", message=message, path=str(source_root))
        for message in comparison.errors
    )

    if ctx.obj.output_format == "plain":
        from fs_tool.output.plain import render_compare

        typer.echo(render_compare(result))
        if not comparison.complete:
            print("fs-tool: error: comparison incomplete", file=sys.stderr)
        for message in comparison.errors:
            print(f"fs-tool: error: {message}", file=sys.stderr)
        return EXIT_INCOMPLETE if not comparison.complete else EXIT_SUCCESS

    envelope = Envelope(
        schema_version=SCHEMA_VERSION,
        success=comparison.complete,
        command="compare",
        result=result,
        errors=error_tuples,
        complete=comparison.complete,
    )
    typer.echo(envelope.to_json())
    return EXIT_INCOMPLETE if not comparison.complete else EXIT_SUCCESS


@verify_group.command(name="inventory")
def verify_inventory_cmd(
    ctx: typer.Context,
    inventory_file: Path = typer.Argument(..., help="Path to inventory JSON file."),
    target: Path = typer.Argument(..., help="Target directory to verify."),
    max_entries: int | None = typer.Option(
        None, "--max-entries", help="Maximum number of entries to scan."
    ),
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
    match_mode: str = typer.Option(
        "path",
        "--match",
        help="Comparison mode: path (default) or content.",
    ),
) -> int:
    """Verify a directory against an inventory file.

    Checks schema_version, then compares entries. Path mode reports missing,
    unexpected, size mismatch, and hash mismatch entries. Content mode ignores
    paths and compares file (size, sha256) pairs and symlink targets as a
    multiset, which verifies reorganizations that rename or move files.

    Global options such as ``--plain`` and ``--allow-root`` precede
    the command, e.g. ``fs-tool --plain verify inventory inventory.json ~/Documents``.
    """
    _reject_tabular(ctx)
    target_root = validate_path(target, tuple(ctx.obj.allow_root))

    try:
        from fs_tool.core.analysis.verification import verify_inventory

        result = verify_inventory(
            inventory_file,
            target_root,
            max_entries=max_entries,
            ignore_dirs=frozenset(ignore_dir),
            ignore_patterns=tuple(ignore_pattern),
            match_mode=match_mode,
        )
    except FsToolError as exc:
        envelope = Envelope(
            schema_version=SCHEMA_VERSION,
            success=False,
            command="verify.inventory",
            result=None,
            errors=(Error(code=exc.code, message=exc.message, path=exc.path),),
            complete=False,
        )
        typer.echo(envelope.to_json())
        return exc.exit_code

    result_dict: dict[str, Any] = {
        "inventory_file": str(inventory_file),
        "target": str(target_root),
        "match_mode": result.match_mode,
        "missing": result.missing,
        "unexpected": result.unexpected,
        "changed": result.changed,
        "size_mismatch": result.size_mismatch,
        "hash_mismatch": result.hash_mismatch,
        "complete": result.complete,
    }
    if result.match_mode == "content":
        result_dict.update(
            {
                "missing_content": result.missing_content,
                "unexpected_content": result.unexpected_content,
                "content_count_mismatch": result.content_count_mismatch,
            }
        )

    error_tuples = tuple(
        Error(code="INACCESSIBLE_ENTRY", message=message, path=str(target_root))
        for message in result.errors
    )

    if result.match_mode == "content":
        success = (
            result.complete
            and not result.missing_content
            and not result.unexpected_content
            and not result.content_count_mismatch
        )
    else:
        success = (
            result.complete and not result.missing and not result.unexpected and not result.changed
        )

    if ctx.obj.output_format == "plain":
        from fs_tool.output.plain import render_verify

        typer.echo(render_verify(result_dict))
        if not result.complete:
            print("fs-tool: error: verification incomplete", file=sys.stderr)
        for message in result.errors:
            print(f"fs-tool: error: {message}", file=sys.stderr)
        if not result.complete:
            return EXIT_INCOMPLETE
        if not success:
            return EXIT_FAILURE
        return EXIT_SUCCESS

    envelope = Envelope(
        schema_version=SCHEMA_VERSION,
        success=success,
        command="verify.inventory",
        result=result_dict,
        errors=error_tuples,
        complete=result.complete,
    )
    typer.echo(envelope.to_json())
    if not result.complete:
        return EXIT_INCOMPLETE
    if not success:
        return EXIT_FAILURE
    return EXIT_SUCCESS


@verify_group.command(name="tree")
def verify_tree_cmd(
    ctx: typer.Context,
    source: Path = typer.Argument(..., help="Source directory to verify against."),
    destination: Path = typer.Argument(..., help="Destination directory to verify."),
    max_entries: int | None = typer.Option(
        None, "--max-entries", help="Maximum number of entries to scan per tree."
    ),
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
    """Verify a destination directory against a source directory.

    Compares both trees and reports missing, unexpected, size
    mismatch, and hash mismatch entries.

    Global options such as ``--plain`` and ``--allow-root`` precede
    the command, e.g. ``fs-tool verify tree ~/Documents ~/Documents_New``.
    """
    _reject_tabular(ctx)
    source_root = validate_path(source, tuple(ctx.obj.allow_root))
    dest_root = validate_path(destination, tuple(ctx.obj.allow_root))

    from fs_tool.core.analysis.verification import verify_tree

    result = verify_tree(
        source_root,
        dest_root,
        max_entries=max_entries,
        ignore_dirs=frozenset(ignore_dir),
        ignore_patterns=tuple(ignore_pattern),
    )

    result_dict: dict[str, Any] = {
        "source": str(source_root),
        "destination": str(dest_root),
        "missing": result.missing,
        "unexpected": result.unexpected,
        "changed": result.changed,
        "size_mismatch": result.size_mismatch,
        "hash_mismatch": result.hash_mismatch,
        "complete": result.complete,
    }

    error_tuples = tuple(
        Error(code="INACCESSIBLE_ENTRY", message=message, path=str(source_root))
        for message in result.errors
    )

    success = (
        result.complete and not result.missing and not result.unexpected and not result.changed
    )

    if ctx.obj.output_format == "plain":
        from fs_tool.output.plain import render_verify

        typer.echo(render_verify(result_dict))
        if not result.complete:
            print("fs-tool: error: verification incomplete", file=sys.stderr)
        for message in result.errors:
            print(f"fs-tool: error: {message}", file=sys.stderr)
        if not result.complete:
            return EXIT_INCOMPLETE
        if not success:
            return EXIT_FAILURE
        return EXIT_SUCCESS

    envelope = Envelope(
        schema_version=SCHEMA_VERSION,
        success=success,
        command="verify.tree",
        result=result_dict,
        errors=error_tuples,
        complete=result.complete,
    )
    typer.echo(envelope.to_json())
    if not result.complete:
        return EXIT_INCOMPLETE
    if not success:
        return EXIT_FAILURE
    return EXIT_SUCCESS


def _emit_write_report(ctx: typer.Context, report: OperationReport) -> int:
    """Emit a structured or concise human-readable write-operation report."""
    command = f"write.{report.operation}"
    result = asdict(report)
    if ctx.obj.output_format == "plain":
        status = "planned" if report.dry_run else "completed"
        typer.echo(f"{report.operation}: {status}")
        typer.echo(f"destination: {report.destination}")
        for path in report.affected:
            typer.echo(f"  {path}")
        return EXIT_SUCCESS

    envelope = Envelope(
        schema_version=SCHEMA_VERSION,
        success=report.complete,
        command=command,
        result=result,
        complete=report.complete,
    )
    typer.echo(envelope.to_json())
    return EXIT_SUCCESS if report.complete else EXIT_INCOMPLETE


def _emit_write_error(ctx: typer.Context, command: str, error: FsToolError) -> int:
    """Emit a stable write-operation error in the selected output format."""
    if ctx.obj.output_format == "plain":
        print(f"fs-tool: error: {error.message}", file=sys.stderr)
    else:
        envelope = Envelope(
            schema_version=SCHEMA_VERSION,
            success=False,
            command=command,
            result=None,
            errors=(
                Error(
                    code=error.code.value,
                    message=error.message,
                    path=error.path,
                    details=error.details,
                ),
            ),
            complete=False,
        )
        typer.echo(envelope.to_json())
    return error.exit_code


@write_group.command(name="mkdir")
def write_mkdir(
    ctx: typer.Context,
    destination: Path = typer.Argument(..., help="Directory to create."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show the planned operation only."),
    yes: bool = typer.Option(False, "--yes", help="Authorize execution."),
    parents: bool = typer.Option(False, "--parents", help="Create missing parent directories."),
) -> int:
    """Create a directory without overwriting existing entries."""
    _reject_tabular(ctx)
    try:
        report = make_directory(
            destination,
            allowed_roots=tuple(Path(root) for root in ctx.obj.allow_root),
            dry_run=dry_run,
            yes=yes,
            parents=parents,
        )
    except FsToolError as exc:
        return _emit_write_error(ctx, "write.mkdir", exc)
    return _emit_write_report(ctx, report)


@write_group.command(name="copy")
def write_copy(
    ctx: typer.Context,
    source: Path = typer.Argument(..., help="File or directory to copy."),
    destination: Path = typer.Argument(..., help="New destination path."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show the planned operation only."),
    yes: bool = typer.Option(False, "--yes", help="Authorize execution."),
    symlinks: str = typer.Option(
        "error",
        "--symlinks",
        help="Symbolic-link policy: error, copy or skip (default: error).",
    ),
) -> int:
    """Copy files or directory trees without following symlinks implicitly."""
    _reject_tabular(ctx)
    try:
        report = copy_path(
            source,
            destination,
            allowed_roots=tuple(Path(root) for root in ctx.obj.allow_root),
            dry_run=dry_run,
            yes=yes,
            symlinks=symlinks,
        )
    except FsToolError as exc:
        return _emit_write_error(ctx, "write.copy", exc)
    return _emit_write_report(ctx, report)


@write_group.command(name="move")
def write_move(
    ctx: typer.Context,
    source: Path = typer.Argument(..., help="File, directory or symlink to move."),
    destination: Path = typer.Argument(..., help="New destination path."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show the planned operation only."),
    yes: bool = typer.Option(False, "--yes", help="Authorize execution."),
    allow_rename: bool = typer.Option(
        False,
        "--allow-rename",
        help="Authorize changing the source filename.",
    ),
) -> int:
    """Move a filesystem entry without overwriting an existing destination."""
    _reject_tabular(ctx)
    try:
        report = move_path(
            source,
            destination,
            allowed_roots=tuple(Path(root) for root in ctx.obj.allow_root),
            dry_run=dry_run,
            yes=yes,
            allow_rename=allow_rename,
        )
    except FsToolError as exc:
        return _emit_write_error(ctx, "write.move", exc)
    return _emit_write_report(ctx, report)


_GLOBAL_FLAGS = frozenset({"-v", "--json", "--plain", "--verbose", "--no-verbose", "--version"})
_GLOBAL_VALUE_OPTIONS = frozenset({"--allow-root", "--config", "--format"})


def _hoist_global_options(args: list[str]) -> list[str]:
    """Move root-level global options before the command.

    Click requires group options to precede the command name, but the
    plan documents forms such as ``fs-tool inspect tree ~/Projects
    --plain``. Moving these options keeps both forms working without
    duplicating the definitions on every subcommand.
    """
    global_args: list[str] = []
    remaining: list[str] = []
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--":
            remaining.extend(args[index:])
            break
        if arg in _GLOBAL_FLAGS:
            global_args.append(arg)
            index += 1
            continue

        matched_option = False
        for option in _GLOBAL_VALUE_OPTIONS:
            if arg == option:
                global_args.append(arg)
                if index + 1 < len(args):
                    global_args.append(args[index + 1])
                    index += 2
                else:
                    index += 1
                matched_option = True
                break
            if arg.startswith(f"{option}="):
                global_args.append(arg)
                index += 1
                matched_option = True
                break
        if matched_option:
            continue

        remaining.append(arg)
        index += 1

    return global_args + remaining


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
    args = _hoist_global_options(list(sys.argv[1:] if argv is None else argv))

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
        exc.show()
        return exc.exit_code if isinstance(exc.exit_code, int) else EXIT_FAILURE
    except Exception as exc:  # CLI boundary: report, do not swallow silently
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return EXIT_FAILURE
    return result if isinstance(result, int) else EXIT_SUCCESS
