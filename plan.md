# fs-tool – Architecture and Functional Specification

## 1. Project Objective

Develop a lightweight, secure and agent-friendly command-line tool for inspecting, analyzing, comparing and organizing local filesystems.

The application supports both interactive human usage and automated execution by AI agents.

The primary use cases are:

- Understanding existing directory structures.
- Creating structured filesystem inventories.
- Collecting file metadata and identifying file types.
- Analyzing selected file formats and source code.
- Finding duplicate files.
- Comparing directory structures and file contents.
- Copying, moving and renaming files and directories.
- Verifying the integrity of filesystem operations.

The initial release focuses exclusively on the CLI and its underlying Python library.

---

## 2. Decisions (govern all implementation)

The following project decisions were agreed before implementation and are authoritative:

| # | Decision | Value |
|---|----------|-------|
| D1 | Python baseline | `>=3.11`; CI tests 3.11 and 3.13 |
| D2 | Legacy template cleanup | Complete: GUI, `config-cli-gui`, legacy `config.yaml`, PyInstaller/GUI builds, GPX examples, `init.sh`, template scripts, `.idea` run configs removed |
| D3 | `verify` interface | Subcommands: `verify inventory <inventory.json> <target>` and `verify tree <source> <target>` |
| D4 | Configuration | TOML via `tomllib`; `--config PATH`; default `$XDG_CONFIG_HOME/fs-tool/config.toml`; no automatic project-config loading; precedence CLI > Config > Defaults; config may only restrict Allowed Roots, never expand them |
| D5 | Document metadata | PDF via optional `[metadata]` extra with `pypdf`; ODF/OOXML via stdlib `zipfile`/`ElementTree`; read-only, no macro/code execution, size limits |
| D6 | Allowed Roots default | Home directory + CWD when `--allow-root` is absent; supplied `--allow-root` values replace those defaults; CWD of `/` still requires explicit `--allow-root /` |
| D7 | Output default | `auto`: TTY → Plain, Pipe/Agent → JSON; `--json`/`--plain` override; additionally `--format auto|json|plain` |
| D8 | Issue/commit cadence | One GitHub Issue per phase; 3–6 commits per phase; then `git push`; then monitor GitHub Actions |
| D9 | No code in this plan | This plan is specification only. No source files are created by editing this document. |

---

## 3. Architectural Principles

### 3.1 Separation of Concerns

The application consists of three logical layers:

```text
        Human User / AI Agent
                 |
                 v
             CLI Layer
          (Typer / JSON)
                 |
                 v
         Filesystem Core
        +---------+---------+
        |         |         |
        v         v         v
     Analysis  Operations  Safety
        |         |         |
        +---------+---------+
                 |
                 v
          Local Filesystem
```

The filesystem core must be usable independently of the CLI.

### 3.2 Design Principles

- Keep the architecture modular but lightweight.
- Avoid unnecessary abstractions and complex frameworks.
- Prefer standard-library functionality.
- Provide deterministic and reproducible results.
- Separate filesystem traversal from content analysis.
- Separate analysis from filesystem modifications.
- Use consistent data structures across commands.
- Never execute analyzed files or import them dynamically.
- Never silently overwrite or delete user data.
- Require explicit authorization for potentially risky operations.
- JSON is the primary interface; Plain is a human-oriented alternative.

### 3.3 Technology Stack

| Component | Technology |
|---|---|
| Language | Python 3.11+ |
| CLI | Typer |
| Filesystem | pathlib, os, shutil |
| Hashing | hashlib |
| Python analysis | ast |
| Serialization | json |
| Configuration | TOML (stdlib `tomllib`) |
| Package management | uv |
| Testing | pytest |
| Linting | Ruff |
| Type checking | mypy |

External dependencies should be introduced only where they provide meaningful functionality. The optional `[metadata]` extra depends on `pypdf`.

---

## 4. CLI Design

### 4.1 General Interface

Executable:

`fs-tool`

Proposed command hierarchy:

```text
fs-tool
│
├── inspect
│   ├── tree
│   ├── info
│   ├── inventory
│   └── read
│
├── find
│
├── duplicates
│
├── compare
│
├── verify
│   ├── inventory <inventory.json> <target>
│   └── tree <source> <target>
│
└── write
    ├── mkdir
    ├── copy
    └── move
```

