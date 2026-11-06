"""Safe, no-overwrite copying of regular files and directory trees."""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import tempfile
from dataclasses import dataclass
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


@dataclass(frozen=True)
class _CopyItem:
    source: Path
    destination: Path
    relative_path: str
    kind: str


def _copy_error(
    message: str,
    path: Path,
    code: ErrorCode = ErrorCode.OPERATION_FAILED,
) -> FsToolError:
    return FsToolError(message, code=code, path=str(path))


def _collect_tree(
    source: Path,
    destination: Path,
    *,
    relative_path: str,
    symlinks: str,
    allowed_roots: tuple[Path, ...],
    items: list[_CopyItem],
    skipped: list[str],
) -> None:
    """Preflight a source tree without following symbolic links."""
    info = lstat_or_none(source)
    if info is None:
        raise _copy_error(f"Source disappeared during preflight: {source}", source)

    if stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode):
        items.append(_CopyItem(source, destination, relative_path, "directory"))
        try:
            with os.scandir(source) as scan:
                children = sorted(scan, key=lambda entry: entry.name)
        except OSError as exc:
            raise_operation_os_error("scan directory", source, exc)
        for child in children:
            child_source = source / child.name
            child_destination = destination / child.name
            child_info = lstat_or_none(child_source)
            if child_info is None:
                raise _copy_error(
                    f"Source entry disappeared during preflight: {child_source}",
                    child_source,
                )
            child_relative = str(Path(relative_path) / child.name) if relative_path else child.name
            if stat.S_ISLNK(child_info.st_mode):
                if symlinks == "error":
                    raise _copy_error(
                        f"Source contains a symbolic link; choose --symlinks copy or skip: "
                        f"{child_source}",
                        child_source,
                        ErrorCode.INVALID_ARGUMENT,
                    )
                if symlinks == "skip":
                    skipped.append(child_relative)
                    continue
                validate_operation_path(child_source, allowed_roots)
                items.append(_CopyItem(child_source, child_destination, child_relative, "symlink"))
            elif stat.S_ISDIR(child_info.st_mode):
                _collect_tree(
                    child_source,
                    child_destination,
                    relative_path=child_relative,
                    symlinks=symlinks,
                    allowed_roots=allowed_roots,
                    items=items,
                    skipped=skipped,
                )
            elif stat.S_ISREG(child_info.st_mode):
                items.append(_CopyItem(child_source, child_destination, child_relative, "file"))
            else:
                raise _copy_error(
                    f"Cannot copy unsupported filesystem entry: {child_source}",
                    child_source,
                )
        return

    if stat.S_ISREG(info.st_mode):
        items.append(_CopyItem(source, destination, relative_path or source.name, "file"))
        return
    if stat.S_ISLNK(info.st_mode):
        if symlinks == "error":
            raise _copy_error(
                f"Source is a symbolic link; choose --symlinks copy or skip: {source}",
                source,
                ErrorCode.INVALID_ARGUMENT,
            )
        if symlinks == "skip":
            skipped.append(source.name)
            return
        validate_operation_path(source, allowed_roots)
        items.append(_CopyItem(source, destination, relative_path or source.name, "symlink"))
        return
    raise _copy_error(f"Cannot copy unsupported filesystem entry: {source}", source)


def _preflight_destinations(destination: Path, items: list[_CopyItem]) -> None:
    """Ensure the destination parent exists and every planned path is unused."""
    require_directory(destination.parent)
    for item in items:
        if lstat_or_none(item.destination) is not None:
            raise FsToolError(
                f"Destination already exists: {item.destination}",
                code=ErrorCode.TARGET_EXISTS,
                path=str(item.destination),
            )


