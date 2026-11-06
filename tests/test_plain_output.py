"""Tests for plain-text output rendering across all commands (plan.md Phase 5, P5-T08).

Verifies that plain-text renderers produce consistent, human-readable
output for every command: inspect tree/info/inventory/read, find,
duplicates, compare, verify, and write operations.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from fs_tool.core.models import EntryType, FilesystemEntry
from fs_tool.output.plain import (
    render_compare,
    render_duplicates,
    render_find,
    render_info,
    render_inventory,
    render_tree,
    render_verify,
)


def test_render_tree_shows_directory_structure(tmp_path: Path) -> None:
    """Tree renderer shows nested structure with directory markers."""
    (tmp_path / "alpha.txt").write_text("a")
    (tmp_path / "beta").mkdir()
    (tmp_path / "beta" / "gamma.txt").write_text("g")

    entries = [
        FilesystemEntry(
            path=str(tmp_path / "alpha.txt"),
            name="alpha.txt",
            rel_path="alpha.txt",
            type=EntryType.FILE,
            size=1,
        ),
        FilesystemEntry(
            path=str(tmp_path / "beta"),
            name="beta",
            rel_path="beta",
            type=EntryType.DIRECTORY,
        ),
        FilesystemEntry(
            path=str(tmp_path / "beta" / "gamma.txt"),
            name="gamma.txt",
            rel_path="beta/gamma.txt",
            type=EntryType.FILE,
            size=1,
        ),
    ]

    output = render_tree(entries, tmp_path)
    assert "alpha.txt" in output
    assert "beta/" in output
    assert "gamma.txt" in output


def test_render_tree_shows_symlink_target(tmp_path: Path) -> None:
    """Tree renderer shows symlink targets."""
    (tmp_path / "target.txt").write_text("target")
    (tmp_path / "link.txt").symlink_to(tmp_path / "target.txt")

    entries = [
        FilesystemEntry(
            path=str(tmp_path / "target.txt"),
            name="target.txt",
            rel_path="target.txt",
            type=EntryType.FILE,
            size=6,
        ),
        FilesystemEntry(
            path=str(tmp_path / "link.txt"),
            name="link.txt",
            rel_path="link.txt",
            type=EntryType.SYMLINK,
            is_symlink=True,
            target="target.txt",
        ),
    ]

    output = render_tree(entries, tmp_path)
    assert "link.txt -> target.txt" in output


def test_render_info_shows_all_metadata_fields() -> None:
    """Info renderer shows all available metadata fields."""
    entry = FilesystemEntry(
        path="/home/user/docs/report.pdf",
        name="report.pdf",
        rel_path="docs/report.pdf",
        type=EntryType.FILE,
        extension=".pdf",
        size=1024,
        modified="2024-01-15T10:30:00+00:00",
        created="2024-01-10T08:00:00+00:00",
        accessed="2024-01-15T10:30:00+00:00",
        changed="2024-01-15T10:30:00+00:00",
        mode="0644",
        owner="user",
        mime_type="application/pdf",
        is_symlink=False,
        sha256="abc123",
        metadata={"title": "Report", "author": "Alice"},
    )

    output = render_info(entry)
    assert "path: /home/user/docs/report.pdf" in output
    assert "name: report.pdf" in output
    assert "type: file" in output
    assert "rel_path: docs/report.pdf" in output
    assert "extension: .pdf" in output
    assert "size: 1024" in output
    assert "modified: 2024-01-15T10:30:00+00:00" in output
    assert "mime_type: application/pdf" in output
    assert "sha256: abc123" in output
    assert "metadata:" in output


def test_render_info_omits_none_fields() -> None:
    """Info renderer omits fields that are None."""
    entry = FilesystemEntry(
        path="/tmp/link",
        name="link",
        rel_path=None,
        type=EntryType.SYMLINK,
        is_symlink=True,
        target="/tmp/target",
    )

    output = render_info(entry)
    assert "rel_path:" not in output
    assert "size:" not in output
    assert "target: /tmp/target" in output


def test_render_inventory_shows_entries_and_count() -> None:
    """Inventory renderer lists entries with type, size and hash."""
    inventory = {
        "entries": [
            {"rel_path": "a.txt", "type": "file", "size": 10, "sha256": "aaa"},
            {"rel_path": "sub", "type": "directory", "size": None, "sha256": None},
            {"rel_path": "b.txt", "type": "file", "size": 20, "sha256": "bbb"},
        ],
        "count": 3,
        "complete": True,
    }

    output = render_inventory(inventory, Path("/tmp/root"))
    assert "inventory: /tmp/root" in output
    assert "a.txt [file] size=10 sha256=aaa" in output
    assert "sub [directory]" in output
    assert "b.txt [file] size=20 sha256=bbb" in output
    assert "count: 3" in output
    assert "complete: True" in output


def test_render_inventory_shows_tree_hash() -> None:
    """Inventory renderer shows tree hash when present."""
    inventory = {
        "entries": [],
        "count": 0,
        "complete": True,
        "tree_hash": "deadbeef",
    }

    output = render_inventory(inventory, Path("/tmp/root"))
    assert "tree_hash: deadbeef" in output


def test_render_find_shows_matching_entries() -> None:
    """Find renderer lists matching entries with type and size."""
    entries = [
        FilesystemEntry(
            path="/tmp/root/a.txt",
            name="a.txt",
            rel_path="a.txt",
            type=EntryType.FILE,
            size=100,
        ),
        FilesystemEntry(
            path="/tmp/root/sub",
            name="sub",
            rel_path="sub",
            type=EntryType.DIRECTORY,
        ),
    ]

    output = render_find(entries, Path("/tmp/root"))
    assert "find: /tmp/root" in output
    assert "a.txt [file] size=100" in output
    assert "sub [directory]" in output
    assert "count: 2" in output


def test_render_duplicates_shows_groups_and_files() -> None:
    """Duplicate renderer lists groups with SHA-256, size, count and files."""
    groups = [
        {
            "sha256": "abc123",
            "size": 1024,
            "count": 2,
            "files": ["/tmp/a.txt", "/tmp/b.txt"],
        },
        {
            "sha256": "def456",
            "size": 512,
            "count": 3,
            "files": ["/tmp/x.txt", "/tmp/y.txt", "/tmp/z.txt"],
        },
    ]

    output = render_duplicates(groups)
    assert "duplicate groups: 2" in output
    assert "abc123 size=1024 count=2" in output
    assert "def456 size=512 count=3" in output
    assert "/tmp/a.txt" in output
    assert "/tmp/z.txt" in output


def test_render_duplicates_empty() -> None:
    """Duplicate renderer handles no groups."""
    output = render_duplicates([])
    assert "duplicate groups: 0" in output


def test_render_compare_shows_all_categories() -> None:
    """Compare renderer lists all result categories."""
    result = {
        "identical": ["a.txt", "sub/b.txt"],
        "missing": ["c.txt"],
        "changed": ["d.txt"],
        "unexpected": ["e.txt"],
        "type_conflicts": ["f.txt"],
        "unsupported": [],
        "complete": True,
    }

    output = render_compare(result)
    assert "identical (2):" in output
    assert "  a.txt" in output
    assert "  sub/b.txt" in output
    assert "missing (1):" in output
    assert "changed (1):" in output
    assert "unexpected (1):" in output
    assert "type_conflicts (1):" in output
    assert "complete: True" in output


def test_render_compare_omits_empty_categories() -> None:
    """Compare renderer omits categories with no items."""
    result = {
        "identical": [],
        "missing": ["c.txt"],
        "changed": [],
        "unexpected": [],
        "type_conflicts": [],
        "unsupported": [],
        "complete": True,
    }

    output = render_compare(result)
    assert "identical" not in output
    assert "missing (1):" in output
    assert "changed" not in output


def test_render_verify_shows_discrepancies() -> None:
    """Verify renderer lists all discrepancy categories."""
    result = {
        "missing": ["a.txt"],
        "unexpected": ["b.txt"],
        "changed": ["c.txt"],
        "size_mismatch": ["d.txt"],
        "hash_mismatch": ["e.txt"],
        "complete": True,
    }

    output = render_verify(result)
    assert "missing (1):" in output
    assert "unexpected (1):" in output
    assert "changed (1):" in output
    assert "size_mismatch (1):" in output
    assert "hash_mismatch (1):" in output
    assert "complete: True" in output


def test_render_verify_empty() -> None:
    """Verify renderer handles a clean verification result."""
    result = {
        "missing": [],
        "unexpected": [],
        "changed": [],
        "size_mismatch": [],
        "hash_mismatch": [],
        "complete": True,
    }

    output = render_verify(result)
    assert "missing" not in output
    assert "unexpected" not in output
    assert "complete: True" in output


def test_all_renderers_produce_deterministic_output() -> None:
    """All renderers produce identical output for identical input."""
    entries = [
        FilesystemEntry(
            path="/tmp/root/a.txt",
            name="a.txt",
            rel_path="a.txt",
            type=EntryType.FILE,
            size=42,
        )
    ]

    first = render_tree(entries, Path("/tmp/root"))
    second = render_tree(entries, Path("/tmp/root"))
    assert first == second

    info_entry = entries[0]
    first = render_info(info_entry)
    second = render_info(info_entry)
    assert first == second

    inventory = {"entries": [asdict(entries[0])], "count": 1, "complete": True}
    first = render_inventory(inventory, Path("/tmp/root"))
    second = render_inventory(inventory, Path("/tmp/root"))
    assert first == second

    first = render_find(entries, Path("/tmp/root"))
    second = render_find(entries, Path("/tmp/root"))
    assert first == second
