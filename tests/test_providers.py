"""Tests for metadata and analysis providers (plan.md Phase 2).

Covers provider selection, format metadata extraction, structured analysis
orchestration, explicit availability states and provider failure isolation.
"""

from __future__ import annotations

import zipfile
from dataclasses import replace
from pathlib import Path

import pytest

from fs_tool.core.analysis.python_analysis import analyze_python_file, module_to_dict
from fs_tool.core.capabilities.models import (
    Capability,
    CapabilityId,
    CapabilityStatus,
    PythonPackageRequirement,
)
from fs_tool.core.capabilities.registry import default_registry
from fs_tool.core.errors import ErrorCode, FsToolError
from fs_tool.core.providers.base import Provider
from fs_tool.core.providers.inspection import analyze_file, inspect_metadata
from fs_tool.core.providers.registry import ProviderRegistry, default_provider_registry

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXAMPLE_FILES = PROJECT_ROOT / "res" / "example_filesystem_unstructured"


def test_default_provider_registry_is_deterministic() -> None:
    providers = default_provider_registry()
    assert [provider.id for provider in providers.all()] == [
        "markdown",
        "odf",
        "ooxml",
        "pdf",
        "python",
        "text",
    ]
    assert [provider.id for provider in providers.for_path(Path("notes.md"))] == ["markdown"]
    assert [provider.id for provider in providers.for_path(Path("notes.ODT"))] == ["odf"]
    assert [provider.id for provider in providers.for_path(Path("archive.unknown"))] == []


def test_provider_capabilities_come_from_the_central_registry() -> None:
    central = default_registry()
    for provider in default_provider_registry().all():
        for capability in provider.capabilities:
            assert capability.provider == provider.id
            assert central.get(capability.id) is not None


def test_python_provider_reuses_existing_ast_analysis(tmp_path: Path) -> None:
    source = tmp_path / "module.py"
    source.write_text(
        """\
import os


def greet(name: str) -> str:
    return f"Hello, {name}"
""",
        encoding="utf-8",
    )
    expected_module = analyze_python_file(source)
    assert expected_module is not None

    report = analyze_file(source)
    assert report.supported is True
    assert len(report.results) == 1
    result = report.results[0]
    assert result.capability is CapabilityId.PYTHON_AST
    assert result.status is CapabilityStatus.AVAILABLE
    assert result.data == module_to_dict(expected_module)


def test_analyze_unsupported_format_has_no_results(tmp_path: Path) -> None:
    source = tmp_path / "archive.bin"
    source.write_bytes(b"\x00\x01\x02")

    report = analyze_file(source)
    assert report.supported is False
    assert report.results == ()


def test_analyze_skips_symlinks(tmp_path: Path) -> None:
    target = tmp_path / "target.py"
    target.write_text("x = 1\n", encoding="utf-8")
    link = tmp_path / "link.py"
    link.symlink_to(target)

    report = analyze_file(link)
    assert report.supported is False
    assert report.results == ()


def test_analyze_one_failure_does_not_stop_other_providers(tmp_path: Path) -> None:
    source = tmp_path / "source.custom"
    source.write_text("content\n", encoding="utf-8")

    class FailingProvider(Provider):
        @property
        def id(self) -> str:
            return "a-failing"

        @property
        def capabilities(self) -> tuple[Capability, ...]:
            return ()

        def supported_extensions(self) -> tuple[str, ...]:
            return (".custom",)

        def analysis_capabilities(self) -> tuple[CapabilityId, ...]:
            return (CapabilityId.PYTHON_AST,)

        def analyze(self, capability: CapabilityId, path: Path) -> dict[str, object]:
            raise FsToolError("Deliberate failure.", code=ErrorCode.CAPABILITY_FAILED)

    class WorkingProvider(Provider):
        @property
        def id(self) -> str:
            return "b-working"

        @property
        def capabilities(self) -> tuple[Capability, ...]:
            return ()

        def supported_extensions(self) -> tuple[str, ...]:
            return (".custom",)

        def analysis_capabilities(self) -> tuple[CapabilityId, ...]:
            return (CapabilityId.TEXT_STRUCTURE,)

        def analyze(self, capability: CapabilityId, path: Path) -> dict[str, object]:
            return {"value": 42}

    providers = ProviderRegistry()
    providers.register(FailingProvider())
    providers.register(WorkingProvider())

    report = analyze_file(source, providers=providers)
    assert [result.capability for result in report.results] == [
        CapabilityId.PYTHON_AST,
        CapabilityId.TEXT_STRUCTURE,
    ]
    failed, available = report.results
    assert failed.status is CapabilityStatus.FAILED
    assert failed.error_code == ErrorCode.CAPABILITY_FAILED.value
    assert available.status is CapabilityStatus.AVAILABLE
    assert available.data == {"value": 42}


