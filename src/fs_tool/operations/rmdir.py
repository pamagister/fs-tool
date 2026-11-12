"""Safe removal of empty directories.

``rmdir`` never deletes files and never recurses into a non-empty directory.
With ``--parents`` it removes an empty parent chain after the requested
directory, stopping at the filesystem root or an allowed root.
"""

from __future__ import annotations

import errno
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


def _is_empty_or_only_planned(path: Path, planned: set[Path]) -> bool:
    """Return True when ``path`` contains no entries outside ``planned``."""
    info = lstat_or_none(path)
    if info is None or stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        return False
    try:
        with os.scandir(path) as scan:
            return all((path / entry.name) in planned for entry in scan)
    except OSError as exc:
        raise_operation_os_error("inspect directory", path, exc)


def _planned_removals(target: Path, allowed_roots: tuple[Path, ...]) -> list[Path]:
    """Return the directory and removable empty parents in bottom-up order."""
    if not _is_empty_or_only_planned(target, set()):
        raise FsToolError(
            f"Cannot remove non-empty directory: {target}",
            code=ErrorCode.OPERATION_FAILED,
            path=str(target),
        )

    planned = [target]
    planned_set = {target}
    allowed = {root.resolve(strict=False) for root in allowed_roots}
    current = target.parent
    while current != current.parent and current.resolve(strict=False) not in allowed:
        if not _is_empty_or_only_planned(current, planned_set):
            break
        planned.append(current)
        planned_set.add(current)
        current = current.parent
    return planned


def remove_directory(
    destination: Path,
    *,
    allowed_roots: tuple[Path, ...],
    dry_run: bool,
    yes: bool,
    parents: bool = False,
) -> OperationReport:
    """Remove one empty directory, optionally with empty parent directories."""
    require_authorization(dry_run, yes)
    target = validate_operation_path(destination, allowed_roots)

    info = lstat_or_none(target)
    if info is None:
        raise FsToolError(
            f"Directory does not exist: {target}",
            code=ErrorCode.INVALID_ARGUMENT,
            path=str(target),
        )
    if stat.S_ISLNK(info.st_mode):
        raise FsToolError(
            f"Refusing to remove a symbolic link: {target}",
            code=ErrorCode.TYPE_CONFLICT,
            path=str(target),
        )
    if not stat.S_ISDIR(info.st_mode):
        raise FsToolError(
            f"Refusing to remove a non-directory entry: {target}",
            code=ErrorCode.TYPE_CONFLICT,
            path=str(target),
        )

    planned = _planned_removals(target, allowed_roots)
    if not parents:
        planned = planned[:1]
    planned_paths = tuple(str(path) for path in planned)

    if dry_run:
        return OperationReport(
            operation="rmdir",
            source=None,
            destination=str(target),
            dry_run=True,
            executed=False,
            affected=planned_paths,
            removed=(),
        )

    removed: list[str] = []
    for path in planned:
        try:
            os.rmdir(path)
        except OSError as exc:
            if path != target and exc.errno in (errno.ENOTEMPTY, errno.EEXIST):
                break
            try:
                raise_operation_os_error("remove directory", path, exc)
            except FsToolError as operation_error:
                operation_error.details["removed"] = removed
                raise
        removed.append(str(path))

    return OperationReport(
        operation="rmdir",
        source=None,
        destination=str(target),
        dry_run=False,
        executed=True,
        affected=tuple(removed),
        removed=tuple(removed),
        created=False,
    )
