"""Shared result and validation helpers for filesystem operations."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from pathlib import Path

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


def raise_operation_os_error(action: str, path: Path, error: OSError) -> None:
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
