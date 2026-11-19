"""TOML configuration loading (plan.md Phase 1, P1-T14, decision D4).

Configuration file: a platform-specific ``config.toml`` below the user
configuration directory (Linux: ``~/.config/fs-tool``, macOS:
``~/Library/Application Support/fs-tool``, Windows: ``%APPDATA%\\fs-tool``),
overridden by ``--config PATH``.

Precedence: CLI ``--allow-root`` > Config ``allowed_roots`` > defaults.
When no CLI roots are given, the configuration is authoritative for
``allowed_roots`` and may include roots outside home and CWD. When CLI roots
are given, they replace the configured roots.

Example config file:

.. code-block:: toml

   [fs-tool]
   allowed_roots = ["/home/user", "/mnt/nas"]
   write_roots = ["/home/user/sorted"]
   allow_manipulate_originals = false
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from platformdirs import user_config_dir

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

    ``allowed_roots`` is the effective read-access set after applying
    CLI > Config > Defaults precedence. ``write_roots`` is the effective
    write-destination set and is always a subset of ``allowed_roots``.
    ``allow_manipulate_originals`` gates destructive operations outside
    ``write_roots``.
    """

    allowed_roots: tuple[Path, ...]
    write_roots: tuple[Path, ...]
    allow_manipulate_originals: bool
    config_path: Path


def _default_config_dir() -> Path:
    """Return the platform-specific user configuration directory."""
    return Path(user_config_dir(CONFIG_DIR_NAME))


def _default_config_path() -> Path:
    return _default_config_dir() / CONFIG_FILE_NAME


def _config_roots(data: dict[str, Any], key: str) -> tuple[Path, ...] | None:
    fs_tool = data.get("fs-tool")
    if not isinstance(fs_tool, dict):
        return None
    roots = fs_tool.get(key)
    if roots is None:
        return None
    if not isinstance(roots, list) or not all(isinstance(root, str) for root in roots):
        raise ConfigError(f"fs-tool.{key} must be a list of strings")
    return tuple(Path(root) for root in roots)


def _config_bool(data: dict[str, Any], key: str, default: bool = False) -> bool:
    fs_tool = data.get("fs-tool")
    if not isinstance(fs_tool, dict):
        return default
    value = fs_tool.get(key, default)
    if not isinstance(value, bool):
        raise ConfigError(f"fs-tool.{key} must be a boolean")
    return value


def load_config(
    config_path: str | Path | None = None,
    cli_roots: tuple[Path, ...] | None = None,
) -> AppConfig:
    """Load the configuration and resolve the effective root sets.

    Precedence:

    1. ``cli_roots`` (from ``--allow-root``) if given; they replace the
       configured roots.
    2. ``allowed_roots`` from the config file when no CLI roots are given.
    3. Defaults (home plus CWD) otherwise.

    ``write_roots`` defaults to ``allowed_roots`` and must lie within it.
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

    config_roots = _config_roots(data, "allowed_roots")
    config_write_roots = _config_roots(data, "write_roots")
    allow_manipulate = _config_bool(data, "allow_manipulate_originals", default=False)

    fs_tool_data = data.get("fs-tool")
    if fs_tool_data is not None and not isinstance(fs_tool_data, dict):
        raise ConfigError("fs-tool section must be a table", path)
    if isinstance(fs_tool_data, dict):
        allowed_keys = {"allowed_roots", "write_roots", "allow_manipulate_originals"}
        unknown = sorted(set(fs_tool_data) - allowed_keys)
        if unknown:
            raise ConfigError(
                f"Unknown fs-tool config key(s): {', '.join(unknown)}; "
                f"allowed: {', '.join(sorted(allowed_keys))}",
                path,
            )

    base: tuple[Path, ...]
    if cli_roots:
        base = tuple(cli_roots)
    elif config_roots is not None:
        base = config_roots
    else:
        base = default_allowed_roots()

    allowed_roots = tuple(dict.fromkeys(normalize_path(root) for root in base))
    if not allowed_roots:
        raise ConfigError("No allowed roots configured.", path)

    if config_write_roots is None:
        write_roots = allowed_roots
    else:
        write_roots = tuple(dict.fromkeys(normalize_path(root) for root in config_write_roots))
        invalid = [
            root
            for root in write_roots
            if not any(is_within_root(root, allowed_root) for allowed_root in allowed_roots)
        ]
        if invalid:
            raise ConfigError(
                "fs-tool.write_roots must be within fs-tool.allowed_roots; "
                f"invalid: {', '.join(str(root) for root in invalid)}",
                path,
            )

    return AppConfig(
        allowed_roots=allowed_roots,
        write_roots=write_roots,
        allow_manipulate_originals=allow_manipulate,
        config_path=path,
    )


def _os_config_hint() -> str:
    """Return a short, platform-specific hint for the default config path."""
    if os.name == "nt":
        return "Windows: %APPDATA%\\fs-tool\\config.toml"
    if os.uname().sysname == "Darwin":  # pragma: no cover - platform-specific
        return "macOS: ~/Library/Application Support/fs-tool/config.toml"
    return "Linux: ~/.config/fs-tool/config.toml (or $XDG_CONFIG_HOME/fs-tool/config.toml)"
