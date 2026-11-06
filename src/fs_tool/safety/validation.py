"""Allowed-root validation (plan.md Phase 1, decision D6).

By default only the user's home directory and the current working
directory are accessible. Anything else requires explicit authorization
via ``--allow-root``. The current working directory of ``/`` is not
implicitly allowed.
"""

from __future__ import annotations

from pathlib import Path

from fs_tool.core.errors import ErrorCode, FsToolError
from fs_tool.core.filesystem import normalize_path, resolve_path


class PathNotAllowedError(FsToolError):
    """A requested path lies outside the allowed roots."""

    def __init__(self, path: str | Path, roots: tuple[Path, ...]) -> None:
        super().__init__(
            f"Path not allowed: {path}",
            code=ErrorCode.ROOT_NOT_ALLOWED,
            path=str(path),
            details={"roots": [str(root) for root in roots]},
        )


def default_allowed_roots() -> tuple[Path, ...]:
    """Default allowed roots: home plus CWD, unless CWD is ``/`` (D6)."""
    roots = [Path.home()]
    if Path.cwd() != Path("/"):
        roots.append(Path.cwd())
    return tuple(roots)


def is_within_root(path: Path, root: Path) -> bool:
    """True if ``path`` is located at or below ``root`` (lexical check)."""
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def validate_path(
    path: str | Path,
    allowed_roots: tuple[Path, ...] | None = None,
) -> Path:
    """Return the normalized path if it is within an allowed root.

    Both the lexically normalized path and the symlink-resolved path
    must lie within an allowed root, so symlinks cannot be used to
    escape an allowed root. Raises :class:`PathNotAllowedError`
    (exit code 3) otherwise.
    """
    roots = tuple(allowed_roots) if allowed_roots is not None else default_allowed_roots()
    candidates = (normalize_path(path), resolve_path(path))
    for candidate in candidates:
        if not any(is_within_root(candidate, root) for root in roots):
            raise PathNotAllowedError(path, roots)
    return candidates[0]


def symlink_components(path: str | Path) -> list[Path]:
    """Return the components of ``path`` that are symbolic links.

    Uses ``lstat`` so symlinks are never followed. Components are
    returned from the filesystem root toward ``path``.
    """
    resolved = normalize_path(path)
    links: list[Path] = []
    current: Path = resolved
    while True:
        if current.is_symlink():
            links.append(current)
        if current == current.parent:
            break
        current = current.parent
    links.reverse()
    return links
