"""Machine-readable capability report used by ``fs-tool capabilities``.

The report is built from the central registry and the availability checker, so
it reflects the current environment without executing any analysis or download.
Serialization uses stable key order and deterministic capability ordering.
"""

from __future__ import annotations

from typing import Any

from fs_tool.core.capabilities.models import (
    CapabilityStatus,
    ExternalResourceRequirement,
    PythonPackageRequirement,
    Requirement,
    RequirementKind,
    resolve_model_dir,
)
from fs_tool.core.capabilities.registry import CapabilityEntry, available_entries

#: Distribution name used in installation instructions.
DISTRIBUTION_NAME = "fs-tool-cli"


def install_command(extra: str | None) -> str:
    """Return a concrete installation command for ``extra``."""
    target = f"{DISTRIBUTION_NAME}[{extra}]" if extra else DISTRIBUTION_NAME
    return f'pip install "{target}"'


def requirement_to_dict(requirement: Requirement) -> dict[str, Any]:
    """Serialize a checked requirement with a stable shape.

    Python package entries expose the distribution name, import name and the
    extra that installs them, plus an exact installation command. External
    resources expose the expected path only.
    """
    if isinstance(requirement, PythonPackageRequirement):
        return {
            "kind": RequirementKind.PYTHON_PACKAGE.value,
            "name": requirement.name,
            "import_name": requirement.import_name,
            "extra": requirement.extra,
            "available": requirement.available,
            "install_command": install_command(requirement.extra),
        }
    if isinstance(requirement, ExternalResourceRequirement):
        return {
            "kind": RequirementKind.EXTERNAL_RESOURCE.value,
            "name": requirement.name,
            "expected_path": requirement.expected_path,
            "available": requirement.available,
        }
    raise TypeError(f"Unsupported requirement: {requirement!r}")


def _unique_install_commands(requirements: list[dict[str, Any]]) -> list[str]:
    commands: list[str] = []
    for requirement in requirements:
        command = requirement.get("install_command")
        if command is not None and command not in commands:
            commands.append(command)
    return commands


def capability_entry_to_dict(entry: CapabilityEntry) -> dict[str, Any]:
    """Serialize a capability and its current availability.

    ``missing_requirements`` repeats the unavailable entries so agents can
    consume them without filtering the complete requirement list. ``setup`` is
    ``None`` when the capability has no setup step.
    """
    capability = entry.capability
    requirements = [requirement_to_dict(item) for item in entry.requirements]
    missing = [item for item in requirements if not item["available"]]
    next_steps = _unique_install_commands(missing)
    if capability.setup_command is not None and any(
        item["kind"] == RequirementKind.EXTERNAL_RESOURCE.value for item in missing
    ):
        next_steps.append(capability.setup_command)
    return {
        "id": capability.id.value,
        "label": capability.label,
        "description": capability.description,
        "provider": capability.provider,
        "supported": True,
        "available": entry.status is CapabilityStatus.AVAILABLE,
        "status": entry.status.value,
        "requirements": requirements,
        "missing_requirements": missing,
        "next_steps": next_steps,
        "setup": (
            {"command": capability.setup_command} if capability.setup_command is not None else None
        ),
    }


def capabilities_report(
    entries: tuple[CapabilityEntry, ...] | None = None,
) -> dict[str, Any]:
    """Build the result payload for ``fs-tool capabilities``."""
    if entries is None:
        entries = available_entries()
    capability_dicts = [capability_entry_to_dict(entry) for entry in entries]
    available_count = sum(1 for item in capability_dicts if item["available"])
    return {
        "capabilities": capability_dicts,
        "count": len(capability_dicts),
        "available_count": available_count,
        "model_directory": str(resolve_model_dir()),
    }


__all__ = [
    "DISTRIBUTION_NAME",
    "capabilities_report",
    "capability_entry_to_dict",
    "install_command",
    "requirement_to_dict",
]
