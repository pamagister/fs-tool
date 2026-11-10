"""Tests for model validation, safe download and the YOLO setup handler.

Downloads are fully mocked: the test suite never requires network access.
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path
from urllib.request import Request

import pytest

from fs_tool.core.errors import ErrorCode, FsToolError
from fs_tool.setup.models import (
    download_model,
    expected_model_path,
    validate_model_file,
)
from fs_tool.setup.yolo import setup_yolo

PAYLOAD = b"small fake ONNX model payload"
PAYLOAD_SHA256 = hashlib.sha256(PAYLOAD).hexdigest()


class _FakeResponse(io.BytesIO):
    """Minimal response object accepted by ``contextlib.closing``."""


@pytest.fixture
def fake_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the YOLO handler at the small fake payload."""
    monkeypatch.setattr("fs_tool.setup.yolo.YOLO_MODEL_URL", "https://example.test/yolo26n.onnx")
    monkeypatch.setattr("fs_tool.setup.yolo.YOLO_MODEL_SIZE", len(PAYLOAD))
    monkeypatch.setattr("fs_tool.setup.yolo.YOLO_MODEL_SHA256", PAYLOAD_SHA256)


def _opener(payload: bytes) -> object:
    def open_url(request: Request) -> _FakeResponse:
        assert request.full_url.startswith("https://")
        return _FakeResponse(payload)

    return open_url


def test_expected_model_path_defaults_to_resolved_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("FS_TOOL_MODEL_DIR", str(tmp_path))
    assert expected_model_path() == tmp_path / "yolo26n.onnx"
    other = tmp_path / "other"
    assert expected_model_path(other) == other / "yolo26n.onnx"


def test_validate_model_file_missing(tmp_path: Path) -> None:
    validation = validate_model_file(tmp_path / "missing.onnx")
    assert validation.valid is False
    assert validation.size is None
    assert validation.sha256 is None
    assert "not found" in validation.message


def test_validate_model_file_accepts_valid_file(tmp_path: Path) -> None:
    model = tmp_path / "model.onnx"
    model.write_bytes(PAYLOAD)
    validation = validate_model_file(
        model,
        expected_sha256=PAYLOAD_SHA256,
        expected_size=len(PAYLOAD),
    )
    assert validation.valid is True
    assert validation.size == len(PAYLOAD)
    assert validation.sha256 == PAYLOAD_SHA256


def test_validate_model_file_rejects_wrong_size_and_checksum(tmp_path: Path) -> None:
    model = tmp_path / "model.onnx"
    model.write_bytes(PAYLOAD)

    wrong_size = validate_model_file(
        model,
        expected_sha256=PAYLOAD_SHA256,
        expected_size=len(PAYLOAD) + 1,
    )
    assert wrong_size.valid is False
    assert "size mismatch" in wrong_size.message

    wrong_hash = validate_model_file(
        model,
        expected_sha256="0" * 64,
        expected_size=len(PAYLOAD),
    )
    assert wrong_hash.valid is False
    assert "checksum mismatch" in wrong_hash.message


def test_setup_yolo_preserves_existing_valid_model(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake_model: None
) -> None:
    model = tmp_path / "yolo26n.onnx"
    model.write_bytes(PAYLOAD)

    def fail_opener(request: Request) -> _FakeResponse:
        raise AssertionError("setup must not download a valid model")

    result = setup_yolo(model_dir=tmp_path, opener=fail_opener)
    assert result.status == "already-present"
    assert result.path == model
    assert model.read_bytes() == PAYLOAD


def test_setup_yolo_refuses_invalid_existing_model_without_force(
    tmp_path: Path, fake_model: None
) -> None:
    model = tmp_path / "yolo26n.onnx"
    model.write_bytes(b"broken")

    with pytest.raises(FsToolError) as exc_info:
        setup_yolo(model_dir=tmp_path, opener=_opener(PAYLOAD))
    assert exc_info.value.code is ErrorCode.RESOURCE_CORRUPT
    assert exc_info.value.path == str(model)
    assert model.read_bytes() == b"broken"


def test_setup_yolo_downloads_via_default_model_dir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, fake_model: None
) -> None:
    monkeypatch.setenv("FS_TOOL_MODEL_DIR", str(tmp_path))
    result = setup_yolo(opener=_opener(PAYLOAD))
    model = tmp_path / "yolo26n.onnx"
    assert result.status == "downloaded"
    assert result.path == model
    assert model.read_bytes() == PAYLOAD
    assert [item.name for item in tmp_path.iterdir()] == ["yolo26n.onnx"]


def test_setup_yolo_force_replaces_invalid_model(tmp_path: Path, fake_model: None) -> None:
    model = tmp_path / "yolo26n.onnx"
    model.write_bytes(b"broken")

    result = setup_yolo(model_dir=tmp_path, force=True, opener=_opener(PAYLOAD))
    assert result.status == "downloaded"
    assert model.read_bytes() == PAYLOAD


def test_download_model_rejects_non_https_url(tmp_path: Path) -> None:
    with pytest.raises(FsToolError) as exc_info:
        download_model(
            tmp_path / "model.onnx",
            url="http://example.test/model.onnx",
            expected_sha256=PAYLOAD_SHA256,
            expected_size=len(PAYLOAD),
            opener=_opener(PAYLOAD),
        )
    assert exc_info.value.code is ErrorCode.SETUP_FAILED
    assert not (tmp_path / "model.onnx").exists()


def test_download_model_rejects_checksum_mismatch_and_cleans_up(tmp_path: Path) -> None:
    destination = tmp_path / "model.onnx"
    with pytest.raises(FsToolError) as exc_info:
        download_model(
            destination,
            url="https://example.test/model.onnx",
            expected_sha256="0" * 64,
            expected_size=len(PAYLOAD),
            opener=_opener(PAYLOAD),
        )
    assert exc_info.value.code is ErrorCode.RESOURCE_CORRUPT
    assert not destination.exists()
    assert list(tmp_path.iterdir()) == []


def test_download_model_wraps_transport_errors(tmp_path: Path) -> None:
    def failing_opener(request: Request) -> _FakeResponse:
        raise OSError("connection refused")

    with pytest.raises(FsToolError) as exc_info:
        download_model(
            tmp_path / "model.onnx",
            url="https://example.test/model.onnx",
            expected_sha256=PAYLOAD_SHA256,
            expected_size=len(PAYLOAD),
            opener=failing_opener,
        )
    assert exc_info.value.code is ErrorCode.SETUP_FAILED
    assert list(tmp_path.iterdir()) == []
