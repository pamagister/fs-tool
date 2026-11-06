"""Duplicate file detection (plan.md Phase 3, section 5.3).

Identifies files with identical content using a two-phase approach:

1. Group files by size to filter out obvious non-duplicates.
2. SHA-256 hash same-size candidates and group by digest.

Hardlinks (same device+inode) are not counted as duplicates. Empty
files are excluded by default; use ``include_empty=True`` to include
them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from fs_tool.core.hashing import sha256_of_file
from fs_tool.core.models import EntryType
from fs_tool.core.traversal import traverse


@dataclass(frozen=True)
class DuplicateGroup:
    """A group of files with identical content."""

    sha256: str
    size: int
    count: int
    files: list[str] = field(default_factory=list)


@dataclass
class DuplicateResult:
    """Result of duplicate detection."""

    groups: list[DuplicateGroup] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    complete: bool = True


def find_duplicates(
    root: Path,
    *,
    min_size: int = 1,
    include_empty: bool = False,
    max_entries: int | None = None,
    ignore_dirs: frozenset[str] | None = None,
    ignore_patterns: tuple[str, ...] = (),
) -> DuplicateResult:
    """Find duplicate files under ``root``.

    Returns a :class:`DuplicateResult` with groups of files sharing
    identical SHA-256 hashes. Files smaller than ``min_size`` (or
    empty files when ``include_empty`` is False) are excluded.
    """

    result = traverse(
        root,
        max_entries=max_entries,
        dirs_only=False,
        ignore_dirs=ignore_dirs,
        ignore_patterns=ignore_patterns,
    )

    # Collect regular files, tracking hardlinks by (dev, inode).
    files: list[tuple[str, int, str]] = []  # (path, size, dev_ino)
    seen_inodes: set[tuple[int, int]] = set()

    for entry in result.entries:
        if entry.type is not EntryType.FILE:
            continue
        if entry.size is None:
            continue
        if entry.size == 0 and not include_empty:
            continue
        if entry.size > 0 and entry.size < min_size:
            continue
        dev_ino = entry.dev_ino
        if dev_ino is not None:
            try:
                dev, ino = dev_ino.split(":", 1)
                key = (int(dev), int(ino))
            except (ValueError, AttributeError):
                key = None
            if key is not None:
                if key in seen_inodes:
                    continue  # hardlink, already seen
                seen_inodes.add(key)
        files.append((entry.path, entry.size, dev_ino or ""))

    # Group candidates by size.
    by_size: dict[int, list[tuple[str, str]]] = {}  # size -> [(path, dev_ino)]
    for path, size, dev_ino in files:
        by_size.setdefault(size, []).append((path, dev_ino))

    # Hash candidates with more than one same-size file.
    groups: list[DuplicateGroup] = []
    errors = [error.message for error in result.errors]
    complete = result.complete
    for size, candidates in by_size.items():
        if len(candidates) < 2:
            continue
        by_hash: dict[str, list[str]] = {}
        for path, _dev_ino in candidates:
            digest = sha256_of_file(path)
            if digest is None:
                complete = False
                errors.append(f"Cannot hash {path}; duplicate detection is incomplete.")
                continue
            by_hash.setdefault(digest, []).append(path)
        for digest, paths in by_hash.items():
            if len(paths) >= 2:
                groups.append(
                    DuplicateGroup(
                        sha256=digest,
                        size=size,
                        count=len(paths),
                        files=sorted(paths),
                    )
                )

    groups.sort(key=lambda g: (-g.count, g.sha256))

    return DuplicateResult(groups=groups, errors=errors, complete=complete)
