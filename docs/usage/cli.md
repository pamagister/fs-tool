# Command-line interface

fs-tool is installed as the `fs-tool` command. From a source checkout, the equivalent module
invocation is:

```bash
python -m fs_tool [OPTIONS] COMMAND [ARGS]
```

Running `fs-tool` without a command prints the help text.

## Command overview

```text
fs-tool
├── inspect
│   ├── tree
│   ├── info
│   ├── analyze
│   ├── inventory
│   └── read
├── find
├── duplicates
├── compare
├── verify
│   ├── inventory
│   └── tree
└── write
    ├── mkdir
    ├── copy
    └── move
```

The command hierarchy separates read-only inspection and analysis from filesystem modifications.

## Global options

Global options may be placed before or after the command, for example:

```bash
fs-tool --plain inspect tree ~/Documents
fs-tool inspect tree ~/Documents --plain
```

| Option | Description |
|---|---|
| `-h`, `--help` | Show help and exit. |
| `--version` | Show the application version and exit. |
| `--allow-root PATH` | Set an allowed root. Repeatable. Supplied values replace the default home and CWD roots. |
| `--config PATH` | Path to a TOML configuration file. |
| `--format auto\|json\|plain` | Select the output format. Default: `auto`. |
| `--json` | Explicitly request JSON output. |
| `--plain` | Human-readable output instead of JSON. |
| `--verbose` | Return the complete existing entry fields instead of the compact default profile. |
| `--install-completion` | Install shell completion for the current shell. |
| `--show-completion` | Print the completion script for the current shell. |

`--json` and `--plain` are mutually exclusive. With `--format auto`, output is plain text when
stdout is a terminal and JSON otherwise (for pipes, redirection and agents).

Commands that return filesystem entries default to a compact per-command profile. `--verbose`
restores the complete entry fields. `--verbose` works independently of the output format and never
triggers extra filesystem analysis, metadata extraction or hashing:

```bash
fs-tool --verbose inspect inventory ~/Documents
fs-tool inspect inventory ~/Documents --verbose
fs-tool --plain --verbose find ~/Documents --extension pdf
```

See [Output formats](output.md) for the JSON envelope and [Configuration](configuration.md) for the
configuration file.

## Global path restrictions

By default, fs-tool only accesses the current user's home directory and the current working
directory. When `--allow-root` is supplied, those values replace the default roots:

```bash
fs-tool --allow-root /mnt/nas inspect inventory /mnt/nas
```

All source and destination paths must lie within an allowed root. A configuration file may restrict
the effective roots further, but it can never expand them. See [Safety model](safety.md).

---

## `inspect tree`

Display a directory tree.

```bash
fs-tool inspect tree SOURCE [OPTIONS]
```

| Option | Description |
|---|---|
| `--max-depth N` | Maximum recursion depth. |
| `--max-entries N` | Maximum number of entries to collect. |
| `--dirs-only` | Include directory entries only. |
| `--ignore-dir NAME` | Ignore a directory by name. Repeatable. |
| `--ignore-pattern PATTERN` | Ignore names matching a glob pattern. Repeatable. |
| `--sort-by MODE` | Sort entries by `name` (default), `size`, `modified` or `extension`. |
| `--no-default-ignore` | Include directories from the default ignore list. |

The default ignore set includes `.git`, `.venv`, `__pycache__`, `.pytest_cache`, `.ruff_cache`,
`.mypy_cache`, `node_modules`, `build`, `dist`, `.idea` and `.vscode`. Use `--no-default-ignore` to
disable it. Symlinks are recorded but never followed.

