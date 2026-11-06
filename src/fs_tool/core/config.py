"""TOML configuration loading (plan.md Phase 1, P1-T14, decision D4).

Configuration file: ``$XDG_CONFIG_HOME/fs-tool/config.toml``, overridden
by ``--config PATH``. There is no automatic loading of project-local
configuration files. Precedence is CLI > Config > Defaults; the
configuration may only restrict the allowed roots, never expand them.

Example config file:

.. code-block:: toml

   [fs-tool]
   allowed_roots = ["/home/user", "/mnt/nas"]
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fs_tool.core.errors import ErrorCode, FsToolError

CONFIG_FILE_NAME = "config.toml"
CONFIG_DIR_NAME = "fs-tool"


class ConfigError(FsToolError):
    """A configuration file could not be read or interpreted."""

    def __init__(self, message: str, path: str | Path | None = None) -> None:
        super().__init__(
            message,
            code=ErrorCode.INVALID_ARGUMENT,
            path=str(path) if path is not None else None,
        )


@dataclass(frozen=True)
class AppConfig:
    """Resolved application configuration.

    ``allowed_roots`` is the effective set of roots after applying CLI
    > Config > Defaults precedence. The configuration may only restrict
    roots; it never expands them.
    """

    allowed_roots: tuple[Path, ...]


def _default_config_path() -> Path:
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg_config_home) if xdg_config_home else Path.home() / ".config"
    return base / CONFIG_DIR_NAME / CONFIG_FILE_NAME


def _config_allowed_roots(data: dict[str, Any]) -> tuple[Path, ...] | None:
    fs_tool = data.get("fs-tool")
    if not isinstance(fs_tool, dict):
        return None
    roots = fs_tool.get("allowed_roots")
    if roots is None:
        return None
    if not isinstance(roots, list) or not all(isinstance(r, str) for r in roots):
        raise ConfigError("fs-tool.allowed_roots must be a list of strings")
    return tuple(Path(root) for root in roots)


def load_config(
    config_path: str | Path | None = None,
    cli_roots: tuple[Path, ...] | None = None,
) -> AppConfig:
    """Load the configuration and resolve the effective allowed roots.

    Precedence:

    1. ``cli_roots`` (from ``--allow-root``) if given, otherwise the
       default roots (home plus CWD).
    2. ``allowed_roots`` from the config file, if present, intersected
       with the CLI roots so the configuration can only restrict roots.
    3. Defaults otherwise.
    """
    from fs_tool.core.filesystem import normalize_path
    from fs_tool.safety.validation import default_allowed_roots, is_within_root

    path = Path(config_path) if config_path is not None else _default_config_path()

    data: dict[str, Any] = {}
    if path.exists():
        try:
            with path.open("rb") as handle:
                data = tomllib.load(handle)
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError(f"Invalid TOML in {path}: {exc}") from exc
        except OSError as exc:
            raise ConfigError(f"Cannot read config file {path}: {exc.strerror or exc}") from exc

    config_roots = _config_allowed_roots(data)

    base: tuple[Path, ...]
    if cli_roots:
        base = cli_roots
    else:
        base = default_allowed_roots()
    # Deduplicate (e.g. CWD == home) and normalize spellings.
    base = tuple(dict.fromkeys(normalize_path(root) for root in base))

    if config_roots is not None:
        config_roots = tuple(dict.fromkeys(normalize_path(root) for root in config_roots))
        # Keep configured roots that lie within an authorized base root.
        # A broader configured root is ignored, so the configuration may
        # only restrict access, never expand it.
        effective = tuple(
            root
            for root in config_roots
            if any(is_within_root(root, base_root) for base_root in base)
        )
        return AppConfig(allowed_roots=effective)

    return AppConfig(allowed_roots=base)
