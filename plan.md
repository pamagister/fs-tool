# fs-tool – File Intelligence & Capability Management

## 1. Mission

Extend fs-tool with a modular, extensible and agent-friendly architecture for file metadata extraction, structured content analysis and optional analysis capabilities.

The implementation introduces three clearly separated inspection functions:

1. `info`: filesystem and format-specific metadata.
2. `analyze`: structured information about file contents and internal structure.
3. `read`: actual file content or an explicitly defined textual representation of supported formats.

Additionally, introduce a central capability management system that allows users and AI agents to discover supported functionality, inspect availability and prepare optional resources.

The central design principle remains:

> The agent makes decisions; fs-tool provides reliable information and executes filesystem operations safely and deterministically.

The implementation must remain lightweight, modular, secure and independent of any particular AI agent or automation framework.

---

## 2. Scope

### 2.1 In Scope

- Separate metadata extraction from content analysis.
- Introduce a common architecture for file-format-specific analysis providers.
- Support structured analysis of PDF, Markdown, Python, image and text files.
- Introduce a central capability registry.
- Introduce `fs-tool capabilities`.
- Introduce `fs-tool setup <capability>` and `fs-tool setup --all`.
- Support optional Python dependencies through package extras.
- Support external resources such as ONNX models.
- Introduce consistent availability and failure reporting.
- Support optional source-file hashing in `info` and `analyze`.
- Extend `read` to support PDF text extraction, keeping extracted text separate from metadata and structural analysis.
- Document architecture, installation, setup and usage.
- Add comprehensive automated tests.

### 2.2 Out of Scope

The following are explicitly not part of this implementation:

- Automatic installation of Python packages or modification of the active Python environment.
- Automatic downloading of models during `info`, `analyze` or `capabilities`.
- Automatic execution of analyzed files, scripts, macros or embedded content.
- General-purpose OCR implementation.
- Audio or video analysis.
- LLM-based semantic interpretation of documents.
- A generic third-party plugin framework.
- Automatic deletion, modification or restructuring of analyzed files.
- A GUI or MCP integration.

The architecture should permit future extensions without implementing them now.

---

## 3. Architectural Decisions

These decisions govern the implementation.

### D1 – Separation of inspection responsibilities

The responsibilities are:

| Command | Responsibility |
|---|---|
| `inspect info` | Filesystem and format-specific metadata |
| `inspect analyze` | Structured content and document analysis |
| `inspect read` | Actual textual content or supported textual representations |
| `inspect tree` | Directory tree |
| `inspect inventory` | Filesystem inventory |

`tree` and `inventory` remain functionally unchanged.

`read` remains independent of `info` and `analyze`. It must not become a general-purpose analysis command.

### D2 – Metadata versus analysis

Three information categories must remain conceptually distinct:

| Category | Description | Examples |
|---|---|---|
| Filesystem information | Properties of the filesystem entry | Size, timestamps, permissions, MIME type |
| Format metadata | Descriptive properties stored in the file format | PDF author, document title, EXIF data, image dimensions |
| Analysis | Information obtained by interpreting file contents | PDF page structure, Python AST, detected image objects |

Format metadata belongs to `info`.

Structured content analysis belongs to `analyze`.

Extracted textual content belongs to `read`.

### D3 – Common provider architecture

Introduce a modular architecture for format-specific information extraction and analysis.

Providers declare:

- Supported file formats.
- Available capabilities.
- Required Python packages.
- Required external resources.
- Capability identifiers.
- Availability checks.
- Analysis implementations.

A provider may expose multiple independent capabilities.

Example:

```text
ImageProvider
├── image_metadata
│   └── Requirements: Pillow
│
└── image_object_detection
    ├── Requirements: Pillow
    ├── Requirements: ONNX Runtime
    └── Requirements: yolo26n.onnx
```

The architecture must not require the CLI to know implementation details of individual file formats.

Use an explicit internal registry. Do not introduce a dynamic plugin-loading framework.

### D4 – Central capability registry

All supported capabilities and their requirements must be described centrally.

The same capability definitions must be used by:

