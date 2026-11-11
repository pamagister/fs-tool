# Architecture

fs-tool is a Python package with a thin CLI layer, a filesystem core, a
capability and provider layer, and a separate output layer. The design keeps
analysis independent of the command line so the same functionality can be
reused by scripts and future integrations (plan.md decision D1).

## Package layout

```text
src/fs_tool/
├── cli.py                 Typer application and command handlers
├── __main__.py            python -m fs_tool entry point
├── core/
│   ├── config.py          TOML configuration and allowed-root resolution
│   ├── errors.py          Error codes and exit-code mapping
│   ├── filesystem.py      Path normalization and symlink resolution
│   ├── hashing.py         SHA-256 file hashing
│   ├── metadata.py        Shared metadata helpers, limits and PDF date parsing
│   ├── models.py          FilesystemEntry and EntryType
│   ├── traversal.py       Read-only directory traversal
│   ├── capabilities/
│   │   ├── __init__.py
│   │   ├── models.py      CapabilityId, Capability, requirements, results
│   │   ├── registry.py    Central capability registry
│   │   └── availability.py Availability checks for requirements
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── base.py        Provider interface
│   │   ├── registry.py    Explicit provider registry
│   │   ├── inspection.py  Metadata and analysis orchestration
│   │   ├── image.py       Image metadata and ONNX object detection
│   │   ├── markdown.py    Markdown structure analysis
│   │   ├── odf.py         ODF metadata
│   │   ├── ooxml.py       OOXML metadata
│   │   ├── pdf.py         PDF metadata and page structure
│   │   ├── python.py      Python AST analysis
│   │   └── text.py        Text structure analysis
│   └── analysis/
│       ├── search.py      Entry filters used by find
│       ├── duplicates.py  Size grouping and hash-based duplicate detection
│       ├── comparison.py  Directory tree comparison
│       ├── verification.py Inventory and tree verification
│       └── python_analysis.py AST-based Python source analysis
├── operations/
│   ├── common.py          OperationReport and shared validation
│   ├── copy.py            No-overwrite file and tree copying
│   ├── mkdir.py           Directory creation
│   └── move.py            No-overwrite moves and renames
├── output/
│   ├── json.py            JSON envelope
│   ├── entries.py         Per-command compact entry profiles
│   ├── results.py         Capability result serialization
│   └── plain.py           Human-readable renderers
├── safety/
│   └── validation.py      Allowed-root checks
└── setup/
    ├── models.py          Model storage, validation and verified download
    └── yolo.py            Explicit YOLO setup handler
```

## Layers

### CLI

`fs_tool/cli.py` defines the Typer application and all commands. It is responsible for:

- parsing arguments and global options,
- resolving the output format and verbosity,
- validating paths against the allowed roots,
- calling the core or operations layer,
- serializing results and mapping errors to exit codes.

The root callback builds a `CliContext` with the allow-listed roots, configuration path, output
settings and verbosity. Global options are accepted before or after the command: `main()` hoists
known global options in front of the command before Click parses them.

`main()` is the process boundary. It converts `FsToolError` into a diagnostic and an exit code,
treats Click usage errors as exit code 2, and reports unexpected exceptions instead of swallowing
them.

### Core

The core package contains all read-only filesystem logic and has no dependency on the output
format or on the CLI.

- `models.py` defines the internal `FilesystemEntry` representation. Serialization happens outside
  the model.
- `traversal.py` walks a tree without following symlinks. Entries are sorted by name, special
  files are reported as `other`, and unreadable entries are collected as errors instead of aborting
  the scan.
- `analysis/` implements filters, duplicate detection, comparison, verification and Python source
  analysis. These modules operate on traversal results or plain paths and do not render output.
- `hashing.py` opens files read-only and uses `O_NOFOLLOW` where available.
- `metadata.py` provides shared helpers for metadata extraction: size limits, safe ZIP member
  reads and PDF date parsing. Format-specific extraction lives in providers.
- `config.py` loads TOML configuration and intersects configured roots with command-line roots, so
  configuration can only restrict access.
- `errors.py` defines `ErrorCode` and the mapping from error codes to process exit codes.

### Providers and capabilities

