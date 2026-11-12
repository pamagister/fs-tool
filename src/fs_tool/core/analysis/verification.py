"""Filesystem verification (plan.md Phase 3, section 5.5).

Verifies a directory against a previously stored inventory file
(``verify inventory``) or against a source directory
(``verify tree``). Detects missing, unexpected, and changed entries,
verifies file sizes and hashes, and reports incomplete verification.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

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
    match_mode: str = "path"
    missing_content: list[dict[str, Any]] = field(default_factory=list)
    unexpected_content: list[dict[str, Any]] = field(default_factory=list)
    content_count_mismatch: bool = False


def _invalid_inventory(path: Path, message: str) -> FsToolError:
    """Build a consistent error for malformed inventory files."""
    return FsToolError(message, code=ErrorCode.INVALID_ARGUMENT, path=str(path))


def _load_inventory(path: Path) -> dict[str, object]:
    """Load and validate an inventory JSON file.

    Accepts both a bare inventory object (with top-level ``entries``)
    and the full JSON envelope emitted by ``inspect inventory`` (where
    the inventory is nested under ``result``). The schema version is
    read from the envelope when present.

    Raises :class:`FsToolError` if the file cannot be read, is not
    valid JSON, has an unsupported schema version, or has an unexpected
    structure.
    """
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise _invalid_inventory(path, f"Cannot load inventory file {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise _invalid_inventory(path, f"Invalid inventory file {path}: expected a JSON object.")

    schema_version = data.get("schema_version")
    inventory: dict[str, object] = data
    result_data = data.get("result")
    if "entries" not in data and isinstance(result_data, dict):
        inventory = result_data
        schema_version = data.get("schema_version", inventory.get("schema_version"))

    if schema_version != 1:
        raise _invalid_inventory(
            path,
            f"Unsupported inventory schema_version: {schema_version!r}; expected 1.",
        )

    entries = inventory.get("entries")
    if not isinstance(entries, list):
        raise _invalid_inventory(path, f"Invalid inventory file {path}: 'entries' must be a list.")

    valid_types = {entry_type.value for entry_type in EntryType}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise _invalid_inventory(
                path, f"Invalid inventory entry at index {index}: expected an object."
            )
        rel_path = entry.get("rel_path")
        if not isinstance(rel_path, str) or not rel_path:
            raise _invalid_inventory(
                path,
                f"Invalid inventory entry at index {index}: 'rel_path' must be a non-empty string.",
            )
        entry_type = entry.get("type")
        if not isinstance(entry_type, str) or entry_type not in valid_types:
            raise _invalid_inventory(
                path,
                f"Invalid inventory entry {rel_path!r}: 'type' must be one of "
                f"{', '.join(sorted(valid_types))}.",
            )
        sha256 = entry.get("sha256")
        if sha256 is not None and not isinstance(sha256, str):
            raise _invalid_inventory(
                path, f"Invalid inventory entry {rel_path!r}: 'sha256' must be a string or null."
            )

    complete = inventory.get("complete", True)
    if not isinstance(complete, bool):
        raise _invalid_inventory(
            path, f"Invalid inventory file {path}: 'complete' must be a boolean."
        )

    return inventory


def _build_entry_map(entries: list[FilesystemEntry]) -> dict[str, FilesystemEntry]:
    """Build a rel_path -> entry map from traversal entries."""
    entry_map: dict[str, FilesystemEntry] = {}
    for entry in entries:
        rel_path = entry.rel_path or entry.name
        entry_map[rel_path] = entry
    return entry_map


ContentKey = tuple[str, Any, Any]


def _record_content(
    counter: Counter[ContentKey],
    paths: dict[ContentKey, list[str]],
    key: ContentKey,
    path: str,
) -> None:
    """Add one content item to a multiset and its path index."""
    counter[key] += 1
    paths.setdefault(key, []).append(path)


def _inventory_content_counts(
    entries: list[object], inventory_path: Path
) -> tuple[Counter[ContentKey], dict[ContentKey, list[str]]]:
    """Build the content multiset described by an inventory."""
    counter: Counter[ContentKey] = Counter()
    paths: dict[ContentKey, list[str]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        rel_path = entry.get("rel_path")
        if not isinstance(rel_path, str):
            continue
        entry_type = entry.get("type")
        if entry_type == EntryType.FILE.value:
            sha256 = entry.get("sha256")
            size = entry.get("size")
            if not isinstance(sha256, str) or not sha256:
                raise _invalid_inventory(
                    inventory_path,
                    f"Inventory entry {rel_path!r} must contain a sha256 hash for content "
                    "verification; regenerate it with --hash.",
                )
            if not isinstance(size, int):
                raise _invalid_inventory(
                    inventory_path,
                    f"Inventory entry {rel_path!r} must contain an integer size for content "
                    "verification.",
                )
            _record_content(counter, paths, ("file", size, sha256), rel_path)
        elif entry_type == EntryType.SYMLINK.value:
            target = entry.get("target")
            if not isinstance(target, str):
                raise _invalid_inventory(
                    inventory_path,
                    f"Inventory entry {rel_path!r} must contain a symlink target for content "
                    "verification; regenerate it with --verbose.",
                )
            _record_content(counter, paths, ("symlink", target, None), rel_path)
    return counter, paths


def _target_content_counts(
    entries: list[FilesystemEntry],
) -> tuple[Counter[ContentKey], dict[ContentKey, list[str]], list[str]]:
    """Build the content multiset of a traversed target tree."""
    counter: Counter[ContentKey] = Counter()
    paths: dict[ContentKey, list[str]] = {}
    errors: list[str] = []
    for entry in entries:
        rel_path = entry.rel_path or entry.name
        if entry.type is EntryType.FILE:
            digest = sha256_of_file(entry.path)
            if digest is None:
                errors.append(f"Cannot hash {rel_path}; content verification is incomplete.")
                continue
            _record_content(counter, paths, ("file", entry.size, digest), rel_path)
        elif entry.type is EntryType.SYMLINK:
            _record_content(counter, paths, ("symlink", entry.target, None), rel_path)
    return counter, paths, errors


def _content_item_to_dict(key: ContentKey, count: int, paths: list[str]) -> dict[str, Any]:
    """Serialize one content multiset difference."""
    item: dict[str, Any] = {"type": key[0]}
    if key[0] == EntryType.FILE.value:
        item["size"] = key[1]
        item["sha256"] = key[2]
    else:
        item["target"] = key[1]
    item["count"] = count
    item["paths"] = sorted(paths)
    return item


def _content_differences(
    inventory_counter: Counter[ContentKey],
    inventory_paths: dict[ContentKey, list[str]],
    target_counter: Counter[ContentKey],
    target_paths: dict[ContentKey, list[str]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return missing and unexpected content items with their paths."""
    missing_counter = inventory_counter - target_counter
    unexpected_counter = target_counter - inventory_counter
    missing = [
        _content_item_to_dict(key, count, inventory_paths[key])
        for key, count in sorted(missing_counter.items(), key=lambda item: repr(item[0]))
    ]
    unexpected = [
        _content_item_to_dict(key, count, target_paths[key])
        for key, count in sorted(unexpected_counter.items(), key=lambda item: repr(item[0]))
    ]
    return missing, unexpected


