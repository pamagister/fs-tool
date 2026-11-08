# fs-tool – Initial Release Plan

This is the original plan when the project was initially set up and first implemented. Things may have changed since then; refer to the code, the documentation in `docs/` and `fs-tool --help`.

## 1. Project Objective

Develop a lightweight, secure and agent-friendly command-line tool for inspecting, analyzing, comparing and organizing local filesystems.

The application supports both interactive human usage and automated execution by AI agents. The initial release focuses exclusively on the CLI and its underlying Python library.

## 2. Primary Use Cases

- Understanding existing directory structures.
- Creating structured filesystem inventories.
- Collecting file metadata and identifying file types.
- Analyzing selected file formats and source code.
- Finding duplicate files.
- Comparing directory structures and file contents.
- Copying, moving and renaming files and directories.
- Verifying the integrity of filesystem operations.

## 3. Architectural Principles

Three logical layers: CLI Layer → Filesystem Core (Analysis, Operations, Safety) → Local Filesystem. The filesystem core must be usable independently of the CLI.

- Keep the architecture modular but lightweight; avoid unnecessary abstractions and complex frameworks.
- Prefer standard-library functionality.
- Provide deterministic and reproducible results.
- Separate filesystem traversal from content analysis; separate analysis from filesystem modifications.
- Use consistent data structures across commands.
- Never execute analyzed files or import them dynamically.
- Never silently overwrite or delete user data; require explicit authorization for potentially risky operations.
- JSON is the primary interface; Plain is a human-oriented alternative.

## 4. Features

- Recursive directory traversal with configurable depth, entry limits, directory-only mode and configurable ignore rules.
- File metadata: path, size, timestamps, permissions, MIME type, symlink targets, SHA-256 hashes.
- Optional document metadata extraction (PDF, ODF/OOXML) — read-only, no embedded content execution.
- Bounded UTF-8 text reading with truncation reporting.
- Search by name, extension, type, size and modification date.
- Duplicate detection via size pre-filtering and SHA-256 grouping; files are never deleted automatically.
- Directory comparison (identical, missing, changed, unexpected, type conflicts).
- Verification against stored inventories or source trees.
- Safe write operations (mkdir, copy, move) with explicit authorization, no-overwrite protection and preflight validation.
- Optional Python source analysis via `ast` — files are never imported or executed.

## 5. Safety

Safety is a core architectural requirement:

- Access is restricted to allowed roots (Home + CWD by default; explicit roots replace them; configuration may restrict roots but never expand them).
- Symlinks are never followed recursively; symlink-based path escapes are detected; broken symlinks are handled explicitly.
- No implicit writes, no silent overwriting, no unrestricted deletion; explicit authorization is required for write operations.
- Incomplete scans never claim full-tree integrity; unsupported entries (FIFOs, sockets, devices) are reported as unsupported and never opened.

## Main Intention

Reliable information first, controlled operations second, verifiable results always.