fs-tool separates metadata extraction from content analysis through a modular provider
architecture (plan.md decision D3).

#### Provider interface

`fs_tool/core/providers/base.py` defines the `Provider` abstract base class. A provider:

- declares a stable `id`,
- declares the `capabilities` it offers (a provider may expose multiple independent
  capabilities),
- declares the `supported_extensions()` it can handle,
- optionally declares a `metadata_capability()` and implements `extract_metadata()`,
- optionally declares `analysis_capabilities()` and implements `analyze()`,
- optionally declares a `content_capability()` and implements `read_content()`.

Capability definitions are resolved from the central registry through
`capabilities_from_registry()`, so providers never duplicate dependency or availability metadata.
Core providers do not import Typer or CLI code and never format output.

The built-in providers are registered explicitly in
`fs_tool/core/providers/registry.py`:

| Provider | Extensions | Metadata | Analysis | Content |
|----------|------------|----------|----------|---------|
| `image` | `.jpg`, `.jpeg`, `.png`, `.gif`, `.bmp`, `.tif`, `.tiff`, `.webp` | `image_metadata` | `image_object_detection` | — |
| `markdown` | `.md`, `.markdown` | — | `markdown_structure` | — |
| `odf` | `.odt`, `.ods`, `.odp`, `.odg` | `odf_metadata` | — | — |
| `ooxml` | `.docx`, `.xlsx`, `.pptx` | `ooxml_metadata` | — | — |
| `pdf` | `.pdf` | `pdf_metadata` | `pdf_pages` | `pdf_text` |
| `python` | `.py` | — | `python_ast` | — |
| `text` | `.txt`, `.text`, `.log` | — | `text_structure` | — |

There is no dynamic plugin-loading framework. Files whose provider declares no content capability
are read with the bounded UTF-8 text reader, preserving the original `inspect read` behavior for
plain text and other text-based formats.

#### Orchestration

`fs_tool/core/providers/inspection.py` connects providers, the capability registry and the
availability checker:

- `inspect_metadata()` selects the provider for the file extension, verifies the metadata
  capability, enforces the metadata size limit and calls the provider.
- `analyze_file()` collects every analysis capability applicable to the file extension, checks
  availability, and runs each capability independently.
- `read_file()` selects a provider with a content capability, verifies that capability through the
  central registry and availability checker, and calls the provider. Files without a content
  capability use the bounded UTF-8 reader in `content.py`.

The orchestrator returns core `MetadataInspection`, `AnalysisReport` and `ContentRead` models. It
does not render output. Providers raise `FsToolError` for extraction, analysis or reading failures;
the orchestrator converts metadata and analysis failures into structured capability results. A
missing reading prerequisite is raised as `CAPABILITY_UNAVAILABLE`, because returning no content
without an explicit error would be misleading.

#### Image analysis

`fs_tool/core/providers/image.py` implements two independent capabilities:

- `image_metadata` reads format, dimensions, colour mode and EXIF data with Pillow. It never loads
  ONNX Runtime or the YOLO model.
- `image_object_detection` runs the installed YOLO26n ONNX model through ONNX Runtime. Missing ONNX
  Runtime, numpy, Pillow or the model makes only this capability unavailable.

Detection input is a `[1, 3, 640, 640]` float32 tensor with pixel values normalized to 0-1. Images
are letterboxed with the Ultralytics padding colour `(114, 114, 114)` and the applied scale and
offsets are used to map boxes back to original-image pixel coordinates. The verified end-to-end
export produces `output0` with shape `[1, 300, 6]`; each row is
`x1, y1, x2, y2, confidence, class_id` in model-input coordinates. Rows below the confidence
threshold (default `0.25`) and empty boxes are discarded. Results are sorted by descending
confidence, then class and coordinates, so output is deterministic for the same model and input.
Class identifiers are mapped to the standard 80 COCO class names.

The provider loads one ONNX Runtime session per model file version and caches it by path, mtime and
size. A model changed on disk therefore gets a fresh session.

#### Capability registry

`fs_tool/core/capabilities/registry.py` defines `CapabilityRegistry`, the single central
source of all supported capability definitions (plan.md decision D4). The same definitions are
used by `info`, `analyze`, `capabilities` and `setup`. Capabilities are registered explicitly;
there is no dynamic plugin-loading framework.

