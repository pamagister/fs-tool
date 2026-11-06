# fs-tool – Implementation Tasklist

Status:
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed
- `[~]` Deferred

Current state: Phase 2 (Inspection Commands) is complete. Phase 3 (Search and Analysis) is in progress.

## Decisions (see plan.md section 2)

- D1: Python >=3.11; CI tests 3.11 and 3.13.
- D2: Complete legacy template cleanup.
- D3: `verify inventory <file> <target>` / `verify tree <src> <dst>`.
- D4: TOML config via `tomllib`; `--config`; `$XDG_CONFIG_HOME/fs-tool/config.toml`; CLI > Config > Defaults; config may only restrict roots.
- D5: Document metadata in initial scope: PDF via optional `[metadata]` extra (`pypdf`); ODF/OOXML via stdlib.
- D6: Allowed Roots default: Home + CWD; explicit `--allow-root` values replace these defaults.
- D7: Output default `auto` (TTY → Plain, pipe → JSON); `--format auto|json|plain`.
- D8: One GitHub Issue per phase (reuse a suitable open issue or create one);
  push after 3–6 task commits or at phase end, then monitor CI.

## Workflow

See `AGENTS_WORKFLOW_AUTOPILOT.md`. Each task follows: inspect → implement →
add/extend tests → `make check` → fix → update this tasklist → commit. Push
after 3–6 commits or at phase end, then monitor CI.

---

## Phase 0 – Project Foundation and Baseline

Issue: #2 "Cleanup legacy stuff" (existing GitHub issue; repurpose for Phase 0).

- [x] P0-T01 Clean up legacy template artefacts
  - Removed GUI, config-cli-gui, legacy config.yaml, PyInstaller/GUI builds, GPX examples, init.sh, template scripts, .idea run configs, HISTORY.md.
  - Acceptance: no GUI/config-cli-gui/PyInstaller artefacts remain; make test and make lint run without missing-module errors.
- [x] P0-T02 Repair `pyproject.toml`
  - Typer dependency, Python >=3.11, optional `[metadata]` extra (`pypdf`), entry point `fs_tool.cli:main`, package discovery `src/`, Ruff/Mypy/Coverage/Pytest config.
  - Acceptance: `uv lock` succeeds; `fs-tool --version` importable after install.
- [x] P0-T03 Repair `Makefile`
  - Targets: `install`, `fmt`, `lint`, `test`, `check`, `syncdocs`, `docs`, `build`, `clean`; no side effects in `fmt`.
  - Acceptance: `make lint`, `make fmt` and `make check` targets exist and execute.
- [x] P0-T04 Repair CI workflows
  - `uv sync --all-groups` plus metadata extra; matrix 3.11/3.13; Linux/macOS/Windows; fix release workflow (remove missing script references).
  - Acceptance: CI YAML is syntactically valid; no references to removed files.
- [x] P0-T05 Define internal data models
  - `core/models.py`: `FilesystemEntry`, `EntryType` per plan.md section 8.
  - Acceptance: data model matches plan.md section 8; mypy-clean.
- [x] P0-T06 Define common JSON response structure
  - `output/json.py`: `schema_version`, `success`, `command`, `result`, `errors`, `warnings`, `complete` per plan.md section 4.3.
  - Acceptance: envelope matches plan.md section 4.3; stable round-trip JSON.
- [x] P0-T07 Implement centralized error handling
  - `core/errors.py`: stable error codes mapped to exit codes 1-5 via `EXIT_CODES`.
  - Acceptance: error codes map to exit codes 1-5; no broad exception swallowing.
- [x] P0-T08 Define process exit codes
  - Documented in `cli.py`: 0/1/2/3/4/5.
  - Acceptance: CLI returns correct exit codes for success/failure/invalid usage.
- [x] P0-T09 Configure pytest and Ruff
  - `pytest.ini`, Ruff config in `pyproject.toml`, coverage config in `pyproject.toml`.
  - Acceptance: `make lint` and `make test` execute on smoke suite (config introduced with P0-T02).
- [x] P0-T10 Add initial README
  - Synced from `docs/index.md` via `make syncdocs`; GUI/executable references removed.
  - Acceptance: `make syncdocs` produces a valid README.
