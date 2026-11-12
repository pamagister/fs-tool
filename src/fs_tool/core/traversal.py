"""Recursive directory traversal (plan.md Phase 1).

Traversal is read-only: symlinks are recorded but never followed by
default, special files are reported as unsupported and never opened,
inaccessible entries are collected as errors instead of aborting the
scan, and results are deterministically sorted by entry name.
"""

from __future__ import annotations

import fnmatch
import mimetypes
import os
import stat
import sys
from collections.abc import Callable
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

SortBy = Literal["name", "size", "modified", "extension"]


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
    truncated: bool = False


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


def _entry_sort_key(entry: FilesystemEntry, sort_by: SortBy) -> tuple[object, ...]:
    """Return a deterministic sort key with a name tie-breaker."""
    name = entry.name
    if sort_by == "size":
        return (entry.size if entry.size is not None else -1, name)
    if sort_by == "modified":
        return (entry.modified or "", name)
    if sort_by == "extension":
        return (entry.extension or "", name)
    return (name,)


def build_entry(path: Path, root: Path, follow_symlinks: bool = False) -> FilesystemEntry:
    """Build a :class:`FilesystemEntry` for ``path`` without following symlinks.

    ``rel_path`` is computed relative to ``root``.
    """
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
        mime_type=mimetypes.guess_type(path)[0],
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
    use_default_ignores: bool = True,
    progress: Callable[[int], None] | None = None,
) -> TraversalResult:
    """Recursively traverse ``root`` and return its entries.

    Symlinks are recorded but never followed unless ``follow_symlinks``
    is set (cycles are still avoided). Inaccessible entries are
    reported as errors and do not abort the scan. Entries are sorted
    within each directory by ``sort_by`` with a deterministic name
    tie-breaker. ``use_default_ignores`` controls the built-in ignore
    list; explicitly supplied ignore names and patterns always apply.
    """
    if sort_by not in ("name", "size", "modified", "extension"):
        raise FsToolError(
            f"Unsupported sort_by value {sort_by!r}; use name, size, modified or extension",
            code=ErrorCode.INVALID_ARGUMENT,
        )
    if max_depth is not None and max_depth < 0:
        raise FsToolError(
            "--max-depth must be a non-negative integer.",
            code=ErrorCode.INVALID_ARGUMENT,
        )
    if max_entries is not None and max_entries < 0:
        raise FsToolError(
            "--max-entries must be a non-negative integer.",
            code=ErrorCode.INVALID_ARGUMENT,
        )

    root_path = normalize_path(root)
    ignored = set(DEFAULT_IGNORE_DIRS) if use_default_ignores else set()
    if ignore_dirs is not None:
        ignored |= set(ignore_dirs)

    result = TraversalResult()
    visited_dirs: set[tuple[int, int]] = set()

    def record_error(path: Path, message: str) -> None:
        result.errors.append(TraversalError(path=str(path), message=message))
        result.complete = False

    def _include_candidate(is_link: bool, is_dir: bool) -> bool:
        if is_link and not follow_symlinks:
            return not dirs_only
        return not dirs_only or is_dir

    def _prepare(path: Path, is_link: bool, is_dir: bool) -> FilesystemEntry | None:
        if not _include_candidate(is_link, is_dir):
            return None
        if is_link and follow_symlinks:
            try:
                real = path.stat(follow_symlinks=True)
            except OSError as exc:
                record_error(path, f"Cannot follow symbolic link: {exc.strerror or exc}")
                return None
            key = (real.st_dev, real.st_ino)
            if key in visited_dirs:
                result.skipped += 1
                return None
            visited_dirs.add(key)
        try:
            return build_entry(path, root_path, follow_symlinks=follow_symlinks)
        except FsToolError as exc:
            record_error(path, exc.message)
            return None

    def report_progress() -> None:
        if progress is not None and len(result.entries) % 1000 == 0:
            progress(len(result.entries))

    def _scan_children(directory: Path) -> list[tuple[Path, bool, bool]] | None:
        try:
            pending = sorted(os.scandir(directory), key=lambda entry: entry.name)
        except OSError as exc:
            record_error(directory, f"Cannot read directory: {exc.strerror or exc}")
            return None
        children: list[tuple[Path, bool, bool]] = []
        for entry in pending:
            name = entry.name
            if name in ignored or any(fnmatch.fnmatch(name, p) for p in ignore_patterns):
                result.skipped += 1
                continue
            path = Path(entry.path)
            try:
                is_link = entry.is_symlink()
                is_dir = entry.is_dir(follow_symlinks=follow_symlinks)
            except OSError as exc:
                record_error(path, f"Cannot inspect entry: {exc.strerror or exc}")
                continue
            children.append((path, is_link, is_dir))
        return children

    def walk(directory: Path, depth: int) -> None:
        """Walk ``directory``; ``depth`` is the level of its entries
        relative to ``root`` (root's direct entries have depth 1)."""
        if max_depth is not None and max_depth < 1:
            return
        if max_entries is not None and len(result.entries) >= max_entries:
            result.complete = False
            result.truncated = True
            return
        children = _scan_children(directory)
        if children is None:
            return

        if sort_by == "name":
            # ``children`` preserves name order. Stream entries so a low
            # ``--max-entries`` does not require building every sibling.
            for path, is_link, is_dir in children:
                if max_entries is not None and len(result.entries) >= max_entries:
                    result.complete = False
                    result.truncated = True
                    return
                built = _prepare(path, is_link, is_dir)
                if built is None:
                    continue
                result.entries.append(built)
                report_progress()
                if is_dir and (max_depth is None or depth < max_depth):
                    walk(path, depth + 1)
            return

        sortable: list[tuple[FilesystemEntry, Path, bool, bool]] = []
        for path, is_link, is_dir in children:
            built = _prepare(path, is_link, is_dir)
            if built is None:
                continue
            sortable.append((built, path, is_link, is_dir))
        sortable.sort(key=lambda item: _entry_sort_key(item[0], sort_by))
        for built, path, _is_link, is_dir in sortable:
            if max_entries is not None and len(result.entries) >= max_entries:
                result.complete = False
                result.truncated = True
                return
            result.entries.append(built)
            report_progress()
            if is_dir and (max_depth is None or depth < max_depth):
                walk(path, depth + 1)

    walk(root_path, 1)
    return result
