"""Recursive directory traversal (plan.md Phase 1).

Traversal is read-only: symlinks are recorded but never followed by
default, special files are reported as unsupported and never opened,
inaccessible entries are collected as errors instead of aborting the
scan, and results are deterministically sorted by entry name.
"""

from __future__ import annotations

import fnmatch
import os
import stat
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from fs_tool.core.errors import ErrorCode, FsToolError
from fs_tool.core.filesystem import normalize_path
from fs_tool.core.models import EntryType, FilesystemEntry

DEFAULT_IGNORE_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        "node_modules",
        "build",
        "dist",
        ".idea",
        ".vscode",
    }
)

SortBy = Literal["name"]


@dataclass(frozen=True)
class TraversalError:
    """An entry that could not be traversed or read."""

    path: str
    message: str


@dataclass
class TraversalResult:
    """Result of a directory traversal."""

    entries: list[FilesystemEntry] = field(default_factory=list)
    errors: list[TraversalError] = field(default_factory=list)
    complete: bool = True
    skipped: int = 0


def _iso_timestamp(seconds: float) -> str:
    return datetime.fromtimestamp(seconds, tz=UTC).isoformat()


def _entry_type(stat_result: os.stat_result | None, is_symlink: bool) -> EntryType:
    if is_symlink:
        return EntryType.SYMLINK
    if stat_result is not None and stat.S_ISDIR(stat_result.st_mode):
        return EntryType.DIRECTORY
    if stat_result is not None and stat.S_ISREG(stat_result.st_mode):
        return EntryType.FILE
    return EntryType.OTHER


def _build_entry(path: Path, root: Path, follow_symlinks: bool = False) -> FilesystemEntry:
    """Build a :class:`FilesystemEntry` without following symlinks."""
    try:
        lst = path.lstat()
    except OSError as exc:
        raise FsToolError(
            f"Cannot stat {path}: {exc.strerror or exc}",
            code=ErrorCode.INVALID_ARGUMENT,
            path=str(path),
        ) from exc

    is_symlink = stat.S_ISLNK(lst.st_mode)
    target: str | None = None
    if is_symlink and not follow_symlinks:
        try:
            target = os.readlink(path)
        except OSError:
            target = None

    stat_result: os.stat_result | None = None
    if not is_symlink or follow_symlinks:
        try:
            stat_result = path.stat()
        except OSError:
            stat_result = None

    owner: str | None = None
    if sys.platform != "win32":
        from pwd import getpwuid  # POSIX only; Windows has no pwd module

        try:
            owner = getpwuid(lst.st_uid).pw_name
        except KeyError:  # pragma: no cover - POSIX without uid entry
            owner = None

    created: str | None = None
    birthtime = getattr(lst, "st_birthtime", None)
    if birthtime is not None:
        created = _iso_timestamp(birthtime)

    return FilesystemEntry(
        path=str(path),
        name=path.name,
        rel_path=str(path.relative_to(root)),
        type=_entry_type(stat_result, is_symlink),
        extension=path.suffix.lower() if path.suffix else None,
        size=lst.st_size,
        modified=_iso_timestamp(lst.st_mtime),
        accessed=_iso_timestamp(lst.st_atime),
        changed=_iso_timestamp(lst.st_ctime),
        created=created,
        mode=stat.filemode(lst.st_mode),
        owner=owner,
        is_symlink=is_symlink,
        target=target,
        dev_ino=f"{lst.st_dev}:{lst.st_ino}",
    )


def traverse(
    root: str | Path,
    *,
    max_depth: int | None = None,
    max_entries: int | None = None,
    dirs_only: bool = False,
    ignore_dirs: frozenset[str] | None = None,
    ignore_patterns: tuple[str, ...] = (),
    follow_symlinks: bool = False,
    sort_by: SortBy = "name",
) -> TraversalResult:
    """Recursively traverse ``root`` and return its entries.

    Symlinks are recorded but never followed unless ``follow_symlinks``
    is set (cycles are still avoided). Inaccessible entries are
    reported as errors and do not abort the scan. Entries are sorted
    alphabetically by name within each directory.
    """
    if sort_by != "name":
        raise FsToolError(
            f"Unsupported sort_by value {sort_by!r}; only 'name' is supported",
            code=ErrorCode.INVALID_ARGUMENT,
        )

    root_path = normalize_path(root)
    ignored = set(DEFAULT_IGNORE_DIRS)
    if ignore_dirs is not None:
        ignored |= set(ignore_dirs)

    result = TraversalResult()
    visited_dirs: set[tuple[int, int]] = set()

    def walk(directory: Path, depth: int) -> None:
        """Walk ``directory``; ``depth`` is the level of its entries
        relative to ``root`` (root's direct entries have depth 1)."""
        if max_entries is not None and len(result.entries) >= max_entries:
            result.complete = False
            return
        try:
            pending = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError as exc:
            result.errors.append(
                TraversalError(
                    path=str(directory),
                    message=f"Cannot read directory: {exc.strerror or exc}",
                )
            )
            return
        for entry in pending:
            if max_entries is not None and len(result.entries) >= max_entries:
                result.complete = False
                return
            name = entry.name
            if name in ignored or any(fnmatch.fnmatch(name, p) for p in ignore_patterns):
                result.skipped += 1
                continue
            path = Path(entry.path)
            try:
                is_link = entry.is_symlink()
                is_dir = entry.is_dir(follow_symlinks=follow_symlinks)
            except OSError:
                is_link = False
                is_dir = False
            if is_link and not follow_symlinks:
                if not dirs_only:
                    _append_entry(path)
                continue
            if is_link and follow_symlinks:
                try:
                    real = entry.stat(follow_symlinks=True)
                except OSError:
                    real = None
                if real is not None:
                    key = (real.st_dev, real.st_ino)
                    if key in visited_dirs:
                        result.skipped += 1
                        continue
                    visited_dirs.add(key)
            if not dirs_only or is_dir:
                _append_entry(path)
            if is_dir and (max_depth is None or depth < max_depth):
                walk(path, depth + 1)

    def _append_entry(path: Path) -> None:
        try:
            result.entries.append(_build_entry(path, root_path, follow_symlinks=follow_symlinks))
        except FsToolError as exc:
            result.errors.append(TraversalError(path=str(path), message=exc.message))

    walk(root_path, 1)
    return result
