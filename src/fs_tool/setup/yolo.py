"""Explicit setup handler for the YOLO object-detection model.

The handler is independent of the CLI so Phase 5 can reuse it. It never
installs Python packages, never downloads during normal analysis and never
overwrites a valid model file.
"""

from __future__ import annotations

from pathlib import Path

from fs_tool.core.errors import ErrorCode, FsToolError
from fs_tool.setup.models import (
    YOLO_MODEL_SHA256,
    YOLO_MODEL_SIZE,
    YOLO_MODEL_URL,
    Opener,
    SetupResult,
    download_model,
    expected_model_path,
    validate_model_file,
)

#: Stable setup capability name.
YOLO_SETUP = "yolo"


def setup_yolo(
    *,
    model_dir: Path | None = None,
    force: bool = False,
    opener: Opener | None = None,
) -> SetupResult:
    """Prepare the YOLO26n ONNX model in the configured model directory.

    Setup is idempotent: an existing valid model is preserved. An existing
    invalid file is rejected unless ``force`` is set, in which case it is
    replaced by a freshly verified download.
    """
    destination = expected_model_path(model_dir)
    if destination.exists():
        existing = validate_model_file(
            destination,
            expected_sha256=YOLO_MODEL_SHA256,
            expected_size=YOLO_MODEL_SIZE,
        )
        if existing.valid:
            return SetupResult(
                capability=YOLO_SETUP,
                path=destination,
                status="already-present",
                message="YOLO model is already present and valid.",
            )
        if not force:
            raise FsToolError(
                "Existing YOLO model file is not valid. Use force to replace it.",
                code=ErrorCode.RESOURCE_CORRUPT,
                path=str(destination),
                details={"reason": existing.message},
            )

    download_model(
        destination,
        url=YOLO_MODEL_URL,
        expected_sha256=YOLO_MODEL_SHA256,
        expected_size=YOLO_MODEL_SIZE,
        opener=opener,
    )
    return SetupResult(
        capability=YOLO_SETUP,
        path=destination,
        status="downloaded",
        message="YOLO model downloaded and verified.",
    )


__all__ = ["YOLO_SETUP", "setup_yolo"]
