"""SHA-256 hashing of files (plan.md Phase 1, P1-T09).

Hashing is read-only: symlinks are never followed and only regular
files are hashed. Special files (FIFOs, sockets, devices) are
explicitly excluded and never opened.
"""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path

CHUNK_SIZE = 1 << 20  # 1 MiB


def sha256_of_file(path: str | Path) -> str | None:
    """Return the SHA-256 hex digest of ``path`` or ``None``.

    ``None`` is returned when the path does not exist, is not a regular
    file (symlinks, directories, FIFOs, sockets, devices), or its
    contents cannot be read. Errors are not raised: callers report them
    as traversal or inventory errors instead.
    """
    p = Path(path)
    try:
        st = p.lstat()
    except OSError:
        return None
    if not stat.S_ISREG(st.st_mode):
        return None

    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW  # never follow a symlink at open time
    try:
        fd = os.open(p, flags)
    except OSError:
        return None

    digest = hashlib.sha256()
    try:
        with os.fdopen(fd, "rb") as f:
            for chunk in iter(lambda: f.read(CHUNK_SIZE), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()
