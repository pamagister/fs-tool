"""Metadata inspection and structured analysis orchestration.

This module connects providers, the central capability registry and the
availability checker. It returns core result models only; it never formats
JSON or plain output (plan.md architectural boundaries).

- :func:`inspect_metadata` implements the format-metadata responsibility of
  ``inspect info``.
- :func:`analyze_file` implements ``inspect analyze``.

A missing prerequisite or a failed analysis is represented explicitly and
never prevents other applicable analyses from running (plan.md decision D6).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fs_tool.core.capabilities.availability import AvailabilityChecker
from fs_tool.core.capabilities.models import (
    Capability,
    CapabilityId,
    CapabilityResult,
    CapabilityStatus,
)
from fs_tool.core.capabilities.registry import CapabilityRegistry, default_registry
from fs_tool.core.errors import ErrorCode, FsToolError
from fs_tool.core.metadata import MAX_METADATA_SIZE
from fs_tool.core.providers.base import Provider
from fs_tool.core.providers.registry import ProviderRegistry, default_provider_registry


@dataclass(frozen=True)
class MetadataInspection:
    """Result of inspecting format metadata for one path.

    ``result`` is ``None`` when no metadata capability applies to the file
    format, which makes unsupported formats distinguishable from unavailable
    ones.
    """

    metadata: dict[str, Any] | None
    result: CapabilityResult | None


@dataclass(frozen=True)
class AnalysisReport:
    """Results of all applicable analyses for one path."""

    results: tuple[CapabilityResult, ...]
    supported: bool


def _unavailable(capability: Capability) -> CapabilityResult:
    return CapabilityResult(
        capability=capability.id,
        status=CapabilityStatus.UNAVAILABLE,
        message=f"{capability.label} is not available.",
    )


def _failed(capability: Capability, exc: FsToolError) -> CapabilityResult:
    status = (
        CapabilityStatus.UNAVAILABLE
        if exc.code is ErrorCode.CAPABILITY_UNAVAILABLE
        else CapabilityStatus.FAILED
    )
    return CapabilityResult(
        capability=capability.id,
        status=status,
        message=exc.message,
        error_code=exc.code.value if status is CapabilityStatus.FAILED else None,
    )


def _missing_definition(capability_id: CapabilityId) -> CapabilityResult:
    return CapabilityResult(
        capability=capability_id,
        status=CapabilityStatus.FAILED,
        message="Capability definition is missing from the central registry.",
        error_code=ErrorCode.CAPABILITY_FAILED.value,
    )


def inspect_metadata(
    path: Path,
    *,
    providers: ProviderRegistry | None = None,
    registry: CapabilityRegistry | None = None,
    checker: AvailabilityChecker | None = None,
) -> MetadataInspection:
    """Extract format metadata for ``path`` through its provider.

    Symlinks are never followed. A missing prerequisite produces an
    ``unavailable`` result; extraction errors produce a ``failed`` result.
    Neither is silently omitted.
    """
    if providers is None:
        providers = default_provider_registry()
    if registry is None:
        registry = default_registry()
    if checker is None:
        checker = AvailabilityChecker()

    provider = next(
        (item for item in providers.for_path(path) if item.metadata_capability() is not None),
        None,
    )
    if provider is None:
        return MetadataInspection(metadata=None, result=None)

    capability_id = provider.metadata_capability()
    assert capability_id is not None
    capability = registry.get(capability_id)
    if capability is None:
        return MetadataInspection(metadata=None, result=_missing_definition(capability_id))

    if checker.check_capability(capability) is not CapabilityStatus.AVAILABLE:
        return MetadataInspection(metadata=None, result=_unavailable(capability))

    try:
        if path.is_symlink() or not path.is_file():
            return MetadataInspection(metadata=None, result=None)
        if path.stat().st_size > MAX_METADATA_SIZE:
            raise FsToolError(
                "File exceeds the metadata size limit.",
                code=ErrorCode.CAPABILITY_FAILED,
                path=str(path),
            )
        metadata = provider.extract_metadata(path)
    except FsToolError as exc:
        return MetadataInspection(metadata=None, result=_failed(capability, exc))
    except Exception as exc:  # defensive: a provider bug must stay structured
        failure = FsToolError(
            f"Metadata extraction failed: {exc}",
            code=ErrorCode.CAPABILITY_FAILED,
            path=str(path),
        )
        return MetadataInspection(metadata=None, result=_failed(capability, failure))

    if metadata is None:
        return MetadataInspection(
            metadata=None,
            result=CapabilityResult(
                capability=capability.id,
                status=CapabilityStatus.AVAILABLE,
                message="No format metadata found.",
            ),
        )
    return MetadataInspection(
        metadata=metadata,
        result=CapabilityResult(
            capability=capability.id,
            status=CapabilityStatus.AVAILABLE,
            message="Format metadata extracted.",
            data=metadata,
        ),
    )


def analyze_file(
    path: Path,
    *,
    providers: ProviderRegistry | None = None,
    registry: CapabilityRegistry | None = None,
    checker: AvailabilityChecker | None = None,
) -> AnalysisReport:
    """Run every applicable analysis capability for ``path``.

    Symlinks are never followed, and analysis results never include complete
    file content. Each result carries its own status; one unavailable or
    failed capability does not stop the others.
    """
    if providers is None:
        providers = default_provider_registry()
    if registry is None:
        registry = default_registry()
    if checker is None:
        checker = AvailabilityChecker()

    if path.is_symlink() or not path.is_file():
        return AnalysisReport(results=(), supported=False)

    applicable: list[tuple[Provider, CapabilityId]] = []
    seen: set[CapabilityId] = set()
    for provider in providers.for_path(path):
        for capability_id in provider.analysis_capabilities():
            if capability_id in seen:
                continue
            seen.add(capability_id)
            applicable.append((provider, capability_id))

    results: list[CapabilityResult] = []
    for provider, capability_id in applicable:
        capability = registry.get(capability_id)
        if capability is None:
            results.append(_missing_definition(capability_id))
            continue
        if checker.check_capability(capability) is not CapabilityStatus.AVAILABLE:
            results.append(_unavailable(capability))
            continue
        try:
            data = provider.analyze(capability_id, path)
        except FsToolError as exc:
            results.append(_failed(capability, exc))
        except Exception as exc:  # defensive: a provider bug must stay structured
            failure = FsToolError(
                f"Analysis failed: {exc}",
                code=ErrorCode.CAPABILITY_FAILED,
                path=str(path),
            )
            results.append(_failed(capability, failure))
        else:
            results.append(
                CapabilityResult(
                    capability=capability.id,
                    status=CapabilityStatus.AVAILABLE,
                    message=f"{capability.label} completed.",
                    data=data,
                )
            )

    return AnalysisReport(results=tuple(results), supported=bool(applicable))
