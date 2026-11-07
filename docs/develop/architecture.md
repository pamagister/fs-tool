# Architecture

fs-tool is a Python package with a thin CLI layer, a filesystem core, and a separate output layer.
The design keeps analysis independent of the command line so the same functionality can be reused
by scripts and future integrations.

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
│   ├── metadata.py        PDF, ODF and OOXML metadata extraction
│   ├── models.py          FilesystemEntry and EntryType
│   ├── traversal.py       Read-only directory traversal
│   └── analysis/
│       ├── search.py      Entry filters used by find
│       ├── duplicates.py  Size grouping and hash-based duplicate detection
│       ├── comparison.py  Directory tree comparison
│       ├── verification.py Inventory and tree verification
│       └── python_analysis.py AST-based Python source analysis
├── operations/
│   ├── common.py          OperationReport and shared validation
│   ├── mkdir.py           Directory creation
│   ├── copy.py            No-overwrite file and tree copying
│   └── move.py            No-overwrite moves and renames
├── output/
│   ├── json.py            JSON envelope
│   └── plain.py           Human-readable renderers
└── safety/
    └── validation.py      Allowed-root checks
```

## Layers

### CLI

`fs_tool/cli.py` defines the Typer application and all commands. It is responsible for:

- parsing arguments and global options,
- resolving the output format,
- validating paths against the allowed roots,
- calling the core or operations layer,
- serializing results and mapping errors to exit codes.

The root callback builds a `CliContext` with the allow-listed roots, configuration path and output
settings. Global options are accepted before or after the command: `main()` hoists known global
options in front of the command before Click parses them.

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
- `metadata.py` extracts document metadata without executing content, with size limits for archives
  and files.
- `config.py` loads TOML configuration and intersects configured roots with command-line roots, so
  configuration can only restrict access.
- `errors.py` defines `ErrorCode` and the mapping from error codes to process exit codes.

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

Copying writes regular files through a temporary file, verifies their content and publishes them
with an exclusive hard link so an existing destination is not overwritten. Moving uses a no-replace
rename primitive where the platform provides one.

### Output

`output/json.py` defines the stable `Envelope` with `schema_version`, `success`, `command`,
`result`, `errors`, `warnings` and `complete`. `output/plain.py` contains renderers for each command
family. The CLI decides which representation to use; the core never imports either module.

## Data flow

```text
argv
  │
  ├─ global options → CliContext (roots, config, format)
  │
  ├─ path validation → safety.validation
  │
  ├─ read path
  │    traversal / analysis / metadata → result model
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
- Results are deterministic: traversal is sorted and inventories use relative paths.
- JSON is the primary interface; plain output is a human-oriented alternative.
- Errors are structured and carry stable codes.
- Destructive behavior is opt-in: writes require authorization and never overwrite or delete.
- The core stays independent of any agent, MCP implementation or external automation framework.

## Entry points

| Entry point | Definition |
|---|---|
| `fs-tool` | `[project.scripts] fs-tool = "fs_tool.cli:main"` |
| `python -m fs_tool` | `src/fs_tool/__main__.py` calls `main()` |

The package version is read from the installed distribution metadata, with a fallback for source
checkouts that are not installed.

## Tests

Tests live in `tests/` and mirror the package structure:

| Area | Test files |
|---|---|
| Traversal and models | `test_traversal.py`, `test_tree.py` |
| Inspection | `test_info.py`, `test_inventory.py`, `test_read.py` |
| Analysis | `test_find.py`, `test_duplicates.py`, `test_compare.py`, `test_verify.py`, `test_python_analysis.py` |
| Operations | `test_operations.py` |
| Safety and configuration | `test_safety.py`, `test_config.py`, `test_hashing.py` |
| CLI and output | `test_cli.py`, `test_output.py`, `test_plain_output.py` |

Run them with `make test`. See [Contributing](contributing.md) for the full workflow.
