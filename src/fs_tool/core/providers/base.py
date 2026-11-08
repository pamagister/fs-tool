"""Internal provider interface.

Providers declare supported file formats and capabilities. Core providers do
not import Typer or CLI code and never format output (plan.md decision D3 and
architectural boundaries).

A provider may expose three independent kinds of functionality:

- format metadata extraction, used by ``inspect info`` (decision D2),
- structured content analysis, used by ``inspect analyze``, and
- textual content reading, used by ``inspect read``.

All kinds are described by the same central capability definitions.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Any

from fs_tool.core.capabilities.models import Capability, CapabilityId
from fs_tool.core.capabilities.registry import default_registry

if TYPE_CHECKING:
    from fs_tool.core.providers.content import ContentRead


class Provider(ABC):
    """Base class for format-specific information and analysis providers.

    A provider may expose multiple independent capabilities (for example,
    ``image_metadata`` and ``image_object_detection``). Providers are
    registered explicitly; availability is checked centrally by the
    capability registry, not by executing file analyses here.
    """

    @property
    @abstractmethod
    def id(self) -> str:
        """Stable provider identifier."""

    @property
    @abstractmethod
    def capabilities(self) -> tuple[Capability, ...]:
        """Capabilities offered by this provider."""

    @abstractmethod
    def supported_extensions(self) -> tuple[str, ...]:
        """File extensions this provider can handle (lowercase, with dot)."""

    def metadata_capability(self) -> CapabilityId | None:
        """Capability describing format metadata extraction, if any."""
        return None

    def extract_metadata(self, path: Path) -> dict[str, Any] | None:
        """Extract format metadata from ``path``.

        Return ``None`` when the file contains no metadata. Raise
        :class:`fs_tool.core.errors.FsToolError` when extraction fails.
        """
        return None

    def analysis_capabilities(self) -> tuple[CapabilityId, ...]:
        """Analysis capabilities this provider implements."""
        return ()

    def analyze(self, capability: CapabilityId, path: Path) -> dict[str, Any]:
        """Run one analysis capability and return its structured data.

        Providers must not return complete file content. Raise
        :class:`fs_tool.core.errors.FsToolError` when the analysis fails.
        """
        raise NotImplementedError(f"{self.id} does not implement {capability.value}")

    def content_capability(self) -> CapabilityId | None:
        """Capability describing textual content reading, if any.

        Providers without a dedicated content capability are read with the
        bounded UTF-8 text reader.
        """
        return None

    def read_content(self, path: Path, *, max_bytes: int) -> ContentRead:
        """Return bounded textual content for ``path``.

        The content must identify its representation and must never include
        binary data. Raise :class:`fs_tool.core.errors.FsToolError` when
        reading fails.
        """
        raise NotImplementedError(f"{self.id} does not implement content reading")


def capabilities_from_registry(
    provider_id: str,
    capability_ids: tuple[CapabilityId, ...],
) -> tuple[Capability, ...]:
    """Resolve capability definitions from the central registry.

    Providers never duplicate capability definitions; the central registry
    remains the single source of truth (plan.md decision D4).
    """
    registry = default_registry()
    capabilities: list[Capability] = []
    for capability_id in capability_ids:
        capability = registry.get(capability_id)
        if capability is None:
            raise LookupError(f"Capability {capability_id.value!r} is not registered.")
        if capability.provider != provider_id:
            raise ValueError(
                f"Capability {capability_id.value!r} belongs to provider "
                f"{capability.provider!r}, not {provider_id!r}."
            )
        capabilities.append(capability)
    return tuple(capabilities)
