"""Safe directory creation."""

from __future__ import annotations

import os
import stat
from pathlib import Path

from fs_tool.core.errors import ErrorCode, FsToolError
from fs_tool.operations.common import (
    OperationReport,
    lstat_or_none,
    raise_operation_os_error,
    require_authorization,
    validate_operation_path,
)


def make_directory(
    destination: Path,
    *,
    allowed_roots: tuple[Path, ...],
    dry_run: bool,
    yes: bool,
    parents: bool = False,
) -> OperationReport:
    """Create one directory, optionally creating missing parent directories."""
    require_authorization(dry_run, yes)
    target = validate_operation_path(destination, allowed_roots)
    existing = lstat_or_none(target)
    if existing is not None:
        if stat.S_ISDIR(existing.st_mode) and not stat.S_ISLNK(existing.st_mode):
            return OperationReport(
                operation="mkdir",
                source=None,
                destination=str(target),
                dry_run=dry_run,
                executed=not dry_run,
                affected=(),
                created=False,
            )
        raise FsToolError(
            f"Cannot create directory because the destination is not a directory: {target}",
            code=ErrorCode.TYPE_CONFLICT,
            path=str(target),
        )

    missing: list[Path] = []
    current = target
    while lstat_or_none(current) is None:
        missing.append(current)
        if not parents:
            break
        parent = current.parent
        if parent == current:
            break
        current = parent

    nearest_existing = missing[-1].parent if not parents else current
    parent_info = lstat_or_none(nearest_existing)
    if parent_info is None:
        raise FsToolError(
            f"Parent directory does not exist: {nearest_existing}; use --parents to create it.",
            code=ErrorCode.INVALID_ARGUMENT,
            path=str(nearest_existing),
        )
    if stat.S_ISLNK(parent_info.st_mode) or not stat.S_ISDIR(parent_info.st_mode):
        raise FsToolError(
            f"Parent is not a directory: {nearest_existing}",
            code=ErrorCode.TYPE_CONFLICT,
            path=str(nearest_existing),
        )

    planned = tuple(str(path) for path in reversed(missing))
    if dry_run:
        return OperationReport(
            operation="mkdir",
            source=None,
            destination=str(target),
            dry_run=True,
            executed=False,
            affected=planned,
            created=None,
        )

    created: list[str] = []
    for path in reversed(missing):
        try:
            os.mkdir(path)
            created.append(str(path))
        except FileExistsError:
            info = lstat_or_none(path)
            if info is not None and stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode):
                continue
            raise FsToolError(
                f"Destination appeared during directory creation: {path}",
                code=ErrorCode.TYPE_CONFLICT,
                path=str(path),
                details={"created": created},
            ) from None
        except OSError as exc:
            try:
                raise_operation_os_error("create directory", path, exc)
            except FsToolError as operation_error:
                operation_error.details["created"] = created
                raise

    return OperationReport(
        operation="mkdir",
        source=None,
        destination=str(target),
        dry_run=False,
        executed=True,
        affected=tuple(created),
        created=str(target) in created,
    )
