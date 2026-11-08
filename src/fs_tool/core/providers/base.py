"""Internal provider interface.

Providers declare supported file formats and capabilities. Core providers do
not import Typer or CLI code and never format output (plan.md decision D3 and
architectural boundaries).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from fs_tool.core.capabilities.models import Capability


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
