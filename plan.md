# fs-tool – Architecture and Functional Specification

## 1. Project Objective

Develop a lightweight, secure and agent-friendly command-line tool for inspecting, analyzing, comparing and organizing local filesystems.

The application should support both interactive human usage and automated execution by AI agents.

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

## 2. Architectural Principles

### 2.1 Separation of Concerns

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
                 |
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

### 2.2 Design Principles

- Keep the architecture modular but lightweight.
- Avoid unnecessary abstractions and complex frameworks.
- Prefer standard-library functionality.
- Provide deterministic and reproducible results.
- Separate filesystem traversal from content analysis.
- Separate analysis from filesystem modifications.
- Use consistent data structures across commands.
- Never execute analyzed files or import them dynamically.

### 2.3 Technology Stack

| Component | Technology |
|---|---|
| Language | Python 3.13+ |
| CLI | Typer |
| Filesystem | pathlib, os, shutil |
| Hashing | hashlib |
| Python analysis | ast |
| Serialization | json |
| Configuration | TOML |
| Package management | uv |
| Testing | pytest |
| Linting | Ruff |

External dependencies should be introduced only where they provide meaningful functionality.

---

## 3. CLI Design

### 3.1 General Interface

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
│
└── write
    ├── mkdir
    ├── copy
    └── move
```

The hierarchy separates inspection and analysis from filesystem modifications.

### 3.2 Global Options

| Option | Description |
|---|---|
| `-h, --help` | Show help |
| `--allow-root PATH` | Explicitly allow an additional filesystem root; repeatable |
| `--plain` | Human-readable output instead of JSON |
| `--json` | Explicitly request JSON output |
| `--version` | Show application version |

JSON is the default output format.

`--plain` and `--json` are mutually exclusive.

The output format must be consistent across all commands.

### 3.3 Output Contract

Every command must return a predictable result structure.

Successful operations:

```json
{
  "success": true,
  "command": "inspect.info",
  "result": {},
  "errors": []
}
```

Failed operations:

```json
{
  "success": false,
  "command": "write.copy",
  "result": null,
  "errors": [
    {
      "code": "TARGET_EXISTS",
      "message": "Destination already exists."
    }
  ]
}
```

Requirements:

- JSON output goes to stdout.
- Human-readable diagnostics may go to stderr.
- Error messages must be understandable and actionable.
- Results must not depend on terminal formatting.
- Use stable error codes.
- Use meaningful process exit codes.

Proposed exit codes:

| Code | Meaning |
|---|---|
| 0 | Successful operation |
| 1 | Operation failed or verification found discrepancies |
| 2 | Invalid arguments or incomplete analysis |
| 3 | Access denied or safety restriction |
| 4 | Operation conflict |

---

## 4. Functional Requirements

## 4.1 Filesystem Inspection

### `inspect tree`

Display a directory tree.

Examples:

```bash
fs-tool inspect tree ~/Documents
fs-tool inspect tree ~/Projects --plain
fs-tool inspect tree ~/Projects --plain --details
fs-tool inspect tree ~/Projects --plain --show-code
```

Features:

- Recursive directory traversal.
- Alphabetical sorting.
- Configurable maximum depth.
- Optional maximum number of entries.
- Optional directory-only mode.
- Optional metadata display.
- Optional Python source structure.
- Optional directory summaries.
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

Ignore rules must be configurable. Hidden directories must not automatically be excluded unless configured.

The JSON output should contain the complete structured tree, not terminal-rendered tree characters.

### `inspect info`

Retrieve metadata for one file or directory.

Example:

```bash
fs-tool inspect info ~/Documents/report.pdf
```

Collect where available:

| Attribute | Description |
|---|---|
| `path` | Absolute path |
| `name` | Filename |
| `type` | File, directory, symlink, other |
| `extension` | File extension |
| `size` | Size in bytes |
| `modified` | Modification timestamp |
| `created` | Creation/birth time, if supported |
| `accessed` | Last access timestamp |
| `mode` | Filesystem permissions |
| `owner` | Owner information where available |
| `mime_type` | Best-effort MIME type |
| `is_symlink` | Whether the entry is a symbolic link |
| `target` | Symlink target, if applicable |

Optional document metadata:

- Author
- Title
- Subject
- Creation date
- Modification date

Initially supported formats:

- PDF
- ODT, ODS, ODP, ODG
- DOCX, XLSX, PPTX

Document metadata extraction must be read-only and must never execute embedded content.

Unavailable metadata must be represented as `null`, not silently omitted.

### `inspect inventory`

Create a deterministic inventory of a directory tree.

Example:

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

The inventory must explicitly indicate whether the scan was complete.

A tree hash must only be generated for a complete inventory.

### `inspect read`

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

## 4.2 File and Directory Search

### `find`

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

Search results must use the common entry schema.

Search should be read-only and must respect all filesystem access restrictions.

---

## 4.3 Duplicate Detection

### `duplicates`

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
    "duplicate_file_count": 2
  },
  "errors": []
}
```