JSON result fields: `root`, `entries`, `count`. Each entry contains `rel_path` and `type` by
default; `--verbose` returns all fields described in
[JSON response schemas](output.md#filesystem-entry). Plain output renders a tree, and `--verbose`
adds a detail block below each entry.

If the scan is truncated or contains unreadable entries, the command reports `complete: false` and
exits with code 5.

## `inspect info`

Show metadata for a single file or directory.

```bash
fs-tool inspect info SOURCE [OPTIONS]
```

| Option | Description |
|---|---|
| `--metadata` | Deprecated compatibility flag. Format metadata is extracted automatically. |
| `--hash` | Calculate the SHA-256 hash of a regular file. |

`inspect info` returns filesystem properties and the format metadata available for the file. Format
metadata is extracted automatically for supported formats: PDF (`.pdf`), OpenDocument (`.odt`,
`.ods`, `.odp`, `.odg`) and Office Open XML (`.docx`, `.xlsx`, `.pptx`). Extraction is read-only and
never executes file content. PDF metadata requires the optional `metadata` extra (`pypdf`); ODF and
OOXML metadata use the standard library. Files larger than 100 MiB are not inspected for metadata.

`--metadata` is retained only for compatibility with earlier releases and has no additional effect.
Content analysis, including Python source structure, belongs to `inspect analyze`.

JSON result: a single filesystem entry plus `metadata_result`. The `metadata` field holds extracted
metadata when extraction succeeds. `metadata_result` is a capability result that reports the
`available`, `unavailable` or `failed` status; it is `null` when the format has no metadata
capability. `sha256` is added when `--hash` is requested and identifies the source file.

## `inspect analyze`

Run every applicable structural analysis for a single regular file.

```bash
fs-tool inspect analyze SOURCE [OPTIONS]
```

| Option | Description |
|---|---|
| `--hash` | Calculate the SHA-256 hash of the source file. |

Analyses return structure without complete file content. The supported analyses are:

| Format | Capability | Result data |
|---|---|---|
| Markdown (`.md`, `.markdown`) | `markdown_structure` | Line count, heading count, maximum heading level and heading list. Headings inside fenced code blocks are ignored. |
| Python (`.py`) | `python_ast` | Module docstring, imports, functions, classes, methods and class attributes. The file is parsed with `ast` and is never imported or executed. |
| Plain text (`.txt`, `.text`, `.log`) | `text_structure` | Line, non-empty line, word, character and paragraph counts, and maximum line length. |
| PDF (`.pdf`) | `pdf_pages` | Page count, and each page's dimensions, orientation and rotation. Requires the optional `metadata` extra (`pypdf`). |

Markdown and text analysis are limited to 5 MiB per file; Python analysis is limited to 1 MiB. A
capability whose prerequisite is missing is reported as `unavailable` with a `help` reference. A
capability that was attempted but failed is reported as `failed` with an `error_code`. One
unavailable or failed capability does not prevent other applicable analyses from running, and the
command still succeeds.

Symlinks and non-regular files are rejected. An unsupported format is not an error: the result has
`supported: false` and an empty `analyses` list.

JSON result fields: `path`, `name`, `extension`, `size`, `sha256`, `supported`, `analyses`. The
`sha256` field is `null` unless `--hash` is supplied. Each entry in `analyses` is a capability
result with `capability`, `status`, `message`, `help`, `error_code` and `data`; see
[Output formats](output.md#capability-results).

## `inspect inventory`

Create a deterministic, portable inventory of a directory tree.

```bash
fs-tool inspect inventory SOURCE [OPTIONS]
```

| Option | Description |
|---|---|
| `--hash` | Calculate SHA-256 hashes for regular files. |
| `--tree-hash` | Calculate an aggregate tree hash. Only produced for complete scans. |
| `--max-depth N` | Maximum recursion depth. |
| `--max-entries N` | Maximum number of entries to collect. |
| `--dirs-only` | Include directory entries only. |
| `--ignore-dir NAME` | Ignore a directory by name. Repeatable. |
| `--ignore-pattern PATTERN` | Ignore names matching a glob pattern. Repeatable. |
| `--sort-by MODE` | Sort entries by `name` (default), `size`, `modified` or `extension`. |
| `--no-default-ignore` | Include directories from the default ignore list. |
| `--extension EXT` | Only include regular files with this extension. |
| `--min-size SIZE` | Minimum file size, for example `1K`, `2M` or `1G`. |
| `--max-size SIZE` | Maximum file size, for example `1K`, `2M` or `1G`. |
| `--fields FIELDS` | Comma-separated entry fields to return. Overrides compact and verbose profiles. |
| `--max-hash-bytes SIZE` | Skip hashing files larger than SIZE and emit a `HASH_SKIPPED` warning. |
| `--progress` | Write progress information to stderr only. |

Inventory entries are addressed by `rel_path` relative to the declared root and omit the absolute
`path`, so an inventory can be compared across machines. JSON result fields: `root`, `entries`,
`count`, `generated_at`, `complete`, and optionally `tree_hash`.

By default each entry contains `rel_path`, `type`, `extension`, `size` and `modified`. `sha256` is
added only with `--hash`. `--verbose` returns every remaining entry field, still without the
absolute `path`. Plain output uses the same compact fields on each entry line, so JSON and plain
default output expose the same inventory information.

Filters (`--extension`, `--min-size`, `--max-size`) are applied after traversal and before hashing
and `tree_hash`. Directories and symlinks are always retained; extension and size filters apply to
regular files. `filtered` is included when filters remove entries. `skipped` counts traversal-level
ignores and `truncated` is true when `--max-entries` stopped the scan.

`--fields` overrides both the compact and verbose profiles. It does not change `tree_hash`.
`--max-hash-bytes` skips hashing for larger files, keeps `sha256: null`, and adds a `HASH_SKIPPED`
warning without making the scan incomplete. `--progress` writes progress lines to stderr only.

The tree hash uses algorithm version 2. It is computed from the sorted entries and hashes only
`rel_path`, `type`, `extension`, `size` and `sha256`. Directory and symlink sizes are normalized to
`null` because their `st_size` is filesystem- or target-path-dependent. It excludes absolute paths,
inode identities, timestamps, permissions, ownership, MIME type and symlink targets, and does not
depend on the selected output profile.

Use `--hash` when the inventory will later be checked with `verify inventory`; without hashes only
sizes and types can be compared.

## `inspect read`

Read bounded textual content from a regular file.

```bash
fs-tool inspect read SOURCE [OPTIONS]
```

| Option | Description |
|---|---|
| `--max-bytes N` | Maximum number of UTF-8 bytes to return. Default: `65536`. |

Plain text files are read as UTF-8. PDF text extraction is available through the optional
`metadata` extra (`pypdf`); it returns extracted text, never PDF metadata or page-structure
analysis. PDF source files larger than 100 MiB are rejected. Text files and PDFs are otherwise
bounded by `--max-bytes`; truncation never splits a UTF-8 character.

Symlinks and non-regular files are rejected. Binary content that is not valid UTF-8 is rejected
unless the format has a dedicated textual representation such as PDF. If the content exceeds
`--max-bytes`, it is truncated and `truncated` is set to `true`.

JSON result fields: `path`, `name`, `size`, `content`, `truncated`, `encoding`, `format`,
`representation`. PDF results additionally include `page_count` and `pages`. `format` is `text` or
`pdf`; `representation` is `utf-8_text` or `extracted_text`. Each PDF page object contains `index`
and `content`, so page boundaries remain available even though `content` is a single string joined
with blank lines.

If the optional dependency is missing, the command fails with the structured error code
`CAPABILITY_UNAVAILABLE` and points to `fs-tool capabilities` for setup instructions. Plain output
prints the content and writes a truncation warning to stderr.

## `capabilities`

List every supported capability and its current availability.

```bash
fs-tool capabilities
fs-tool capabilities --plain
fs-tool capabilities --json
```

The command only checks the environment; it does not analyze files, install packages or download
resources. JSON is the default and is the primary interface for agents; use `--plain` for
human-readable output.

Each capability reports:

- `id` — stable capability identifier (for example `image_object_detection`).
- `supported` — `true` for every registered capability. An unsupported format is reported
  differently by `inspect info` (`metadata: null` with `metadata_result: null`) and `inspect
  analyze` (`supported: false` with an empty `analyses` list).
- `available` — whether all prerequisites are present right now.
- `status` — `available`, `unavailable` or `failed`.
- `requirements` — each declared Python package or external resource, with its availability and an
  exact installation command for missing packages.
- `missing_requirements` — the unavailable requirements, repeated for convenient consumption.
- `next_steps` — actionable commands such as `pip install "fs-tool-cli[image]"` or
  `fs-tool setup yolo`.
- `setup` — the setup command, when the capability has one (for example `fs-tool setup yolo`).

The top-level result also includes `count`, `available_count` and `model_directory` (the resolved
model storage directory).

Example JSON response for a capability whose prerequisites are missing:

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

See [Setup](setup.md) for the full setup instructions, the YOLO model details and the
`FS_TOOL_MODEL_DIR` override.

## `setup`

Prepare optional capabilities without changing the Python environment.

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
| `pdf` | Checks the `pypdf` dependency (extra `metadata`) used by PDF metadata, page-structure and text capabilities. |
| `image` | Checks Pillow, numpy and ONNX Runtime (extra `image`) used by image metadata and object detection. Never downloads the model. |
| `yolo` | Checks the image dependencies and downloads and verifies the YOLO26n ONNX model when it is missing. |

Use `--all` to prepare every target independently. Use `--force` with `yolo` to replace only an
invalid existing model file; a valid model is never overwritten.

Setup is idempotent: calling it again for an already-ready target does not re-download or re-check
unnecessarily beyond re-verifying requirements.

Exit code 1 indicates that at least one target failed; invalid usage exits with code 2. See
[Setup](setup.md) for the YOLO model source, license, checksum, storage location and the
`FS_TOOL_MODEL_DIR` override.

---

## `find`

Find filesystem entries matching filters.

```bash
fs-tool find SOURCE [OPTIONS]
```

| Option | Description |
|---|---|
| `--name PATTERN` | Match filenames against a glob pattern. Repeatable; multiple patterns are combined with OR. |
| `--extension EXT` | Filter by file extension, with or without a leading dot. Case-insensitive. |
| `--type TYPE` | Filter by entry type: `file`, `directory`, `symlink` or `other`. |
| `--min-size SIZE` | Minimum file size, for example `1K`, `2M` or `1G`. |
| `--max-size SIZE` | Maximum file size, for example `1K`, `2M` or `1G`. |
| `--modified-after TIMESTAMP` | Entries modified at or after an ISO-8601 timestamp. |
| `--modified-before TIMESTAMP` | Entries modified at or before an ISO-8601 timestamp. |
| `--max-depth N` | Maximum recursion depth. |
| `--max-entries N` | Maximum number of entries to scan. |
| `--ignore-dir NAME` | Ignore a directory by name. Repeatable. |
| `--ignore-pattern PATTERN` | Ignore names matching a glob pattern. Repeatable. |
| `--sort-by MODE` | Sort matches by `name` (default), `size`, `modified` or `extension`. |
| `--no-default-ignore` | Include directories from the default ignore list. |

All specified filters are combined with logical AND. Sizes use binary multipliers (`K` = 1024,
`M` = 1024², `G` = 1024³, `T` = 1024⁴). Timestamps use the format accepted by
`datetime.fromisoformat`, for example `2026-01-31` or `2026-01-31T12:00:00+00:00`.

JSON result fields: `root`, `entries`, `count`, `complete`. Each entry contains `rel_path`, `type`
and `size` by default; `--verbose` returns the complete entry fields described in
[JSON response schemas](output.md#filesystem-entry).

## `duplicates`

Find regular files with identical content.

```bash
fs-tool duplicates SOURCE [OPTIONS]
```

| Option | Description |
|---|---|
| `--min-size SIZE` | Minimum file size considered. Default: `1` byte. |
| `--include-empty` | Include empty files in duplicate detection. |
| `--max-entries N` | Maximum number of entries to scan. |
| `--ignore-dir NAME` | Ignore a directory by name. Repeatable. |
| `--ignore-pattern PATTERN` | Ignore names matching a glob pattern. Repeatable. |
| `--no-default-ignore` | Include directories from the default ignore list. |

Detection first groups files by size and then compares SHA-256 hashes. Hardlinks are tracked by
`(st_dev, st_ino)` and are not reported as duplicates.

JSON result fields:

| Field | Description |
|---|---|
| `root` | Scanned root. |
| `duplicate_groups` | Groups with `sha256`, `size`, `count` and `files`. |
| `duplicate_group_count` | Number of duplicate groups. |
| `duplicate_file_count` | Total number of files in duplicate groups. |
| `complete` | Whether the whole tree could be scanned. |

## `compare`

Compare two directory trees.

```bash
fs-tool compare SOURCE DESTINATION [OPTIONS]
```

| Option | Description |
|---|---|
| `--max-entries N` | Maximum number of entries to scan per tree. |
| `--ignore-dir NAME` | Ignore a directory by name. Repeatable. |
| `--ignore-pattern PATTERN` | Ignore names matching a glob pattern. Repeatable. |
| `--no-default-ignore` | Include directories from the default ignore list. |

Regular files are compared by SHA-256. Directories must exist in both trees. Symlinks are compared by
their recorded target.

JSON result fields: `source`, `destination`, `identical`, `missing`, `changed`, `unexpected`,
`type_conflicts`, `unsupported`, `complete`.

| Category | Meaning |
|---|---|
| `identical` | Present in both trees with identical content or target. |
| `missing` | Present in the source but absent from the destination. |
| `changed` | Present in both trees with different content or symlink target. |
| `unexpected` | Present in the destination but absent from the source. |
| `type_conflicts` | Same relative path has a different entry type. |
| `unsupported` | Special files that are reported but not compared. |

## `verify inventory`

Verify a target directory against a previously generated inventory.

```bash
fs-tool verify inventory INVENTORY_FILE TARGET [OPTIONS]
```

| Option | Description |
|---|---|
| `--max-entries N` | Maximum number of entries to scan. |
| `--ignore-dir NAME` | Ignore a directory by name. Repeatable. |
| `--ignore-pattern PATTERN` | Ignore names matching a glob pattern. Repeatable. |

The inventory may be either the full JSON envelope produced by `inspect inventory` or a bare
inventory object. The `schema_version` must be `1`; the inventory must contain `rel_path` and `type`
for every entry. Inventories produced from an incomplete scan make the verification incomplete.

`size`, `target` and `sha256` are compared only when the inventory contains them. The compact
default profile keeps `size`, so size mismatches are detected. It omits `target`, so symlink-target
changes are skipped; generate the inventory with `--verbose` or `--hash` when target or content
comparison is required.

JSON result fields: `inventory_file`, `target`, `missing`, `unexpected`, `changed`, `size_mismatch`,
`hash_mismatch`, `complete`. Size and hash mismatches are also listed under `changed`.

A verification succeeds only when it is complete and reports no missing, unexpected or changed
entries. Otherwise it exits with code 1; an incomplete verification exits with code 5.

## `verify tree`

Verify a destination directory against a source directory.

```bash
fs-tool verify tree SOURCE DESTINATION [OPTIONS]
```

| Option | Description |
|---|---|
| `--max-entries N` | Maximum number of entries to scan per tree. |
| `--ignore-dir NAME` | Ignore a directory by name. Repeatable. |
| `--ignore-pattern PATTERN` | Ignore names matching a glob pattern. Repeatable. |

Both trees are traversed and compared by relative path. Regular files are checked by size and
SHA-256; symlinks are checked by target. JSON result fields: `source`, `destination`, `missing`,
`unexpected`, `changed`, `size_mismatch`, `hash_mismatch`, `complete`.

---

## Write operations

All write commands require exactly one of `--dry-run` or `--yes`:

- `--dry-run` validates the operation and reports what would happen without changing the filesystem.
- `--yes` authorizes execution.

Every write operation validates all paths against the allowed roots, never overwrites an existing
destination, and returns a structured operation report. Existing data is never deleted.

### `write mkdir`

Create a directory without overwriting existing entries.

```bash
fs-tool write mkdir DESTINATION (--dry-run | --yes) [--parents]
```

| Option | Description |
|---|---|
| `--parents` | Create missing parent directories. |
| `--dry-run` | Show the planned operation only. |
| `--yes` | Authorize execution. |

If the destination is already a directory, the operation is idempotent and reports `created: false`.
If the destination exists as another entry type, the command fails with a conflict (exit code 4).
Without `--parents`, a missing parent directory is an error.

### `write copy`

Copy a file or directory tree without overwriting.

```bash
fs-tool write copy SOURCE DESTINATION (--dry-run | --yes) [--symlinks POLICY]
```

| Option | Description |
|---|---|
| `--symlinks POLICY` | Symlink policy: `error` (default), `copy` or `skip`. |
| `--dry-run` | Show the planned operation only. |
| `--yes` | Authorize execution. |

The destination must not exist, and its parent directory must exist. Copying a directory into itself
or one of its descendants is rejected. Regular files are written to a temporary file, verified by
SHA-256 and published without overwriting. File mode and timestamps are preserved where supported.
The `--symlinks` policy applies to symbolic links inside a copied tree; symlinks are never followed
implicitly. With `skip`, skipped entries are listed in the report.

### `write move`

Move a file, directory or symlink without overwriting.

```bash
fs-tool write move SOURCE DESTINATION (--dry-run | --yes) [--allow-rename]
```

| Option | Description |
|---|---|
| `--allow-rename` | Authorize changing the source filename. |
| `--dry-run` | Show the planned operation only. |
| `--yes` | Authorize execution. |

The destination must not exist, and its parent directory must exist. Moving a filesystem root,
moving a directory into itself, and cross-device moves are rejected. A move that changes the
filename requires both `--allow-rename` and `--yes`. The command verifies that the entry exists at
the destination and no longer exists at the source.

---

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Successful operation. |
| `1` | Operation failed or verification found discrepancies. |
| `2` | Invalid arguments or incomplete analysis. |
| `3` | Access denied or safety restriction. |
| `4` | Operation conflict, such as an existing destination. |
| `5` | Incomplete scan or verification. |

`--help` and `--version` are documented exceptions to the JSON envelope. Invalid command-line usage
exits with code 2.

## Working with large trees

Use `--max-depth` and `--max-entries` to bound scans. A truncated scan is never reported as complete:
the JSON envelope has `success: false` and `complete: false`, the command exits with code 5, and
plain output writes a diagnostic to stderr. Partial results are still returned.
