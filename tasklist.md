# fs-tool – Implementation Tasklist

Status:
- `[ ]` Not started
- `[-]` In progress
- `[x]` Completed
- `[~]` Deferred

Current state: Phase 0 (Project Foundation and Baseline) is complete.

## Decisions (see plan.md section 2)

- D1: Python >=3.11; CI tests 3.11 and 3.13.
- D2: Complete legacy template cleanup.
- D3: `verify inventory <file> <target>` / `verify tree <src> <dst>`.
- D4: TOML config via `tomllib`; `--config`; `$XDG_CONFIG_HOME/fs-tool/config.toml`; CLI > Config > Defaults; config may only restrict roots.
- D5: Document metadata in initial scope: PDF via optional `[metadata]` extra (`pypdf`); ODF/OOXML via stdlib.
- D6: Allowed Roots default: Home + CWD.
- D7: Output default `auto` (TTY → Plain, pipe → JSON); `--format auto|json|plain`.
- D8: One GitHub Issue per phase; 3–6 commits per phase; then push; then monitor CI.

## Workflow

See `workflow.md`. Every task follows: inspect → plan → implement → add/extend tests → `make check` → fix → commit → (every 3–6 commits) push → monitor CI → update this tasklist.

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
- [ ] P1-T03 Implement path traversal protection
- [ ] P1-T04 Implement symlink detection and handling
- [ ] P1-T05 Implement recursive directory traversal
- [ ] P1-T06 Implement deterministic sorting
- [ ] P1-T07 Implement file and directory metadata extraction
- [ ] P1-T08 Implement MIME type detection
- [ ] P1-T09 Implement SHA-256 hashing
- [ ] P1-T10 Implement scan completeness and error reporting
- [ ] P1-T11 Add tests for inaccessible paths
- [ ] P1-T12 Add tests for symlinks and path escapes
- [ ] P1-T13 Add tests for allowed-root restrictions
- [ ] P1-T14 Implement TOML configuration loader (`--config`, default location, precedence)

**Milestone:** A reusable and tested filesystem core.

---

## Phase 2 – Inspection Commands

### `inspect tree`

- [ ] P2-T01 Implement recursive tree generation
- [ ] P2-T02 Implement configurable maximum depth
- [ ] P2-T03 Implement entry limits
- [ ] P2-T04 Implement ignored directories and patterns
- [ ] P2-T05 Implement directory-only mode
- [ ] P2-T06 Implement plain tree rendering
- [ ] P2-T07 Implement optional metadata summaries
- [ ] P2-T08 Implement optional Python code structure

### `inspect info`

- [ ] P2-T09 Implement single-path metadata inspection
- [ ] P2-T10 Implement timestamps and permissions
- [ ] P2-T11 Implement owner information
- [ ] P2-T12 Implement MIME type information
- [ ] P2-T13 Implement symlink information
- [ ] P2-T14 Implement `--metadata` document extraction (PDF/ODF/OOXML)

### `inspect inventory`

- [ ] P2-T15 Implement structured directory inventories
- [ ] P2-T16 Implement optional SHA-256 calculation
- [ ] P2-T17 Implement deterministic tree hashing
- [ ] P2-T18 Implement inventory completeness reporting
- [ ] P2-T19 Implement JSON serialization
- [ ] P2-T20 Implement `root` + `rel_path` portability

### `inspect read`

- [ ] P2-T21 Implement bounded UTF-8 reading
- [ ] P2-T22 Implement configurable maximum size
- [ ] P2-T23 Implement truncation reporting
- [ ] P2-T24 Prevent accidental binary and symlink reading

**Milestone:** Complete read-only filesystem inspection.

---

## Phase 3 – Search and Analysis

### `find`

- [ ] P3-T01 Implement filename pattern matching
- [ ] P3-T02 Implement extension filtering
- [ ] P3-T03 Implement file type filtering
- [ ] P3-T04 Implement size filtering
- [ ] P3-T05 Implement modification date filtering

### `duplicates`

- [ ] P3-T06 Implement file-size-based candidate filtering
- [ ] P3-T07 Implement SHA-256 comparison
- [ ] P3-T08 Implement duplicate grouping
- [ ] P3-T09 Implement duplicate reports
- [ ] P3-T10 Handle incomplete scans correctly

### `compare`

- [ ] P3-T11 Implement source/destination traversal
- [ ] P3-T12 Compare relative paths
- [ ] P3-T13 Detect identical files
- [ ] P3-T14 Detect missing files
- [ ] P3-T15 Detect changed files
- [ ] P3-T16 Detect unexpected files
- [ ] P3-T17 Detect type conflicts
- [ ] P3-T18 Report unsupported entries

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

---

## Stop Conditions

Stop and ask before proceeding when any of the following occurs:

- Destructive or irreversible decision (e.g. adding `delete` functionality).
- Unclear public interface or CLI contract.
- Missing credentials needed for CI/PyPI release.
- CI fails repeatedly and the error cannot be reproduced locally.
- Changes would be required outside this repository.