- `info`
- `analyze`
- `capabilities`
- `setup`

Avoid maintaining separate and potentially inconsistent dependency or availability checks.

The capability system must distinguish:

- Supported functionality.
- Installed dependencies.
- Available external resources.
- Actual runtime availability.

### D5 – Optional dependencies and setup

Python dependencies are managed by the package manager.

External resources such as ONNX models may be managed by fs-tool.

Examples:

```bash
uv pip install "fs-tool-cli[pdf]"
uv pip install "fs-tool-cli[image]"
```

The actual distribution name is `fs-tool-cli`; documentation must use the correct package name.

`fs-tool setup` must never silently install Python packages or modify the active Python environment.

If a Python dependency is missing, setup reports the appropriate installation command.

External resources may be downloaded only through an explicit setup invocation.

### D6 – Capability availability and result status

Every applicable analysis result must explicitly communicate its status.

Use at least these states:

| Status | Meaning |
|---|---|
| `available` | Analysis was successfully performed |
| `unavailable` | Analysis is supported but a prerequisite is missing |
| `failed` | Analysis was attempted but could not be completed |

Unsupported formats or capabilities must be distinguishable from unavailable capabilities.

Unavailable results must never be silently omitted.

Each result must contain a stable capability identifier and a concise message. Detailed setup instructions belong in the central capability output.

Example:

```json
{
  "objects": {
    "status": "unavailable",
    "capability": "image_object_detection",
    "message": "Object detection is not available.",
    "help": "fs-tool capabilities"
  }
}
```

For failed analyses, include a stable machine-readable error code and a useful diagnostic reference.

Other available analyses must continue even if one capability is unavailable or fails.

Optional capability unavailability must not automatically turn the entire CLI invocation into a fatal command error.

### D7 – Hash semantics

`--hash` always identifies the original source file.

It must not hash metadata, analysis output or serialized JSON.

Examples:

```bash
fs-tool inspect info document.pdf --hash
fs-tool inspect analyze document.pdf --hash
```

Both commands must return the same SHA-256 value if the source file has not changed.

No separate result hash is required.

### D8 – Model storage

Use a predictable user-specific model directory:

```text
~/.local/share/fs-tool/models/
```

Initial YOLO model:

```text
~/.local/share/fs-tool/models/yolo26n.onnx
```

Support overriding the directory through:

```text
FS_TOOL_MODEL_DIR
```

The actual path must be resolved centrally and exposed through `capabilities`.

The model must not be included in the Python package or downloaded automatically during normal operation.

### D9 – Documentation is part of the architecture

`docs/develop/architecture.md` must be updated as an integral part of this implementation.

It must describe:

- Provider architecture.
- Capability registry.
- Capability lifecycle and availability checks.
- Separation of metadata, analysis and content reading.
- Setup responsibilities.
- Optional dependencies and external resources.
- Model storage and configuration.
- Result status and error reporting.
- Data flow between core, CLI and output layers.

The architecture documentation must reflect the implemented system, not merely describe the original proposal.

### D10 – Compatibility and output conventions

Preserve the existing JSON envelope and its general semantics.

Preserve the existing `inspect` command hierarchy.

Existing `inspect info --hash` behavior must remain available.

The existing `--metadata` option must be reviewed: because format metadata becomes the normal responsibility of `info`, extraction should no longer require this flag. Retain it temporarily as a documented compatibility option if practical, without maintaining two different extraction paths.

Keep Plain and JSON output consistent with the existing output architecture.

---

## 4. Target Functionality

### 4.1 `info` – Filesystem and Format Metadata

Example:

```bash
fs-tool inspect info document.pdf
fs-tool inspect info image.jpg --hash
```

General filesystem information remains based on `FilesystemEntry`.

Format-specific metadata is extracted automatically when supported and available.

Initial formats:

| Format | Metadata |
|---|---|
| PDF | Author, title, subject, creation date, modification date, page count where appropriate |
| ODF | Existing metadata fields |
| OOXML | Existing metadata fields |
| Image | Format, width, height, color mode, EXIF information where available |
| Text | Encoding and other inexpensive format properties where reliably detectable |

