"""Tests for setup orchestration and the ``fs-tool setup`` command.

Downloads are fully mocked: the test suite never requires network access.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

from fs_tool.core.capabilities.models import (
    ExternalResourceRequirement,
    Requirement,
)
from fs_tool.core.errors import ErrorCode, FsToolError
from fs_tool.setup.models import SetupResult
from fs_tool.setup.service import (
    SETUP_TARGET_NAMES,
    setup_all,
    setup_report,
    setup_target,
)

ALL_PACKAGES = {"pypdf", "onnxruntime", "PIL", "numpy"}


class FakeChecker:
    """Availability checker backed by a mutable set of available names."""

    def __init__(self, available: set[str] | None = None) -> None:
        self.available = set(available or ())

    def check_requirement(self, requirement: Requirement) -> Requirement:
        if isinstance(requirement, ExternalResourceRequirement):
            name = requirement.name
        else:
            name = requirement.import_name or requirement.name
        return replace(requirement, available=name in self.available)


def _patch_checker(monkeypatch: pytest.MonkeyPatch, checker: FakeChecker) -> None:
    monkeypatch.setattr("fs_tool.setup.service.AvailabilityChecker", lambda: checker)


def _patch_yolo(
    monkeypatch: pytest.MonkeyPatch,
    checker: FakeChecker,
    *,
    status: str = "downloaded",
    model_path: Path | None = None,
    error: FsToolError | None = None,
) -> None:
    """Replace the YOLO handler with a deterministic fake."""
    path = model_path or Path("/models/yolo26n.onnx")
    message = {
        "downloaded": "YOLO model downloaded and verified.",
        "already-present": "YOLO model is already present and valid.",
    }.get(status, "YOLO model ready.")

    def fake_setup_yolo(
        *,
        model_dir: Path | None = None,
        force: bool = False,
        opener: Any = None,
    ) -> SetupResult:
        if error is not None:
            raise error
        checker.available.add(path.name)
        return SetupResult(capability="yolo", path=path, status=status, message=message)

    monkeypatch.setattr("fs_tool.setup.service.setup_yolo", fake_setup_yolo)


def test_pdf_target_ready_when_pypdf_is_available() -> None:
    target = setup_target("pdf", checker=FakeChecker({"pypdf"}))

    assert target["capability"] == "pdf"
    assert target["status"] == "ready"
    assert target["error_code"] is None
    assert target["resource"] is None
    assert target["missing_requirements"] == []
    assert target["next_steps"] == []
    assert [item["name"] for item in target["requirements"]] == ["pypdf"]


def test_pdf_target_reports_missing_dependency_and_install_command() -> None:
    target = setup_target("pdf", checker=FakeChecker())

    assert target["status"] == "missing-dependencies"
    assert target["error_code"] is None
    assert [item["name"] for item in target["missing_requirements"]] == ["pypdf"]
    assert target["next_steps"] == ['pip install "fs-tool-cli[metadata]"']


def test_image_target_checks_only_python_dependencies() -> None:
    target = setup_target("image", checker=FakeChecker(ALL_PACKAGES))

    assert target["status"] == "ready"
    assert target["resource"] is None
    assert target["missing_requirements"] == []
    assert {item["kind"] for item in target["requirements"]} == {"python_package"}
    assert [item["name"] for item in target["requirements"]] == [
        "Pillow",
        "onnxruntime",
        "numpy",
    ]


def test_image_target_reports_missing_packages() -> None:
    target = setup_target("image", checker=FakeChecker({"PIL"}))

    assert target["status"] == "missing-dependencies"
    assert [item["name"] for item in target["missing_requirements"]] == [
        "onnxruntime",
        "numpy",
    ]
    assert target["next_steps"] == ['pip install "fs-tool-cli[image]"']


def test_yolo_target_downloads_model_and_becomes_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checker = FakeChecker(ALL_PACKAGES)
    _patch_yolo(monkeypatch, checker)

    target = setup_target("yolo", checker=checker)

    assert target["status"] == "ready"
    assert target["error_code"] is None
    assert target["missing_requirements"] == []
    assert target["next_steps"] == []
    assert target["resource"] == {
        "name": "yolo26n.onnx",
        "path": "/models/yolo26n.onnx",
        "status": "downloaded",
        "message": "YOLO model downloaded and verified.",
    }
    assert target["message"] == "YOLO model downloaded and verified."


def test_yolo_target_preserves_already_present_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checker = FakeChecker(ALL_PACKAGES | {"yolo26n.onnx"})
    _patch_yolo(monkeypatch, checker, status="already-present")

    target = setup_target("yolo", checker=checker)

    assert target["status"] == "ready"
    assert target["resource"]["status"] == "already-present"
    assert target["message"] == "YOLO model is already present and valid."


def test_yolo_target_reports_partial_setup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checker = FakeChecker()
    _patch_yolo(monkeypatch, checker)

    target = setup_target("yolo", checker=checker)

    assert target["status"] == "missing-dependencies"
    assert target["resource"]["status"] == "downloaded"
    assert [item["name"] for item in target["missing_requirements"]] == [
        "onnxruntime",
        "Pillow",
        "numpy",
    ]
    assert target["next_steps"] == ['pip install "fs-tool-cli[image]"']


def test_yolo_target_reports_download_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checker = FakeChecker(ALL_PACKAGES)
    _patch_yolo(
        monkeypatch,
        checker,
        error=FsToolError(
            "Cannot download model: connection refused",
            code=ErrorCode.SETUP_FAILED,
            path="/models/yolo26n.onnx",
        ),
    )

    target = setup_target("yolo", checker=checker)

    assert target["status"] == "failed"
    assert target["error_code"] == "SETUP_FAILED"
    assert target["resource"]["status"] == "failed"
    assert target["resource"]["path"] == "/models/yolo26n.onnx"
    assert target["next_steps"] == ["fs-tool setup yolo"]


def test_yolo_target_suggests_force_for_corrupt_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checker = FakeChecker(ALL_PACKAGES)
    _patch_yolo(
        monkeypatch,
        checker,
        error=FsToolError(
            "Existing YOLO model file is not valid. Use force to replace it.",
            code=ErrorCode.RESOURCE_CORRUPT,
            path="/models/yolo26n.onnx",
        ),
    )

    target = setup_target("yolo", checker=checker)

    assert target["status"] == "failed"
    assert target["error_code"] == "RESOURCE_CORRUPT"
    assert "fs-tool setup yolo --force" in target["next_steps"]


def test_yolo_target_force_does_not_repeat_force_suggestion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checker = FakeChecker(ALL_PACKAGES)
    _patch_yolo(
        monkeypatch,
        checker,
        error=FsToolError(
            "Existing YOLO model file is not valid. Use force to replace it.",
            code=ErrorCode.RESOURCE_CORRUPT,
            path="/models/yolo26n.onnx",
        ),
    )

    target = setup_target("yolo", force=True, checker=checker)

    assert target["status"] == "failed"
    assert "fs-tool setup yolo --force" not in target["next_steps"]


def test_setup_all_runs_targets_independently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checker = FakeChecker()
    _patch_yolo(
        monkeypatch,
        checker,
        error=FsToolError("Download failed.", code=ErrorCode.SETUP_FAILED),
    )

    report = setup_all(checker=checker)

    assert [target["capability"] for target in report["targets"]] == list(SETUP_TARGET_NAMES)
    assert [target["status"] for target in report["targets"]] == [
        "missing-dependencies",
        "missing-dependencies",
        "failed",
    ]
    assert report["count"] == 3
    assert report["failed_count"] == 1


def test_setup_report_counts_only_failed_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    checker = FakeChecker({"pypdf"})
    _patch_yolo(monkeypatch, checker)

    report = setup_report(("pdf", "yolo"), checker=checker)

    assert report["count"] == 2
    assert report["failed_count"] == 0
    assert [target["capability"] for target in report["targets"]] == ["pdf", "yolo"]


def test_setup_command_json_ready(cli: Any, capsys: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_checker(monkeypatch, FakeChecker({"pypdf"}))

    assert cli(["--json", "setup", "pdf"]) == 0

    envelope = json.loads(capsys.readouterr().out)
    assert envelope["success"] is True
    assert envelope["command"] == "setup"
    assert envelope["complete"] is True
    assert envelope["errors"] == []
    assert envelope["result"]["count"] == 1
    assert envelope["result"]["failed_count"] == 0
    assert envelope["result"]["targets"][0]["capability"] == "pdf"
    assert envelope["result"]["targets"][0]["status"] == "ready"


def test_setup_command_plain_reports_missing_dependency(
    cli: Any, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_checker(monkeypatch, FakeChecker())

    assert cli(["--plain", "setup", "pdf"]) == 0

    output = capsys.readouterr().out
    assert "setup: 1 target(s)" in output
    assert "pdf [missing-dependencies]" in output
    assert "missing: pypdf (import pypdf)" in output
    assert 'next: pip install "fs-tool-cli[metadata]"' in output


def test_setup_command_all_uses_deterministic_order(
    cli: Any, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    checker = FakeChecker(ALL_PACKAGES)
    _patch_checker(monkeypatch, checker)
    _patch_yolo(monkeypatch, checker)

    assert cli(["--json", "setup", "--all"]) == 0

    envelope = json.loads(capsys.readouterr().out)
    targets = envelope["result"]["targets"]
    assert [target["capability"] for target in targets] == ["pdf", "image", "yolo"]
    assert envelope["result"]["failed_count"] == 0
    assert targets[2]["resource"]["status"] == "downloaded"


def test_setup_command_passes_force_to_yolo(
    cli: Any, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    checker = FakeChecker(ALL_PACKAGES | {"yolo26n.onnx"})
    _patch_checker(monkeypatch, checker)
    calls: dict[str, bool] = {}

    def fake_setup_yolo(
        *,
        model_dir: Path | None = None,
        force: bool = False,
        opener: Any = None,
    ) -> SetupResult:
        calls["force"] = force
        return SetupResult(
            capability="yolo",
            path=Path("/models/yolo26n.onnx"),
            status="already-present",
            message="YOLO model is already present and valid.",
        )

    monkeypatch.setattr("fs_tool.setup.service.setup_yolo", fake_setup_yolo)

    assert cli(["--json", "setup", "yolo", "--force"]) == 0

    assert calls["force"] is True
    assert json.loads(capsys.readouterr().out)["result"]["failed_count"] == 0


def test_setup_command_failure_returns_exit_one(
    cli: Any, capsys: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    checker = FakeChecker(ALL_PACKAGES)
    _patch_checker(monkeypatch, checker)
    _patch_yolo(
        monkeypatch,
        checker,
        error=FsToolError(
            "Cannot download model: connection refused",
            code=ErrorCode.SETUP_FAILED,
            path="/models/yolo26n.onnx",
        ),
    )

    assert cli(["--json", "setup", "yolo"]) == 1

    envelope = json.loads(capsys.readouterr().out)
    assert envelope["success"] is False
    assert envelope["complete"] is True
    assert envelope["result"]["failed_count"] == 1
    assert envelope["errors"] == [
        {
            "code": "SETUP_FAILED",
            "message": "Cannot download model: connection refused",
            "path": "/models/yolo26n.onnx",
            "details": {},
        }
    ]


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (["--json", "setup"], "Specify a capability"),
        (["--json", "setup", "pdf", "--all"], "either a capability or --all"),
        (["--json", "setup", "video"], "Unknown setup target"),
    ],
)
def test_setup_invalid_usage_json(cli: Any, capsys: Any, argv: list[str], message: str) -> None:
    assert cli(argv) == 2

    envelope = json.loads(capsys.readouterr().out)
    assert envelope["success"] is False
    assert envelope["command"] == "setup"
    assert envelope["complete"] is False
    assert envelope["errors"][0]["code"] == "INVALID_ARGUMENT"
    assert message in envelope["errors"][0]["message"]


def test_setup_invalid_usage_plain_writes_stderr(cli: Any, capsys: Any) -> None:
    assert cli(["--plain", "setup"]) == 2

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "fs-tool: error: Specify a capability" in captured.err


def test_setup_help(cli: Any, capsys: Any) -> None:
    assert cli(["setup", "--help"]) == 0

    output = capsys.readouterr().out
    assert "setup" in output
    assert "--all" in output
    assert "--force" in output