Requirements:

- Never delete files automatically.
- Do not follow symlinks.
- Exclude incomplete or unreadable files from verified duplicate groups.
- Clearly distinguish confirmed duplicates from incomplete scan results.
- Avoid hashing files unnecessarily by using file size as an initial filter.

---

## 4.4 Directory Comparison

### `compare`

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

The comparison should use relative paths as the primary structural reference.

SHA-256 should be used to verify file content.

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

A comparison must not assume that files with identical names have identical contents.

---

## 4.5 Verification

### `verify`

Verify the result of a filesystem operation or restructuring.

Examples:

```bash
fs-tool verify inventory.json ~/Documents_New
fs-tool verify ~/Documents ~/Documents_New
```

The first syntax represents verification against a previously stored inventory.

The second represents verification against a source directory.

Requirements:

- Check expected files and directories.
- Compare file sizes and hashes where available.
- Detect missing entries.
- Detect unexpected entries.
- Detect changed contents.
- Report incomplete verification.
- Return machine-readable discrepancy reports.

Verification must distinguish between a complete successful result and a result that could not be fully verified.

---

## 4.6 Filesystem Operations

All modifications belong to the `write` command group.

### General Rules

Every write operation must support:

- `--dry-run`
- `--yes`

Exactly one of these options must be specified.

`--dry-run` displays the planned operation without modifying the filesystem.

`--yes` authorizes execution.

Additional rules:

- Never overwrite existing files or directories.
- Never delete data.
- Validate source and destination paths.
- Check allowed roots.
- Avoid following symlinks unexpectedly.
- Return a structured operation report.

### `write mkdir`

Create a directory, including missing parent directories.

Example:

```bash
fs-tool write mkdir ~/Documents/NewFolder --dry-run
fs-tool write mkdir ~/Documents/NewFolder --yes
```

### `write copy`

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

Symlink copying must use an explicit policy. The default must never follow a source symlink and copy its target implicitly.

### `write move`

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
- Report the operation result.

The rename authorization is an additional requirement, not a replacement for `--yes`.

---

## 5. Safety and Security

Safety is a core architectural requirement.

### 5.1 Allowed Roots

By default, only the current user's home directory is accessible.

Additional roots must be explicitly authorized:

```bash
fs-tool --allow-root /mnt/nas inspect inventory /mnt/nas
```

All source and destination paths must be checked against the allowed roots.

### 5.2 Symlink Handling

- Never recursively follow symlinks by default.
- Record symlink targets during inspection.
- Detect symlink-based path escapes.
- Avoid following links during copy and hashing.
- Handle broken symlinks explicitly.

Path validation should account for symlink resolution and filesystem race conditions.

### 5.3 Write Protection

- No implicit write operations.
- No silent overwriting.
- No unrestricted deletion functionality.
- Explicit Dry-Run or execution authorization.
- Additional authorization for renaming.
- Verify copy operations.
- Provide clear failure reports.

For safety-critical operations, path validation and execution should minimize time-of-check/time-of-use race conditions. Where platform-specific filesystem primitives are necessary, document the limitations.

### 5.4 Scan Integrity

An inventory must distinguish:

- Complete scans.
- Incomplete scans.
- Unreadable files.
- Skipped files.
- Unsupported entries.

Incomplete scans must never produce a success claim for full-tree integrity verification.

---

## 6. Data Model

Use a consistent internal representation for filesystem entries.

Proposed model:

