"""Tests for the capability registry and availability mechanism (plan.md Phase 1).

Covers P1-W03 through P1-W07: capability identifiers and models, the central
registry, requirements, availability checks, and result models.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from fs_tool.core.capabilities.availability import AvailabilityChecker
from fs_tool.core.capabilities.models import (
    Capability,
    CapabilityId,
    CapabilityResult,
    CapabilityStatus,
    ExternalResourceRequirement,
    PythonPackageRequirement,
    resolve_model_dir,
)
from fs_tool.core.capabilities.registry import (
    CapabilityRegistry,
    available_entries,
    default_registry,
)
from fs_tool.core.errors import EXIT_CODES, ErrorCode
from fs_tool.core.providers.base import Provider
from fs_tool.core.providers.registry import ProviderRegistry


class _StubProvider(Provider):
    """Test provider with multiple independent capabilities."""

    def __init__(self, provider_id: str, capabilities):
        self._id = provider_id
        self._capabilities = tuple(capabilities)

    @property
    def id(self) -> str:
        return self._id

    @property
    def capabilities(self):
        return self._capabilities

    def supported_extensions(self):
        return (".txt",)


def test_registry_holds_capabilities_centrally() -> None:
    registry = default_registry()
    ids = sorted(cap.id.value for cap in registry.all())
    assert ids == [
        "image_metadata",
        "image_object_detection",
        "markdown_structure",
        "odf_metadata",
        "ooxml_metadata",
        "pdf_metadata",
        "pdf_pages",
        "pdf_text",
        "python_ast",
        "text_structure",
    ]


def test_capability_identifiers_are_stable_strings() -> None:
    assert CapabilityId.PDF_METADATA == "pdf_metadata"
    assert CapabilityId.IMAGE_OBJECT_DETECTION == "image_object_detection"
    assert CapabilityId.PYTHON_AST == "python_ast"


def test_provider_may_declare_multiple_capabilities() -> None:
    cap_a = Capability(
        id=CapabilityId.IMAGE_METADATA,
        label="Image metadata",
        description="Extract image metadata.",
        provider="image",
    )
    cap_b = Capability(
        id=CapabilityId.IMAGE_OBJECT_DETECTION,
        label="Image object detection",
        description="Detect objects.",
        provider="image",
    )
    provider = _StubProvider("image", (cap_a, cap_b))
    assert provider.capabilities == (cap_a, cap_b)
    assert [c.id for c in provider.capabilities] == [
        CapabilityId.IMAGE_METADATA,
        CapabilityId.IMAGE_OBJECT_DETECTION,
    ]


def test_registry_register_get_and_all_are_deterministic() -> None:
    registry = CapabilityRegistry()
    registry.register(
        Capability(id=CapabilityId.TEXT_STRUCTURE, label="Text", description="t", provider="text")
    )
    registry.register(
        Capability(id=CapabilityId.PYTHON_AST, label="Python", description="p", provider="python")
    )
    assert registry.contains(CapabilityId.PYTHON_AST) is True
    assert registry.contains("nonexistent") is False
    assert registry.get("nonexistent") is None
    ids = [cap.id.value for cap in registry.all()]
    assert ids == ["python_ast", "text_structure"]


def test_default_registry_assigns_requirements(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("FS_TOOL_MODEL_DIR", str(tmp_path))
    registry = default_registry()
    yolo = registry.get(CapabilityId.IMAGE_OBJECT_DETECTION)
    assert yolo is not None
    kinds = {req.__class__.__name__ for req in yolo.requirements}
    assert "PythonPackageRequirement" in kinds
    assert "ExternalResourceRequirement" in kinds
    models = [req for req in yolo.requirements if isinstance(req, ExternalResourceRequirement)]
    assert len(models) == 1
    assert models[0].name == "yolo26n.onnx"
    assert models[0].expected_path == str(tmp_path / "yolo26n.onnx")
    assert yolo.setup_command == "fs-tool setup yolo"


def test_python_package_availability_without_side_effects() -> None:
    checker = AvailabilityChecker()
    # standard package should be available. Self-test of checker
    assert checker.python_package_available("json") is True
    # pypdf is installed in this environment.
    assert checker.python_package_available("pypdf") is True
    # The check reflects the environment without importing the package.
    assert checker.python_package_available("onnxruntime") is (
        importlib.util.find_spec("onnxruntime") is not None
    )
    assert checker.python_package_available("does-not-exist-package") is False


def test_requirement_uses_import_name_when_it_differs() -> None:
    checker = AvailabilityChecker()
    requirement = PythonPackageRequirement(name="Pillow", extra="image", import_name="PIL")

    checked = checker.check_requirement(requirement)

    assert checked.import_name == "PIL"
    assert checked.available is (importlib.util.find_spec("PIL") is not None)
    assert checked.available is True


def test_availability_check_does_not_execute_file_analysis(tmp_path: Path) -> None:
    # The checker is stateless and path-free: it never reads or analyzes files.
    source = tmp_path / "source.py"
    source.write_text("print('hello')\n")
    checker = AvailabilityChecker()
    cap = Capability(
        id=CapabilityId.PYTHON_AST,
        label="Python AST",
        description="Python analysis.",
        provider="python",
    )
    assert checker.check_capability(cap) is CapabilityStatus.AVAILABLE
    # No file was required to exist or to be parsed.
    assert source.read_text() == "print('hello')\n"


def test_external_resource_availability(tmp_path: Path) -> None:
    checker = AvailabilityChecker()
    missing = checker.external_resource_available(
        "~/.local/share/fs-tool/models/does-not-exist.onnx"
    )
    assert missing is False

    present = tmp_path / "a-model.onnx"
    present.write_text("not-a-real-model", encoding="utf-8")
    assert checker.external_resource_available(str(present)) is True


def test_capability_status_unavailable_when_prerequisite_missing(tmp_path: Path) -> None:
    checker = AvailabilityChecker()
    cap = Capability(
        id=CapabilityId.IMAGE_OBJECT_DETECTION,
        label="YOLO",
        description="Object detection.",
        provider="image",
        requirements=(
            PythonPackageRequirement(name="onnxruntime", extra="image"),
            ExternalResourceRequirement(
                name="yolo26n.onnx",
                expected_path=str(tmp_path / "missing.onnx"),
            ),
        ),
    )
    assert checker.check_capability(cap) is CapabilityStatus.UNAVAILABLE


def test_capability_status_available_when_all_requirements_met() -> None:
    checker = AvailabilityChecker()
    cap = Capability(
        id=CapabilityId.PDF_METADATA,
        label="PDF metadata",
        description="PDF metadata.",
        provider="pdf",
        requirements=(PythonPackageRequirement(name="pypdf", extra="metadata"),),
    )
    assert checker.check_capability(cap) is CapabilityStatus.AVAILABLE


def test_available_entries_populate_requirement_availability(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("FS_TOOL_MODEL_DIR", str(tmp_path))
    entries = available_entries()
    assert entries
    yolo = next(
        (e for e in entries if e.capability.id == CapabilityId.IMAGE_OBJECT_DETECTION), None
    )
    assert yolo is not None
    assert yolo.status is CapabilityStatus.UNAVAILABLE
    models = [req for req in yolo.requirements if isinstance(req, ExternalResourceRequirement)]
    assert [req.available for req in models] == [False]
    pdf = next((e for e in entries if e.capability.id == CapabilityId.PDF_METADATA), None)
    assert pdf is not None
    assert pdf.status is CapabilityStatus.AVAILABLE
    assert all(req.available for req in pdf.requirements)


def test_result_models_distinguish_statuses() -> None:
    available = CapabilityResult(
        capability=CapabilityId.PYTHON_AST,
        status=CapabilityStatus.AVAILABLE,
        message="Python AST analysis is available.",
    )
    unavailable = CapabilityResult(
        capability=CapabilityId.IMAGE_OBJECT_DETECTION,
        status=CapabilityStatus.UNAVAILABLE,
        message="Object detection is not available.",
        help="fs-tool capabilities",
    )
    failed = CapabilityResult(
        capability=CapabilityId.PDF_PAGES,
        status=CapabilityStatus.FAILED,
        message="PDF page analysis failed.",
        error_code=ErrorCode.CAPABILITY_FAILED.value,
    )
    assert available.status is CapabilityStatus.AVAILABLE
    assert unavailable.status is CapabilityStatus.UNAVAILABLE
    assert failed.status is CapabilityStatus.FAILED
    assert failed.error_code == ErrorCode.CAPABILITY_FAILED.value
    assert available.help == "fs-tool capabilities"


def test_capability_error_codes_and_exit_codes() -> None:
    assert ErrorCode.CAPABILITY_NOT_SUPPORTED.value == "CAPABILITY_NOT_SUPPORTED"
    assert ErrorCode.CAPABILITY_UNAVAILABLE.value == "CAPABILITY_UNAVAILABLE"
    assert ErrorCode.CAPABILITY_FAILED.value == "CAPABILITY_FAILED"
    assert ErrorCode.RESOURCE_NOT_FOUND.value == "RESOURCE_NOT_FOUND"
    assert ErrorCode.RESOURCE_CORRUPT.value == "RESOURCE_CORRUPT"
    assert ErrorCode.SETUP_FAILED.value == "SETUP_FAILED"
    assert EXIT_CODES[ErrorCode.CAPABILITY_NOT_SUPPORTED] == 2
    assert EXIT_CODES[ErrorCode.CAPABILITY_UNAVAILABLE] == 2
    assert EXIT_CODES[ErrorCode.CAPABILITY_FAILED] == 1
    assert EXIT_CODES[ErrorCode.RESOURCE_NOT_FOUND] == 1
    assert EXIT_CODES[ErrorCode.RESOURCE_CORRUPT] == 1
    assert EXIT_CODES[ErrorCode.SETUP_FAILED] == 1


def test_provider_registry_tracks_capabilities() -> None:
    registry = ProviderRegistry()
    cap = Capability(
        id=CapabilityId.TEXT_STRUCTURE,
        label="Text structure",
        description="Structure.",
        provider="text",
    )
    provider = _StubProvider("text", (cap,))
    registry.register(provider)
    assert registry.contains("text") is True
    assert registry.get("missing") is None
    assert [c.id.value for c in registry.capabilities()] == ["text_structure"]
    assert [p.id for p in registry.all()] == ["text"]


def test_resolve_model_dir_defaults_and_honors_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FS_TOOL_MODEL_DIR", raising=False)
    assert resolve_model_dir() == Path("~/.local/share/fs-tool/models").expanduser()
    monkeypatch.setenv("FS_TOOL_MODEL_DIR", "/tmp/fs-tool-models")
    assert resolve_model_dir() == Path("/tmp/fs-tool-models")
