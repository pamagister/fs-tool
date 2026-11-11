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


def project_entry_dict(data: dict[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    """Project a serialized entry onto ``fields`` in profile order."""
    return {field: data[field] for field in fields if field in data}


def _entry_dict(entry: FilesystemEntry, *, exclude_path: bool = False) -> dict[str, Any]:
    data = asdict(entry)
    if exclude_path:
        data.pop("path", None)
    return data


def tree_entry_dict(entry: FilesystemEntry, *, verbose: bool = False) -> dict[str, Any]:
    """Serialize an entry for ``inspect tree``.

    Compact output communicates structure only: relative path and type.
    Verbose output keeps the complete existing entry representation.
    """
    data = _entry_dict(entry)
    return data if verbose else project_entry_dict(data, TREE_COMPACT_FIELDS)


def inventory_entry_dict(entry: FilesystemEntry, *, verbose: bool = False) -> dict[str, Any]:
    """Serialize an entry for ``inspect inventory``.

    Inventories stay portable and omit the absolute ``path``. Compact output
    keeps the metadata needed to identify and describe an entry. Verbose
    output keeps every remaining entry field.
    """
    data = _entry_dict(entry, exclude_path=True)
    return data if verbose else project_entry_dict(data, INVENTORY_COMPACT_FIELDS)


def find_entry_dict(entry: FilesystemEntry, *, verbose: bool = False) -> dict[str, Any]:
    """Serialize an entry for ``find``.

    Compact output keeps the match identity and size. Verbose output keeps
    the complete existing entry representation.
    """
    data = _entry_dict(entry)
    return data if verbose else project_entry_dict(data, FIND_COMPACT_FIELDS)


def _format_detail_value(value: Any) -> str:
    """Render a detail value using JSON-like literals for empty values."""
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)


def entry_dict_detail_lines(
    data: dict[str, Any],
    *,
    exclude: tuple[str, ...] = (),
    include_empty: bool = False,
) -> list[str]:
    """Render verbose-only plain-text detail lines from a serialized entry.

    By default empty values (``None`` and ``False``) are omitted for compact
    human-oriented output. ``include_empty`` renders them explicitly as
    ``null`` and ``false`` so callers can present the complete entry
    representation.
    """
    lines: list[str] = []
    for field in ENTRY_DETAIL_FIELDS:
        if field in exclude or field not in data:
            continue
        value = data[field]
        if not include_empty and (value is None or value is False):
            continue
        lines.append(f"{field}: {_format_detail_value(value)}")
    if "metadata" in data and (data["metadata"] or include_empty):
        lines.append(f"metadata: {_format_detail_value(data['metadata'])}")
    return lines


def entry_detail_lines(entry: FilesystemEntry, *, exclude: tuple[str, ...] = ()) -> list[str]:
    """Render the verbose-only plain-text detail lines for one entry."""
    data = asdict(entry)
    return entry_dict_detail_lines(data, exclude=exclude)
