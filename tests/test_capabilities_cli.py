"""Tests for capability reporting and the ``fs-tool capabilities`` command."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from fs_tool.core.capabilities.models import (
    Capability,
    CapabilityId,
    CapabilityStatus,
    ExternalResourceRequirement,
    PythonPackageRequirement,
    Requirement,
)
from fs_tool.core.capabilities.registry import CapabilityEntry
from fs_tool.core.capabilities.report import (
    capabilities_report,
    capability_entry_to_dict,
    install_command,
)


def _entry(capability: Capability, requirements: tuple[Requirement, ...] = ()) -> CapabilityEntry:
    status = (
        CapabilityStatus.AVAILABLE
        if all(requirement.available for requirement in requirements)
        else CapabilityStatus.UNAVAILABLE
    )
    return CapabilityEntry(capability=capability, status=status, requirements=requirements)


def _pdf_capability() -> Capability:
    return Capability(
        id=CapabilityId.PDF_METADATA,
        label="PDF metadata",
        description="Extract PDF metadata.",
        provider="pdf",
        requirements=(PythonPackageRequirement(name="pypdf", extra="metadata"),),
    )


def test_install_command_uses_package_extras() -> None:
    assert install_command("metadata") == 'pip install "fs-tool-cli[metadata]"'
    assert install_command("image") == 'pip install "fs-tool-cli[image]"'
    assert install_command(None) == 'pip install "fs-tool-cli"'


def test_available_capability_reports_no_missing_requirements() -> None:
    capability = _pdf_capability()
    entry = _entry(
        capability,
        (PythonPackageRequirement(name="pypdf", extra="metadata", available=True),),
    )

    data = capability_entry_to_dict(entry)

    assert data["id"] == "pdf_metadata"
    assert data["available"] is True
    assert data["status"] == "available"
    assert data["missing_requirements"] == []
    assert data["next_steps"] == []
    assert data["setup"] is None
    assert data["requirements"][0]["install_command"] == 'pip install "fs-tool-cli[metadata]"'


def test_missing_python_dependency_has_install_command() -> None:
    entry = _entry(
        _pdf_capability(),
        (PythonPackageRequirement(name="pypdf", extra="metadata", available=False),),
    )

    data = capability_entry_to_dict(entry)

    assert data["available"] is False
    assert [item["name"] for item in data["missing_requirements"]] == ["pypdf"]
    assert data["next_steps"] == ['pip install "fs-tool-cli[metadata]"']


def test_missing_model_reports_path_and_setup_command(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("FS_TOOL_MODEL_DIR", str(tmp_path))
    model_path = tmp_path / "yolo26n.onnx"
    capability = Capability(
        id=CapabilityId.IMAGE_OBJECT_DETECTION,
        label="Image object detection",
        description="Detect objects.",
        provider="image",
        requirements=(
            PythonPackageRequirement(name="onnxruntime", extra="image", available=True),
            ExternalResourceRequirement(
                name="yolo26n.onnx",
                expected_path=str(model_path),
                available=False,
            ),
        ),
        setup_command="fs-tool setup yolo",
    )

    data = capability_entry_to_dict(_entry(capability, capability.requirements))

    assert data["missing_requirements"] == [
        {
            "kind": "external_resource",
            "name": "yolo26n.onnx",
            "expected_path": str(model_path),
            "available": False,
        }
    ]
    assert data["next_steps"] == ["fs-tool setup yolo"]
    assert data["setup"] == {"command": "fs-tool setup yolo"}


def test_capabilities_report_is_deterministic_and_includes_model_directory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("FS_TOOL_MODEL_DIR", str(tmp_path))
    capability = _pdf_capability()
    entries = (
        _entry(
            capability,
            (PythonPackageRequirement(name="pypdf", extra="metadata", available=True),),
        ),
    )

    report = capabilities_report(entries)

    assert report["count"] == 1
    assert report["available_count"] == 1
    assert report["model_directory"] == str(tmp_path)
    assert [item["id"] for item in report["capabilities"]] == ["pdf_metadata"]


def test_capabilities_command_json(cli: Any, capsys: Any) -> None:
    capability = _pdf_capability()
    entry = _entry(
        capability,
        (PythonPackageRequirement(name="pypdf", extra="metadata", available=True),),
    )

    import fs_tool.core.capabilities.report as report_module

    original = report_module.available_entries
    report_module.available_entries = lambda: (entry,)
    try:
        code = cli(["--json", "capabilities"])
    finally:
        report_module.available_entries = original

    assert code == 0
    envelope = json.loads(capsys.readouterr().out)
    assert envelope["success"] is True
    assert envelope["command"] == "capabilities"
    assert envelope["complete"] is True
    assert envelope["result"]["count"] == 1
    assert envelope["result"]["capabilities"][0]["id"] == "pdf_metadata"


def test_capabilities_command_plain(cli: Any, capsys: Any) -> None:
    capability = _pdf_capability()
    entry = _entry(
        capability,
        (PythonPackageRequirement(name="pypdf", extra="metadata", available=False),),
    )

    import fs_tool.core.capabilities.report as report_module

    original = report_module.available_entries
    report_module.available_entries = lambda: (entry,)
    try:
        code = cli(["--plain", "capabilities"])
    finally:
        report_module.available_entries = original

    assert code == 0
    output = capsys.readouterr().out
    assert "capabilities: 1 total, 0 available" in output
    assert "pdf_metadata [unavailable] PDF metadata" in output
    assert "missing: pypdf (import pypdf)" in output
    assert 'next: pip install "fs-tool-cli[metadata]"' in output
    assert "model directory:" in output


def test_capabilities_help(cli: Any, capsys: Any) -> None:
    assert cli(["capabilities", "--help"]) == 0
    output = capsys.readouterr().out
    assert "capabilities" in output
    assert "availability" in output
