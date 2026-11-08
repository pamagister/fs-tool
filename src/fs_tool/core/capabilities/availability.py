"""Availability checking for capabilities.

Checks verify that prerequisites are present without executing any file
analysis. A missing prerequisite makes a capability ``unavailable``; it never
triggers an analysis, an import of an analyzed file, or a download.
"""

from __future__ import annotations

import importlib.util
from dataclasses import replace
from pathlib import Path

from fs_tool.core.capabilities.models import (
    DEFAULT_MODEL_DIR,
    Capability,
    CapabilityStatus,
    ExternalResourceRequirement,
    PythonPackageRequirement,
    Requirement,
    resolve_model_dir,
)


class AvailabilityChecker:
    """Stateless availability checks for capability requirements."""

    @staticmethod
    def python_package_available(name: str) -> bool:
        """Return True if ``name`` can be imported without side effects.

        Uses :func:`importlib.util.find_spec`, which does not execute the
        package.
        """
        return importlib.util.find_spec(name) is not None

    @staticmethod
    def external_resource_available(expected_path: str) -> bool:
        """Return True if the external resource file exists at ``expected_path``.

        The path may contain ``~`` and ``$FS_TOOL_MODEL_DIR`` is honored by
        :func:`resolve_model_dir` when callers build expected paths.
        """
        return Path(expected_path).expanduser().is_file()

    def check_requirement(self, requirement: Requirement) -> Requirement:
        """Return a copy of ``requirement`` with ``available`` populated."""
        if isinstance(requirement, PythonPackageRequirement):
            return replace(
                requirement,
                available=self.python_package_available(requirement.name),
            )
        if isinstance(requirement, ExternalResourceRequirement):
            return replace(
                requirement,
                available=self.external_resource_available(requirement.expected_path),
            )
        return requirement

    def check_capability(self, capability: Capability) -> CapabilityStatus:
        """Return the availability status of ``capability``.

        A capability is available only when every requirement is satisfied.
        Missing prerequisites produce ``unavailable``; the analysis itself is
        never executed here.
        """
        for requirement in capability.requirements:
            checked = self.check_requirement(requirement)
            if not checked.available:
                return CapabilityStatus.UNAVAILABLE
        return CapabilityStatus.AVAILABLE

    def model_dir(self) -> Path:
        """Return the configured model storage directory."""
        return resolve_model_dir()

    @property
    def default_model_dir(self) -> Path:
        """The default model directory, ignoring ``FS_TOOL_MODEL_DIR``."""
        return DEFAULT_MODEL_DIR
