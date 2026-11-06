"""Safe same-filesystem moves and renames without destination replacement."""

from __future__ import annotations

import ctypes
import os
import stat
import sys
from pathlib import Path

from fs_tool.core.errors import ErrorCode, FsToolError
from fs_tool.operations.common import (
    OperationReport,
    lstat_or_none,
    raise_operation_os_error,
    require_authorization,
    require_directory,
    validate_operation_path,
)


def _rename_no_replace(source: Path, destination: Path) -> None:
    """Atomically rename without replacing a destination where supported.

    Windows ``os.rename`` is non-replacing. Linux uses ``renameat2`` and
    macOS uses ``renameatx_np`` with their exclusive-rename flags. Other
    POSIX platforms fail closed rather than use a racy check-then-rename.
    """
    if os.name == "nt":
        os.rename(source, destination)
        return

    symbol = "renameat2"
    flags = 1  # RENAME_NOREPLACE
    if sys.platform == "darwin":
        symbol = "renameatx_np"
        flags = 4  # RENAME_EXCL
    elif sys.platform != "linux":
        raise FsToolError(
            f"Atomic no-overwrite moves are not supported on {sys.platform}.",
            code=ErrorCode.OPERATION_FAILED,
            path=str(destination),
        )

    library = ctypes.CDLL(None, use_errno=True)
    rename_function = getattr(library, symbol, None)
    if rename_function is None:
        raise FsToolError(
            f"Atomic no-overwrite moves are unavailable on {sys.platform}.",
            code=ErrorCode.OPERATION_FAILED,
            path=str(destination),
        )

    rename_function.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    rename_function.restype = ctypes.c_int
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    source_parent_fd = -1
    destination_parent_fd = -1
    try:
        source_parent_fd = os.open(source.parent, directory_flags)
        destination_parent_fd = os.open(destination.parent, directory_flags)
        result = rename_function(
            source_parent_fd,
            os.fsencode(source.name),
            destination_parent_fd,
            os.fsencode(destination.name),
            flags,
        )
        if result != 0:
            error_number = ctypes.get_errno()
            raise OSError(error_number, os.strerror(error_number), str(destination))
    finally:
        if source_parent_fd >= 0:
            os.close(source_parent_fd)
        if destination_parent_fd >= 0:
            os.close(destination_parent_fd)


def move_path(
    source: Path,
    destination: Path,
    *,
    allowed_roots: tuple[Path, ...],
    dry_run: bool,
    yes: bool,
    allow_rename: bool = False,
) -> OperationReport:
    """Move a file, directory, or symlink without overwriting."""
    require_authorization(dry_run, yes)
    source_path = validate_operation_path(source, allowed_roots)
    destination_path = validate_operation_path(destination, allowed_roots)

    if source_path.parent == source_path:
        raise FsToolError(
            f"Refusing to move a filesystem root: {source_path}",
            code=ErrorCode.INVALID_ARGUMENT,
            path=str(source_path),
        )
    if source_path == destination_path:
        raise FsToolError(
            "Source and destination are the same path.",
            code=ErrorCode.INVALID_ARGUMENT,
            path=str(source_path),
        )

    source_info = lstat_or_none(source_path)
    if source_info is None:
        raise FsToolError(
            f"Source does not exist: {source_path}",
            code=ErrorCode.INVALID_ARGUMENT,
            path=str(source_path),
        )
    if not (
        stat.S_ISREG(source_info.st_mode)
        or stat.S_ISDIR(source_info.st_mode)
        or stat.S_ISLNK(source_info.st_mode)
    ):
        raise FsToolError(
            f"Cannot move unsupported filesystem entry: {source_path}",
            code=ErrorCode.OPERATION_FAILED,
            path=str(source_path),
        )

    if source_path.name != destination_path.name and not allow_rename:
        raise FsToolError(
            "Changing the filename requires --allow-rename.",
            code=ErrorCode.INVALID_ARGUMENT,
            path=str(destination_path),
        )

    if stat.S_ISDIR(source_info.st_mode) and not stat.S_ISLNK(source_info.st_mode):
        try:
            destination_path.relative_to(source_path)
        except ValueError:
            pass
        else:
            raise FsToolError(
                "Cannot move a directory into itself or one of its descendants.",
                code=ErrorCode.INVALID_ARGUMENT,
                path=str(destination_path),
            )

    destination_parent_info = require_directory(destination_path.parent)
    if lstat_or_none(destination_path) is not None:
        raise FsToolError(
            f"Destination already exists: {destination_path}",
            code=ErrorCode.TARGET_EXISTS,
            path=str(destination_path),
        )
    if source_info.st_dev != destination_parent_info.st_dev:
        raise FsToolError(
            "Cross-device moves are not supported; source and destination must be on the same "
            "filesystem.",
            code=ErrorCode.OPERATION_FAILED,
            path=str(destination_path),
        )

    if dry_run:
        return OperationReport(
            operation="move",
            source=str(source_path),
            destination=str(destination_path),
            dry_run=True,
            executed=False,
            affected=(str(destination_path),),
        )

    try:
        _rename_no_replace(source_path, destination_path)
    except FsToolError:
        raise
    except OSError as exc:
        raise_operation_os_error("move to", destination_path, exc)

    try:
        moved_info = lstat_or_none(destination_path)
        source_after = lstat_or_none(source_path)
    except FsToolError as exc:
        exc.details["moved"] = True
        raise
    verified = (
        moved_info is not None
        and source_after is None
        and moved_info.st_dev == source_info.st_dev
        and moved_info.st_ino == source_info.st_ino
    )
    if not verified:
        raise FsToolError(
            f"Move completed but could not be fully verified: {destination_path}",
            code=ErrorCode.INCOMPLETE_VERIFICATION,
            path=str(destination_path),
            details={"moved": True},
        )

    return OperationReport(
        operation="move",
        source=str(source_path),
        destination=str(destination_path),
        dry_run=False,
        executed=True,
        affected=(str(destination_path),),
        verified=True,
    )