The hierarchy separates inspection and analysis from filesystem modifications.

### 4.2 Global Options

| Option | Description |
|---|---|
| `-h, --help` | Show help |
| `--version` | Show application version |
| `--allow-root PATH` | Set an allowed root; repeatable. When supplied, these roots replace the default Home+CWD roots |
| `--config PATH` | Path to TOML configuration file |
| `--format auto\|json\|plain` | Output format; default `auto` |
| `--json` | Explicitly request JSON output |
| `--plain` | Human-readable output instead of JSON |

JSON is the default interface for piped/agent usage. `--format auto` chooses Plain on a TTY and JSON otherwise. `--plain` and `--json` are mutually exclusive.

The output format must be consistent across all commands.

### 4.3 Output Contract

Every command must return a predictable result structure.

Successful operation:

```json
{
  "schema_version": 1,
  "success": true,
  "command": "inspect.info",
  "result": {},
  "errors": [],
  "warnings": [],
  "complete": true
}
```

Failed operation:

```json
{
  "schema_version": 1,
  "success": false,
  "command": "write.copy",
  "result": null,
  "errors": [
    {
      "code": "TARGET_EXISTS",
      "message": "Destination already exists.",
      "path": "/home/user/file.txt",
      "details": {}
    }
  ],
  "warnings": [],
  "complete": false
}
```

Requirements:

- JSON output goes to stdout.
- Human-readable diagnostics may go to stderr.
- Error messages must be understandable and actionable.
- Results must not depend on terminal formatting.
- Use stable error codes.
- Use meaningful process exit codes.
- `complete: false` means the operation could not be fully verified; never claim full-tree integrity for incomplete scans.
- An incomplete scan may return its partial result, but must set `success: false`, `complete: false`, and exit with code 5.
- `--help`/`--version` are documented exceptions to the JSON envelope.

Proposed exit codes:

| Code | Meaning |
|---|---|
| 0 | Successful operation |
| 1 | Operation failed or verification found discrepancies |
| 2 | Invalid arguments or incomplete analysis |
| 3 | Access denied or safety restriction |
| 4 | Operation conflict |
| 5 | Incomplete scan or verification (not fully verifiable) |

---

## 5. Functional Requirements

### 5.1 Filesystem Inspection

#### `inspect tree`

Display a directory tree.

Examples:

```bash
fs-tool inspect tree ~/Documents
fs-tool inspect tree ~/Projects --plain
fs-tool --plain inspect tree ~/Projects
```

Features:

- Recursive directory traversal.
- Alphabetical sorting.
- Configurable maximum depth.
- Optional maximum number of entries.
- Optional directory-only mode.
- Structured per-entry metadata in JSON output.
- Optional human-readable metadata summaries are planned for Phase 5.
- Python source structure is deferred to Phase 6.
- File-type-specific symbols in plain output.
- Configurable ignored directories and file patterns.

Typical ignored directories:

```text
.git
.venv
__pycache__
.pytest_cache
.ruff_cache
.mypy_cache
node_modules
build
dist
.idea
.vscode
```

Ignore rules must be configurable. Hidden directories must not automatically be excluded unless configured. The JSON output should contain the complete structured tree, not terminal-rendered tree characters.

#### `inspect info`

Retrieve metadata for one file or directory.

Example:

```bash
fs-tool inspect info ~/Documents/report.pdf
fs-tool inspect info ~/Documents/report.pdf --metadata
```

Collect where available:

| Attribute | Description |
|---|---|
| `path` | Absolute path |
| `name` | Filename |
| `rel_path` | Path relative to scan root |
| `type` | File, directory, symlink, other |
| `extension` | File extension |
| `size` | Size in bytes |
| `modified` | Modification timestamp (ISO-8601 UTC) |
| `created` | Creation/birth time, if supported; otherwise `null` |
| `accessed` | Last access timestamp |
| `changed` | Inode/metadata change timestamp (POSIX `st_ctime`) |
| `mode` | Filesystem permissions |
| `owner` | Owner information where available |
| `mime_type` | Best-effort MIME type |
| `is_symlink` | Whether the entry is a symbolic link |
| `target` | Symlink target, if applicable |
| `sha256` | SHA-256 hash when requested |
| `metadata` | Document-specific / language-specific information |

