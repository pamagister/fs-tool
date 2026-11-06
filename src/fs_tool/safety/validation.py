"""Allowed-root validation (plan.md Phase 1, decision D6).

By default only the user's home directory and the current working
directory are accessible. Anything else requires explicit authorization
via ``--allow-root``. The current working directory of ``/`` is not
implicitly allowed.
"""

from __future__ import annotations

from pathlib import Path

from fs_tool.core.errors import ErrorCode, FsToolError
from fs_tool.core.filesystem import normalize_path


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

    Raises :class:`PathNotAllowedError` (exit code 3) otherwise.
    """
    roots = tuple(allowed_roots) if allowed_roots is not None else default_allowed_roots()
    normalized = normalize_path(path)
    if any(is_within_root(normalized, root) for root in roots):
        return normalized
    raise PathNotAllowedError(path, roots)