ODF and OOXML extraction should continue to use standard-library functionality where practical.

PDF support uses the optional PDF dependency.

Image metadata uses the optional image dependency.

Missing optional dependencies must be reported through the common capability mechanism.

Existing size limits and archive safety checks must be retained.

### 4.2 `analyze` – Structured Content Analysis

Example:

```bash
fs-tool inspect analyze document.pdf
fs-tool inspect analyze image.jpg
fs-tool inspect analyze source.py --hash
```

An invocation without additional analysis-selection flags performs all applicable, currently available analyses.

The default behavior must remain conservative: analyze structure and derive useful information without returning the complete file content.

Initial analysis capabilities:

| Format | Analysis results |
|---|---|
| PDF | Page count, page structure, page dimensions and orientation where available |
| Markdown | Headings and document structure |
| Python | AST, classes, functions, imports |
| Image | Object detection, recognized classes, bounding boxes and confidence scores |
| Text | Line count, paragraph count and simple structural information |

#### PDF

Do not return extracted full text through `analyze`.

Page-level structural information belongs here.

Text extraction belongs to `read`.

#### Markdown

Extract heading hierarchy and structural information.

Do not return the complete Markdown document.

#### Python

Reuse and integrate the existing AST analysis in `core/analysis/python_analysis.py`.

Do not import or execute analyzed Python files.

#### Images

Provide inexpensive image information separately from object detection.

Object detection uses YOLO through ONNX Runtime.

Return structured detections, including:

- Class index.
- Class name.
- Confidence.
- Bounding box.

Model absence must not prevent other image analysis from running.

#### Text files

Provide inexpensive structural information without returning the actual text.

Avoid duplicating `read`.

### 4.3 `read` – Actual Content

Preserve the existing bounded UTF-8 text-reading behavior.

Extend it to support PDF text extraction through the optional PDF dependency.

PDF extraction must:

- Return textual content, not metadata.
- Clearly identify the source format and returned content representation.
- Preserve page boundaries where practical.
- Respect size and resource limits.
- Report unavailable extraction when the required dependency is missing.

Do not return binary file contents by default.

Keep existing symlink restrictions, allowed-root validation and maximum-byte behavior.

### 4.4 `tree` and `inventory`

No functional changes are intended.

Only shared internal model changes that are strictly necessary may affect these commands.

Regression tests must prove that their existing behavior remains intact.

---

## 5. Capability Management CLI

### 5.1 `capabilities`

Introduce a top-level command:

```bash
fs-tool capabilities
fs-tool capabilities --json
```

The command lists supported capabilities and their current availability.

JSON is the primary agent interface.

Example:

```json
{
  "schema_version": 1,
  "success": true,
  "command": "capabilities",
  "result": {
    "capabilities": [
      {
        "id": "image_object_detection",
        "supported": true,
        "available": false,
        "requirements": {
          "python_package": {
            "name": "onnxruntime",
            "extra": "image",
            "available": false
          },
          "model": {
            "name": "yolo26n.onnx",
            "available": false,
            "expected_path": "~/.local/share/fs-tool/models/yolo26n.onnx"
          }
        },
        "setup": {
          "command": "fs-tool setup yolo"
        }
      }
    ]
  },
  "errors": [],
  "warnings": [],
  "complete": true
}
```

The actual schema must be designed consistently with the existing output envelope.

Requirements:

- Stable capability identifiers.
- Explicit supported/available state.
- Machine-readable missing requirements.
- Exact model paths.
- Concrete installation instructions.
- Setup commands where applicable.
- Human-readable Plain output.
- Deterministic ordering.

The output must not expose unnecessary environment or personal information.

### 5.2 `setup`

Introduce a top-level command:

```bash
fs-tool setup yolo
fs-tool setup pdf
fs-tool setup --all
```

Responsibilities:

- Check relevant Python dependencies.
- Report missing dependencies and exact package installation instructions.
- Download and prepare explicitly supported external resources.
- Verify downloaded resources.
- Store resources in the configured model directory.
- Report final capability availability.

Setup must be idempotent.