Timestamps: `modified`, `accessed`, `changed`, `created`. On Linux `st_ctime` is the inode change time, not a birth time; it is exposed as `changed`. `created` is `null` when birth time is unavailable.

Optional document metadata with `--metadata`:

- Author
- Title
- Subject
- Creation date
- Modification date

Initially supported formats:

- PDF (via optional `pypdf`)
- ODT, ODS, ODP, ODG
- DOCX, XLSX, PPTX

Document metadata extraction must be read-only and must never execute embedded content. Size and zip-bomb limits apply. Unavailable metadata must be represented as `null`, not silently omitted.

#### `inspect inventory`

Create a deterministic inventory of a directory tree.

Examples:

```bash
fs-tool inspect inventory ~/Documents
fs-tool inspect inventory ~/Archive --hash
```

Features:

- Recursive traversal.
- File and directory metadata.
- Optional SHA-256 hashes.
- Symlink target recording without following links.
- Configurable ignored paths.
- Maximum entry limits.
- Error reporting for inaccessible entries.
- Deterministic sorting.
- Optional aggregate tree hash.

The inventory must explicitly indicate whether the scan was complete (`complete`).

A tree hash must only be generated for a complete inventory. Inventory entries use `rel_path` relative to the declared `root`; absolute paths are not stored to keep inventories portable across machines. `generated_at` is informational and must not be part of the tree hash.

Tree hash specification:

- Canonical JSON with sorted keys.
- Entries sorted by `rel_path`.
- Fields excluded from hash: `generated_at`, absolute `path`.
- Versioned via `schema_version`.

#### `inspect read`

Read bounded text files.

Example:

```bash
fs-tool inspect read ~/Documents/notes.txt
fs-tool inspect read ~/Projects/README.md --max-bytes 65536
```

Requirements:

- UTF-8 decoding.
- Configurable maximum file size.
- No symlink following.
- No binary file reading by default.
- Explicit indication when content is truncated.

---

### 5.2 File and Directory Search

#### `find`

Find filesystem entries by name, extension or pattern.

Examples:

```bash
fs-tool find ~/Documents --name "*.pdf"
fs-tool find ~/Projects --extension py
fs-tool find ~/Downloads --name "*invoice*"
fs-tool find ~/Documents --type file --min-size 1M
```

Supported filters:

- Filename patterns.
- Extensions.
- Entry type.
- Minimum and maximum size.
- Modification date.
- Optional case sensitivity.

Search results must use the common entry schema. Search should be read-only and must respect all filesystem access restrictions.

---

### 5.3 Duplicate Detection

#### `duplicates`

Identify files with identical content.

Example:

```bash
fs-tool duplicates ~/Documents
fs-tool duplicates ~/Archive --min-size 1024
```

Features:

1. Identify candidate files by size.
2. Calculate hashes for candidates.
3. Group files by identical SHA-256 hash.
4. Return all paths belonging to each duplicate group.

Example output:

```json
{
  "schema_version": 1,
  "success": true,
  "command": "duplicates",
  "result": {
    "duplicate_groups": [
      {
        "sha256": "abc123...",
        "size": 102400,
        "count": 2,
        "files": [
          "/data/documents/report.pdf",
          "/data/backup/report_old.pdf"
        ]
      }
    ],
    "duplicate_group_count": 1,
    "duplicate_file_count": 2,
    "complete": true
  },
  "errors": [],
  "warnings": []
}
```

Requirements:

- Never delete files automatically.
- Do not follow symlinks.
- Exclude incomplete or unreadable files from verified duplicate groups.
- Clearly distinguish confirmed duplicates from incomplete scan results.
- Avoid hashing files unnecessarily by using file size as an initial filter.
- Hardlinks are not counted as duplicates (same inode).
- Empty files are excluded by default; `--include-empty` enables them.

---

### 5.4 Directory Comparison

#### `compare`

Compare source and destination directory trees.

