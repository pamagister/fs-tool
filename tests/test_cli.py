"""Smoke tests for the fs-tool CLI (plan.md phase 0, task P0-T11)."""

from __future__ import annotations

from typing import Any

import pytest

from fs_tool.cli import __version__


def test_version(cli: Any, capsys: Any) -> None:
    """``fs-tool --version`` prints the version and exits 0."""
    code = cli(["--version"])
    assert code == 0
    output = capsys.readouterr().out
    assert "fs-tool" in output
    assert __version__ in output


def test_help(cli: Any) -> None:
    """``fs-tool --help`` shows the command hierarchy and exits 0."""
    assert cli(["--help"]) == 0


def test_help_lists_commands(cli: Any, capsys: Any) -> None:
    """The commands from plan.md section 4.1 appear in help output."""
    cli(["--help"])
    output = capsys.readouterr().out
    for command in ("inspect", "find", "duplicates", "compare", "verify", "write"):
        assert command in output


def test_no_arguments_shows_help(cli: Any) -> None:
    """``fs-tool`` with no arguments shows help and exits 0."""
    assert cli([]) == 0


def test_unknown_command(cli: Any) -> None:
    """An unknown subcommand is a usage error: exit 2."""
    assert cli(["does-not-exist"]) == 2


def test_unknown_command_shows_diagnostic(cli: Any, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli(["does-not-exist"]) == 2
    assert "No such command" in capsys.readouterr().err


def test_global_option_after_command(
    cli: Any, tmp_path: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "note.txt").write_text("hello")
    assert cli(["--allow-root", str(tmp_path), "inspect", "tree", str(tmp_path), "--plain"]) == 0
    output = capsys.readouterr().out
    assert "note.txt" in output


def test_allow_root_after_command(cli: Any, tmp_path: Any) -> None:
    (tmp_path / "note.txt").write_text("hello")
    assert cli(["inspect", "info", str(tmp_path / "note.txt"), "--allow-root", str(tmp_path)]) == 0


def test_json_and_plain_are_mutually_exclusive(cli: Any) -> None:
    """``--json`` and ``--plain`` cannot be combined: exit 2."""
    assert cli(["--json", "--plain"]) == 2


def test_invalid_format(cli: Any) -> None:
    """An unknown --format value is rejected: exit 2."""
    assert cli(["--format", "yaml"]) == 2


def test_allow_root_is_repeatable(cli: Any) -> None:
    """``--allow-root`` can be repeated without error."""
    assert cli(["--allow-root", "/mnt/nas", "--allow-root", "/data", "--version"]) == 0


@pytest.mark.parametrize("command", ["inspect", "find", "duplicates", "compare", "verify", "write"])
def test_command_group_help(cli: Any, command: str, capsys: Any) -> None:
    """Each command group shows its help and exits 0 (no subcommands yet in Phase 0)."""
    assert cli([command, "--help"]) == 0
    output = capsys.readouterr().out
    assert command in output


@pytest.mark.parametrize("command", ["inspect", "verify", "write"])
def test_command_group_bare_shows_help(cli: Any, command: str, capsys: Any) -> None:
    """A command group with no subcommand shows its help: exit 0."""
    assert cli([command]) == 0
    output = capsys.readouterr().out
    assert command in output


@pytest.mark.parametrize("command", ["find", "duplicates", "compare"])
def test_direct_command_requires_argument(cli: Any, command: str) -> None:
    """Direct analysis commands require their path arguments: exit 2."""
    assert cli([command]) == 2
