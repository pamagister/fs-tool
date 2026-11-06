"""Filesystem verification (plan.md Phase 3, section 5.5).

Verifies a directory against a previously stored inventory file
(``verify inventory``) or against a source directory
(``verify tree``). Detects missing, unexpected, and changed entries,
verifies file sizes and hashes, and reports incomplete verification.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from fs_tool.core.errors import ErrorCode, FsToolError
from fs_tool.core.hashing import sha256_of_file
from fs_tool.core.models import EntryType, FilesystemEntry
from fs_tool.core.traversal import traverse


@dataclass
class VerificationResult:
    """Result of verifying a filesystem state."""

    missing: list[str] = field(default_factory=list)
    unexpected: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    size_mismatch: list[str] = field(default_factory=list)
    hash_mismatch: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    complete: bool = True


def _load_inventory(path: Path) -> dict[str, object]:
    """Load and validate an inventory JSON file.

    Raises :class:`FsToolError` if the file cannot be read, is not
    valid JSON, or has an unsupported schema version.
    """
    try:
        with path.open("r", encoding="utf-8") as f:
            data: dict[str, object] = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise FsToolError(
            f"Cannot load inventory file {path}: {exc}",
            code=ErrorCode.INVALID_ARGUMENT,
            path=str(path),
        ) from exc

    schema_version = data.get("schema_version")
    if schema_version != 1:
        raise FsToolError(
            f"Unsupported inventory schema_version: {schema_version!r}; expected 1.",
            code=ErrorCode.INVALID_ARGUMENT,
            path=str(path),
        )

    return data


def _build_entry_map(entries: list[FilesystemEntry]) -> dict[str, FilesystemEntry]:
    """Build a rel_path -> entry map from traversal entries."""
    entry_map: dict[str, FilesystemEntry] = {}
    for entry in entries:
        rel_path = entry.rel_path or entry.name
        entry_map[rel_path] = entry
    return entry_map


def verify_inventory(
    inventory_path: Path,
    target: Path,
    *,
    max_entries: int | None = None,
    ignore_dirs: frozenset[str] | None = None,
    ignore_patterns: tuple[str, ...] = (),
) -> VerificationResult:
    """Verify ``target`` against an inventory file.

    Loads the inventory, traverses ``target``, and compares entries.
    Reports missing entries (in inventory but not in target),
    unexpected entries (in target but not in inventory), size
    mismatches, and hash mismatches where inventory hashes are
    available.
    """
    data = _load_inventory(inventory_path)

    inventory_entries = data.get("entries", [])
    if not isinstance(inventory_entries, list):
        inventory_entries = []
    inventory_map: dict[str, dict[str, object]] = {}
    for entry in inventory_entries:
        if not isinstance(entry, dict):
            continue
        rel_path = entry.get("rel_path", "")
        if rel_path:
            inventory_map[rel_path] = entry

    target_result = traverse(
        target,
        max_entries=max_entries,
        dirs_only=False,
        ignore_dirs=ignore_dirs,
        ignore_patterns=ignore_patterns,
    )

    result = VerificationResult()
    result.errors = [error.message for error in target_result.errors]
    result.complete = target_result.complete

    target_map = _build_entry_map(target_result.entries)

    inventory_paths = set(inventory_map.keys())
    target_paths = set(target_map.keys())

    # Missing: in inventory but not in target
    for rel_path in sorted(inventory_paths - target_paths):
        result.missing.append(rel_path)

    # Unexpected: in target but not in inventory
    for rel_path in sorted(target_paths - inventory_paths):
        result.unexpected.append(rel_path)

    # Common paths: verify sizes and hashes
    for rel_path in sorted(inventory_paths & target_paths):
        inv_entry = inventory_map[rel_path]
        tgt_entry = target_map[rel_path]

        # Type conflict
        inv_type = inv_entry.get("type")
        if tgt_entry.type.value != inv_type:
            result.changed.append(rel_path)
            continue

        # Size mismatch
        inv_size = inv_entry.get("size")
        if inv_size is not None and tgt_entry.size is not None:
            if inv_size != tgt_entry.size:
                result.size_mismatch.append(rel_path)
                result.changed.append(rel_path)
                continue

        # Hash mismatch (only when inventory has SHA-256)
        inv_hash = inv_entry.get("sha256")
        if inv_hash is not None:
            tgt_hash = sha256_of_file(tgt_entry.path)
            if tgt_hash is None:
                result.hash_mismatch.append(rel_path)
                result.changed.append(rel_path)
            elif tgt_hash != inv_hash:
                result.hash_mismatch.append(rel_path)
                result.changed.append(rel_path)

    return result


def verify_tree(
    source: Path,
    destination: Path,
    *,
    max_entries: int | None = None,
    ignore_dirs: frozenset[str] | None = None,
    ignore_patterns: tuple[str, ...] = (),
) -> VerificationResult:
    """Verify ``destination`` against ``source``.

    Traverses both trees and compares entries. Reports missing entries
    (in source but not in destination), unexpected entries (in
    destination but not in source), size mismatches, and hash
    mismatches.
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

    result = VerificationResult()
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
        result.missing.append(rel_path)

    # Unexpected: in destination but not in source
    for rel_path in sorted(dest_paths - source_paths):
        result.unexpected.append(rel_path)

    # Common paths: verify sizes and hashes
    for rel_path in sorted(source_paths & dest_paths):
        src_entry = source_map[rel_path]
        dst_entry = dest_map[rel_path]

        # Type conflict
        if src_entry.type is not dst_entry.type:
            result.changed.append(rel_path)
            continue

        # Size mismatch
        if src_entry.size is not None and dst_entry.size is not None:
            if src_entry.size != dst_entry.size:
                result.size_mismatch.append(rel_path)
                result.changed.append(rel_path)
                continue

        # Hash mismatch (for regular files only)
        if src_entry.type is EntryType.FILE:
            src_hash = sha256_of_file(src_entry.path)
            dst_hash = sha256_of_file(dst_entry.path)
            if src_hash is None or dst_hash is None:
                result.hash_mismatch.append(rel_path)
                result.changed.append(rel_path)
            elif src_hash != dst_hash:
                result.hash_mismatch.append(rel_path)
                result.changed.append(rel_path)

    return result