Example:

```bash
fs-tool compare ~/Documents ~/Documents_New
```

The comparison should identify:

- Files present in both locations with identical content.
- Files missing in the destination.
- Files with different content.
- Unexpected files in the destination.
- Directory differences.
- Type conflicts.
- Unsupported entries.
- Incomplete comparisons.

The comparison should use relative paths as the primary structural reference. SHA-256 should be used to verify file content.

A comparison must not assume that files with identical names have identical contents.

The JSON result must contain separate lists for:

```text
identical
missing
changed
unexpected
type_conflicts
unsupported
errors
```

---

### 5.5 Verification

#### `verify inventory`

Verify a directory against a previously stored inventory file.

Example:

```bash
fs-tool verify inventory inventory.json ~/Documents_New
```

#### `verify tree`

Verify a destination directory against a source directory.

Example:

```bash
fs-tool verify tree ~/Documents ~/Documents_New
```

Requirements:

- Check expected files and directories.
- Compare file sizes and hashes where available.
- Detect missing entries.
- Detect unexpected entries.
- Detect changed contents.
- Report incomplete verification.
- Return machine-readable discrepancy reports.
- Prune `schema_version` of the inventory file; reject unknown or incompatible versions.

Verification must distinguish between a complete successful result and a result that could not be fully verified (`complete: false`).

---

### 5.6 Filesystem Operations

All modifications belong to the `write` command group.

#### General Rules

Every write operation must support:

- `--dry-run`
- `--yes`

Exactly one of these options must be specified.

`--dry-run` displays the planned operation without modifying the filesystem. `--yes` authorizes execution.

Additional rules:

- Never overwrite existing files or directories.
- Never delete data.
- Validate source and destination paths.
- Check allowed roots.
- Avoid following symlinks unexpectedly.
- Return a structured operation report.
- Preflight: validate all conflicts before writing; either apply everything or abort.
- Atomic destination creation where practical (temp file + rename, `O_EXCL`).

#### `write mkdir`

Create a directory, including missing parent directories.

Example:

```bash
fs-tool write mkdir ~/Documents/NewFolder --dry-run
fs-tool write mkdir ~/Documents/NewFolder --yes
```

Requirements:

- Existing directory is idempotent (`created: false`).
- Existing file at target path is a conflict.
- `--parents` creates missing parents explicitly.

#### `write copy`

Copy files and, in a subsequent implementation step, directory trees.

Example:

```bash
fs-tool write copy source.pdf destination.pdf --dry-run
fs-tool write copy source.pdf destination.pdf --yes
```

Requirements:

- No overwriting.
- Copy regular files initially.
- Directory copying must preserve relative paths.
- Preserve file metadata where appropriate.
- Verify copied file contents using SHA-256.
- Use temporary files and safe destination creation where practical.
- Report partial failures explicitly.

Symlink copying must use an explicit policy: `error|copy|skip`. Default `error` (never follow a source symlink and copy its target implicitly).

#### `write move`

Move files and directories or rename them.

Example:

```bash
fs-tool write move old.pdf new.pdf --dry-run
fs-tool write move old.pdf new.pdf --allow-rename --yes
```

Requirements:

- No overwriting.
- Support files, directories and symlinks.
- Refuse filesystem root operations.
- Validate source and destination.
- Preserve metadata where supported.
- Detect whether the operation changes the filename.
- Require `--allow-rename` for filename changes.
- Same-device moves initially; cross-device moves rejected.
- Report the operation result.

The rename authorization is an additional requirement, not a replacement for `--yes`.

---

## 6. Safety and Security

Safety is a core architectural requirement.

### 6.1 Allowed Roots

By default, only the current user's home directory and the current working directory are accessible.
If one or more `--allow-root` values are provided, they replace those default roots.

Explicit roots must be authorized:

```bash
fs-tool --allow-root /mnt/nas inspect inventory /mnt/nas
```

All source and destination paths must be checked against the allowed roots. Configuration may restrict roots but never expand them beyond CLI authorization.

### 6.2 Symlink Handling

- Never recursively follow symlinks by default.
- Record symlink targets during inspection.
- Detect symlink-based path escapes.
- Avoid following links during copy and hashing.
- Handle broken symlinks explicitly.

