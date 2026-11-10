"""Explicit provider registry.

Providers are registered explicitly; no dynamic plugin-loading framework is
used (plan.md decision D3).
"""

from __future__ import annotations

from pathlib import Path

from fs_tool.core.capabilities.models import Capability
from fs_tool.core.providers.base import Provider
from fs_tool.core.providers.image import ImageProvider
from fs_tool.core.providers.markdown import MarkdownProvider
from fs_tool.core.providers.odf import OdfProvider
from fs_tool.core.providers.ooxml import OoxmlProvider
from fs_tool.core.providers.pdf import PdfProvider
from fs_tool.core.providers.python import PythonProvider
from fs_tool.core.providers.text import TextProvider


class ProviderRegistry:
    """Registry of format providers."""

    def __init__(self) -> None:
        self._providers: dict[str, Provider] = {}

    def register(self, provider: Provider) -> None:
        """Register ``provider``. Re-registering replaces it."""
        self._providers[provider.id] = provider

    def get(self, provider_id: str) -> Provider | None:
        """Return the provider for ``provider_id``, or ``None``."""
        return self._providers.get(provider_id)

    def contains(self, provider_id: str) -> bool:
        """Return True when ``provider_id`` is registered."""
        return self.get(provider_id) is not None

    def all(self) -> tuple[Provider, ...]:
        """Return all registered providers in deterministic (identifier) order."""
        return tuple(self._providers[key] for key in sorted(self._providers))

    def capabilities(self) -> tuple[Capability, ...]:
        """All capabilities offered by registered providers, in provider order."""
        result: list[Capability] = []
        for provider in self.all():
            result.extend(provider.capabilities)
        return tuple(result)

    def for_extension(self, extension: str) -> tuple[Provider, ...]:
        """Providers handling ``extension`` (lowercase, with dot), in id order."""
        normalized = extension.lower()
        return tuple(
            provider for provider in self.all() if normalized in provider.supported_extensions()
        )

    def for_path(self, path: Path) -> tuple[Provider, ...]:
        """Providers handling the file extension of ``path``, in id order."""
        return self.for_extension(path.suffix.lower())


def default_provider_registry() -> ProviderRegistry:
    """Registry pre-populated with all built-in format providers."""
    registry = ProviderRegistry()
    for provider in (
        ImageProvider(),
        MarkdownProvider(),
        OdfProvider(),
        OoxmlProvider(),
        PdfProvider(),
        PythonProvider(),
        TextProvider(),
    ):
        registry.register(provider)
    return registry