It must not overwrite a valid existing model without explicit authorization.

`setup --all` must process all known setup-capable resources without installing Python packages.

Capabilities that require no setup must be skipped or reported as already available.

Missing Python dependencies must not prevent unrelated model setup tasks.

#### YOLO setup

`fs-tool setup yolo` must:

1. Check the configured model directory.
2. Check whether a valid model already exists.
3. If necessary, download the model from a documented and trusted source.
4. Verify the downloaded file using a pinned checksum.
5. Store it at the documented location.
6. Verify that the model can be loaded when the required runtime is installed.
7. Report the final availability status.

Before implementation, establish:

- The authoritative model source.
- Model version and provenance.
- License and redistribution conditions.
- SHA-256 checksum.
- Expected ONNX input and output format.
- Compatibility with the selected ONNX Runtime.

Do not invent or assume these details.

If the runtime dependency is missing, provide the installation instructions. Do not install it automatically.

---

## 6. Proposed Internal Architecture

The existing architecture should be extended incrementally.

Possible target structure:

```text
src/fs_tool/
├── cli.py
├── __main__.py
├── core/
│   ├── config.py
│   ├── errors.py
│   ├── filesystem.py
│   ├── hashing.py
│   ├── metadata.py
│   ├── models.py
│   ├── traversal.py
│   ├── capabilities/
│   │   ├── registry.py
│   │   ├── models.py
│   │   └── availability.py
│   ├── providers/
│   │   ├── registry.py
│   │   ├── pdf.py
│   │   ├── markdown.py
│   │   ├── text.py
│   │   └── image.py
│   └── analysis/
│       ├── search.py
│       ├── duplicates.py
│       ├── comparison.py
│       ├── verification.py
│       └── python_analysis.py
├── setup/
│   ├── models.py
│   └── yolo.py
├── operations/
├── output/
└── safety/
```

This is a conceptual target, not a requirement to create every module exactly as shown.

Avoid unnecessary indirection.

The existing Python analysis and metadata implementations should be reused where possible.

### Architectural boundaries

- Core providers must not import Typer or CLI code.
- Core analysis must not format JSON or Plain output.
- Capability availability must be independent of output formatting.
- Setup handlers must not be embedded in CLI command functions.
- File-format-specific code must remain isolated.
- Model storage and download logic must be centralized.
- Safety validation must be reused rather than bypassed.

---

## 7. Implementation Phases

### Phase 1 – Architecture and Data Model

**Objective:** Establish the common architecture before adding additional format implementations.

- [x] P1-W01: Review existing `FilesystemEntry`, metadata extraction, Python analysis and output models.
- [x] P1-W02: Define the internal provider interface.
- [x] P1-W03: Define capability identifiers and capability model.
- [x] P1-W04: Define the central registry.
- [x] P1-W05: Define dependency and external-resource requirements.
- [x] P1-W06: Define the availability-checking mechanism.
- [x] P1-W07: Define result models for `available`, `unavailable` and `failed`.
- [x] P1-W08: Define stable error codes and diagnostic references.
- [x] P1-W09: Update `docs/develop/architecture.md` with the approved architecture.
- [x] P1-W10: Add focused unit tests for the registry and availability mechanism.

**Acceptance criteria**

- Providers can declare multiple independent capabilities.
- Capability definitions are available centrally.
- Availability checks do not execute file analyses.
- Core modules remain independent of CLI and output formatting.
- Result models distinguish missing prerequisites from execution failures.
- Architecture documentation describes the actual agreed design.

**Phase gate:** Do not proceed until the provider and capability interfaces are stable and documented.

### Phase 2 – Metadata and Analysis Separation

**Objective:** Establish the new `info` and `analyze` behavior while preserving existing functionality.

