# Setup

fs-tool keeps its Python dependencies minimal and manages optional functionality through
[package extras](#optional-python-extras) and an explicit `fs-tool setup` command. Nothing is
installed or downloaded automatically during normal operation.

## Optional Python extras

The published package is `fs-tool-cli`. Optional format support is installed through extras:

| Extra | Installs | Used by |
|---|---|---|
| `metadata` | `pypdf>=5,<6` | PDF metadata, PDF page structure, PDF text extraction |
| `image` | `Pillow>=10`, `numpy>=1.26`, `onnxruntime>=1.18` | Image metadata and YOLO object detection |

Install an extra with:

```bash
pip install "fs-tool-cli[metadata]"
pip install "fs-tool-cli[image]"
```

From a source checkout:

```bash
uv pip install ".[metadata]"
uv pip install ".[image]"
```

Missing optional dependencies never make fs-tool fail outright. Instead, the affected capability is
reported as `unavailable` by `fs-tool capabilities`, `inspect info` and `inspect analyze`, with an
exact installation command as a next step.

ODF and OOXML text extraction (`odf_text` and `ooxml_text`) uses only the Python standard library;
it requires no extra and is available in a normal installation.

## `fs-tool capabilities`

List every supported capability and its current availability:

```bash
fs-tool capabilities
fs-tool capabilities --plain
fs-tool capabilities --json
```

JSON is the default and is the primary interface for agents. The command only checks the
environment; it does not analyze files, install packages or download resources.

### Capability statuses

| Status | Meaning |
|---|---|
| `available` | All prerequisites are present; the capability can be executed. |
| `unavailable` | The capability is supported but a prerequisite (Python package or external resource) is missing. |
| `failed` | The capability was attempted but could not complete. |

One unavailable or failed capability never prevents other available analyses from running.

Each capability result carries a stable `id`, a concise `message`, a `help` reference
(`fs-tool capabilities`) and — for failures — a stable machine-readable `error_code`.

### Example JSON response

```json
{
  "schema_version": 1,
  "success": true,
  "command": "capabilities",
  "result": {
    "capabilities": [
      {
        "id": "image_object_detection",
        "label": "Image object detection",
        "description": "Detect objects with YOLO through ONNX Runtime.",
        "provider": "image",
        "supported": true,
        "available": false,
        "status": "unavailable",
        "requirements": [
          {
            "kind": "python_package",
            "name": "onnxruntime",
            "import_name": "onnxruntime",
            "extra": "image",
            "available": false,
            "install_command": 'pip install "fs-tool-cli[image]"'
          },
          {
            "kind": "external_resource",
            "name": "yolo26n.onnx",
            "expected_path": "~/.local/share/fs-tool/models/yolo26n.onnx",
            "available": false
          }
        ],
        "missing_requirements": [...],
        "next_steps": [
          'pip install "fs-tool-cli[image]"',
          "fs-tool setup yolo"
        ],
        "setup": {
          "command": "fs-tool setup yolo"
        }
      }
    ],
    "count": 9,
    "available_count": 5,
    "model_directory": "~/.local/share/fs-tool/models/"
  },
  "errors": [],
  "warnings": [],
  "complete": true
}
```

## `fs-tool setup`

Prepare optional capabilities without changing the Python environment:

```bash
fs-tool setup pdf
fs-tool setup image
fs-tool setup yolo
fs-tool setup --all
fs-tool setup yolo --force
```

Setup never installs Python packages or modifies the active Python environment. Missing packages are
reported with exact installation commands instead. Each target is independent, so `setup --all`
keeps going when one target fails.

| Target | What it prepares |
|---|---|
| `pdf` | Checks the `pypdf` dependency (extra `metadata`) used by PDF metadata, page structure and text extraction. |
| `image` | Checks Pillow, numpy and ONNX Runtime (extra `image`) used by image metadata and object detection. Never downloads the model. |
| `yolo` | Checks the image dependencies and downloads and verifies the YOLO26n ONNX model when it is missing. |

Setup is idempotent. An existing valid model is preserved; `setup` does not re-download it. Use
`--force` with `yolo` to replace only an invalid existing model file.

Exit code 1 indicates that at least one target failed; invalid usage exits with code 2.

## YOLO model

Object detection uses the YOLO26n ONNX model. The model is **not** bundled with the Python package
and is **never** downloaded during `info`, `analyze` or `capabilities`. It is fetched only by an
explicit `fs-tool setup yolo` invocation.

| Property | Value |
|---|---|
| File | `yolo26n.onnx` |
| Source | `zwh20081/yolo26-onnx` on Hugging Face, a direct ONNX export of the official Ultralytics YOLO26 weights |
| Download URL | `https://huggingface.co/zwh20081/yolo26-onnx/resolve/main/yolo26n.onnx` (HTTPS only) |
| License | AGPL-3.0 |
| Size | 9,941,470 bytes |
| SHA-256 | `356b2726bbdba982e2a304e14b4d9a18b2726b7705b3206093d21331e4dbdd98` |

### Storage location

Models are stored in a predictable user-specific directory:

```text
~/.local/share/fs-tool/models/yolo26n.onnx
```

The directory can be overridden through the `FS_TOOL_MODEL_DIR` environment variable:

```bash
export FS_TOOL_MODEL_DIR=/mnt/models/fs-tool
fs-tool setup yolo
```

The resolved path is reported centrally by `fs-tool capabilities` under `model_directory` and by
`expected_model_path()` in the setup layer. The directory is not created until a model is downloaded.

### Download and verification

`setup yolo` streams the model to a temporary file next to its destination, verifies both the size
and the SHA-256 checksum against the pinned values above, and atomically moves it into place only
after validation succeeds. Failed or invalid downloads are removed. Existing valid models are never
overwritten; a corrupt model requires `--force` to be replaced.

If the ONNX Runtime dependency is missing, setup reports the installation command but does not
install it automatically.

## Output formats and exit codes

`fs-tool capabilities` and `fs-tool setup` support `--json` (default for pipes and agents) and
`--plain` (human-readable). Exit codes follow the [CLI exit codes](cli.md#exit-codes): 0 on
success, 1 when a setup target fails, and 2 on invalid usage.