def verify_inventory(
    inventory_path: Path,
    target: Path,
    *,
    max_entries: int | None = None,
    ignore_dirs: frozenset[str] | None = None,
    ignore_patterns: tuple[str, ...] = (),
    match_mode: str = "path",
) -> VerificationResult:
    """Verify ``target`` against an inventory file.

    Loads the inventory, traverses ``target``, and compares entries.
    Path mode reports missing entries (in inventory but not in target),
    unexpected entries (in target but not in inventory), size mismatches,
    and hash mismatches where inventory hashes are available. Content mode
    ignores paths and compares the multiset of file ``(size, sha256)`` pairs
    and symlink targets, which makes pure renames verifiable.
    """
    if match_mode not in {"path", "content"}:
        raise _invalid_inventory(
            inventory_path,
            f"Unsupported inventory match mode {match_mode!r}; use path or content.",
        )

    data = _load_inventory(inventory_path)

    inventory_entries = cast(list[object], data["entries"])
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

    result = VerificationResult(match_mode=match_mode)
    result.errors = [error.message for error in target_result.errors]
    result.complete = target_result.complete
    if not bool(data.get("complete", True)):
        result.complete = False
        result.errors.append(
            "Inventory was generated from an incomplete scan; verification is incomplete."
        )

    if match_mode == "content":
        inventory_counter, inventory_paths = _inventory_content_counts(
            inventory_entries, inventory_path
        )
        target_counter, target_paths, hash_errors = _target_content_counts(target_result.entries)
        result.errors.extend(hash_errors)
        if hash_errors:
            result.complete = False
        result.missing_content, result.unexpected_content = _content_differences(
            inventory_counter, inventory_paths, target_counter, target_paths
        )
        result.content_count_mismatch = sum(inventory_counter.values()) != sum(
            target_counter.values()
        )
        return result

    target_map = _build_entry_map(target_result.entries)

    inventory_paths_set = set(inventory_map.keys())
    target_paths_set = set(target_map.keys())

    # Missing: in inventory but not in target
    for rel_path in sorted(inventory_paths_set - target_paths_set):
        result.missing.append(rel_path)

    # Unexpected: in target but not in inventory
    for rel_path in sorted(target_paths_set - inventory_paths_set):
        result.unexpected.append(rel_path)

    # Common paths: verify sizes and hashes
    for rel_path in sorted(inventory_paths_set & target_paths_set):
        inv_entry = inventory_map[rel_path]
        tgt_entry = target_map[rel_path]

        # Type conflict
        inv_type = inv_entry.get("type")
        if tgt_entry.type.value != inv_type:
            result.changed.append(rel_path)
            continue

        # Symlinks: compare the recorded target. Directory sizes are
        # filesystem-specific and not portable, so only regular files
        # are compared by size below.
        if tgt_entry.type is EntryType.SYMLINK:
            inv_target = inv_entry.get("target")
            if isinstance(inv_target, str) and tgt_entry.target != inv_target:
                result.changed.append(rel_path)
            continue
        if tgt_entry.type is not EntryType.FILE:
            continue

        # Size mismatch (regular files only)
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
                result.complete = False
                result.errors.append(f"Cannot hash {rel_path}; verification is incomplete.")
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

        # Symlinks: compare targets. Directory sizes are
        # filesystem-specific and not portable, so only regular files
        # are compared by size below.
        if src_entry.type is EntryType.SYMLINK:
            if src_entry.target != dst_entry.target:
                result.changed.append(rel_path)
            continue
        if src_entry.type is not EntryType.FILE:
            continue

        # Size mismatch (regular files only)
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
                result.complete = False
                result.errors.append(f"Cannot hash {rel_path}; verification is incomplete.")
            elif src_hash != dst_hash:
                result.hash_mismatch.append(rel_path)
                result.changed.append(rel_path)

    return result
