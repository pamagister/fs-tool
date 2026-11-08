"""Data model for capabilities, requirements and capability results.

The model is independent of the CLI and of output formatting. Fields that are
unavailable or not applicable are ``None`` or ``False``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class CapabilityId(str, Enum):
    """Stable, machine-readable capability identifiers.

    Identifiers are permanent: once a capability is released under an
    identifier it must not change, so agents and scripts can rely on it.
    """

    # Format metadata (belongs to ``inspect info``).
    PDF_METADATA = "pdf_metadata"
    IMAGE_METADATA = "image_metadata"

    # Structured content analysis (belongs to ``inspect analyze``).
    PYTHON_AST = "python_ast"
    MARKDOWN_STRUCTURE = "markdown_structure"
    TEXT_STRUCTURE = "text_structure"
    PDF_PAGES = "pdf_pages"

    # Model-backed analysis (belongs to ``inspect analyze``).
    IMAGE_OBJECT_DETECTION = "image_object_detection"

    # Content reading (belongs to ``inspect read``).
    PDF_TEXT = "pdf_text"


class RequirementKind(str, Enum):
    """Kind of requirement a capability can declare."""

    PYTHON_PACKAGE = "python_package"
    EXTERNAL_RESOURCE = "external_resource"


@dataclass(frozen=True)
class PythonPackageRequirement:
    """A required Python package.

    ``extra`` names the package extra that installs it, e.g. ``"pdf"`` for
    ``pypdf`` or ``"image"`` for ``Pillow``/``onnxruntime``.
    """

    name: str
    extra: str | None = None
    available: bool = False


@dataclass(frozen=True)
class ExternalResourceRequirement:
    """A required external resource, e.g. an ONNX model file."""

    name: str
    expected_path: str
    available: bool = False


#: A requirement of either kind.
Requirement = PythonPackageRequirement | ExternalResourceRequirement


@dataclass(frozen=True)
class Capability:
    """A single supported capability declared by a provider.

    ``provider`` names the provider that implements the capability.
    ``setup_command``, when set, tells users how to prepare the capability
    (for example ``fs-tool setup yolo``).
    """

    id: CapabilityId
    label: str
    description: str
    provider: str
    requirements: tuple[Requirement, ...] = ()
    setup_command: str | None = None


class CapabilityStatus(str, Enum):
    """Lifecycle status of a capability result.

    - ``available``: the capability can be executed.
    - ``unavailable``: supported, but a prerequisite is missing.
    - ``failed``: execution was attempted but could not complete.
    """

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


@dataclass(frozen=True)
class CapabilityResult:
    """Result of checking or executing a capability.

    Every result carries a stable capability identifier and a concise
    message (plan.md decision D6). Failed results additionally carry a
    stable machine-readable error code.
    """

    capability: CapabilityId
    status: CapabilityStatus
    message: str
    help: str = "fs-tool capabilities"
    requirements: tuple[Requirement, ...] = ()
    error_code: str | None = None


#: Environment variable overriding the model storage directory.
MODEL_DIR_ENV = "FS_TOOL_MODEL_DIR"

#: Default model storage directory (plan.md decision D8).
DEFAULT_MODEL_DIR = Path("~/.local/share/fs-tool/models").expanduser()


def resolve_model_dir() -> Path:
    """Resolve the model storage directory.

    Honors ``FS_TOOL_MODEL_DIR`` and falls back to
    ``~/.local/share/fs-tool/models/``. The directory is not created here.
    """
    override = os.environ.get(MODEL_DIR_ENV)
    return Path(override).expanduser() if override else DEFAULT_MODEL_DIR
