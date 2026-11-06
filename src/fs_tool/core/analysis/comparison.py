"""Directory tree comparison (plan.md Phase 3, section 5.4).

Compares a source directory tree against a destination directory tree,
categorizing each relative path as identical, missing, changed,
unexpected, type_conflict, or unsupported. Uses SHA-256 hashing to
verify file content.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from fs_tool.core.hashing import sha256_of_file
from fs_tool.core.models import EntryType, FilesystemEntry
from fs_tool.core.traversal import traverse


@dataclass
class ComparisonResult:
    """Result of comparing two directory trees."""

    identical: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    unexpected: list[str] = field(default_factory=list)
    type_conflicts: list[str] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    complete: bool = True


def _build_entry_map(
    entries: list[FilesystemEntry],
) -> dict[str, FilesystemEntry]:
    """Build a rel_path -> entry map from traversal entries."""
    entry_map: dict[str, FilesystemEntry] = {}
    for entry in entries:
        rel_path = entry.rel_path or entry.name
        entry_map[rel_path] = entry
    return entry_map


def compare_trees(
    source: Path,
    destination: Path,
    *,
    max_entries: int | None = None,
    ignore_dirs: frozenset[str] | None = None,
    ignore_patterns: tuple[str, ...] = (),
) -> ComparisonResult:
    """Compare ``source`` and ``destination`` directory trees.

    Returns a :class:`ComparisonResult` categorizing entries by
    relative path. Files are compared by SHA-256 hash.
    """
    source_result = traverse(
        source,
        max_entries=max_entries,
        dirs_only=False,
        ignore_dirs=ignore_dirs,
        ignore_patterns=ignore_patterns,
    )
    dest_result = traverse(
        destination,
        max_entries=max_entries,
        dirs_only=False,
        ignore_dirs=ignore_dirs,
        ignore_patterns=ignore_patterns,
    )

    result = ComparisonResult()
    result.errors = [error.message for error in source_result.errors] + [
        error.message for error in dest_result.errors
    ]
    result.complete = source_result.complete and dest_result.complete

    source_map = _build_entry_map(source_result.entries)
    dest_map = _build_entry_map(dest_result.entries)

    source_paths = set(source_map.keys())
    dest_paths = set(dest_map.keys())

    # Missing: in source but not in destination
    for rel_path in sorted(source_paths - dest_paths):
        entry = source_map[rel_path]
        if entry.type is EntryType.OTHER:
            result.unsupported.append(rel_path)
        else:
            result.missing.append(rel_path)

    # Unexpected: in destination but not in source
    for rel_path in sorted(dest_paths - source_paths):
        entry = dest_map[rel_path]
        if entry.type is EntryType.OTHER:
            result.unsupported.append(rel_path)
        else:
            result.unexpected.append(rel_path)

    # Common paths: compare
    for rel_path in sorted(source_paths & dest_paths):
        src_entry = source_map[rel_path]
        dst_entry = dest_map[rel_path]

        # Type conflict
        if src_entry.type is not dst_entry.type:
            result.type_conflicts.append(rel_path)
            continue

        # Unsupported types
        if src_entry.type is EntryType.OTHER:
            result.unsupported.append(rel_path)
            continue

        # Directories: just need to exist in both
        if src_entry.type is EntryType.DIRECTORY:
            result.identical.append(rel_path)
            continue

        # Symlinks: compare targets
        if src_entry.type is EntryType.SYMLINK:
            if src_entry.target == dst_entry.target:
                result.identical.append(rel_path)
            else:
                result.changed.append(rel_path)
            continue

        # Regular files: compare by SHA-256
        src_hash = sha256_of_file(src_entry.path)
        dst_hash = sha256_of_file(dst_entry.path)

        if src_hash is None or dst_hash is None:
            # Cannot hash one or both files; treat as changed
            result.changed.append(rel_path)
        elif src_hash == dst_hash:
            result.identical.append(rel_path)
        else:
            result.changed.append(rel_path)

    return result