- [x] P2-W01: Refactor existing metadata extraction into the provider architecture.
- [x] P2-W02: Integrate existing PDF, ODF and OOXML metadata support.
- [x] P2-W03: Make format metadata extraction the normal behavior of `inspect info`.
- [x] P2-W04: Review compatibility of the existing `--metadata` option.
- [x] P2-W05: Integrate existing Python AST analysis as an analysis provider.
- [x] P2-W06: Introduce `inspect analyze`.
- [x] P2-W07: Introduce Markdown structural analysis.
- [x] P2-W08: Introduce simple text structural analysis.
- [x] P2-W09: Introduce PDF page structure analysis.
- [x] P2-W10: Implement consistent structured result serialization.
- [x] P2-W11: Integrate optional source-file hashing into `analyze`.
- [x] P2-W12: Preserve and test source-file hashing in `info`.
- [x] P2-W13: Ensure that `tree` and `inventory` remain unchanged.

**Acceptance criteria**

- `info` returns filesystem and available format metadata.
- `analyze` returns structural analysis without full document text.
- Python AST analysis is reused, not duplicated.
- Hashes identify the original source file.
- Missing capabilities are represented explicitly.
- Existing `tree` and `inventory` tests pass unchanged.
- Existing `info` functionality remains compatible where intended.

**Phase gate:** Metadata and analysis must be clearly separated in both implementation and JSON output.

### Phase 3 – Read and PDF Text Extraction [x]

**Objective:** Keep content retrieval independent of structural analysis.

- [x] P3-W01: Review the existing bounded text-reading implementation.
- [x] P3-W02: Define a format-aware content-reading interface.
- [x] P3-W03: Add PDF text extraction using the optional PDF dependency.
- [x] P3-W04: Preserve page boundaries where practical.
- [x] P3-W05: Define consistent output metadata for extracted textual content.
- [x] P3-W06: Report missing dependencies through the common capability mechanism.
- [x] P3-W07: Preserve size limits, UTF-8 handling and truncation behavior.
- [x] P3-W08: Add PDF and text-reading regression tests.

**Acceptance criteria**

- Existing text-reading behavior remains intact.
- PDF text can be retrieved through `read`.
- `analyze` does not duplicate full PDF text extraction.
- Binary files are not accidentally returned as text.
- Missing optional dependencies are clearly reported.
- Existing safety restrictions remain effective.

**Phase gate:** `read` must provide actual textual content or an explicitly identified textual representation, never silently substitute analysis results.

### Phase 4 – Image Analysis and Model Setup [x]

**Objective:** Implement the first model-backed analysis capability.

- [x] P4-W01: Review image examples in `res/example_filesystem_unstructured/Bilder`.
- [x] P4-W02: Evaluate suitable image metadata and ONNX Runtime dependencies.
- [x] P4-W03: Define the `[image]` optional dependency group.
- [x] P4-W04: Research and select the YOLO ONNX model source.
- [x] P4-W05: Verify model license, provenance and checksum.
- [x] P4-W06: Define the model storage path and `FS_TOOL_MODEL_DIR` override.
- [x] P4-W07: Implement safe model discovery and validation.
- [x] P4-W08: Implement the explicit YOLO setup handler.
- [x] P4-W09: Implement image metadata extraction.
- [x] P4-W10: Implement ONNX-based object detection.
- [x] P4-W11: Return structured detections with class, confidence and bounding box.
- [x] P4-W12: Ensure object detection is independently available from image metadata.
- [x] P4-W13: Add tests using mocked model loading and inference.
- [x] P4-W14: Add optional integration tests for a locally available model.

**Acceptance criteria**

- Image metadata works independently of YOLO.
- Missing ONNX Runtime or model resources are reported accurately.
- No automatic download occurs during normal analysis.
- Explicit setup downloads only from the documented source.
- Downloaded models are checksum-verified.
- Existing valid models are not overwritten.
- Object detection returns deterministic, structured output for the same model and input.
- Model setup works with the default and overridden model directories.

**Phase gate:** Do not ship model downloads until source, license, checksum and compatibility have been verified.

### Phase 5 – Capability and Setup CLI

**Objective:** Make optional functionality discoverable and manageable by users and agents.