def _copy_regular_file(source: Path, destination: Path) -> str:
    """Copy one regular file atomically and return its verified SHA-256."""
    source_info = lstat_or_none(source)
    if source_info is None or not stat.S_ISREG(source_info.st_mode):
        raise _copy_error(f"Source is no longer a regular file: {source}", source)

    source_fd = -1
    temporary_fd = -1
    temporary_path: Path | None = None
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        source_fd = os.open(source, flags)
        opened_info = os.fstat(source_fd)
        if (
            not stat.S_ISREG(opened_info.st_mode)
            or opened_info.st_dev != source_info.st_dev
            or opened_info.st_ino != source_info.st_ino
        ):
            raise _copy_error(f"Source changed during copy: {source}", source)

        temporary_fd, temporary_name = tempfile.mkstemp(
            prefix=".fs-tool-copy-",
            dir=destination.parent,
        )
        temporary_path = Path(temporary_name)
        source_hash = hashlib.sha256()

        with os.fdopen(source_fd, "rb") as source_stream:
            source_fd = -1
            with os.fdopen(temporary_fd, "wb") as destination_stream:
                temporary_fd = -1
                while chunk := source_stream.read(1024 * 1024):
                    source_hash.update(chunk)
                    destination_stream.write(chunk)
                destination_stream.flush()
                os.fsync(destination_stream.fileno())
                if hasattr(os, "fchmod"):
                    os.fchmod(destination_stream.fileno(), stat.S_IMODE(source_info.st_mode))

        os.utime(
            temporary_path,
            ns=(source_info.st_atime_ns, source_info.st_mtime_ns),
            follow_symlinks=False,
        )
        expected_hash = source_hash.hexdigest()
        destination_hash = hashlib.sha256()
        with temporary_path.open("rb") as copied_file:
            while chunk := copied_file.read(1024 * 1024):
                destination_hash.update(chunk)
        if destination_hash.hexdigest() != expected_hash:
            raise _copy_error(
                f"Copied file failed SHA-256 verification: {destination}",
                destination,
            )

        os.link(temporary_path, destination)
        temporary_path.unlink()
        temporary_path = None
        return expected_hash
    except FsToolError:
        raise
    except OSError as exc:
        raise_operation_os_error("copy file to", destination, exc)
    finally:
        if source_fd >= 0:
            os.close(source_fd)
        if temporary_fd >= 0:
            os.close(temporary_fd)
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass


def copy_path(
    source: Path,
    destination: Path,
    *,
    allowed_roots: tuple[Path, ...],
    dry_run: bool,
    yes: bool,
    symlinks: str = "error",
) -> OperationReport:
    """Copy a regular file or directory tree without overwriting."""
    require_authorization(dry_run, yes)
    if symlinks not in {"error", "copy", "skip"}:
        raise FsToolError(
            "Invalid --symlinks value; use error, copy or skip.",
            code=ErrorCode.INVALID_ARGUMENT,
        )

    source_path = validate_operation_path(source, allowed_roots)
    destination_path = validate_operation_path(destination, allowed_roots)
    source_info = lstat_or_none(source_path)
    if source_info is None:
        raise FsToolError(
            f"Source does not exist: {source_path}",
            code=ErrorCode.INVALID_ARGUMENT,
            path=str(source_path),
        )

    if stat.S_ISDIR(source_info.st_mode) and not stat.S_ISLNK(source_info.st_mode):
        try:
            destination_path.relative_to(source_path)
        except ValueError:
            pass
        else:
            raise FsToolError(
                "Cannot copy a directory into itself or one of its descendants.",
                code=ErrorCode.INVALID_ARGUMENT,
                path=str(destination_path),
            )

    items: list[_CopyItem] = []
    skipped: list[str] = []
    _collect_tree(
        source_path,
        destination_path,
        relative_path="",
        symlinks=symlinks,
        allowed_roots=allowed_roots,
        items=items,
        skipped=skipped,
    )
    if items:
        _preflight_destinations(destination_path, items)

    planned = tuple(str(item.destination) for item in items)
    if dry_run:
        return OperationReport(
            operation="copy",
            source=str(source_path),
            destination=str(destination_path),
            dry_run=True,
            executed=False,
            affected=planned,
            skipped=tuple(skipped),
        )

    created: list[str] = []
    file_hashes: list[str] = []
    try:
        for item in items:
            if item.kind == "directory":
                os.mkdir(item.destination)
                created.append(str(item.destination))
            elif item.kind == "file":
                file_hashes.append(_copy_regular_file(item.source, item.destination))
                created.append(str(item.destination))
            else:
                link_target = os.readlink(item.source)
                target_path = Path(link_target)
                if not target_path.is_absolute():
                    target_path = item.source.parent / target_path
                os.symlink(
                    link_target,
                    item.destination,
                    target_is_directory=target_path.is_dir(),
                )
                created.append(str(item.destination))

        for item in reversed(items):
            if item.kind == "directory":
                shutil.copystat(item.source, item.destination, follow_symlinks=False)
    except FsToolError as exc:
        exc.details.update({"affected": created, "skipped": skipped, "complete": False})
        raise
    except OSError as exc:
        try:
            raise_operation_os_error("copy entry to", item.destination, exc)
        except FsToolError as operation_error:
            operation_error.details.update(
                {"affected": created, "skipped": skipped, "complete": False}
            )
            raise

    return OperationReport(
        operation="copy",
        source=str(source_path),
        destination=str(destination_path),
        dry_run=False,
        executed=True,
        affected=tuple(created),
        skipped=tuple(skipped),
        sha256=file_hashes[0] if len(file_hashes) == 1 else None,
        verified=True,
    )
