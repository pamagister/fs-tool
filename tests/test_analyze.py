"""Tests for ``inspect analyze`` (plan.md Phase 2).

Verifies structured content analysis for Markdown, text and Python files,
PDF page structure, explicit capability statuses, source-file hashing and the
absence of complete document content from analysis results.
"""

from __future__ import annotations

import hashlib
import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from fs_tool.cli import EXIT_INCOMPLETE, EXIT_INVALID_ARGS, EXIT_SUCCESS, main
from fs_tool.core.capabilities.availability import AvailabilityChecker
from fs_tool.core.metadata import HAS_PYPDF

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE_FILES = PROJECT_ROOT / "res" / "example_filesystem_unstructured"


def analyze_json(source: Path, *extra: str) -> tuple[int, dict]:
    buffer = io.StringIO()
    argv = ["--allow-root", str(source.parent), "inspect", "analyze", str(source), *extra]
    with redirect_stdout(buffer):
        code = main(argv)
    return code, json.loads(buffer.getvalue())


def info_json(source: Path, *extra: str) -> tuple[int, dict]:
    buffer = io.StringIO()
    argv = ["--allow-root", str(source.parent), "inspect", "info", str(source), *extra]
    with redirect_stdout(buffer):
        code = main(argv)
    return code, json.loads(buffer.getvalue())


def test_analyze_markdown_structure(tmp_path: Path) -> None:
    source = tmp_path / "document.md"
    source.write_text(
        """\
# Title

Intro text.

## Section

```markdown
# Not a heading
```

### Details
""",
        encoding="utf-8",
    )

    code, data = analyze_json(source)
    assert code == EXIT_SUCCESS
    assert data["success"] is True
    assert data["command"] == "inspect.analyze"
    result = data["result"]
    assert result["supported"] is True
    assert result["extension"] == ".md"
    assert result["sha256"] is None
    assert len(result["analyses"]) == 1
    analysis = result["analyses"][0]
    assert analysis["capability"] == "markdown_structure"
    assert analysis["status"] == "available"
    assert analysis["help"] == "fs-tool capabilities"
    structure = analysis["data"]
    assert structure["heading_count"] == 3
    assert structure["max_heading_level"] == 3
    assert [heading["text"] for heading in structure["headings"]] == [
        "Title",
        "Section",
        "Details",
    ]
    assert structure["headings"][1]["line"] == 5
    assert "content" not in structure


def test_analyze_text_structure_without_content(tmp_path: Path) -> None:
    source = tmp_path / "notes.txt"
    source.write_text("hello world\n\nsecond paragraph\n", encoding="utf-8")

    code, data = analyze_json(source)
    assert code == EXIT_SUCCESS
    analysis = data["result"]["analyses"][0]
    assert analysis["capability"] == "text_structure"
    assert analysis["status"] == "available"
    structure = analysis["data"]
    assert structure["encoding"] == "utf-8"
    assert structure["line_count"] == 3
    assert structure["non_empty_line_count"] == 2
    assert structure["word_count"] == 4
    assert structure["paragraph_count"] == 2
    assert structure["character_count"] == len("hello world\n\nsecond paragraph\n")
    assert structure["max_line_length"] == len("second paragraph")
    assert "content" not in structure
    assert "hello world" not in json.dumps(structure)


def test_analyze_unsupported_format_is_not_unavailable(tmp_path: Path) -> None:
    source = tmp_path / "archive.bin"
    source.write_bytes(b"\x00\x01\x02")

    code, data = analyze_json(source)
    assert code == EXIT_SUCCESS
    result = data["result"]
    assert result["supported"] is False
    assert result["analyses"] == []
    assert data["errors"] == []


def test_analyze_invalid_pdf_reports_failure(tmp_path: Path) -> None:
    if not HAS_PYPDF:
        pytest.skip("pypdf not installed")
    source = tmp_path / "broken.pdf"
    source.write_bytes(b"%PDF-1.4\nnot a real document\n")

    code, data = analyze_json(source)
    assert code == EXIT_SUCCESS
    analysis = data["result"]["analyses"][0]
    assert analysis["capability"] == "pdf_pages"
    assert analysis["status"] == "failed"
    assert analysis["error_code"] == "CAPABILITY_FAILED"
    assert analysis["data"] is None


