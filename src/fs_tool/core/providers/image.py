"""Image metadata and ONNX-based object detection provider.

Image metadata uses Pillow and belongs to ``inspect info``. Object detection
uses ONNX Runtime with the explicitly installed YOLO26n model and belongs to
``inspect analyze``. The two capabilities are independent: missing ONNX
Runtime or a missing model never prevents metadata extraction, and image
metadata never loads the model.

Detection output is deterministic for the same model and input. Boxes are
returned in original-image pixel coordinates after letterboxing is reversed.
"""

from __future__ import annotations

import importlib
import importlib.util
import math
from pathlib import Path
from typing import Any

from fs_tool.core.capabilities.models import Capability, CapabilityId
from fs_tool.core.errors import ErrorCode, FsToolError
from fs_tool.core.providers.base import Provider, capabilities_from_registry
from fs_tool.setup.models import (
    YOLO_MODEL_FILENAME,
    expected_model_path,
    validate_model_file,
)

#: Square input size expected by the supported YOLO26n ONNX export.
MODEL_INPUT_SIZE = 640

#: Minimum confidence accepted for a detection.
CONFIDENCE_THRESHOLD = 0.25

#: Ultralytics letterbox padding colour.
PADDING_COLOR = (114, 114, 114)

# Optional dependencies are detected without importing them, so normal
# inspection stays lightweight when the ``[image]`` extra is not installed.
HAS_PILLOW = importlib.util.find_spec("PIL") is not None
HAS_NUMPY = importlib.util.find_spec("numpy") is not None
HAS_ONNX_RUNTIME = importlib.util.find_spec("onnxruntime") is not None

# Standard COCO class names, in model class-id order.
COCO_CLASS_NAMES = (
    "person",
    "bicycle",
    "car",
    "motorcycle",
    "airplane",
    "bus",
    "train",
    "truck",
    "boat",
    "traffic light",
    "fire hydrant",
    "stop sign",
    "parking meter",
    "bench",
    "bird",
    "cat",
    "dog",
    "horse",
    "sheep",
    "cow",
    "elephant",
    "bear",
    "zebra",
    "giraffe",
    "backpack",
    "umbrella",
    "handbag",
    "tie",
    "suitcase",
    "frisbee",
    "skis",
    "snowboard",
    "sports ball",
    "kite",
    "baseball bat",
    "baseball glove",
    "skateboard",
    "surfboard",
    "tennis racket",
    "bottle",
    "wine glass",
    "cup",
    "fork",
    "knife",
    "spoon",
    "bowl",
    "banana",
    "apple",
    "sandwich",
    "orange",
    "broccoli",
    "carrot",
    "hot dog",
    "pizza",
    "donut",
    "cake",
    "chair",
    "couch",
    "potted plant",
    "bed",
    "dining table",
    "toilet",
    "tv",
    "laptop",
    "mouse",
    "remote",
    "keyboard",
    "cell phone",
    "microwave",
    "oven",
    "toaster",
    "sink",
    "refrigerator",
    "book",
    "clock",
    "vase",
    "scissors",
    "teddy bear",
    "hair drier",
    "toothbrush",
)

_SESSION_CACHE: dict[tuple[str, int, int], Any] = {}