- [x] P0-T11 Add smoke tests
  - `tests/conftest.py`, `tests/test_cli.py`, `tests/test_output.py`: `--version`, `--help`, JSON envelope, exit codes.
  - Acceptance: `make test` green with 27 smoke tests passing.

**Milestone:** A working CLI with help output, version information and consistent JSON responses; `make check` green.

---

## Phase 1 – Filesystem Core and Safety

Issue: #3 "Phase 1: Filesystem Core and Safety".

- [x] P1-T01 Implement path normalization
- [x] P1-T02 Implement allowed-root restrictions (Home + CWD default)
- [x] P1-T03 Implement path traversal protection
- [x] P1-T04 Implement symlink detection and handling
- [x] P1-T05 Implement recursive directory traversal
- [x] P1-T06 Implement deterministic sorting
- [x] P1-T07 Implement file and directory metadata extraction
- [x] P1-T08 Implement MIME type detection
- [x] P1-T09 Implement SHA-256 hashing
- [x] P1-T10 Implement scan completeness and error reporting
- [x] P1-T11 Add tests for inaccessible paths
- [x] P1-T12 Add tests for symlinks and path escapes
- [x] P1-T13 Add tests for allowed-root restrictions
- [x] P1-T14 Implement TOML configuration loader (`--config`, default location, precedence)

**Milestone:** A reusable and tested filesystem core.

---

## Phase 2 – Inspection Commands

Issue: #4 "Phase 2: Inspection Commands".

**Milestone reached:** Complete read-only filesystem inspection.
`make check` green: 130 tests passing, ruff/format/mypy clean.

### `inspect tree`

- [x] P2-T01 Implement recursive tree generation
- [x] P2-T02 Implement configurable maximum depth
- [x] P2-T03 Implement entry limits
- [x] P2-T04 Implement ignored directories and patterns
- [x] P2-T05 Implement directory-only mode
- [x] P2-T06 Implement plain tree rendering
- [x] P2-T07 Include structured per-entry metadata in JSON output
- [~] P2-T08 Implement optional Python code structure (deferred to Phase 6 per roadmap)

### `inspect info`

- [x] P2-T09 Implement single-path metadata inspection
- [x] P2-T10 Implement timestamps and permissions
- [x] P2-T11 Implement owner information
- [x] P2-T12 Implement MIME type information
- [x] P2-T13 Implement symlink information
- [x] P2-T14 Implement `--metadata` document extraction (PDF/ODF/OOXML)

### `inspect inventory`

- [x] P2-T15 Implement structured directory inventories
- [x] P2-T16 Implement optional SHA-256 calculation
- [x] P2-T17 Implement deterministic tree hashing
- [x] P2-T18 Implement inventory completeness reporting
- [x] P2-T19 Implement JSON serialization
- [x] P2-T20 Implement `root` + `rel_path` portability

### `inspect read`

- [x] P2-T21 Implement bounded UTF-8 reading
- [x] P2-T22 Implement configurable maximum size
- [x] P2-T23 Implement truncation reporting
- [x] P2-T24 Prevent accidental binary and symlink reading

**Milestone:** Complete read-only filesystem inspection.

---

## Phase 3 – Search and Analysis

Issue: #5 "Phase 3: Search and Analysis".

### `find`

- [x] P3-T01 Implement filename pattern matching
- [x] P3-T02 Implement extension filtering
- [x] P3-T03 Implement file type filtering
- [x] P3-T04 Implement size filtering
- [x] P3-T05 Implement modification date filtering

### `duplicates`

- [x] P3-T06 Implement file-size-based candidate filtering
- [x] P3-T07 Implement SHA-256 comparison
- [x] P3-T08 Implement duplicate grouping
- [x] P3-T09 Implement duplicate reports
- [x] P3-T10 Handle incomplete scans correctly

### `compare`

- [x] P3-T11 Implement source/destination traversal
- [x] P3-T12 Compare relative paths
- [x] P3-T13 Detect identical files
- [x] P3-T14 Detect missing files
- [x] P3-T15 Detect changed files
- [x] P3-T16 Detect unexpected files
- [x] P3-T17 Detect type conflicts
- [x] P3-T18 Report unsupported entries

