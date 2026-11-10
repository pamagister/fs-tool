"""Tests for image metadata and ONNX-backed object detection (plan.md Phase 4).

Inference is mocked, so the suite never requires network access or a
downloaded YOLO model. One optional integration test runs only when a valid
model is already present in the configured model directory.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fs_tool.core.capabilities.models import CapabilityId, CapabilityStatus
from fs_tool.core.errors import ErrorCode, FsToolError
from fs_tool.core.providers import image as image_provider
from fs_tool.core.providers.image import (
    COCO_CLASS_NAMES,
    ImageProvider,
    detections_from_output,
    letterbox_image,
)
from fs_tool.core.providers.inspection import analyze_file, inspect_metadata
from fs_tool.setup.models import ModelValidation, expected_model_path, validate_model_file

np = pytest.importorskip("numpy")
Image = pytest.importorskip("PIL.Image")

MODEL_NAME = "yolo26n.onnx"


class _FakeInput:
    name = "images"


class _FakeOutput:
    name = "output0"


class _FakeSession:
    """Minimal ONNX Runtime session returning a prepared output tensor."""

    def __init__(self, output: object) -> None:
        self.output = output
        self.calls: list[tuple[list[str], dict[str, object]]] = []

    def get_inputs(self) -> list[_FakeInput]:
        return [_FakeInput()]

    def get_outputs(self) -> list[_FakeOutput]:
        return [_FakeOutput()]

    def run(self, output_names: list[str], input_feed: dict[str, object]) -> list[object]:
        self.calls.append((output_names, input_feed))
        return [self.output]


def _write_image(path: Path, size: tuple[int, int] = (1280, 720)) -> Path:
    Image.new("RGB", size, (200, 30, 30)).save(path)
    return path


def _model_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    monkeypatch.setenv("FS_TOOL_MODEL_DIR", str(model_dir))
    return model_dir


def _end_to_end_output(rows: list[list[float]]) -> object:
    """Build a ``[1, 300, 6]`` tensor, padding unused rows with zeroes."""
    output = np.zeros((1, 300, 6), dtype=np.float32)
    output[0, : len(rows)] = np.asarray(rows, dtype=np.float32)
    return output


@pytest.mark.skipif(not image_provider.HAS_PILLOW, reason="Pillow is not installed")
def test_image_metadata_via_inspect_info(tmp_path: Path) -> None:
    source = _write_image(tmp_path / "sample.png")

    inspection = inspect_metadata(source)

    assert inspection.result is not None
    assert inspection.result.capability is CapabilityId.IMAGE_METADATA
    assert inspection.result.status is CapabilityStatus.AVAILABLE
    assert inspection.metadata == {
        "format": "png",
        "width": 1280,
        "height": 720,
        "mode": "RGB",
        "exif": {},
    }


@pytest.mark.skipif(not image_provider.HAS_PILLOW, reason="Pillow is not installed")
def test_image_metadata_is_independent_of_yolo(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _model_dir(monkeypatch, tmp_path)
    monkeypatch.setattr(image_provider, "HAS_ONNX_RUNTIME", False)
    source = _write_image(tmp_path / "sample.jpg", size=(64, 48))

    inspection = inspect_metadata(source)

    assert inspection.result is not None
    assert inspection.result.status is CapabilityStatus.AVAILABLE
    assert inspection.metadata is not None
    assert (inspection.metadata["width"], inspection.metadata["height"]) == (64, 48)


def test_object_detection_is_unavailable_without_model(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _model_dir(monkeypatch, tmp_path)
    source = _write_image(tmp_path / "sample.png")

    report = analyze_file(source)

    assert report.supported is True
    assert len(report.results) == 1
    result = report.results[0]
    assert result.capability is CapabilityId.IMAGE_OBJECT_DETECTION
    assert result.status is CapabilityStatus.UNAVAILABLE
    assert result.error_code is None
    assert result.help == "fs-tool capabilities"


def test_object_detection_reports_missing_onnxruntime(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(image_provider, "HAS_ONNX_RUNTIME", False)

    with pytest.raises(FsToolError) as exc_info:
        ImageProvider().analyze(CapabilityId.IMAGE_OBJECT_DETECTION, tmp_path / "photo.png")

    assert exc_info.value.code is ErrorCode.CAPABILITY_UNAVAILABLE
    assert "onnxruntime" in exc_info.value.message


def test_object_detection_reports_missing_model(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _model_dir(monkeypatch, tmp_path)

    with pytest.raises(FsToolError) as exc_info:
        ImageProvider().analyze(CapabilityId.IMAGE_OBJECT_DETECTION, tmp_path / "photo.png")

    assert exc_info.value.code is ErrorCode.RESOURCE_NOT_FOUND
    assert exc_info.value.path == str(expected_model_path())


def test_object_detection_reports_corrupt_model(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    model_dir = _model_dir(monkeypatch, tmp_path)
    (model_dir / MODEL_NAME).write_bytes(b"not the verified model")
    source = _write_image(tmp_path / "sample.png")

    report = analyze_file(source)

    assert report.supported is True
    result = report.results[0]
    assert result.capability is CapabilityId.IMAGE_OBJECT_DETECTION
    assert result.status is CapabilityStatus.FAILED
    assert result.error_code == ErrorCode.RESOURCE_CORRUPT.value


def test_letterbox_preserves_aspect_ratio() -> None:
    image = Image.new("RGB", (1280, 720), (0, 128, 255))

    letterboxed, scale, pad_x, pad_y = letterbox_image(image)

    assert letterboxed.size == (640, 640)
    assert scale == 0.5
    assert (pad_x, pad_y) == (0.0, 140.0)


def test_detections_from_output_maps_boxes_to_original_image() -> None:
    rows = [
        [100, 200, 300, 400, 0.9, 0],
        [110, 210, 310, 410, 0.9, 0],
        [50, 50, 150, 150, 0.9, 2],
        [10, 10, 100, 100, 0.1, 0],
    ]

    detections = detections_from_output(
        _end_to_end_output(rows),
        scale=0.5,
        pad_x=0.0,
        pad_y=140.0,
        image_width=1280,
        image_height=720,
    )

    assert [item["class_name"] for item in detections] == ["person", "person", "car"]
    assert [item["class_id"] for item in detections] == [0, 0, 2]
    assert detections[0]["box"] == {"x1": 200.0, "y1": 120.0, "x2": 600.0, "y2": 520.0}
    assert detections[1]["box"] == {"x1": 220.0, "y1": 140.0, "x2": 620.0, "y2": 540.0}
    # Clipped to the original image bounds.
    assert detections[2]["box"] == {"x1": 100.0, "y1": 0.0, "x2": 300.0, "y2": 20.0}
    assert all(item["confidence"] == 0.9 for item in detections)


def test_detections_from_output_is_deterministic() -> None:
    rows = [
        [300, 300, 400, 400, 0.5, 1],
        [100, 100, 200, 200, 0.5, 1],
        [200, 200, 300, 300, 0.8, 3],
    ]
    output = _end_to_end_output(rows)

    first = detections_from_output(
        output, scale=1.0, pad_x=0.0, pad_y=0.0, image_width=640, image_height=640
    )
    second = detections_from_output(
        output, scale=1.0, pad_x=0.0, pad_y=0.0, image_width=640, image_height=640
    )

    assert first == second
    assert [item["box"]["x1"] for item in first] == [200.0, 100.0, 300.0]


def test_class_names_are_complete_coco_set() -> None:
    assert len(COCO_CLASS_NAMES) == 80
    assert COCO_CLASS_NAMES[0] == "person"
    assert COCO_CLASS_NAMES[-1] == "toothbrush"


@pytest.mark.skipif(not image_provider.HAS_ONNX_RUNTIME, reason="onnxruntime is not installed")
def test_object_detection_uses_mocked_session(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    model_dir = _model_dir(monkeypatch, tmp_path)
    model_path = model_dir / MODEL_NAME
    model_path.write_bytes(b"mocked model")
    source = _write_image(tmp_path / "scene.png")
    rows = [
        [100, 200, 300, 400, 0.9, 0],
        [110, 210, 310, 410, 0.9, 0],
        [50, 50, 150, 150, 0.9, 2],
        [10, 10, 100, 100, 0.1, 0],
    ]
    session = _FakeSession(_end_to_end_output(rows))

    monkeypatch.setattr(
        image_provider,
        "validate_model_file",
        lambda path, **kwargs: ModelValidation(
            path=path, valid=True, size=1, sha256="mocked", message="ok"
        ),
    )
    monkeypatch.setattr(image_provider, "_load_session", lambda path: session)

    report = analyze_file(source)

    assert report.supported is True
    result = report.results[0]
    assert result.status is CapabilityStatus.AVAILABLE
    assert result.data is not None
    assert result.data["model"] == MODEL_NAME
    assert result.data["width"] == 1280
    assert result.data["height"] == 720
    assert result.data["confidence_threshold"] == 0.25
    assert result.data["count"] == 3
    assert [item["class_name"] for item in result.data["detections"]] == [
        "person",
        "person",
        "car",
    ]

    assert len(session.calls) == 1
    output_names, input_feed = session.calls[0]
    assert output_names == ["output0"]
    tensor = input_feed["images"]
    assert tensor.shape == (1, 3, 640, 640)
    assert tensor.dtype == np.float32
    assert float(tensor.min()) >= 0.0
    assert float(tensor.max()) <= 1.0


@pytest.mark.skipif(not image_provider.HAS_ONNX_RUNTIME, reason="onnxruntime is not installed")
def test_object_detection_with_locally_available_model(tmp_path: Path) -> None:
    model_path = expected_model_path()
    if not validate_model_file(model_path).valid:
        pytest.skip("no verified local YOLO model available")

    source = _write_image(tmp_path / "sample.png", size=(640, 480))
    report = analyze_file(source)

    assert report.supported is True
    result = report.results[0]
    assert result.status is CapabilityStatus.AVAILABLE
    assert result.data is not None
    assert result.data["model"] == MODEL_NAME
    assert result.data["count"] == len(result.data["detections"])
    for detection in result.data["detections"]:
        assert detection["class_name"]
        assert 0.0 <= detection["confidence"] <= 1.0
        assert detection["box"]["x2"] > detection["box"]["x1"]
        assert detection["box"]["y2"] > detection["box"]["y1"]
