"""Tests for TOML configuration loading (plan.md Phase 1, P1-T14, D4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from fs_tool.core.config import AppConfig, ConfigError, load_config


def _write_config(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _isolate_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    config_home = tmp_path / "config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    return config_home


def test_missing_config_falls_back_to_defaults(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    _isolate_env(tmp_path, monkeypatch)
    config = load_config()
    assert isinstance(config, AppConfig)
    assert config.allowed_roots == (Path.home(), tmp_path)


def test_explicit_config_path_is_used(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    _isolate_env(tmp_path, monkeypatch)
    default_config = tmp_path / "config" / "fs-tool" / "config.toml"
    _write_config(default_config, '[fs-tool]\nallowed_roots = ["/other"]\n')
    custom = tmp_path / "custom.toml"
    _write_config(custom, f'[fs-tool]\nallowed_roots = ["{tmp_path}"]\n')
    config = load_config(custom, cli_roots=(tmp_path,))
    # The default config is not used; only the explicitly given one applies.
    assert config.allowed_roots == (tmp_path,)


def test_config_from_xdg_config_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "configured"
    home.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(home)
    config_home = _isolate_env(tmp_path, monkeypatch)
    config_path = config_home / "fs-tool" / "config.toml"
    _write_config(config_path, f'[fs-tool]\nallowed_roots = ["{home}"]\n')
    config = load_config()
    assert config.allowed_roots == (home,)


def test_config_may_restrict_default_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.chdir(home)
    config_path = tmp_path / "config.toml"
    _write_config(
        config_path,
        f'[fs-tool]\nallowed_roots = ["{home}", "/mnt/nas"]\n',
    )
    config = load_config(config_path)
    assert config.allowed_roots == (home,)


def test_config_never_expands_cli_roots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    config_path = tmp_path / "config.toml"
    _write_config(
        config_path,
        '[fs-tool]\nallowed_roots = ["/elsewhere"]\n',
    )
    config = load_config(config_path, cli_roots=(tmp_path,))
    assert config.allowed_roots == ()


def test_invalid_toml_reports_config_error(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text("not valid toml: [[[", encoding="utf-8")
    with pytest.raises(ConfigError) as exc:
        load_config(config_path)
    assert exc.value.exit_code == 2


def test_allowed_roots_must_be_a_list(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text("[fs-tool]\nallowed_roots = 42\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(config_path)
