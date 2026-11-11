# Output formats

fs-tool supports a machine-readable JSON interface and a human-oriented plain-text interface. Both
describe the same results; only the presentation differs.

## Selecting a format

| Invocation | Result |
|---|---|
| `--json` | JSON output. |
| `--plain` | Plain-text output. |
| `--format json` | JSON output. |
| `--format plain` | Plain-text output. |
| `--format auto` | Plain when stdout is a terminal, JSON otherwise. |

`auto` is the default. Pipes, redirection and captured process output therefore receive JSON,
which makes the CLI predictable for scripts and agents.

`--json` and `--plain` are mutually exclusive. Global options may be placed before or after the
command:

```bash
fs-tool --json inspect tree ~/Documents
fs-tool inspect tree ~/Documents --json
```

`--help` and `--version` are exceptions: they always print plain text.

## Compact and verbose entry output

Commands that return filesystem entries default to a compact per-command profile. `--verbose`
restores the complete existing entry fields. The option applies to both JSON and plain output and
may be placed before or after the command:

```bash
fs-tool --verbose inspect inventory ~/Documents
fs-tool inspect inventory ~/Documents --verbose
fs-tool --plain --verbose find ~/Documents
```

| Mode | Behavior |
|---|---|
| Default | Compact profile of the affected command. |
| `--verbose` | Complete existing entry fields. |
| `--json --verbose` | Complete JSON entry fields. |
| `--plain --verbose` | Compact line plus `key: value` detail lines. |

Verbosity changes presentation only. It never changes the number of returned entries, the analysis
result, completeness, warnings, errors or exit codes, and it never triggers hashing or additional
metadata extraction.

| Command | Compact entry fields |
|---|---|
| `inspect tree` | `rel_path`, `type` |
| `inspect inventory` | `rel_path`, `type`, `extension`, `size`, `modified`, plus `sha256` with `--hash` |
| `find` | `rel_path`, `type`, `size` |

`inspect info` returns a single entry with its complete metadata and `inspect analyze` returns an
analysis report, so neither command has a compact profile; their output is unchanged by
`--verbose`.

## JSON envelope

Every command except `--help` and `--version` returns one JSON object on stdout:

```json
{
  "schema_version": 1,
  "success": true,
  "command": "inspect.tree",
  "result": {},
  "errors": [],
  "warnings": [],
  "complete": true
}
```

| Field | Type | Meaning |
|---|---|---|
| `schema_version` | integer | Envelope schema version. Currently `1`. |
| `success` | boolean | `true` when the command completed without an error. |
| `command` | string | Command identifier, for example `inspect.tree` or `write.copy`. |
| `result` | object or null | Command-specific payload. |
| `errors` | array | Structured errors. Empty on success. |
| `warnings` | array | Structured warnings. |
| `complete` | boolean | Whether the requested analysis covered the whole input. |

Key order is stable. Output is a single line of JSON by default. Timestamps are ISO-8601 strings
in UTC; sizes are bytes; hashes are lowercase hexadecimal SHA-256 values.

### Errors

Each error entry has this shape:

```json
{
  "code": "ROOT_NOT_ALLOWED",
  "message": "Path not allowed: /mnt/nas",
  "path": "/mnt/nas",
  "details": {"roots": ["/home/user", "/home/user/projects"]}
}
```

| Field | Meaning |
|---|---|
| `code` | Stable machine-readable error code. |
| `message` | Human-readable description. |
| `path` | Affected path, when applicable. |
| `details` | Additional structured context. |

Warnings use the same `code`, `message`, `path` and `details` fields.

`inspect inventory --max-hash-bytes` emits a `HASH_SKIPPED` warning for each file above the limit.
The file keeps `sha256: null`; the scan itself remains complete.