Each capability (`fs_tool/core/capabilities/models.py`) declares:

- a stable `CapabilityId`,
- the `provider` that implements it,
- its `requirements`: Python packages and/or external resources (for example an ONNX model),
- an optional `setup_command` telling users how to prepare the capability.

#### Availability checking

`fs_tool/core/capabilities/availability.py` defines `AvailabilityChecker`. It verifies that
prerequisites are present without executing any file analysis:

- Python packages are checked with `importlib.util.find_spec` (no import side effects).
- External resources are checked by file existence.

A missing prerequisite makes a capability `unavailable`; the analysis itself is never run during
a check.

#### Result statuses and serialization

Every capability result communicates its status explicitly (plan.md decision D6):

| Status | Meaning |
|--------|---------|
| `available` | Analysis was successfully performed |
| `unavailable` | Supported, but a prerequisite is missing |
| `failed` | Analysis was attempted but could not complete |

Each result carries a stable capability identifier, a concise message, a `help` reference and —
for failures — a stable machine-readable error code. Optional structured payloads live in `data`.
`fs_tool/output/results.py` is the single serializer for this shape. Unavailable results are never
silently omitted, and one unavailable or failed capability never prevents other available
analyses from running.

A file format with no applicable capability is distinguishable from an unavailable one: its
`inspect analyze` result has `supported: false` and an empty `analyses` list, while `inspect info`
returns `metadata: null` with `metadata_result: null`.


### Separation of metadata, analysis and content reading (decisions D1 and D2)

Three information categories remain conceptually distinct:

| Category | Description | Command |
|----------|-------------|---------|
| Filesystem information | Properties of the filesystem entry | `inspect info` |
| Format metadata | Descriptive properties stored in the file format | `inspect info` |
| Analysis | Information obtained by interpreting file contents | `inspect analyze` |
| Content | Actual file content or a textual representation | `inspect read` |

`tree` and `inspect inventory` remain functionally unchanged.

`read` stays independent of `info` and `analyze`: it returns actual textual content or an
explicitly identified textual representation, never analysis results.

Every result identifies its source `format` and its `representation`. Plain text uses
`format: "text"` and `representation: "utf-8_text"`. PDF text extraction uses `format: "pdf"` and
`representation: "extracted_text"`. PDF results additionally carry `page_count` and a `pages` list,
so page boundaries are preserved even though `content` is a single bounded string. Pages are joined
with a blank line in `content`.

Bounded reading applies to every format: `--max-bytes` limits the UTF-8 encoded output, truncation
never splits a character, and PDF source files above the reading size limit are rejected. Binary
content is never returned as text.

### Safety

`safety/validation.py` implements the allowed-root policy. `validate_path()` normalizes the
requested path and also resolves symlinks; both results must lie inside an allowed root. This
prevents a symlink from escaping an allowed root.

### Operations

The `operations` package performs filesystem modifications. Every operation:

1. validates both source and destination against the allowed roots,
2. requires exactly one of `--dry-run` or `--yes`,
3. preflights all conflicts before writing,
4. never overwrites an existing destination and never deletes data,
5. returns an `OperationReport`.

### Output

`output/json.py` defines the stable `Envelope` with `schema_version`, `success`, `command`,
`result`, `errors`, `warnings` and `complete`. `output/entries.py` defines the compact serialization
profiles for commands that return filesystem entries, and `output/plain.py` contains renderers for
each command family. The CLI decides which representation to use; the core never imports either
module.

Compact profiles are command-specific. `inspect tree` keeps `rel_path` and `type`, `inspect
inventory` keeps portable metadata (`rel_path`, `type`, `extension`, `size`, `modified`, plus
`sha256` only with `--hash`), and `find` keeps `rel_path`, `type` and `size`. The global `--verbose`
option restores the complete `FilesystemEntry` representation for these commands. Filtering happens
after analysis in the presentation layer: core models stay complete, entry counts and completeness
are unchanged, and verbose mode performs no additional filesystem work or hashing. `inspect info`
and `inspect analyze` have no compact profile, and `tree_hash` is computed from the full entry
representation so it does not depend on the selected profile.

