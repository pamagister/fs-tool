"""Internal filesystem data model.

A consistent internal representation for filesystem entries
(plan.md section 8). The model is independent of JSON serialization
and terminal rendering. Fields that are unavailable or not applicable
are ``None``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class EntryType(str, Enum):
    FILE = "file"
    DIRECTORY = "directory"
    SYMLINK = "symlink"
    OTHER = "other"


@dataclass(frozen=True)
class FilesystemEntry:
    """A single filesystem entry as observed by fs-tool."""

    path: str
    name: str
    rel_path: str | None = None
    type: EntryType = EntryType.FILE
    extension: str | None = None
    size: int | None = None
    modified: str | None = None
    created: str | None = None
    accessed: str | None = None
    changed: str | None = None
    mode: str | None = None
    owner: str | None = None
    mime_type: str | None = None
    is_symlink: bool = False
    target: str | None = None
    sha256: str | None = None
    dev_ino: str | None = None
    metadata: dict[str, Any] | None = None