def test_analyze_unavailable_capability_is_explicit(tmp_path: Path) -> None:
    source = tmp_path / "source.py"
    source.write_text("x = 1\n", encoding="utf-8")
    registry = default_registry()
    capability = registry.get(CapabilityId.PYTHON_AST)
    assert capability is not None
    registry.register(
        replace(
            capability,
            requirements=(PythonPackageRequirement(name="package-that-is-not-installed"),),
        )
    )

    report = analyze_file(source, registry=registry)
    assert len(report.results) == 1
    result = report.results[0]
    assert result.status is CapabilityStatus.UNAVAILABLE
    assert result.message.endswith("is not available.")
    assert result.help == "fs-tool capabilities"


def test_metadata_unsupported_format_has_no_result(tmp_path: Path) -> None:
    source = tmp_path / "notes.txt"
    source.write_text("hello\n", encoding="utf-8")

    inspection = inspect_metadata(source)
    assert inspection.metadata is None
    assert inspection.result is None


def test_metadata_extracts_odf_data() -> None:
    source = EXAMPLE_FILES / "Reise-Checkliste.odt"
    assert source.is_file(), f"test fixture missing: {source}"

    inspection = inspect_metadata(source)
    assert inspection.metadata is not None
    assert inspection.metadata["author"] == "Paul L."
    assert inspection.result is not None
    assert inspection.result.capability is CapabilityId.ODF_METADATA
    assert inspection.result.status is CapabilityStatus.AVAILABLE
    assert inspection.result.data == inspection.metadata


def test_metadata_unavailable_capability_is_explicit(tmp_path: Path) -> None:
    source = tmp_path / "document.pdf"
    source.write_bytes(b"%PDF-1.4\n")
    registry = default_registry()
    capability = registry.get(CapabilityId.PDF_METADATA)
    assert capability is not None
    registry.register(
        replace(
            capability,
            requirements=(PythonPackageRequirement(name="package-that-is-not-installed"),),
        )
    )

    inspection = inspect_metadata(source, registry=registry)
    assert inspection.metadata is None
    assert inspection.result is not None
    assert inspection.result.status is CapabilityStatus.UNAVAILABLE
    assert inspection.result.capability is CapabilityId.PDF_METADATA


def test_metadata_failure_is_structured(tmp_path: Path) -> None:
    source = tmp_path / "broken.odt"
    source.write_bytes(b"not a zip archive")

    inspection = inspect_metadata(source)
    assert inspection.metadata is None
    assert inspection.result is not None
    assert inspection.result.status is CapabilityStatus.FAILED
    assert inspection.result.error_code == ErrorCode.CAPABILITY_FAILED.value


def test_metadata_size_limit_is_enforced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "document.odt"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("meta.xml", "<meta/>")
    monkeypatch.setattr("fs_tool.core.providers.inspection.MAX_METADATA_SIZE", 0)

    inspection = inspect_metadata(source)
    assert inspection.result is not None
    assert inspection.result.status is CapabilityStatus.FAILED
    assert "size limit" in inspection.result.message
