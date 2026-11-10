"""Central capability registry.

All capability definitions live here and are shared by ``info``, ``analyze``,
``capabilities`` and ``setup`` (plan.md decision D4). The registry is
populated explicitly; there is no dynamic plugin-loading framework.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fs_tool.core.capabilities.availability import AvailabilityChecker
from fs_tool.core.capabilities.models import (
    Capability,
    CapabilityId,
    CapabilityStatus,
    ExternalResourceRequirement,
    PythonPackageRequirement,
    Requirement,
)
from fs_tool.setup.models import expected_model_path


@dataclass(frozen=True)
class CapabilityEntry:
    """A capability definition together with its current availability status."""

    capability: Capability
    status: CapabilityStatus
    requirements: tuple[Requirement, ...] = field(compare=False)


def _default_capabilities() -> tuple[Capability, ...]:
    """All supported capabilities with their declared requirements.

    This is the single source of capability definitions. Requirements describe
    what is needed; :class:`AvailabilityChecker` determines what is present.
    """

    return (
        Capability(
            id=CapabilityId.PDF_METADATA,
            label="PDF metadata",
            description="Extract author, title, subject and dates from PDF files.",
            provider="pdf",
            requirements=(PythonPackageRequirement(name="pypdf", extra="metadata"),),
        ),
        Capability(
            id=CapabilityId.ODF_METADATA,
            label="ODF metadata",
            description="Extract author, title, subject and dates from ODF files.",
            provider="odf",
        ),
        Capability(
            id=CapabilityId.OOXML_METADATA,
            label="OOXML metadata",
            description="Extract author, title, subject and dates from OOXML files.",
            provider="ooxml",
        ),
        Capability(
            id=CapabilityId.IMAGE_METADATA,
            label="Image metadata",
            description="Extract format, dimensions, color mode and EXIF data from images.",
            provider="image",
            requirements=(PythonPackageRequirement(name="Pillow", extra="image"),),
        ),
        Capability(
            id=CapabilityId.PYTHON_AST,
            label="Python AST analysis",
            description="Analyze Python source structure: imports, functions, classes and methods.",
            provider="python",
            requirements=(),
        ),
        Capability(
            id=CapabilityId.MARKDOWN_STRUCTURE,
            label="Markdown structure",
            description="Extract heading hierarchy and document structure from Markdown files.",
            provider="markdown",
            requirements=(),
        ),
        Capability(
            id=CapabilityId.TEXT_STRUCTURE,
            label="Text structure",
            description="Report line count, paragraph count and simple structural information.",
            provider="text",
            requirements=(),
        ),
        Capability(
            id=CapabilityId.PDF_PAGES,
            label="PDF page structure",
            description="Report PDF page count, dimensions and orientation.",
            provider="pdf",
            requirements=(PythonPackageRequirement(name="pypdf", extra="metadata"),),
        ),
        Capability(
            id=CapabilityId.IMAGE_OBJECT_DETECTION,
            label="Image object detection",
            description="Detect objects with YOLO through ONNX Runtime.",
            provider="image",
            requirements=(
                PythonPackageRequirement(name="onnxruntime", extra="image"),
                PythonPackageRequirement(name="Pillow", extra="image"),
                ExternalResourceRequirement(
                    name="yolo26n.onnx",
                    expected_path=str(expected_model_path()),
                ),
            ),
            setup_command="fs-tool setup yolo",
        ),
        Capability(
            id=CapabilityId.PDF_TEXT,
            label="PDF text extraction",
            description="Extract textual content from a PDF file.",
            provider="pdf",
            requirements=(PythonPackageRequirement(name="pypdf", extra="metadata"),),
        ),
    )


class CapabilityRegistry:
    """Central registry of capability definitions.

    Use :func:`default_registry` to obtain the registry pre-populated with all
    supported capabilities.
    """

    def __init__(self) -> None:
        self._capabilities: dict[CapabilityId, Capability] = {}

    def register(self, capability: Capability) -> None:
        """Register a capability definition. Re-registering replaces it."""
        self._capabilities[capability.id] = capability

    def get(self, capability_id: CapabilityId | str) -> Capability | None:
        """Return the capability definition for ``capability_id``, or ``None``."""
        if isinstance(capability_id, CapabilityId):
            key = capability_id
        else:
            try:
                key = CapabilityId(capability_id)
            except ValueError:
                return None
        return self._capabilities.get(key)

    def contains(self, capability_id: CapabilityId | str) -> bool:
        """Return True when ``capability_id`` is registered."""
        return self.get(capability_id) is not None

    def all(self) -> tuple[Capability, ...]:
        """Return all registered capabilities in deterministic (identifier) order."""
        return tuple(self._capabilities[key] for key in sorted(self._capabilities))

    def by_provider(self, provider: str) -> tuple[Capability, ...]:
        """Return capabilities offered by ``provider``, in identifier order."""
        return tuple(cap for cap in self.all() if cap.provider == provider)


def default_registry() -> CapabilityRegistry:
    """Registry pre-populated with all supported capabilities."""
    registry = CapabilityRegistry()
    for capability in _default_capabilities():
        registry.register(capability)
    return registry


def available_entries(registry: CapabilityRegistry | None = None) -> tuple[CapabilityEntry, ...]:
    """Return every registered capability with its current availability.

    Availability is determined by :class:`AvailabilityChecker` and does not
    execute any file analysis.
    """
    if registry is None:
        registry = default_registry()
    checker = AvailabilityChecker()
    entries: list[CapabilityEntry] = []
    for capability in registry.all():
        status = checker.check_capability(capability)
        requirements = tuple(checker.check_requirement(req) for req in capability.requirements)
        entries.append(
            CapabilityEntry(
                capability=capability,
                status=status,
                requirements=requirements,
            )
        )
    return tuple(entries)