### Optional dependencies, external resources and model storage (decisions D5 and D8)

Python dependencies are managed by the package manager through optional extras (for example
`fs-tool-cli[pdf]`, `fs-tool-cli[image]`). The `image` extra installs `Pillow`, `numpy` and
`onnxruntime`. `fs-tool setup` never silently installs Python packages or modifies the active Python
environment.

External resources such as ONNX models may be managed by fs-tool through an explicit `setup`
invocation only. Models are stored in a predictable user-specific directory:

```text
~/.local/share/fs-tool/models/
```

The directory can be overridden through the `FS_TOOL_MODEL_DIR` environment variable and is
resolved centrally by `fs_tool.core.capabilities.models.resolve_model_dir()`. The model is not
bundled in the Python package and is never downloaded automatically during normal operation.

#### YOLO model

The supported model is `yolo26n.onnx` from the `zwh20081/yolo26-onnx` Hugging Face repository, a
direct ONNX export of the official Ultralytics YOLO26 weights. It is licensed AGPL-3.0. The file is
9,941,470 bytes with SHA-256:

```text
356b2726bbdba982e2a304e14b4d9a18b2726b7705b3206093d21331e4dbdd98
```

`setup_yolo()` downloads only from the documented HTTPS URL, streams to a temporary file in the
model directory, verifies size and checksum, and atomically replaces the destination. Existing
valid models are preserved; `force` replaces only invalid files. Download and validation logic
lives in `fs_tool/setup/models.py`; the handler lives in `fs_tool/setup/yolo.py`.

### Error codes

`core/errors.py` defines stable `ErrorCode` values mapped to process exit codes (plan.md section 4.3).
Capability-specific codes include `CAPABILITY_NOT_SUPPORTED`, `CAPABILITY_UNAVAILABLE`,
`CAPABILITY_FAILED`, `RESOURCE_NOT_FOUND`, `RESOURCE_CORRUPT` and `SETUP_FAILED`. Detailed setup
instructions belong in the central `capabilities` output, not in individual result messages.

## Data flow

```text
argv
  │
  ├─ global options → CliContext (roots, config, format)
  │
  ├─ path validation → safety.validation
  │
  ├─ read path
  │    traversal / analysis / metadata / providers → result model
  │
  ├─ capability lookup → capabilities.registry + capabilities.availability
  │
  ├─ write path
  │    operations → OperationReport
  │
  └─ output.json / output.plain → stdout, diagnostics → stderr
```

## Invariants

- Read operations never modify the filesystem.
- Analysis modules do not format output.
- Output formatting does not influence filesystem operations.
- Availability checks never execute file analyses.
- Results are deterministic: traversal is sorted and capability identifiers are stable.
- JSON is the primary interface; plain output is a human-oriented alternative.
- Errors are structured and carry stable codes.
- Destructive behavior is opt-in: writes require authorization and never overwrite or delete.
- The core stays independent of any agent, MCP implementation or external automation framework.
- One unavailable or failed capability never aborts other available analyses.

## Entry points

| Entry point | Definition |
|-------------|------------|
| `fs-tool` | `[project.scripts] fs-tool = "fs_tool.cli:main"` |
| `python -m fs_tool` | `src/fs_tool/__main__.py` calls `main()` |

The package version is read from the installed distribution metadata, with a fallback for source
checkouts that are not installed.

## Tests

Tests live in `tests/` and mirror the package structure:

| Area | Test files |
|------|------------|
| Traversal and models | `test_traversal.py`, `test_tree.py` |
| Inspection | `test_info.py`, `test_inventory.py`, `test_read.py` |
| Capabilities and providers | `test_capabilities.py`, `test_setup.py`, `test_image_analysis.py` |
| Analysis | `test_find.py`, `test_duplicates.py`, `test_compare.py`, `test_verify.py`, `test_python_analysis.py` |
| Operations | `test_operations.py` |
| Safety and configuration | `test_safety.py`, `test_config.py`, `test_hashing.py` |
| CLI and output | `test_cli.py`, `test_output.py`, `test_plain_output.py` |

Run them with `make test`. See [Contributing](contributing.md) for the full workflow.
