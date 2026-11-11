"""Filesystem-entry output profiles.

The core data models always stay complete. Output profiles decide which of
those fields a command presents by default and which fields ``--verbose``
adds. Filtering happens after analysis, so it never changes scanning,
completeness or the number of returned entries.

Each command owns its compact profile. The profiles below are intentionally
command-specific: a tree needs structure, an inventory needs portable file
metadata, and ``find`` needs match details.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fs_tool.core.models import FilesystemEntry

TREE_COMPACT_FIELDS = ("rel_path", "type")
INVENTORY_COMPACT_FIELDS = ("rel_path", "type", "extension", "size", "modified")
FIND_COMPACT_FIELDS = ("rel_path", "type", "size")

# Plain-text verbose output shows the remaining entry attributes as
# ``key: value`` lines. Fields already represented by the command's compact
# line are excluded to avoid repetition.
ENTRY_DETAIL_FIELDS = (
    "name",
    "extension",
    "size",
    "modified",
    "created",
    "accessed",
    "changed",
    "mode",
    "owner",
    "mime_type",
    "is_symlink",
    "target",
    "sha256",
    "dev_ino",
)


def _project(entry: FilesystemEntry, fields: tuple[str, ...]) -> dict[str, Any]:
    """Return only ``fields`` from the serialized entry, in profile order."""
    data = asdict(entry)
    return {field: data[field] for field in fields}


def tree_entry_dict(entry: FilesystemEntry, *, verbose: bool = False) -> dict[str, Any]:
    """Serialize an entry for ``inspect tree``.

    Compact output communicates structure only: relative path and type.
    Verbose output keeps the complete existing entry representation.
    """
    return asdict(entry) if verbose else _project(entry, TREE_COMPACT_FIELDS)


def inventory_entry_dict(entry: FilesystemEntry, *, verbose: bool = False) -> dict[str, Any]:
    """Serialize an entry for ``inspect inventory``.

    Inventories stay portable and omit the absolute ``path``. Compact output
    keeps the metadata needed to identify and describe an entry. Verbose
    output keeps every remaining entry field.
    """
    data = asdict(entry)
    data.pop("path", None)
    if verbose:
        return data
    return {field: data[field] for field in INVENTORY_COMPACT_FIELDS}


def find_entry_dict(entry: FilesystemEntry, *, verbose: bool = False) -> dict[str, Any]:
    """Serialize an entry for ``find``.

    Compact output keeps the match identity and size. Verbose output keeps
    the complete existing entry representation.
    """
    return asdict(entry) if verbose else _project(entry, FIND_COMPACT_FIELDS)


def entry_dict_detail_lines(data: dict[str, Any], *, exclude: tuple[str, ...] = ()) -> list[str]:
    """Render verbose-only plain-text detail lines from a serialized entry."""
    lines: list[str] = []
    for field in ENTRY_DETAIL_FIELDS:
        if field in exclude:
            continue
        value = data.get(field)
        if value is not None and value is not False:
            lines.append(f"{field}: {value}")
    if data.get("metadata"):
        lines.append(f"metadata: {data['metadata']}")
    return lines


def entry_detail_lines(entry: FilesystemEntry, *, exclude: tuple[str, ...] = ()) -> list[str]:
    """Render the verbose-only plain-text detail lines for one entry."""
    data = asdict(entry)
    return entry_dict_detail_lines(data, exclude=exclude)