```text
FilesystemEntry
├── path
├── name
├── type
├── extension
├── size
├── modified
├── created
├── accessed
├── mode
├── owner
├── mime_type
├── is_symlink
├── target
├── sha256
└── metadata
```

Fields that are unavailable or not applicable should be `null`.

Document-specific and language-specific information belongs in `metadata`.

The internal data model should be independent of JSON serialization and terminal rendering.

---

## 7. Optional Content Analysis

Content analysis extends basic filesystem metadata with additional information.

### Python Source Analysis

Reuse functionality from `project_structure.py`.

Use Python's `ast` module to identify:

- Modules.
- Functions.
- Classes.
- Methods.
- Function signatures.
- Class attributes.
- Instance attributes.
- Docstrings (optional).

Never import or execute analyzed Python files.

The feature should be optional and invoked through a dedicated inspection option or subcommand.

### Document Metadata

Reuse the existing metadata extraction functionality from `show_tree.py` where appropriate.

Document metadata extraction should be modular so that additional file formats can be supported later.

Specialized content analysis is secondary to reliable filesystem operations.

---

## 8. Output and Presentation

### JSON

JSON is the default interface.

Requirements:

- Stable schemas.
- Deterministic ordering where applicable.
- Consistent success and error structures.
- No decorative terminal formatting.
- Machine-readable timestamps and sizes.
- Explicit completeness indicators.

### Plain Output

`--plain` provides human-friendly terminal output.

It should support:

- Tree rendering.
- Metadata summaries.
- Duplicate group summaries.
- Comparison reports.
- Operation previews.
- Operation results.

Reuse the visual strengths of `show_tree.py`.

Terminal output should remain optional and must never influence the underlying filesystem operations.

---

## 9. Configuration

Support an optional TOML configuration file.

Potential settings:

- Allowed roots.
- Ignored directories.
- Ignored file patterns.
- Default maximum scan depth.
- Default entry limits.
- Output preferences.

Configuration must never silently expand filesystem permissions.

Explicit command-line security restrictions take precedence.

Avoid implementing a complex configuration system in the initial release.

---

## 10. Proposed Project Structure

```text
fs-tool/
│
├── AGENTS.md
├── README.md
├── plan.md
├── tasklist.md
├── pyproject.toml
├── uv.lock
├── .gitignore
│
├── src/
│   └── fs_tool/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
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
    ├── test_traversal.py
    ├── test_metadata.py
    ├── test_inventory.py
    ├── test_hashing.py
    ├── test_duplicates.py
    ├── test_comparison.py
    ├── test_operations.py
    └── test_safety.py
```

This is a proposed structure, not a requirement to create every module immediately. Modules should only be introduced when they have a clear responsibility.

---

## 11. Implementation Roadmap

### Phase 1 – Project Foundation

- Initialize project with uv.
- Configure Typer and entry points.
- Define internal data models.
- Establish JSON output contract.
- Implement common error handling.
- Set up pytest and Ruff.

### Phase 2 – Filesystem Core

- Implement safe path handling.
- Implement directory traversal.
- Implement symlink handling.
- Implement metadata extraction.
- Implement SHA-256 hashing.
- Implement allowed-root validation.

### Phase 3 – Inspection and Analysis

- Implement `inspect tree`.
- Implement `inspect info`.
- Implement `inspect inventory`.
- Implement `inspect read`.
- Implement `find`.
- Implement `duplicates`.
- Implement `compare`.
- Implement `verify`.

### Phase 4 – Filesystem Operations

- Implement `write mkdir`.
- Implement `write copy`.
- Implement `write move`.
- Add rename authorization.
- Implement Dry-Run previews.
- Add post-operation verification.

### Phase 5 – Output and Additional Analysis

- Implement plain tree rendering.
- Implement detailed metadata output.
- Integrate Python AST analysis.
- Add document metadata extraction.
- Improve summaries and reports.

### Phase 6 – Documentation and Release

- Complete README.
- Document all CLI commands.
- Document JSON schemas.
- Document security restrictions.
- Add practical usage examples.
- Test installation and execution on Kubuntu.
- Prepare initial release.

---

## 12. Definition of Done

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

**Guiding principle: Reliable information first, controlled operations second, verifiable results always.**

---

## 13. Future Extensions (Out of Initial Scope)

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

These features must not delay or complicate the initial CLI implementation.