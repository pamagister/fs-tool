"""Model storage, validation and safe download helpers.

The YOLO model is an external resource: it is never bundled with the package,
never downloaded during ``info`` or ``analyze``, and only fetched by an explicit
setup invocation. Every download is streamed to a temporary file next to its
destination and accepted only after its size and SHA-256 checksum match the
values documented here.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from fs_tool.core.capabilities.models import resolve_model_dir
from fs_tool.core.errors import ErrorCode, FsToolError

#: File name of the supported YOLO26 detection model.
YOLO_MODEL_FILENAME = "yolo26n.onnx"

#: Documented download location (HTTPS only).
YOLO_MODEL_URL = "https://huggingface.co/zwh20081/yolo26-onnx/resolve/main/yolo26n.onnx"

#: Upstream repository and license of the model file.
YOLO_MODEL_SOURCE = "zwh20081/yolo26-onnx (Hugging Face)"
YOLO_MODEL_LICENSE = "AGPL-3.0"

#: Verified size and SHA-256 checksum of the model file.
YOLO_MODEL_SIZE = 9_941_470
YOLO_MODEL_SHA256 = "356b2726bbdba982e2a304e14b4d9a18b2726b7705b3206093d21331e4dbdd98"

#: Streaming chunk size for checksumming and downloading.
CHUNK_SIZE = 1024 * 1024

Opener = Callable[[Request], Any]


@dataclass(frozen=True)
class ModelValidation:
    """Outcome of validating an external model file."""

    path: Path
    valid: bool
    size: int | None
    sha256: str | None
    message: str


@dataclass(frozen=True)
class SetupResult:
    """Outcome of preparing an external resource."""

    capability: str
    path: Path
    status: str
    message: str


def expected_model_path(model_dir: Path | None = None) -> Path:
    """Return the expected location of the YOLO model.

    ``model_dir`` defaults to the centrally resolved model directory, which
    honors ``FS_TOOL_MODEL_DIR``.
    """
    base = model_dir if model_dir is not None else resolve_model_dir()
    return base / YOLO_MODEL_FILENAME


def _hash_file(path: Path) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_SIZE):
            size += len(chunk)
            digest.update(chunk)
    return size, digest.hexdigest()


def validate_model_file(
    path: Path,
    *,
    expected_sha256: str = YOLO_MODEL_SHA256,
    expected_size: int = YOLO_MODEL_SIZE,
) -> ModelValidation:
    """Validate an existing model file without modifying it.

    A missing or unreadable file, an unexpected size or a checksum mismatch
    produces an invalid result with an actionable message.
    """
    if not path.is_file():
        return ModelValidation(
            path=path,
            valid=False,
            size=None,
            sha256=None,
            message="Model file not found.",
        )
    try:
        size, sha256 = _hash_file(path)
    except OSError:
        return ModelValidation(
            path=path,
            valid=False,
            size=None,
            sha256=None,
            message="Model file cannot be read.",
        )
    if size != expected_size:
        return ModelValidation(
            path=path,
            valid=False,
            size=size,
            sha256=sha256,
            message=f"Model size mismatch: expected {expected_size} bytes, found {size}.",
        )
    if sha256 != expected_sha256:
        return ModelValidation(
            path=path,
            valid=False,
            size=size,
            sha256=sha256,
            message="Model checksum mismatch.",
        )
    return ModelValidation(
        path=path,
        valid=True,
        size=size,
        sha256=sha256,
        message="Model file is valid.",
    )


def download_model(
    destination: Path,
    *,
    url: str = YOLO_MODEL_URL,
    expected_sha256: str = YOLO_MODEL_SHA256,
    expected_size: int = YOLO_MODEL_SIZE,
    opener: Opener | None = None,
) -> ModelValidation:
    """Download and verify a model, then move it into place atomically.

    Only HTTPS URLs are accepted. The response is streamed to a temporary file
    in the destination directory; the destination is replaced only after the
    size and checksum have been verified. Failed or invalid downloads are
    removed.
    """
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise FsToolError(
            "Model downloads require an HTTPS URL.",
            code=ErrorCode.SETUP_FAILED,
            path=str(destination),
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    open_url = opener if opener is not None else urlopen
    request = Request(url, headers={"User-Agent": "fs-tool"})
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".part",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            digest = hashlib.sha256()
            size = 0
            with closing(open_url(request)) as response:
                while chunk := response.read(CHUNK_SIZE):
                    size += len(chunk)
                    if size > expected_size:
                        raise FsToolError(
                            "Downloaded model exceeds the expected size.",
                            code=ErrorCode.RESOURCE_CORRUPT,
                            path=str(destination),
                        )
                    digest.update(chunk)
                    handle.write(chunk)

        validation = validate_model_file(
            temporary,
            expected_sha256=expected_sha256,
            expected_size=expected_size,
        )
        if not validation.valid:
            raise FsToolError(
                f"Downloaded model failed validation: {validation.message}",
                code=ErrorCode.RESOURCE_CORRUPT,
                path=str(destination),
                details={"expected_sha256": expected_sha256, "expected_size": expected_size},
            )
        os.replace(temporary, destination)
        temporary = None
        return ModelValidation(
            path=destination,
            valid=True,
            size=expected_size,
            sha256=expected_sha256,
            message="Model downloaded and verified.",
        )
    except FsToolError:
        raise
    except Exception as exc:
        raise FsToolError(
            f"Cannot download model: {exc}",
            code=ErrorCode.SETUP_FAILED,
            path=str(destination),
        ) from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
