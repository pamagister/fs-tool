# Safety model

fs-tool is read-only by default. Only the `write` command group modifies the filesystem, and every
write operation requires explicit authorization.

## Allowed roots

Every path passed to fs-tool must lie inside an allowed root. By default these are:

- the current user's home directory, and
- the current working directory, unless it is the filesystem root `/`.

Other locations require `--allow-root`:

```bash
fs-tool --allow-root /mnt/nas inspect tree /mnt/nas
```

`--allow-root` is repeatable. When supplied, the values replace the default home and CWD roots
instead of extending them. A configuration file can restrict the effective roots further, but it
cannot add new ones. See [Configuration](configuration.md).

Validation checks both the normalized path and the symlink-resolved path. A symlink cannot be used
to escape an allowed root. Violations fail with exit code 3.

## Read-only guarantees

Inspection and analysis commands do not modify the filesystem:

- Traversal records symlinks but never follows them. There is no `--follow-symlinks` option, and
  no command resolves, opens or descends into a symbolic link.
- Special files (sockets, devices, FIFOs) are reported as type `other` and are never opened.
- `inspect read` rejects symlinks and non-regular files, rejects non-UTF-8 binary content, and
  truncates at `--max-bytes` (default 64 KiB). PDF text extraction requires the optional
  `metadata` extra, rejects PDF source files larger than 100 MiB, and never returns binary PDF
  bytes.
- Hashing opens files read-only and uses `O_NOFOLLOW` where the platform supports it.
- `inspect info` extracts format metadata automatically and never executes file content. PDF
  metadata requires the optional `metadata` extra; files larger than 100 MiB are not inspected for
  metadata.
- `inspect analyze` rejects symlinks and non-regular files and returns structure only, never
  complete file content. Markdown and text analysis are limited to 5 MiB per file, and Python
  analysis is limited to 1 MiB. Python files are parsed with `ast` and never imported or executed.
  PDF page analysis requires the optional `metadata` extra.
- Unreadable entries are reported as errors; the rest of the scan continues.

A scan that could not read every entry is marked incomplete and exits with code 5. Partial results
are still returned but must not be treated as a complete picture.

## Write authorization

Every `write` command requires exactly one of:

- `--dry-run` — validate the operation and report what would happen without touching the
  filesystem.
- `--yes` — authorize execution.

Supplying neither, or both, is an invalid-argument error (exit code 2).

Additional safeguards:

- Source and destination are validated against the allowed roots.
- Existing destinations are never overwritten.
- Data is never deleted.
- All conflicts are checked before the first write; the operation either applies as a whole or
  aborts.
- Symlinks are never followed, and no option can enable following them.
- The command verifies the result and returns a structured operation report.

## Operation-specific rules

### `write mkdir`

- Creates missing parent directories only with `--parents`.
- An existing directory is idempotent and reports `created: false`.
- An existing non-directory entry is a conflict (exit code 4).

### `write copy`

- The destination must not exist and its parent must exist.
- Copying a directory into itself or a descendant is rejected.
- Regular files are written to a temporary file, verified by SHA-256, and published with an
  exclusive hard link so an existing destination is never overwritten.
- File mode and timestamps are preserved where supported.
- `--symlinks error` (default) refuses a tree containing symlinks. `--symlinks copy` copies the
  link itself without following it. `--symlinks skip` omits links and lists them under `skipped`.

### `write move`

- The destination must not exist and its parent must exist.
- Moving a filesystem root is rejected.
- Moving a directory into itself or a descendant is rejected.
- Cross-device moves are rejected; use `write copy` followed by manual verification instead.
- A move that changes the filename requires `--allow-rename` in addition to `--yes`.
- Renames use a no-replace primitive where available, so a destination appearing at the last moment
  is not overwritten.
- The command verifies that the entry exists at the destination and no longer exists at the
  source.

## Failure behavior

| Situation | Exit code |
|---|---|
| Successful operation | 0 |
| Verification found discrepancies or an operation failed | 1 |
| Invalid arguments, bad configuration, unsupported request | 2 |
| Path outside an allowed root or permission denied | 3 |
| Destination already exists or type conflict | 4 |
| Incomplete scan or verification | 5 |

Errors are reported as a structured JSON envelope when the output format is JSON, and as a
diagnostic on stderr for plain output. See [Output formats](output.md) and
[Exit codes](cli.md#exit-codes).

## Limits

- Allowed-root validation is not a sandbox; it constrains paths passed to fs-tool, not other
  processes.
- Filesystem races are reduced by atomic creation and no-replace renames, but fs-tool does not
  lock the filesystem. Another process can still change entries between validation and execution.
- Operating-system permissions still apply. fs-tool reports access errors rather than bypassing
  them.