Path validation should account for symlink resolution and filesystem race conditions. Use `lstat`/`O_NOFOLLOW` where practical.

### 6.3 Write Protection

- No implicit write operations.
- No silent overwriting.
- No unrestricted deletion functionality.
- Explicit Dry-Run or execution authorization.
- Additional authorization for renaming.
- Verify copy operations.
- Provide clear failure reports.

For safety-critical operations, path validation and execution should minimize time-of-check/time-of-use race conditions. Where platform-specific filesystem primitives are necessary, document the limitations.

### 6.4 Scan Integrity

An inventory must distinguish:

- Complete scans.
- Incomplete scans.
- Unreadable files.
- Skipped files.
- Unsupported entries.

Incomplete scans must never produce a success claim for full-tree integrity verification.

### 6.5 Special Files

FIFOs, sockets, devices and other non-regular entries must be reported as `unsupported` and never opened or followed. Hardlinks are tracked by `(st_dev, st_ino)` and not treated as ordinary duplicates.

---

## 7. Configuration

Support an optional TOML configuration file.

Potential settings:

- Allowed roots.
- Ignored directories.
- Ignored file patterns.
- Default maximum scan depth.
- Default entry limits.
- Output preferences.

Configuration must never silently expand filesystem permissions. Explicit command-line security restrictions take precedence.

Avoid implementing a complex configuration system in the initial release. Default config location: `$XDG_CONFIG_HOME/fs-tool/config.toml`, overridden by `--config`.

---

## 8. Data Model

Use a consistent internal representation for filesystem entries.

Proposed model:

```text
FilesystemEntry
├── path
├── name
├── rel_path
├── type
├── extension
├── size
├── modified
├── created
├── accessed
├── changed
├── mode
├── owner
├── mime_type
├── is_symlink
├── target
├── sha256
├── dev_ino
└── metadata
```

Fields that are unavailable or not applicable should be `null`. Document-specific and language-specific information belongs in `metadata`.

The internal data model should be independent of JSON serialization and terminal rendering.

---

## 9. Optional Content Analysis

Content analysis extends basic filesystem metadata with additional information.

### 9.1 Python Source Analysis

Use Python's `ast` module to identify:

- Modules.
- Functions.
- Classes.
- Methods.
- Function signatures.
- Class attributes.
- Instance attributes.
- Docstrings (optional).

Never import or execute analyzed Python files. The feature should be optional and invoked through a dedicated inspection option or subcommand. Size-limited to avoid analysis of very large files.

### 9.2 Document Metadata

Document metadata extraction should be modular so that additional file formats can be supported later. PDF via optional `pypdf` extra; ODF/OOXML via stdlib.

Specialized content analysis is secondary to reliable filesystem operations.

---

## 10. Output and Presentation

### 10.1 JSON

JSON is the default interface.

Requirements:

- Stable schemas.
- Deterministic ordering where applicable.
- Consistent success and error structures.
- No decorative terminal formatting.
- Machine-readable timestamps and sizes.
- Explicit completeness indicators.
- ISO-8601 UTC timestamps, integer bytes, lowercase SHA-256 hashes.

### 10.2 Plain Output

`--plain` provides human-friendly terminal output.

It should support:

- Tree rendering.
- Metadata summaries.
- Duplicate group summaries.
- Comparison reports.
- Operation previews.
- Operation results.

Terminal output should remain optional and must never influence the underlying filesystem operations.

---

## 11. Proposed Project Structure