@pytest.mark.skipif(not HAS_PYPDF, reason="pypdf not installed")
def test_analyze_pdf_page_structure() -> None:
    source = EXAMPLE_FILES / "Der Goldschatz partygame.pdf"
    assert source.is_file(), f"test fixture missing: {source}"

    code, data = analyze_json(source)
    assert code == EXIT_SUCCESS
    analysis = data["result"]["analyses"][0]
    assert analysis["capability"] == "pdf_pages"
    assert analysis["status"] == "available"
    structure = analysis["data"]
    assert structure["page_count"] >= 1
    assert len(structure["pages"]) == structure["page_count"]
    page = structure["pages"][0]
    assert page["index"] == 1
    assert page["width"] > 0
    assert page["height"] > 0
    assert page["orientation"] in {"portrait", "landscape", "square"}
    assert isinstance(page["rotation"], int)
    assert "text" not in structure


def test_analyze_reports_unavailable_capability_explicitly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = EXAMPLE_FILES / "Der Goldschatz partygame.pdf"
    assert source.is_file(), f"test fixture missing: {source}"

    original = AvailabilityChecker.python_package_available

    def fake_available(name: str) -> bool:
        if name == "pypdf":
            return False
        return original(name)

    monkeypatch.setattr(
        AvailabilityChecker, "python_package_available", staticmethod(fake_available)
    )

    code, data = analyze_json(source)
    assert code == EXIT_SUCCESS
    assert data["success"] is True
    analysis = data["result"]["analyses"][0]
    assert analysis["status"] == "unavailable"
    assert analysis["error_code"] is None
    assert analysis["help"] == "fs-tool capabilities"
    assert analysis["data"] is None


def test_analyze_hash_matches_info_hash(tmp_path: Path) -> None:
    source = tmp_path / "notes.txt"
    content = b"hash me\n"
    source.write_bytes(content)
    expected = hashlib.sha256(content).hexdigest()

    info_code, info_data = info_json(source, "--hash")
    analyze_code, analyze_data = analyze_json(source, "--hash")
    assert info_code == analyze_code == EXIT_SUCCESS
    assert info_data["result"]["sha256"] == expected
    assert analyze_data["result"]["sha256"] == expected


def test_analyze_hash_failure_is_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "notes.txt"
    source.write_text("hello\n", encoding="utf-8")
    monkeypatch.setattr("fs_tool.cli.sha256_of_file", lambda path: None)

    code, data = analyze_json(source, "--hash")
    assert code == EXIT_INCOMPLETE
    assert data["success"] is False
    assert data["complete"] is False
    assert data["errors"][0]["code"] == "INCOMPLETE_SCAN"
    assert data["result"]["sha256"] is None


def test_analyze_rejects_symlink(tmp_path: Path) -> None:
    target = tmp_path / "target.txt"
    target.write_text("hello\n", encoding="utf-8")
    link = tmp_path / "link.txt"
    link.symlink_to(target)

    code, data = analyze_json(link)
    assert code == EXIT_INVALID_ARGS
    assert data["success"] is False
    assert data["errors"][0]["code"] == "INVALID_ARGUMENT"


def test_analyze_rejects_directory(tmp_path: Path) -> None:
    directory = tmp_path / "folder"
    directory.mkdir()

    code, data = analyze_json(directory)
    assert code == EXIT_INVALID_ARGS
    assert data["success"] is False
    assert data["errors"][0]["code"] == "INVALID_ARGUMENT"


def test_analyze_plain_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = tmp_path / "document.md"
    source.write_text("# Title\n\nBody.\n", encoding="utf-8")

    code = main(["--allow-root", str(tmp_path), "--plain", "inspect", "analyze", str(source)])
    assert code == EXIT_SUCCESS
    output = capsys.readouterr().out
    assert f"analyze: {source}" in output
    assert "supported: true" in output
    assert "markdown_structure [available]" in output
    assert "# Title (line 1)" in output
