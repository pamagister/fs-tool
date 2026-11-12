"""Shared result and validation helpers for filesystem operations."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

from fs_tool.core.errors import ErrorCode, FsToolError
from fs_tool.safety.validation import validate_path


@dataclass(frozen=True)
class OperationReport:
    """Structured result shared by write commands."""

    operation: str
    source: str | None
    destination: str
    dry_run: bool
    executed: bool
    affected: tuple[str, ...]
    skipped: tuple[str, ...] = ()
    created: bool | None = None
    sha256: str | None = None
    verified: bool | None = None
    complete: bool = True
    created_directories: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()


def require_authorization(dry_run: bool, yes: bool) -> None:
    """Require exactly one of dry-run or execution authorization."""
    if dry_run == yes:
        raise FsToolError(
            "Specify exactly one of --dry-run or --yes.",
            code=ErrorCode.INVALID_ARGUMENT,
        )


def validate_operation_path(path: Path, allowed_roots: tuple[Path, ...]) -> Path:
    """Normalize and enforce allowed-root restrictions for an operation path."""
    return validate_path(path, allowed_roots)


def destination_for_existing_directory(source: Path, destination: Path) -> Path:
    """Append the source basename when the destination is an existing directory.

    This is the natural agent operation: ``write move file existing-dir`` and
    ``write copy tree existing-dir`` mean ``existing-dir/file`` and
    ``existing-dir/tree``. A symbolic link to a directory is treated as an
    existing entry, never as an implicit directory destination.
    """
    info = lstat_or_none(destination)
    if info is not None and stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode):
        return destination / source.name
    return destination


def ensure_parent_directory(
    destination: Path,
    *,
    allowed_roots: tuple[Path, ...],
    dry_run: bool,
    yes: bool,
) -> tuple[str, ...]:
    """Create or plan the missing parent directories of ``destination``.

    Returns the affected parent paths. The operation is delegated to
    :func:`fs_tool.operations.mkdir.make_directory` so no-overwrite and
    allowed-root checks stay identical.
    """
    from fs_tool.operations.mkdir import make_directory

    report = make_directory(
        destination.parent,
        allowed_roots=allowed_roots,
        dry_run=dry_run,
        yes=yes,
        parents=True,
    )
    return report.affected


def lstat_or_none(path: Path) -> os.stat_result | None:
    """Return lstat information, preserving broken symlinks as existing entries."""
    try:
        return path.lstat()
    except FileNotFoundError:
        return None
    except PermissionError as exc:
        raise FsToolError(
            f"Access denied while inspecting {path}: {exc.strerror or exc}",
            code=ErrorCode.ACCESS_DENIED,
            path=str(path),
        ) from exc
    except OSError as exc:
        raise FsToolError(
            f"Cannot inspect {path}: {exc.strerror or exc}",
            code=ErrorCode.OPERATION_FAILED,
            path=str(path),
        ) from exc


def require_directory(path: Path) -> os.stat_result:
    """Require an existing, non-symlink directory."""
    info = lstat_or_none(path)
    if info is None:
        raise FsToolError(
            f"Directory does not exist: {path}",
            code=ErrorCode.INVALID_ARGUMENT,
            path=str(path),
        )
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise FsToolError(
            f"Expected a directory, found a non-directory entry: {path}",
            code=ErrorCode.TYPE_CONFLICT,
            path=str(path),
        )
    return info


def raise_operation_os_error(action: str, path: Path, error: OSError) -> NoReturn:
    """Translate a filesystem error into a stable fs-tool error."""
    if isinstance(error, PermissionError):
        code = ErrorCode.ACCESS_DENIED
    elif isinstance(error, FileExistsError):
        code = ErrorCode.TARGET_EXISTS
    else:
        code = ErrorCode.OPERATION_FAILED
    raise FsToolError(
        f"Cannot {action} {path}: {error.strerror or error}",
        code=code,
        path=str(path),
    ) from error
