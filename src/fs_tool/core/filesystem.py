"""Filesystem path normalization (plan.md Phase 1).

Pure lexical normalization: expand the user's home directory, make the
path absolute and collapse ``.`` and ``..`` components. No filesystem
access is performed and symlinks are not resolved here (see
:func:`resolve_path` for symlink-aware resolution).
"""

from __future__ import annotations

import os
from pathlib import Path


def normalize_path(path: str | Path) -> Path:
    """Lexically normalize ``path``.

    Expands ``~``, makes the path absolute against the current working
    directory and collapses redundant separators, ``.`` and up-level
    references (``..``) without touching the filesystem. Symlinks are
    not resolved; use :func:`resolve_path` for that.
    """
    expanded = os.path.expanduser(os.fspath(path))
    absolute = os.path.abspath(expanded)
    parsed = Path(absolute)
    collapsed: list[str] = []
    for part in parsed.parts:
        if part == "." or part == "":
            continue
        if part == parsed.anchor:
            if collapsed and collapsed[-1] == parsed.anchor:
                continue
            collapsed.append(part)
            continue
        if part == "..":
            if len(collapsed) > 1 and collapsed[-1] != parsed.anchor:
                collapsed.pop()
            # At the filesystem root, ".." goes nowhere.
            continue
        collapsed.append(part)
    return Path(*collapsed)


def resolve_path(path: str | Path) -> Path:
    """Resolve symlinks and up-level references as far as possible.

    Unlike :func:`normalize_path`, this accesses the filesystem. Missing
    path components are kept as-is (``strict=False`` behavior).
    """
    return Path(os.path.expanduser(os.fspath(path))).resolve(strict=False)