- [x] P5-W01: Implement `fs-tool capabilities`.
- [x] P5-W02: Implement structured JSON capability output.
- [x] P5-W03: Implement readable Plain capability output.
- [x] P5-W04: Include exact missing Python dependencies and installation commands.
- [x] P5-W05: Include exact model paths and setup commands.
- [x] P5-W06: Implement `fs-tool setup <capability>`.
- [x] P5-W07: Implement `fs-tool setup --all`.
- [x] P5-W08: Ensure setup does not install Python packages.
- [x] P5-W09: Ensure setup is idempotent.
- [x] P5-W10: Implement safe download and existing-resource handling.
- [x] P5-W11: Add tests for missing dependencies, missing models and partial setup.
- [x] P5-W12: Add CLI help and error handling.

**Acceptance criteria**

- Agents can discover all supported capabilities using one command.
- Availability and missing requirements are machine-readable.
- Every unavailable capability provides a useful next step.
- Setup can prepare external resources without changing the Python environment.
- `setup --all` handles independent setup tasks without failing unnecessarily.
- Setup never overwrites valid resources without explicit authorization.
- Capability output reflects the actual current state.

**Phase gate:** The agent must be able to discover, prepare and verify the YOLO capability using the CLI alone.

### Phase 6 – Documentation, Integration and Quality Assurance

**Objective:** Complete the implementation and ensure consistency across code, documentation and tests.

[x] P6-W01: Finalize `docs/develop/architecture.md`.
[x] P6-W02: Document the provider and capability architecture.
[x] P6-W03: Document all new CLI commands.
[x] P6-W04: Document optional Python extras and their installation commands.
[x] P6-W05: Document YOLO model setup, source, license, checksum and exact storage location.
[x] P6-W06: Document `FS_TOOL_MODEL_DIR`.
[x] P6-W07: Document capability statuses and example JSON responses.
[x] P6-W08: Update user documentation navigation where necessary.
[x] P6-W09: Update project overview and CLI examples.
[x] P6-W10: Review package build and optional dependency declarations.
[x] P6-W11: Run the full test suite.
[x] P6-W12: Run Ruff, formatting checks and mypy.
[x] P6-W13: Run `make precommit`.
[x] P6-W14: Build the package and verify optional extras.
[x] P6-W15: Perform an end-to-end test with and without optional dependencies and models.

**Acceptance criteria**

- Architecture documentation matches the implementation.
- User documentation contains complete setup instructions.
- CLI help is sufficient to discover the relevant commands.
- All examples reflect the actual output schema.
- Existing functionality remains intact.
- Full test, lint, type-check and build workflows pass.
- Optional functionality works without being installed.
- No external model is bundled unintentionally.

**Final phase gate:** The implementation is complete only when functionality, tests, CLI help and documentation agree.

---

## 8. Cross-Cutting Requirements

These requirements apply to every implementation phase.

### Security

- Never execute analyzed files.
- Never follow symlinks outside allowed roots.
- Preserve existing allowed-root validation.
- Do not load arbitrary Python modules from analyzed files.
- Validate model downloads and verify checksums.
- Avoid unsafe archive extraction.
- Apply reasonable file-size and resource limits.
- Do not automatically download resources during inspection.
- Do not overwrite existing user resources silently.

### Performance

- Avoid loading expensive models unless the corresponding capability is executed.
- Do not repeatedly initialize ONNX Runtime sessions unnecessarily.
- Avoid duplicate parsing when metadata and analysis can share safe intermediate information.
- Keep lightweight analysis independent of model-backed functionality.
- Preserve bounded reading and analysis behavior.

### Determinism

- Use stable capability identifiers.
- Return predictable JSON structures.
- Sort collections where order has no semantic meaning.
- Use stable error codes.
- Keep model versions and checksums explicit.
- Avoid exposing machine-specific absolute paths except where required for actionable setup instructions.

### Maintainability

- Prefer simple explicit interfaces over generic frameworks.
- Reuse existing implementations.
- Keep CLI functions thin.
- Keep providers independent of output formatting.
- Keep capability registration centralized.
- Add tests for every new provider and capability.
- Avoid unnecessary dependencies.

---

## 9. Test Strategy

Tests should follow the existing repository conventions.

Relevant existing test areas include:

- `tests/test_info.py`
- `tests/test_read.py`
- `tests/test_python_analysis.py`
- `tests/test_hashing.py`
- `tests/test_output.py`
- `tests/test_plain_output.py`
- `tests/test_cli.py`

Add focused test modules where appropriate:

- `tests/test_capabilities.py`
- `tests/test_providers.py`
- `tests/test_analyze.py`
- `tests/test_setup.py`
- `tests/test_image_analysis.py`

Test at least the following situations:

| Scenario | Expected behavior |
|---|---|
| Supported format, all requirements available | Analysis succeeds |
| Optional Python dependency missing | Capability is unavailable |
| Model missing | Object detection is unavailable |
| Model present, runtime missing | Object detection is unavailable |
| Model and runtime available | Object detection succeeds |
| Corrupt model | Capability reports a clear failure |
| Invalid PDF | PDF analysis reports a structured failure |
| Unsupported file format | No misleading missing-dependency message |
| One analysis fails | Other available analyses still run |
| Setup called twice | Second call does not unnecessarily download again |
| Existing valid model | Setup preserves it |
| Download checksum mismatch | Model is rejected |
| `info --hash` and `analyze --hash` | Same source hash |
| Tree and inventory | Existing behavior unchanged |

Network-dependent tests must use mocks or controlled fixtures. The regular test suite must not require network access or a downloaded YOLO model.

---

## 10. Definition of Done

The mission is complete when:

1. `info`, `analyze` and `read` have clearly separated responsibilities.
2. Existing `tree` and `inventory` functionality remains intact.
3. PDF, Markdown, Python, image and text analysis work as specified.
4. Optional capabilities are centrally registered and discoverable.
5. `fs-tool capabilities` provides reliable machine-readable availability information.
6. `fs-tool setup` can prepare external resources explicitly and safely.
7. YOLO setup and object detection work with the documented model.
8. Missing and failed analyses are explicitly represented.
9. Hashes consistently identify source files.
10. `docs/develop/architecture.md` documents the implemented architecture.
11. User documentation and CLI help explain installation and setup.
12. All automated tests, linting, type checking and package build checks pass.

---

## 11. Implementation Notes

- This document is an implementation specification, not source code.
- Existing code and tests are authoritative when assessing compatibility.
- Do not unnecessarily rewrite working filesystem functionality.
- If implementation reveals a significant architectural conflict, update this plan before proceeding with a divergent implementation.
- Do not silently expand scope.
- Keep the implementation incremental and testable.
- Each phase must satisfy its acceptance criteria before the next phase begins.
- Future capabilities such as OCR, audio transcription and video analysis should be added through the same capability architecture, not through special-case CLI implementations.
---

## Progress / Handoff

### 2026-11-08 – Phase 3 complete

- Phase 3 (read and PDF text extraction) is implemented, tested, documented and pushed.
- Provider layer now exposes `content_capability()` / `read_content()`; `read_file()` orchestrates
  content reading and falls back to the bounded UTF-8 reader.
- PDF text extraction uses the optional `pypdf` dependency, reports `format` and `representation`,
  preserves page boundaries via `pages`, and bounds output and source size.
- Missing PDF dependencies are reported as `CAPABILITY_UNAVAILABLE`.
- A real PDF fixture is committed at `tests/example_pdf.pdf`.
- Issue: #12 (reused, not closed).
- Commits: `6781273`, `1cde1f6`, `b225d9d`; CI run `42531097345` passed on all platforms.
- Next: Phase 4 (image analysis and model setup), not started.

### 2026-11-10 – Phase 4 complete

- Phase 4 (image analysis and model setup) is implemented, tested, documented and pushed.
- `ImageProvider` adds `image_metadata` (Pillow) and `image_object_detection` (ONNX Runtime),
  registered independently so metadata works without the YOLO model or ONNX Runtime.
- `fs_tool.setup` provides a verified YOLO26n ONNX model workflow: HTTPS streaming download from
  the documented Hugging Face source, size and SHA-256 verification, atomic replacement, cleanup
  on failure, and idempotent re-runs. Valid existing models are never overwritten; `force`
  replaces only invalid files. Normal analysis never downloads models.
