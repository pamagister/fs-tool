"""Filesystem entry search and filtering (plan.md Phase 3, section 5.2).

Provides filtering functions over :class:`FilesystemEntry` instances
produced by :func:`fs_tool.core.traversal.traverse`. All filters are
pure and read-only: they never open or modify files.
"""

from __future__ import annotations

import fnmatch
from datetime import UTC, datetime
from pathlib import Path

from fs_tool.core.models import EntryType, FilesystemEntry
from fs_tool.core.traversal import SortBy


def matches_name(entry: FilesystemEntry, pattern: str) -> bool:
    """Return True if ``entry.name`` matches the glob ``pattern``.

    Matching is case-insensitive on case-insensitive filesystems
    (Windows) and case-sensitive elsewhere, consistent with
    :func:`fnmatch.fnmatch`.
    """
    return fnmatch.fnmatch(entry.name, pattern)


def matches_extension(entry: FilesystemEntry, extension: str) -> bool:
    """Return True if ``entry.extension`` equals ``extension``.

    The extension is compared case-insensitively. Callers should pass
    the extension with or without a leading dot; both forms are
    accepted.
    """
    entry_ext = entry.extension or ""
    ext = extension.lower()
    if not ext.startswith("."):
        ext = f".{ext}"
    return entry_ext == ext


def matches_type(entry: FilesystemEntry, entry_type: EntryType) -> bool:
    """Return True if ``entry.type`` equals ``entry_type``."""
    return entry.type is entry_type


def matches_min_size(entry: FilesystemEntry, min_size: int) -> bool:
    """Return True if ``entry.size`` is at least ``min_size``.

    Entries with no size information (e.g. directories) do not match.
    """
    if entry.size is None:
        return False
    return entry.size >= min_size


def matches_max_size(entry: FilesystemEntry, max_size: int) -> bool:
    """Return True if ``entry.size`` is at most ``max_size``.

    Entries with no size information (e.g. directories) do not match.
    """
    if entry.size is None:
        return False
    return entry.size <= max_size


def matches_modified_after(entry: FilesystemEntry, timestamp: str) -> bool:
    """Return True if ``entry.modified`` is at or after ``timestamp``.

    ``timestamp`` must be an ISO-8601 string parseable by
    :meth:`datetime.fromisoformat`. Entries with no modification time
    do not match.
    """
    if entry.modified is None:
        return False
    try:
        entry_time = datetime.fromisoformat(entry.modified)
        filter_time = datetime.fromisoformat(timestamp)
    except ValueError:
        return False
    if entry_time.tzinfo is None:
        entry_time = entry_time.replace(tzinfo=UTC)
    if filter_time.tzinfo is None:
        filter_time = filter_time.replace(tzinfo=UTC)
    return entry_time >= filter_time


def matches_modified_before(entry: FilesystemEntry, timestamp: str) -> bool:
    """Return True if ``entry.modified`` is at or before ``timestamp``.

    See :func:`matches_modified_after` for format details.
    """
    if entry.modified is None:
        return False
    try:
        entry_time = datetime.fromisoformat(entry.modified)
        filter_time = datetime.fromisoformat(timestamp)
    except ValueError:
        return False
    if entry_time.tzinfo is None:
        entry_time = entry_time.replace(tzinfo=UTC)
    if filter_time.tzinfo is None:
        filter_time = filter_time.replace(tzinfo=UTC)
    return entry_time <= filter_time


def filter_entries(
    entries: list[FilesystemEntry],
    *,
    name_patterns: tuple[str, ...] = (),
    extension: str | None = None,
    entry_type: EntryType | None = None,
    min_size: int | None = None,
    max_size: int | None = None,
    modified_after: str | None = None,
    modified_before: str | None = None,
) -> list[FilesystemEntry]:
    """Return entries matching all given filters.

    Filters are combined with logical AND; multiple name patterns are
    combined with logical OR. An entry must satisfy every specified
    filter to be included.
    """
    result: list[FilesystemEntry] = []
    for entry in entries:
        if name_patterns and not any(matches_name(entry, pattern) for pattern in name_patterns):
            continue
        if extension is not None and not matches_extension(entry, extension):
            continue
        if entry_type is not None and not matches_type(entry, entry_type):
            continue
        if min_size is not None and not matches_min_size(entry, min_size):
            continue
        if max_size is not None and not matches_max_size(entry, max_size):
            continue
        if modified_after is not None and not matches_modified_after(entry, modified_after):
            continue
        if modified_before is not None and not matches_modified_before(entry, modified_before):
            continue
        result.append(entry)
    return result


def parse_size(value: str) -> int:
    """Parse a size value with optional binary suffix (K, M, G, T).

    Examples: ``"1024"``, ``"1K"``, ``"2.5M"``, ``"1G"``.
    """
    value = value.strip()
    if not value:
        raise ValueError("empty size value")
    suffix = value[-1]
    if suffix in "KMGTkmgt":
        number_part = value[:-1]
        multiplier = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}[suffix.upper()]
    else:
        number_part = value
        multiplier = 1
    try:
        result = int(float(number_part) * multiplier)
    except (ValueError, OverflowError) as exc:
        raise ValueError(f"invalid size value: {value!r}") from exc
    if result < 0:
        raise ValueError(f"size must not be negative: {value!r}")
    return result


def find_entries(
    root: Path,
    *,
    name_patterns: tuple[str, ...] = (),
    extension: str | None = None,
    entry_type: EntryType | None = None,
    min_size: int | None = None,
    max_size: int | None = None,
    modified_after: str | None = None,
    modified_before: str | None = None,
    max_depth: int | None = None,
    max_entries: int | None = None,
    ignore_dirs: frozenset[str] | None = None,
    ignore_patterns: tuple[str, ...] = (),
    sort_by: SortBy = "name",
    use_default_ignores: bool = True,
) -> tuple[list[FilesystemEntry], list[str], bool]:
    """Traverse ``root`` and return entries matching all filters.

    Returns a tuple of ``(matching_entries, error_messages, complete)``
    where error_messages describes traversal errors encountered during
    the scan and ``complete`` is False when the scan was truncated or
    could not read part of the tree.
    """
    from fs_tool.core.traversal import traverse

    result = traverse(
        root,
        max_depth=max_depth,
        max_entries=max_entries,
        dirs_only=False,
        ignore_dirs=ignore_dirs,
        ignore_patterns=ignore_patterns,
        sort_by=sort_by,
        use_default_ignores=use_default_ignores,
    )

    errors = [error.message for error in result.errors]

    matching = filter_entries(
        result.entries,
        name_patterns=name_patterns,
        extension=extension,
        entry_type=entry_type,
        min_size=min_size,
        max_size=max_size,
        modified_after=modified_after,
        modified_before=modified_before,
    )

    return matching, errors, result.complete