### `verify`

- [ ] P3-T19 Implement inventory-based verification
- [ ] P3-T20 Implement source/destination verification
- [ ] P3-T21 Detect missing and unexpected entries
- [ ] P3-T22 Verify file sizes and hashes
- [ ] P3-T23 Report incomplete verification
- [ ] P3-T24 Implement `schema_version` check for inventory files

**Milestone:** Reliable filesystem analysis and integrity verification.

---

## Phase 4 – Filesystem Operations

### General

- [ ] P4-T01 Implement common write-operation interface
- [ ] P4-T02 Implement mandatory Dry-Run or execution authorization
- [ ] P4-T03 Implement structured operation reports
- [ ] P4-T04 Implement no-overwrite protection
- [ ] P4-T05 Implement preflight validation
- [ ] P4-T06 Validate source and destination paths

### `write mkdir`

- [ ] P4-T07 Implement directory creation
- [ ] P4-T08 Support missing parent directories
- [ ] P4-T09 Implement Dry-Run
- [ ] P4-T10 Add tests

### `write copy`

- [ ] P4-T11 Implement regular file copying
- [ ] P4-T12 Implement safe destination creation
- [ ] P4-T13 Preserve metadata where appropriate
- [ ] P4-T14 Verify copied contents
- [ ] P4-T15 Implement recursive directory copying
- [ ] P4-T16 Define explicit symlink handling
- [ ] P4-T17 Implement Dry-Run
- [ ] P4-T18 Add tests for conflicts and partial failures

### `write move`

- [ ] P4-T19 Implement file moving
- [ ] P4-T20 Implement directory moving
- [ ] P4-T21 Implement symlink moving
- [ ] P4-T22 Implement filename-change detection
- [ ] P4-T23 Require `--allow-rename` for renaming
- [ ] P4-T24 Implement Dry-Run
- [ ] P4-T25 Implement no-overwrite protection
- [ ] P4-T26 Add tests for conflicts and safety restrictions

**Milestone:** Safe and verifiable filesystem modifications.

---

## Phase 5 – Output and Presentation

- [ ] P5-T01 Finalize JSON output schemas
- [ ] P5-T02 Implement consistent `--plain` handling
- [ ] P5-T03 Implement human-readable metadata summaries
- [ ] P5-T04 Implement tree visualization
- [ ] P5-T05 Implement duplicate reports
- [ ] P5-T06 Implement comparison reports
- [ ] P5-T07 Implement operation previews
- [ ] P5-T08 Test output consistency across commands

**Milestone:** Consistent machine-readable and human-readable interfaces.

---

## Phase 6 – Additional Metadata and Analysis

- [ ] P6-T01 Integrate Python AST analysis
- [ ] P6-T02 Extract functions and classes
- [ ] P6-T03 Extract method signatures and attributes
- [ ] P6-T04 Support optional docstrings
- [ ] P6-T05 Implement PDF metadata extraction (`pypdf` extra)
- [ ] P6-T06 Implement ODF metadata extraction
- [ ] P6-T07 Implement OOXML metadata extraction
- [ ] P6-T08 Define optional dependency handling

**Milestone:** Extended file understanding without executing file contents.

---

## Phase 7 – Documentation and Release

- [ ] P7-T01 Complete README
- [ ] P7-T02 Document installation using uv
- [ ] P7-T03 Document all CLI commands
- [ ] P7-T04 Document global options
- [ ] P7-T05 Document JSON response schemas
- [ ] P7-T06 Document exit codes
- [ ] P7-T07 Document safety restrictions
- [ ] P7-T08 Add practical examples
- [ ] P7-T09 Test installation on Kubuntu
- [ ] P7-T10 Run complete test suite
- [ ] P7-T11 Run Ruff checks
- [ ] P7-T12 Prepare initial release

**Milestone:** First stable release.

---

## Work Log