```text
fs-tool/
│
├── AGENTS.md
├── README.md
├── plan.md
├── tasklist.md
├── workflow.md
├── pyproject.toml
├── uv.lock
├── .gitignore
│
├── src/
│   └── fs_tool/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── errors.py
│       ├── config.py
│       ├── py.typed
│       │
│       ├── core/
│       │   ├── __init__.py
│       │   ├── models.py
│       │   ├── filesystem.py
│       │   ├── traversal.py
│       │   ├── metadata.py
│       │   └── hashing.py
│       │
│       ├── analysis/
│       │   ├── __init__.py
│       │   ├── inventory.py
│       │   ├── search.py
│       │   ├── duplicates.py
│       │   ├── comparison.py
│       │   ├── verification.py
│       │   └── python_analysis.py
│       │
│       ├── operations/
│       │   ├── __init__.py
│       │   ├── copy.py
│       │   ├── move.py
│       │   └── mkdir.py
│       │
│       ├── safety/
│       │   ├── __init__.py
│       │   └── validation.py
│       │
│       └── output/
│           ├── __init__.py
│           ├── json.py
│           └── plain.py
│
└── tests/
    ├── conftest.py
    ├── test_cli.py
    ├── test_output.py
    ├── test_traversal.py
    ├── test_metadata.py
    ├── test_inventory.py
    ├── test_hashing.py
    ├── test_duplicates.py
    ├── test_comparison.py
    ├── test_verification.py
    ├── test_operations.py
    └── test_safety.py
```

This is a proposed structure, not a requirement to create every module immediately. Modules should only be introduced when they have a clear responsibility.

Use res/example_filesystem_unstructured as an example directory that contains unsorted files. You can build tests upon these files, if needed. You can also verify if the cli works with these real files. Consider that tests also run in github actions CI.


---

## 12. Implementation Roadmap

### Phase 0 – Project Foundation and Baseline

- Clean up legacy template artefacts (GUI, config-cli-gui, PyInstaller, config.yaml, GPX examples, init.sh, template scripts, `.idea` run configs).
- Repair `pyproject.toml`: Typer, Python >=3.11, optional `[metadata]` extra, entry point `fs_tool.cli:main`, package discovery `src/`.
- Repair `Makefile`: `install`, `fmt`, `lint`, `test`, `check`, `syncdocs`, `docs`, `build`, `clean`; no side effects in `fmt`.
- Repair CI: `uv sync --all-groups` plus metadata extra; matrix 3.11/3.13; Linux/macOS/Windows; fix release workflow.
- Define internal data models.
- Define common JSON response structure.
- Implement centralized error handling.
- Define process exit codes.
- Configure pytest and Ruff.
- Add initial README.
- Add smoke tests: `fs-tool --version`, `fs-tool --help`, JSON envelope, exit codes.

**Milestone:** A working CLI with help output, version information and consistent JSON responses; `make check` green.

### Phase 1 – Filesystem Core and Safety

- Implement path normalization.
- Implement allowed-root restrictions (Home + CWD default).
- Implement path traversal protection.
- Implement symlink detection and handling.
- Implement recursive directory traversal.
- Implement deterministic sorting.
- Implement file and directory metadata extraction.
- Implement MIME type detection.
- Implement SHA-256 hashing.
- Implement scan completeness and error reporting.
- Add tests for inaccessible paths.
- Add tests for symlinks and path escapes.
- Add tests for allowed-root restrictions.
- Implement TOML configuration loader (`--config`, default location, precedence).

**Milestone:** A reusable and tested filesystem core.

### Phase 2 – Inspection Commands

#### `inspect tree`

- Implement recursive tree generation.
- Implement configurable maximum depth.
- Implement entry limits.
- Implement ignored directories and patterns.
- Implement directory-only mode.
- Implement plain tree rendering.
- Implement optional metadata summaries.
- Implement optional Python code structure.

#### `inspect info`

- Implement single-path metadata inspection.
- Implement timestamps and permissions.
- Implement owner information.
- Implement MIME type information.
- Implement symlink information.
- Implement `--metadata` document extraction (PDF/ODF/OOXML).

#### `inspect inventory`

- Implement structured directory inventories.
- Implement optional SHA-256 calculation.
- Implement deterministic tree hashing.
- Implement inventory completeness reporting.
- Implement JSON serialization.
- Implement `root` + `rel_path` portability.

#### `inspect read`

- Implement bounded UTF-8 reading.
- Implement configurable maximum size.
- Implement truncation reporting.
- Prevent accidental binary and symlink reading.

**Milestone:** Complete read-only filesystem inspection.

### Phase 3 – Search and Analysis

#### `find`

- Implement filename pattern matching.
- Implement extension filtering.
- Implement file type filtering.
- Implement size filtering.
- Implement modification date filtering.