Error codes map to process exit codes. For example, `ROOT_NOT_ALLOWED` exits with code 3,
`TARGET_EXISTS` with code 4, and `INCOMPLETE_SCAN` with code 5. See
[Exit codes](cli.md#exit-codes).

### Incomplete results

An incomplete scan still returns partial results, but sets `success` to `false` and `complete` to
`false`, and exits with code 5. `errors` describes what could not be read. Consumers should check
`complete` before treating a result as authoritative.

## Result payloads

### Filesystem entry

`inspect tree`, `inspect info`, `find` and the inventory commands use this complete entry shape:

| Field | Type | Meaning |
|---|---|---|
| `path` | string | Absolute path. Removed from `inspect inventory` entries. |
| `name` | string | Entry name. |
| `rel_path` | string | Path relative to the declared root. |
| `type` | string | `file`, `directory`, `symlink` or `other`. |
| `extension` | string or null | Lowercase suffix including the dot. |
| `size` | integer | Size in bytes (`lstat` size). |
| `modified` | string | Modification timestamp. |
| `created` | string or null | Creation timestamp where the platform provides one. |
| `accessed` | string | Last-access timestamp. |
| `changed` | string | Metadata-change timestamp. |
| `mode` | string | POSIX file mode, for example `-rw-r--r--`. |
| `owner` | string or null | Owner name on POSIX systems. |
| `mime_type` | string or null | Guessed MIME type. |
| `is_symlink` | boolean | Whether the entry is a symbolic link. |
| `target` | string or null | Symlink target. |
| `sha256` | string or null | Hash, when requested. |
| `dev_ino` | string | Device and inode identity, for example `2049:12345`. |
| `metadata` | object or null | Extracted format metadata. Populated by `inspect info`. |

`inspect tree`, `inspect inventory` and `find` return only their compact profile by default;
`--verbose` returns every field above. `inspect inventory` never includes the absolute `path`.

```json
{
  "schema_version": 1,
  "success": true,
  "command": "inspect.tree",
  "result": {
    "root": "/home/user/documents",
    "entries": [
      {"rel_path": "reports", "type": "directory"},
      {"rel_path": "reports/q4.pdf", "type": "file"}
    ],
    "count": 2
  },
  "errors": [],
  "warnings": [],
  "complete": true
}
```

With `--verbose`, each entry expands to the complete representation:

```json
{
  "path": "/home/user/documents/reports/q4.pdf",
  "name": "q4.pdf",
  "rel_path": "reports/q4.pdf",
  "type": "file",
  "extension": ".pdf",
  "size": 245760,
  "modified": "2026-11-11T18:30:00+00:00",
  "created": null,
  "accessed": "2026-11-11T18:31:02+00:00",
  "changed": "2026-11-11T18:30:00+00:00",
  "mode": "-rw-r--r--",
  "owner": "user",
  "mime_type": "application/pdf",
  "is_symlink": false,
  "target": null,
  "sha256": null,
  "dev_ino": "2049:12345",
  "metadata": null
}
```

`inspect info` additionally adds `metadata_result` next to the entry fields. It is a
[capability result](#capability-results) or `null` when the format has no metadata capability.

### Capability results

`inspect info` (`metadata_result`) and `inspect analyze` (`analyses[]`) use the same result shape:

| Field | Type | Meaning |
|---|---|---|
| `capability` | string | Stable capability identifier, for example `pdf_metadata` or `python_ast`. |
| `status` | string | `available`, `unavailable` or `failed`. |
| `message` | string | Concise human-readable description. |
| `help` | string or null | Suggested next step when a capability is unavailable. |
| `error_code` | string or null | Stable machine-readable code for a failed capability. |
| `data` | object or null | Capability-specific structured payload; never complete file content. |

| Status | Meaning |
|---|---|
| `available` | The capability ran successfully. |
| `unavailable` | The format is supported, but a prerequisite such as `pypdf` is missing. |
| `failed` | The capability was attempted but could not complete. |

A missing or failed capability never prevents other applicable analyses from running. A format with
no applicable capability is distinct from an unavailable one: `inspect info` returns
`metadata: null` with `metadata_result: null`, and `inspect analyze` returns `supported: false`
with `analyses: []`.

### Command results

| Command | `result` fields |
|---|---|
| `inspect tree` | `root`, `entries`, `count` |
| `inspect info` | A single filesystem entry, plus `metadata_result`, metadata values and `sha256` when requested |
| `inspect analyze` | `path`, `name`, `extension`, `size`, `sha256`, `supported`, `analyses` |
| `inspect inventory` | `root`, `entries`, `count`, `generated_at`, `complete`, `skipped`, `truncated`, optional `filtered`, optional `tree_hash` |
| `inspect read` | `path`, `name`, `size`, `content`, `truncated`, `encoding`, `format`, `representation`; PDFs add `page_count` and `pages` |
| `find` | `root`, `entries`, `count`, `complete` |
| `duplicates` | `root`, `duplicate_groups`, `duplicate_group_count`, `duplicate_file_count`, `complete` |
| `compare` | `source`, `destination`, `identical`, `missing`, `changed`, `unexpected`, `type_conflicts`, `unsupported`, `complete` |
| `verify inventory` | `inventory_file`, `target`, `missing`, `unexpected`, `changed`, `size_mismatch`, `hash_mismatch`, `complete` |
| `verify tree` | `source`, `destination`, `missing`, `unexpected`, `changed`, `size_mismatch`, `hash_mismatch`, `complete` |
| `write mkdir` | `operation`, `source`, `destination`, `dry_run`, `executed`, `affected`, `skipped`, `created`, `sha256`, `verified`, `complete` |
| `write copy` | Operation report with `affected`, `skipped`, `sha256` and `verified` |
| `write move` | Operation report with `affected` and `verified` |

`duplicate_groups` contains objects with `sha256`, `size`, `count` and `files`.

## Plain-text output

Plain output is intended for humans. It is not a stable machine interface.

| Command | Plain representation |
|---|---|
| `inspect tree` | Indented tree; `--verbose` adds a detail block per entry. |
| `inspect info` | `key: value` lines, including extracted metadata and any metadata status. |
| `inspect analyze` | One block per analysis with capability, status and structured result. |
| `inspect inventory` | One line per entry with type, size, modification time, extension and optional hash; `--verbose` adds detail lines. |
| `inspect read` | File content (UTF-8 text or extracted PDF text). A truncation warning goes to stderr. |
| `find` | One line per match with type and size; `--verbose` adds detail lines. |
| `duplicates` | Duplicate groups with hash, size, count and file paths. |
| `compare` | Categories with entries, followed by `complete`. |
| `verify` | Discrepancy categories, followed by `complete`. |
| `write` | Operation status, destination and affected paths. |

Diagnostics and warnings are written to stderr. Result content is written to stdout, so plain
output can be redirected without mixing in error messages.

Compact plain output keeps the existing line format. For `inspect inventory`, the compact line uses
the same information as the JSON compact profile: `rel_path`, `type`, `size`, `modified`, `extension`
and optional `sha256`. With `--verbose`, each entry line is followed by indented `key: value` detail
lines for the remaining fields:

```text
find: /home/user/documents
  reports [directory] size=4096
    name: reports
    modified: 2026-11-11T18:30:00+00:00
    accessed: 2026-11-11T18:31:02+00:00
    changed: 2026-11-11T18:30:00+00:00
    mode: drwxr-xr-x
    owner: user
    dev_ino: 2049:12345
  reports/q4.pdf [file] size=245760
    name: q4.pdf
    extension: .pdf
    modified: 2026-11-11T18:30:00+00:00
    accessed: 2026-11-11T18:31:02+00:00
    changed: 2026-11-11T18:30:00+00:00
    mode: -rw-r--r--
    owner: user
    mime_type: application/pdf
    dev_ino: 2049:12346
count: 2
```

For `inspect inventory`, `--plain --verbose` is complete for the entry representation: fields that
are `null` or `false` are shown explicitly, for example `sha256: null`, `is_symlink: false`,
`target: null` and `metadata: null`. `inspect tree` and `find` keep their existing human-oriented
detail behavior and omit empty values.

## Determinism

- Entries are sorted by name during traversal; result order is reproducible.
- Inventory entries use `rel_path` and omit absolute paths, so inventories are portable across
  machines.
- `tree_hash` (algorithm version 2) is computed from a canonical JSON representation of the sorted
  entries. It hashes only `rel_path`, `type`, `extension`, `size` and `sha256`; directory and
  symlink sizes are normalized to `null` because their `st_size` is filesystem- or
  target-path-dependent. It excludes absolute paths, inode identities, timestamps, permissions,
  ownership, MIME type and symlink targets, and does not depend on the selected output profile.
- Top-level envelope keys have a fixed order; result keys follow the order defined by each command.

The schema version is part of the contract. Consumers should reject or handle envelopes whose
`schema_version` they do not support; `verify inventory` currently requires version `1`.