- The `[image]` extra declares `Pillow`, `numpy` and `onnxruntime`; capability checks honor an
  optional `import_name` so Pillow is detected via `PIL`.
- Detection uses letterboxing, maps boxes back to original image coordinates and returns
  deterministic, confidence-sorted structured output; tests mock inference and an optional
  integration test runs against a locally available model.
- Model provenance: `zwh20081/yolo26-onnx`, file `yolo26n.onnx`, AGPL-3.0, direct ONNX export
  from official Ultralytics YOLO26 weights; size 9,941,470 bytes; SHA-256
  `356b2726bbdba982e2a304e14b4d9a18b2726b7705b3206093d21331e4dbdd98`.
- Issue: #14 (closed after CI passed).
- Commits: `eebe36d`, `c2b8f65`, plus this plan status update; CI run `42898450826` passed.
- Next: Phase 5 (capability and setup CLI).

### 2026-11-10 – Phase 5 complete

- Phase 5 (capability and setup CLI) is implemented, tested, documented and pushed.
- `fs-tool capabilities` reports every registered capability with deterministic ordering, per-requirement
  availability, missing requirements, install commands for Python extras (`metadata`, `image`), model
  paths and `setup` next steps. JSON is the default; `--plain` provides readable output.
- `fs-tool setup <capability>` supports `pdf`, `image` and `yolo`; `--all` runs each target
  independently. Setup reports missing Python dependencies and exact install commands but never installs
  packages or changes the Python environment.
- `setup yolo` reuses the verified model workflow and is idempotent; valid existing models are preserved,
  corrupt models require `--force`, and downloads remain atomic and checksum-verified. `setup image`
  checks Python dependencies only and never downloads a model.
- Missing Python dependencies are reported as `missing-dependencies` without failing the command; actual
  setup or download failures mark the target `failed`, contribute to `failed_count`, populate envelope
  errors and return exit 1. Invalid usage returns exit 2 with `INVALID_ARGUMENT`.
- Tests cover capability JSON/Plain output, missing dependencies, partial setup, corrupt-model handling,
  idempotency, `--all`, invalid usage, help and error envelopes. Downloads are mocked; the suite never
  requires network access.
- Issue: #15 (reused, not closed).
- Commits: `f829f22`, `52d8e6c`; CI run `42905527267` passed.
- Next: Phase 6 (documentation, integration and quality assurance).

### 2026-11-10 – Phase 6 complete

- Phase 6 (documentation, integration and quality assurance) is implemented, tested, documented and pushed.
- New `docs/usage/setup.md`: optional Python extras (`metadata`, `image`) and install commands,
  capability statuses (`available`/`unavailable`/`failed`) with example JSON, `fs-tool capabilities`
  and `fs-tool setup` target descriptions, YOLO model source (`zwh20081/yolo26-onnx`), license AGPL-3.0,
  size 9,941,470 bytes, SHA-256 `356b2726...`, storage `~/.local/share/fs-tool/models/yolo26n.onnx`,
  and the `FS_TOOL_MODEL_DIR` override.
- `docs/usage/cli.md`: added `capabilities` and `setup` command references plus example JSON response.
- `docs/usage/examples.md`: added capability discovery and setup workflow examples.
- `docs/index.md`: linked the new Setup page; `mkdocs build` succeeds and renders `usage/setup`.
- All phase-6 work packages complete: package build (`uv build`) succeeds with sdist+wheel; optional
  extras verified; no YOLO model bundled or auto-downloaded (model dir absent after normal operation).
- Tests: 367 passed, 1 skipped (network-dependent model integration test), coverage 85%.
- Lint/type/format: `ruff check`, `ruff format --check`, `mypy --strict` all pass; `make precommit` green.
- End-to-end: `capabilities`, `setup pdf`/`setup image`/`setup --all`, `info`, `analyze`, `read`
  all verified with JSON and plain output.
- Issue: GitHub issue creation for this phase failed (401 Requires authentication); no issue reference.
- Commit: `c42cc20`; branch `phase-6-documentation-qa` pushed to origin.
- Next: none — implementation complete.