| Date | Phase | Task | Summary |
|------|-------|------|---------|
| 2026-11-06 | 1 | P1-T07 | core/traversal.py: entries carry accessed/changed/created timestamps, mode, owner (POSIX), dev:inode; tests assert metadata presence. |
| 2026-11-06 | 1 | P1-T06 | core/traversal.py: children are deterministically sorted by name (sort_by parameter); tests prove stable ordering. |
| 2026-11-06 | 1 | P1-T05 | core/traversal.py: recursive traversal with depth/entry limits, ignore dirs and patterns, dirs-only, symlink recording without following, error collection, completeness flag; tests in tests/test_traversal.py. |
| 2026-11-06 | 1 | P1-T04 | symlink_components() detects symlink components via lstat without following links; traversal never follows symlinks by default. |
| 2026-11-06 | 1 | P1-T03 | safety/validation.py: validate_path now also rejects symlink-resolved escapes (traversal protection); symlink_components() detects symlink components via lstat without following links. |
| 2026-11-06 | 1 | P1-T02 | safety/validation.py: allowed-root validation; default roots home + CWD (CWD of / not implicit); PathNotAllowedError maps to exit code 3; tests in tests/test_safety.py. |
| 2026-11-06 | 1 | P1-T01 | core/filesystem.py: normalize_path (lexical, ~ expansion, absolute, collapses ./..) and resolve_path (symlink-aware); tests in tests/test_traversal.py. |
| 2026-11-06 | 0 | P0-T01 | Removed legacy template artefacts (GUI, config-cli-gui, config.yaml, PyInstaller builds, GPX examples, init.sh, template scripts, .idea run configs, HISTORY.md). |
| 2026-11-06 | 0 | P0-T02 | Repaired pyproject.toml: typer, Python >=3.11, [metadata] extra (pypdf), fs_tool.cli:main entry point, src/ package discovery, ruff/mypy/coverage/pytest config; click pinned <8.2 for typer 0.12 help rendering. uv lock succeeds. |
| 2026-11-06 | 0 | P0-T03 | Repaired Makefile: install, lock, fmt, lint, test, check, syncdocs, docs, build, clean targets; fmt has no side effects beyond formatting. Pre-commit hook now runs make check. |
| 2026-11-06 | 0 | P0-T04 | Repaired CI: main.yml matrix 3.11/3.13 on linux/macOS/windows with uv sync + metadata extra; release.yml changelog from git log (removed missing release_message.sh); PyInstaller build workflows removed. |
| 2026-11-06 | 0 | P0-T05 | core/models.py: FilesystemEntry and EntryType per plan.md section 8. |
| 2026-11-06 | 0 | P0-T06 | output/json.py: envelope with schema_version/success/command/result/errors/warnings/complete; stable key order and round-trip JSON. |
| 2026-11-06 | 0 | P0-T07 | core/errors.py: stable error codes mapped to exit codes 1-5 via EXIT_CODES; FsToolError base class. |
| 2026-11-06 | 0 | P0-T08 | cli.py: exit codes 0/1/2/3/4/5 documented; CLI returns 0 for --version/--help, 2 for invalid usage. |
| 2026-11-06 | 0 | P0-T09 | pytest.ini and pyproject.toml [tool.pytest]/[tool.ruff]/[tool.coverage] configuration (introduced with P0-T02). |
| 2026-11-06 | 0 | P0-T10 | docs/index.md adjusted (Python >=3.11); README.md regenerated via make syncdocs from docs/index.md. |
| 2026-11-06 | 0 | P0-T11 | Smoke tests: tests/conftest.py, tests/test_cli.py (27 tests), tests/test_output.py; make test green. |
| 2026-11-06 | 1 | P1-T08 | core/traversal.py: MIME type detection via mimetypes.guess_type. |
| 2026-11-06 | 1 | P1-T09 | core/hashing.py: sha256_of_file with O_NOFOLLOW where available; symlinks and special files yield None; tests in tests/test_hashing.py. |
| 2026-11-06 | 1 | P1-T10 | core/traversal.py completeness flag; test max_entries truncation sets complete=False. |
| 2026-11-06 | 1 | P1-T11 | tests/test_traversal.py covers the inaccessible-root error; permission-based cases are not deterministically testable as root. |
| 2026-11-06 | 1 | P1-T12 | tests/test_traversal.py and tests/test_safety.py cover symlinks and path escapes. |
| 2026-11-06 | 1 | P1-T13 | tests/test_safety.py covers allowed-root restrictions (default roots, explicit allow-root, rejection outside roots). |
| 2026-11-06 | 1 | P1-T14 | core/config.py: TOML config loader; XDG_CONFIG_HOME/fs-tool/config.toml; --config override; CLI > Config > Defaults; roots intersected with CLI roots so config may only restrict; tests in tests/test_config.py. |
| 2026-11-06 | 2 | P2-T01 | cli.py: inspect tree command with path validation, traversal, JSON envelope, completeness flag, exit codes. |
| 2026-11-06 | 2 | P2-T02 | cli.py: --max-depth option on inspect tree. |
| 2026-11-06 | 2 | P2-T03 | cli.py: --max-entries option on inspect tree (truncation sets complete=false). |
| 2026-11-06 | 2 | P2-T04 | cli.py: --ignore-dir and --ignore-pattern options; default ignore set (.git, __pycache__, ...). |
| 2026-11-06 | 2 | P2-T05 | cli.py: --dirs-only option on inspect tree. |
| 2026-11-06 | 2 | P2-T06 | output/plain.py: plain tree rendering; cli.py: --plain global option support (before the command). |
| 2026-11-06 | 2 | P2-T07 | cli.py: inspect tree JSON result carries structured per-entry metadata (timestamps, mode, owner, MIME, ...); human-readable summaries remain in P5-T03. |
| 2026-11-06 | 2 | P2-T08 | Deferred to Phase 6 (Python AST analysis per roadmap). |
| 2026-11-06 | 2 | Review follow-up | Traversal errors now make scans incomplete and unsuccessful; incomplete plain output is diagnosed; Click usage errors are shown; root-option and tree-metadata contracts aligned with the specification. Regression tests cover missing/file roots, nested read failures, option diagnostics, and explicit root replacement. |
| 2026-11-06 | 2 | P2-T09..P2-T13 | cli.py: inspect info command with single-path metadata (timestamps, permissions, owner, MIME, symlink); traversal._build_entry refactored to public build_entry; output/plain.py: render_info(); tests in tests/test_info.py; 9 new tests, 103 total passing; make check green. |
| 2026-11-06 | 2 | P2-T14 | core/metadata.py: document metadata extraction (PDF via optional pypdf, ODF/OOXML via stdlib zipfile/ElementTree); size limit 100 MiB; read-only, no code execution; --metadata flag on inspect info; tests using res/example_filesystem_unstructured fixtures; 4 new tests, 107 total passing; make check green. |
| 2026-11-06 | 2 | P2-T15..P2-T20 | cli.py: inspect inventory command with --hash, --tree-hash, --max-depth, --max-entries, --ignore-dir, --ignore-pattern, --dirs-only; _compute_tree_hash() with canonical JSON (excludes path/dev_ino/generated_at); output/plain.py: render_inventory(); tests in tests/test_inventory.py; 13 new tests, 120 total passing; make check green. |
| 2026-11-06 | 3 | P3-T06..P3-T10 | core/analysis/duplicates.py: DuplicateGroup/DuplicateResult, find_duplicates() with size-based candidate filtering, SHA-256 hashing, hardlink dedup, empty file handling; cli.py: duplicates files command with --min-size, --include-empty options; output/plain.py: render_duplicates(); tests in tests/test_duplicates.py; 7 new tests, 155 total passing; make check green. |\n| 2026-11-06 | 3 | P3-T11..P3-T18 | core/analysis/comparison.py: ComparisonResult, compare_trees() with identical/missing/changed/unexpected/type_conflicts/unsupported categorization; cli.py: compare trees command; output/plain.py: render_compare(); tests in tests/test_compare.py; 5 new tests, 160 total passing; make check green. |

---

## Stop Conditions

Stop and ask before proceeding when any of the following occurs:

- Destructive or irreversible decision (e.g. adding `delete` functionality).
- Unclear public interface or CLI contract.
- Missing credentials needed for CI/PyPI release.
- CI fails repeatedly and the error cannot be reproduced locally.
- Changes would be required outside this repository.