#### `duplicates`

- Implement file-size-based candidate filtering.
- Implement SHA-256 comparison.
- Implement duplicate grouping.
- Implement duplicate reports.
- Handle incomplete scans correctly.

#### `compare`

- Implement source/destination traversal.
- Compare relative paths.
- Detect identical files.
- Detect missing files.
- Detect changed files.
- Detect unexpected files.
- Detect type conflicts.
- Report unsupported entries.

#### `verify`

- Implement inventory-based verification.
- Implement source/destination verification.
- Detect missing and unexpected entries.
- Verify file sizes and hashes.
- Report incomplete verification.
- Implement `schema_version` check for inventory files.

**Milestone:** Reliable filesystem analysis and integrity verification.

### Phase 4 – Filesystem Operations

#### General

- Implement common write-operation interface.
- Implement mandatory Dry-Run or execution authorization.
- Implement structured operation reports.
- Implement no-overwrite protection.
- Implement preflight validation.
- Validate source and destination paths.

#### `write mkdir`

- Implement directory creation.
- Support missing parent directories.
- Implement Dry-Run.
- Add tests.

#### `write copy`

- Implement regular file copying.
- Implement safe destination creation.
- Preserve metadata where appropriate.
- Verify copied contents.
- Implement recursive directory copying.
- Define explicit symlink handling.
- Implement Dry-Run.
- Add tests for conflicts and partial failures.

#### `write move`

- Implement file moving.
- Implement directory moving.
- Implement symlink moving.
- Implement filename-change detection.
- Require `--allow-rename` for renaming.
- Implement Dry-Run.
- Implement no-overwrite protection.
- Add tests for conflicts and safety restrictions.

**Milestone:** Safe and verifiable filesystem modifications.

### Phase 5 – Output and Presentation

- Finalize JSON output schemas.
- Implement consistent `--plain` handling.
- Implement human-readable metadata summaries.
- Implement tree visualization.
- Implement duplicate reports.
- Implement comparison reports.
- Implement operation previews.
- Test output consistency across commands.

**Milestone:** Consistent machine-readable and human-readable interfaces.

### Phase 6 – Additional Metadata and Analysis

- Integrate Python AST analysis.
- Extract functions and classes.
- Extract method signatures and attributes.
- Support optional docstrings.
- Implement PDF metadata extraction (`pypdf` extra).
- Implement ODF metadata extraction.
- Implement OOXML metadata extraction.
- Define optional dependency handling.

**Milestone:** Extended file understanding without executing file contents.

### Phase 7 – Documentation and Release

- Complete README.
- Document installation using uv.
- Document all CLI commands.
- Document global options.
- Document JSON response schemas.
- Document exit codes.
- Document safety restrictions.
- Add practical examples.
- Test installation on Kubuntu.
- Run complete test suite.
- Run Ruff checks.
- Prepare initial release.

**Milestone:** First stable release.

---

## 13. Definition of Done

The initial CLI is considered complete when it can:

1. Recursively inspect directories and individual files.
2. Produce deterministic, machine-readable inventories.
3. Retrieve useful file metadata.
4. Calculate SHA-256 hashes.
5. Identify duplicate files.
6. Compare directory trees and file contents.
7. Verify expected filesystem states.
8. Copy and move files safely.
9. Rename files only with explicit authorization.
10. Present results in JSON and human-readable formats.
11. Enforce allowed-root restrictions.
12. Report incomplete operations and scans accurately.
13. Pass `make check` (format, lint, type check, tests, coverage).
14. Have green CI on all matrix jobs.

**Guiding principle: Reliable information first, controlled operations second, verifiable results always.**

---

## 14. Future Extensions (Out of Initial Scope)

Potential extensions:

- MCP adapter.
- OpenCode skill integration.
- Agent-assisted restructuring plans.
- Batch operation plans.
- Transaction-like execution and rollback support.
- Additional document and media metadata.
- Image dimensions and EXIF extraction.
- File-type detection based on file signatures.
- More advanced duplicate detection.
- Exportable HTML reports.
- Delete functionality (to be designed deliberately if added later).

These features must not delay or complicate the initial CLI implementation.