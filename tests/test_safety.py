"""Tests for the originals-protection safety policy."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

import pytest

from fs_tool.cli import (
    EXIT_ACCESS_DENIED,
    EXIT_FAILURE,
    EXIT_SUCCESS,
)


def run_json(cli: Any, argv: list[str]) -> tuple[int, dict[str, Any]]:
    output = io.StringIO()
    with redirect_stdout(output):
        code = cli(argv)
    return code, json.loads(output.getvalue())


def _write_config(
    tmp_path: Path,
    *,
    write_roots: list[Path] | None = None,
    allow_manipulate_originals: bool = False,
) -> Path:
    lines = ["[fs-tool]"]
    if write_roots is not None:
        rendered = ", ".join(f'"{path}"' for path in write_roots)
        lines.append(f"write_roots = [{rendered}]")
    if allow_manipulate_originals:
        lines.append("allow_manipulate_originals = true")
    config = tmp_path / "fs-tool-config.toml"
    config.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return config


def _layout(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    allowed = tmp_path / "allowed"
    target = allowed / "target"
    other = allowed / "other"
    allowed.mkdir()
    target.mkdir()
    other.mkdir()
    source = allowed / "source.txt"
    source.write_text("content", encoding="utf-8")
    return allowed, target, other, source


def test_copy_outside_write_roots_is_denied(cli: Any, tmp_path: Path) -> None:
    allowed, _target, other, source = _layout(tmp_path)
    config = _write_config(tmp_path, write_roots=[allowed / "target"])

    code, data = run_json(
        cli,
        [
            "--allow-root",
            str(allowed),
            "--config",
            str(config),
            "write",
            "copy",
            str(source),
            str(other / "new.txt"),
            "--yes",
        ],
    )

    assert code == EXIT_ACCESS_DENIED
    assert data["errors"][0]["code"] == "ROOT_NOT_ALLOWED"
    assert not (other / "new.txt").exists()


def test_copy_inside_write_roots_succeeds(cli: Any, tmp_path: Path) -> None:
    allowed, target, _other, source = _layout(tmp_path)
    config = _write_config(tmp_path, write_roots=[target])

    code, data = run_json(
        cli,
        [
            "--allow-root",
            str(allowed),
            "--config",
            str(config),
            "write",
            "copy",
            str(source),
            str(target / "new.txt"),
            "--yes",
        ],
    )

    assert code == EXIT_SUCCESS
    assert data["success"] is True
    assert (target / "new.txt").exists()


def test_move_outside_write_roots_is_denied(cli: Any, tmp_path: Path) -> None:
    allowed, _target, other, source = _layout(tmp_path)
    config = _write_config(tmp_path, write_roots=[allowed / "target"])

    code, data = run_json(
        cli,
        [
            "--allow-root",
            str(allowed),
            "--config",
            str(config),
            "write",
            "move",
            str(source),
            str(other / "moved.txt"),
            "--yes",
        ],
    )

    assert code == EXIT_ACCESS_DENIED
    assert data["errors"][0]["code"] == "ORIGINAL_PROTECTED"
    assert source.exists()
    assert not (other / "moved.txt").exists()


def test_move_inside_write_roots_succeeds_without_flag(cli: Any, tmp_path: Path) -> None:
    allowed, target, _other, _source = _layout(tmp_path)
    inner = target / "a.txt"
    inner.write_text("inner", encoding="utf-8")
    config = _write_config(tmp_path, write_roots=[target])

    code, data = run_json(
        cli,
        [
            "--allow-root",
            str(allowed),
            "--config",
            str(config),
            "write",
            "move",
            str(inner),
            str(target / "b.txt"),
            "--allow-rename",
            "--yes",
        ],
    )

    assert code == EXIT_SUCCESS
    assert not inner.exists()
    assert (target / "b.txt").read_text(encoding="utf-8") == "inner"


def test_move_outside_write_roots_succeeds_with_flag(cli: Any, tmp_path: Path) -> None:
    allowed, target, _other, source = _layout(tmp_path)
    config = _write_config(
        tmp_path,
        write_roots=[target],
        allow_manipulate_originals=True,
    )

    code, data = run_json(
        cli,
        [
            "--allow-root",
            str(allowed),
            "--config",
            str(config),
            "write",
            "move",
            str(source),
            str(target / "moved.txt"),
            "--allow-rename",
            "--yes",
        ],
    )

    assert code == EXIT_SUCCESS
    assert not source.exists()
    assert (target / "moved.txt").read_text(encoding="utf-8") == "content"


def test_rmdir_outside_write_roots_is_denied(cli: Any, tmp_path: Path) -> None:
    allowed, _target, _other, _source = _layout(tmp_path)
    empty = allowed / "empty"
    empty.mkdir()
    config = _write_config(tmp_path, write_roots=[allowed / "target"])

    code, data = run_json(
        cli,
        [
            "--allow-root",
            str(allowed),
            "--config",
            str(config),
            "write",
            "rmdir",
            str(empty),
            "--yes",
        ],
    )

    assert code == EXIT_ACCESS_DENIED
    assert data["errors"][0]["code"] == "ORIGINAL_PROTECTED"
    assert empty.is_dir()


def test_apply_move_outside_write_roots_fails_preflight(cli: Any, tmp_path: Path) -> None:
    allowed, _target, other, source = _layout(tmp_path)
    config = _write_config(tmp_path, write_roots=[allowed / "target"])
    plan = tmp_path / "plan.json"
    plan.write_text(
        json.dumps(
            {
                "plan_version": 1,
                "operations": [
                    {
                        "op": "move",
                        "source": str(source),
                        "destination": str(other / "moved.txt"),
                        "allow_rename": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    code, data = run_json(
        cli,
        [
            "--allow-root",
            str(allowed),
            "--config",
            str(config),
            "write",
            "apply",
            str(plan),
            "--yes",
        ],
    )

    assert code == EXIT_FAILURE
    assert data["success"] is False
    operation = data["result"]["operations"][0]
    assert operation["status"] == "failed"
    assert operation["error"]["code"] == "ORIGINAL_PROTECTED"
    assert source.exists()


def test_apply_move_outside_write_roots_succeeds_with_flag(cli: Any, tmp_path: Path) -> None:
    allowed, target, _other, source = _layout(tmp_path)
    config = _write_config(
        tmp_path,
        write_roots=[target],
        allow_manipulate_originals=True,
    )
    plan = tmp_path / "plan.json"
    plan.write_text(
        json.dumps(
            {
                "plan_version": 1,
                "operations": [
                    {
                        "op": "move",
                        "source": str(source),
                        "destination": str(target / "moved.txt"),
                        "allow_rename": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    code, data = run_json(
        cli,
        [
            "--allow-root",
            str(allowed),
            "--config",
            str(config),
            "write",
            "apply",
            str(plan),
            "--yes",
        ],
    )

    assert code == EXIT_SUCCESS
    assert not source.exists()
    assert (target / "moved.txt").read_text(encoding="utf-8") == "content"


def test_mkdir_outside_write_roots_is_denied(cli: Any, tmp_path: Path) -> None:
    allowed, _target, other, _source = _layout(tmp_path)
    config = _write_config(tmp_path, write_roots=[allowed / "target"])

    code, data = run_json(
        cli,
        [
            "--allow-root",
            str(allowed),
            "--config",
            str(config),
            "write",
            "mkdir",
            str(other / "newdir"),
            "--yes",
        ],
    )

    assert code == EXIT_ACCESS_DENIED
    assert data["errors"][0]["code"] == "ROOT_NOT_ALLOWED"
    assert not (other / "newdir").exists()


def test_default_write_roots_equal_allowed_roots(cli: Any, tmp_path: Path) -> None:
    allowed, _target, other, source = _layout(tmp_path)

    code, data = run_json(
        cli,
        [
            "--allow-root",
            str(allowed),
            "write",
            "copy",
            str(source),
            str(other / "new.txt"),
            "--yes",
        ],
    )

    # Without a config, write roots default to allowed roots and copy is
    # non-destructive, so it remains allowed.
    assert code == EXIT_SUCCESS
    assert (other / "new.txt").exists()


def test_show_config_prints_resolved_values(
    cli: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = cli(["--show-config"])
    output = capsys.readouterr().out
    data = json.loads(output)

    assert code == EXIT_SUCCESS
    assert "config_path" in data
    assert "allowed_roots" in data
    assert "write_roots" in data
    assert data["allow_manipulate_originals"] is False