def _json_safe(value: Any) -> Any:
    """Convert an EXIF value to a deterministic JSON-safe value."""
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    if isinstance(value, tuple | list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return number if math.isfinite(number) else str(value)


def letterbox_image(image: Any, *, size: int = MODEL_INPUT_SIZE) -> tuple[Any, float, float, float]:
    """Resize an image into ``size`` x ``size`` while preserving aspect ratio.

    Returns the padded image, the applied scale and the left/top padding in
    model-input pixels. The padding is recorded as integers because that is
    how Pillow pastes the resized image.
    """
    pil_image = importlib.import_module("PIL.Image")
    width, height = image.size
    if width <= 0 or height <= 0:
        raise FsToolError("Image has invalid dimensions.", code=ErrorCode.CAPABILITY_FAILED)

    scale = min(size / width, size / height)
    resized_width = max(1, round(width * scale))
    resized_height = max(1, round(height * scale))
    resized = image.resize(
        (resized_width, resized_height),
        resample=pil_image.Resampling.BILINEAR,
    )
    canvas = pil_image.new("RGB", (size, size), PADDING_COLOR)
    pad_x = round((size - resized_width) / 2)
    pad_y = round((size - resized_height) / 2)
    canvas.paste(resized, (pad_x, pad_y))
    return canvas, scale, float(pad_x), float(pad_y)


def prepare_input(
    image: Any,
    *,
    size: int = MODEL_INPUT_SIZE,
) -> tuple[Any, float, float, float]:
    """Convert an image to a ``[1, 3, size, size]`` float32 tensor.

    Pixel values are normalized to the 0-1 range expected by the model.
    """
    if not HAS_NUMPY:
        raise FsToolError(
            "Image object detection requires the optional numpy package.",
            code=ErrorCode.CAPABILITY_UNAVAILABLE,
        )
    numpy = importlib.import_module("numpy")
    letterboxed, scale, pad_x, pad_y = letterbox_image(image, size=size)
    array = numpy.asarray(letterboxed, dtype=numpy.float32) / 255.0
    tensor = numpy.ascontiguousarray(array.transpose(2, 0, 1)[None, ...])
    return tensor, scale, pad_x, pad_y


def detections_from_output(
    output: Any,
    *,
    scale: float,
    pad_x: float,
    pad_y: float,
    image_width: int,
    image_height: int,
    confidence_threshold: float = CONFIDENCE_THRESHOLD,
) -> list[dict[str, Any]]:
    """Convert raw end-to-end YOLO output rows to structured detections.

    Rows use the verified contract ``[x1, y1, x2, y2, confidence, class_id]``
    in model-input coordinates. Boxes are mapped back to original-image pixel
    coordinates, clipped to the image and sorted deterministically.
    """
    if not HAS_NUMPY:
        raise FsToolError(
            "Image object detection requires the optional numpy package.",
            code=ErrorCode.CAPABILITY_UNAVAILABLE,
        )
    numpy = importlib.import_module("numpy")
    array = numpy.asarray(output, dtype=numpy.float32)
    if array.ndim == 3:
        array = array[0]
    if array.ndim != 2 or array.shape[1] < 6:
        raise FsToolError(
            "Unexpected YOLO output shape.",
            code=ErrorCode.CAPABILITY_FAILED,
            details={"shape": list(array.shape)},
        )
    if scale <= 0:
        raise FsToolError("Invalid image scaling factor.", code=ErrorCode.CAPABILITY_FAILED)

    detections: list[dict[str, Any]] = []
    for row in array:
        confidence = float(row[4])
        if not math.isfinite(confidence) or confidence < confidence_threshold:
            continue
        x1 = (float(row[0]) - pad_x) / scale
        y1 = (float(row[1]) - pad_y) / scale
        x2 = (float(row[2]) - pad_x) / scale
        y2 = (float(row[3]) - pad_y) / scale
        x1 = min(max(x1, 0.0), float(image_width))
        y1 = min(max(y1, 0.0), float(image_height))
        x2 = min(max(x2, 0.0), float(image_width))
        y2 = min(max(y2, 0.0), float(image_height))
        if x2 <= x1 or y2 <= y1:
            continue
        class_id = int(round(float(row[5])))
        class_name = (
            COCO_CLASS_NAMES[class_id]
            if 0 <= class_id < len(COCO_CLASS_NAMES)
            else f"class_{class_id}"
        )
        detections.append(
            {
                "class_id": class_id,
                "class_name": class_name,
                "confidence": round(confidence, 4),
                "box": {
                    "x1": round(x1, 2),
                    "y1": round(y1, 2),
                    "x2": round(x2, 2),
                    "y2": round(y2, 2),
                },
            }
        )

    detections.sort(
        key=lambda item: (
            -item["confidence"],
            item["class_id"],
            item["box"]["x1"],
            item["box"]["y1"],
            item["box"]["x2"],
            item["box"]["y2"],
        )
    )
    return detections


def _load_session(path: Path) -> Any:
    """Load and cache an ONNX Runtime session for one model file version."""
    stat = path.stat()
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    cached = _SESSION_CACHE.get(key)
    if cached is not None:
        return cached
    onnxruntime = importlib.import_module("onnxruntime")
    session = onnxruntime.InferenceSession(
        str(path),
        providers=["CPUExecutionProvider"],
    )
    _SESSION_CACHE[key] = session
    return session


class ImageProvider(Provider):
    """Provider for image metadata and YOLO object detection."""

    _CAPABILITY_IDS = (
        CapabilityId.IMAGE_METADATA,
        CapabilityId.IMAGE_OBJECT_DETECTION,
    )

    @property
    def id(self) -> str:
        return "image"

    @property
    def capabilities(self) -> tuple[Capability, ...]:
        return capabilities_from_registry(self.id, self._CAPABILITY_IDS)

    def supported_extensions(self) -> tuple[str, ...]:
        return (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff", ".webp")

    def metadata_capability(self) -> CapabilityId:
        return CapabilityId.IMAGE_METADATA

    def analysis_capabilities(self) -> tuple[CapabilityId, ...]:
        return (CapabilityId.IMAGE_OBJECT_DETECTION,)

    def extract_metadata(self, path: Path) -> dict[str, Any] | None:
        if not HAS_PILLOW:
            raise FsToolError(
                "Image metadata extraction requires the optional Pillow package.",
                code=ErrorCode.CAPABILITY_UNAVAILABLE,
                path=str(path),
            )
        image_module = importlib.import_module("PIL.Image")
        exif_tags = importlib.import_module("PIL.ExifTags")
        try:
            with image_module.open(path) as image:
                width, height = image.size
                mode = image.mode
                image_format = image.format.lower() if image.format else None
                exif: dict[str, Any] = {}
                try:
                    for tag, value in image.getexif().items():
                        name = exif_tags.TAGS.get(tag, str(tag))
                        exif[name] = _json_safe(value)
                except Exception:
                    # Malformed EXIF must not hide otherwise usable metadata.
                    exif = {}
        except Exception as exc:
            raise FsToolError(
                "Cannot read image metadata.",
                code=ErrorCode.CAPABILITY_FAILED,
                path=str(path),
            ) from exc
        return {
            "format": image_format,
            "width": width,
            "height": height,
            "mode": mode,
            "exif": dict(sorted(exif.items())),
        }

    def analyze(self, capability: CapabilityId, path: Path) -> dict[str, Any]:
        if capability is not CapabilityId.IMAGE_OBJECT_DETECTION:
            raise NotImplementedError(f"image does not implement {capability.value}")
        return self._detect_objects(path)

    def _detect_objects(self, path: Path) -> dict[str, Any]:
        if not HAS_ONNX_RUNTIME:
            raise FsToolError(
                "Image object detection requires the optional onnxruntime package.",
                code=ErrorCode.CAPABILITY_UNAVAILABLE,
                path=str(path),
            )
        if not HAS_NUMPY:
            raise FsToolError(
                "Image object detection requires the optional numpy package.",
                code=ErrorCode.CAPABILITY_UNAVAILABLE,
                path=str(path),
            )
        if not HAS_PILLOW:
            raise FsToolError(
                "Image object detection requires the optional Pillow package.",
                code=ErrorCode.CAPABILITY_UNAVAILABLE,
                path=str(path),
            )

        model_path = expected_model_path()
        if not model_path.is_file():
            raise FsToolError(
                "YOLO model is missing. Run `fs-tool capabilities` for setup instructions.",
                code=ErrorCode.RESOURCE_NOT_FOUND,
                path=str(model_path),
            )
        validation = validate_model_file(model_path)
        if not validation.valid:
            raise FsToolError(
                f"YOLO model is invalid: {validation.message}",
                code=ErrorCode.RESOURCE_CORRUPT,
                path=str(model_path),
            )

        try:
            session = _load_session(model_path)
            image_module = importlib.import_module("PIL.Image")
            with image_module.open(path) as image:
                rgb = image.convert("RGB")
                width, height = rgb.size
                tensor, scale, pad_x, pad_y = prepare_input(rgb)
            input_name = session.get_inputs()[0].name
            output_name = session.get_outputs()[0].name
            outputs = session.run([output_name], {input_name: tensor})
            detections = detections_from_output(
                outputs[0],
                scale=scale,
                pad_x=pad_x,
                pad_y=pad_y,
                image_width=width,
                image_height=height,
            )
        except FsToolError:
            raise
        except Exception as exc:
            raise FsToolError(
                "Image object detection failed.",
                code=ErrorCode.CAPABILITY_FAILED,
                path=str(path),
            ) from exc

        return {
            "model": YOLO_MODEL_FILENAME,
            "width": width,
            "height": height,
            "confidence_threshold": CONFIDENCE_THRESHOLD,
            "count": len(detections),
            "detections": detections,
        }
