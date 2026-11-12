# Mission: Agentic Filesystem Reorganization Support

## Objective

Make `fs-tool` sufficient for the `filesystem-organizer` skill to plan, preview, execute and verify
multi-step filesystem reorganizations without manually orchestrating dozens of individual commands
and without losing content verification across renames.

The desired outcome is a CLI that supports:

1. a declarative, multi-step write plan with a real dry-run,
2. safe execution with per-operation reporting and explicit failure handling,
3. content-set verification that survives renames and moves,
4. practical move/copy ergonomics for agents,
5. bounded text extraction from ODF and OOXML documents,
6. removal of the documentation and validation defects found during the assessment.

## Scope, Constraints and Non-Goals

### In scope

- `write apply` plan execution for `mkdir`, `move`, `copy` and empty-directory `rmdir`.
- Plan-level preflight and dry-run that simulates planned directory creation and later operations.
- `verify inventory --match path|content` for content-preserving verification after renames.
- Existing-directory destination semantics for `write move` and `write copy`.
- `--parents` support for `write copy` and `write move`.
- A safe `write rmdir` command that removes only empty directories.
- Bounded `odf_text` and `ooxml_text` extraction through `inspect read`.
- Inventory filter/hashing correction and validation of negative numeric options.
- Documentation, tests and integration QA for the above.

### Explicit non-goals

- No agent framework, MCP adapter, LLM integration or autonomous planner.
- No general recursive delete and no unrestricted `write delete`.
- No cross-device move support; cross-device reorganizations remain copy-plus-verification.
- No automatic rollback of a partially executed `write apply` plan in this increment.
- No `inspect analyze` text-structure analysis for ODF/OOXML in this increment; `inspect read`
  is the content interface for those formats.
- No change to the symlink policy: symlinks are recorded, never followed.
- No change to `schema_version`; new result fields must be additive and backward-compatible.
- No cloud or remote filesystem support.

## Baseline and Assessment

### Baseline

- Repository: `/home/paul/PycharmProjects/fs-tool`
- Branch: `main`
- Baseline commit: `aeee05f` (`docs(v3): document inventory features and QA results`)
- Tests: `441 passed` with `uv run pytest -q`
- Lint: `make lint` passes (`ruff check`, `ruff format --check`, `mypy src/`)
- CLI version: `1.0.1.dev15+geebe36d25.d20261110` at assessment time
- Python target: 3.11

### What works well

- Read-only inspection is strong: `tree`, `inventory`, `find`, `duplicates`, `compare`, `info`,
  `analyze`, `read`, hashing, JSON envelope and structured errors.
- PDF text extraction and PDF page analysis work on the example files.
- Image metadata and YOLO object detection work when the optional image extra and model are present.
- Individual write operations are safe: `--dry-run`/`--yes`, allowed-root validation, no
  overwrite, SHA-256 verification for copies and inode verification for moves.
- The test suite and lint/type checks are green.

### Findings from the example reorganization test

A moderate reorganization was executed on a temporary copy of
`res/example_filesystem_unstructured` (5 `mkdir` operations and 16 `move` operations). The result:

- 28 files before and 28 files after.
- The SHA-256 multiset was identical before and after: no file content was lost or changed.
- `tree_hash` changed from `f5b29bc2...` to `55a2f87d...`, which is expected because paths changed.
- `verify inventory` against the pre-reorganization inventory reported 22 missing paths and many
  unexpected paths even though the content multiset was identical. Path-based verification cannot
  validate renames.
- The source directory `Beruf` remained empty after its only file was moved. There is no `rmdir` or
  delete command, so empty directories cannot be cleaned up.
- `write mkdir --parents` worked, but `write copy --dry-run` and `write move --dry-run` failed when
  the destination parent did not exist yet. A plan-level dry-run cannot preview a sequence where an
  earlier step creates the parent directory.
- Moving a file into an existing directory failed with `TARGET_EXISTS` unless the full destination
  file path was supplied. Moving into an existing directory is the natural agent operation.
- `inspect read` rejects `.odt` and `.docx` as “not valid UTF-8 text (binary file)”.
  `inspect analyze` reports `supported: false` for both. Only format metadata is available for ODF
  and OOXML, which is insufficient for content-based classification.
- `inspect inventory --extension pdf --hash` hashes every file before applying the extension filter.
  This contradicts the documented filter order and wastes work on large trees.
- Documentation defects found:
  - capability examples still say `count: 9` and `available_count: 5`; the registry has 10
    capabilities,
  - the `write copy` example using `--allow-root /mnt/nas` omits the source root and is therefore
    invalid,
  - `docs/usage/safety.md` claims that a write operation “either applies as a whole or aborts”,
    but a copy can partially apply after an I/O failure; the partial paths are reported,
  - the architecture package layout omits `output/tabular.py`, `setup/service.py`,
    `core/providers/content.py` and `core/capabilities/report.py`,
  - `pyproject.toml` still references the removed `docs/develop/initial-release` data-files path.

### Suitability verdict

`fs-tool` is already suitable for **individual, well-understood moves and copies** and for
**inspection/analysis**. It is not yet sufficient for **autonomous multi-step reorganization** because
it lacks plan-level preflight/dry-run, content-set verification after renames, empty-directory
cleanup, and content extraction for ODF/OOXML. The work below closes those gaps without changing the
project’s safety model.

## Architecture and Decisions

### 1. One declarative write plan

`write apply` consumes a JSON plan file. Minimum schema:

```json
{
  "plan_version": 1,
  "operations": [
    {"op": "mkdir", "destination": "/abs/or/relative/path", "parents": true},
    {"op": "move", "source": "/path/source", "destination": "/path/destination", "allow_rename": true},
    {"op": "copy", "source": "/path/source", "destination": "/path/destination", "symlinks": "skip"},
    {"op": "rmdir", "destination": "/path/empty-dir", "parents": false}
  ]
}
```

- `plan_version` is independent of the JSON envelope `schema_version`, which stays `1`.
- Relative paths are resolved against the current working directory.
- Every source and destination is validated against the allowed roots, exactly like existing write
  commands.
- Unknown operations, invalid options and duplicate paths are rejected before execution.

### 2. Preflight is an in-memory simulation

`write apply --dry-run` simulates the complete plan against an in-memory path model:

- planned `mkdir` operations create virtual directories for later operations,
- planned `move`/`copy` operations reserve destination paths and remove source paths,
- planned `rmdir` operations remove only virtual empty directories,
- conflicts, missing parents, existing destinations, cross-device moves, directory cycles and
  symlink escapes are detected before any filesystem change,
- the dry-run never touches the filesystem.

The simulation cannot predict runtime I/O errors. Those are handled during execution and reported.

### 3. Execution is sequential and explicit

`write apply --yes` executes operations in plan order.

- Default: stop at the first failed operation.
- `--on-error continue`: continue with later operations when they remain valid; report all failures.
- No automatic rollback in this increment. The result reports completed, failed and pending
  operations plus affected paths so the agent can decide how to recover.
- Exactly one of `--dry-run` or `--yes` is required, consistent with existing write commands.

### 4. Content-set verification is a first-class mode

`verify inventory INVENTORY TARGET --match path|content`:

- `path` is the default and preserves the current behavior.
- `content` compares multisets of regular files by `(size, sha256)` and symlink targets by target
  string. Directories are ignored because their metadata is not content.
- The inventory must contain hashes; otherwise the command fails with a clear error.
- Duplicate content is represented by multiset counts, so intentional deduplication is detected.
- Additive result fields: `match_mode`, `missing_content`, `unexpected_content` and
  `content_count_mismatch`. Path-mode fields remain unchanged.

### 5. ODF/OOXML text extraction uses the standard library only

- `odf_text` reads `content.xml` from ODF ZIP containers and extracts text paragraphs/headings.
- `ooxml_text` reads the relevant XML parts for `.docx`, `.xlsx` and `.pptx` and extracts text.
- Extraction is bounded by the existing ZIP-member limit and a new text-output limit.
- Macros and embedded objects are never executed.
- Results use `representation: "extracted_text"` and format identifiers `odf` / `ooxml`.
- `inspect analyze` remains structure-only for these formats in this increment.

### 6. Inventory filters run before hashing

`inspect inventory` applies `--extension`, `--min-size` and `--max-size` before hashing and before
computing `tree_hash`. `filtered`, `count`, `skipped` and `truncated` keep their documented meaning.

## Implementation Phases

## Phase 1: Inventory Correctness and Content-Set Verification [x]

**Objective:** Make inventory filtering match its documented order and add verification that proves
content preservation across renames.

- [x] P1-W01: Move `--extension`, `--min-size` and `--max-size` filtering before hashing and
  `tree_hash` calculation in `inspect_inventory`.
- [x] P1-W02: Add tests proving that files removed by filters are not hashed and that `filtered`,
  `count` and `tree_hash` keep their documented semantics.
- [x] P1-W03: Add `verify inventory --match path|content` with content-mode comparison of regular
  files and symlink targets, including the additive result fields.
- [x] P1-W04: Add tests for pure renames, changed content, missing/extra content, duplicate content,
  empty files, hardlinks, missing hashes and incomplete inventories.
- [x] P1-W05: Update `docs/usage/cli.md`, `docs/usage/output.md` and
  `docs/usage/examples.md` for filter order and content-set verification.

**Acceptance criteria**

- `inspect inventory --extension pdf --hash` does not hash non-PDF files.
- `verify inventory --match path` behaves exactly as before.
- `verify inventory --match content` returns success for a pure rename/move reorganization with
  identical file content and fails when content is missing, added or changed.
- Existing inventory and verification tests pass.

**Phase gate:** Inventory filtering and content verification are stable before write-plan execution
depends on them.

## Phase 2: Write Command Ergonomics [x]

**Objective:** Make individual write commands match the way agents naturally describe moves and
copies, and add safe empty-directory cleanup.

- [x] P2-W01: Support existing-directory destinations for `write move` and `write copy`: when the
  destination is an existing directory, append the source basename; report a conflict if the
  resulting path exists.
- [x] P2-W02: Add `--parents` to `write copy` and `write move` so missing destination parent
  directories are created after preflight.
- [x] P2-W03: Add `write rmdir` for empty directories only, with `--parents` to remove an empty
  parent chain, `--dry-run`/`--yes`, and refusal for non-empty directories, symlinks and
  non-directories.
- [x] P2-W04: Improve write reports: plain output includes the source and affected paths; JSON keeps
  the existing `OperationReport` fields and adds only additive detail where useful.
- [x] P2-W05: Add tests for existing-directory destinations, `--parents`, `rmdir` edge cases, and
  report contents.
- [x] P2-W06: Update `docs/usage/cli.md`, `docs/usage/safety.md` and `docs/usage/examples.md`.

**Acceptance criteria**

- `fs-tool write move file existing-dir --yes` moves the file to `existing-dir/file` without
  requiring `--allow-rename`.
- `fs-tool write copy tree existing-dir --yes` copies the tree to `existing-dir/tree`.
- `--parents` creates missing parents for both commands and is reflected in dry-run output.
- `write rmdir` removes an empty directory, refuses a non-empty directory, and never deletes files.
- Existing operation tests remain green.

**Phase gate:** Individual write ergonomics are stable before the multi-step plan is added.

## Phase 3: Multi-Step Write Plan Execution [x]

**Objective:** Add `write apply` with plan-level dry-run, preflight and sequential execution.

- [x] P3-W01: Define the `plan_version: 1` JSON schema and validation rules for `mkdir`, `move`,
  `copy` and `rmdir`.
- [x] P3-W02: Implement the in-memory preflight simulator, including planned directory creation,
  destination reservation, conflict detection, cross-device detection and directory-cycle checks.
- [x] P3-W03: Implement `write apply --dry-run` with per-operation status, affected paths and an
  overall `would_succeed` result.
- [x] P3-W04: Implement `write apply --yes` with sequential execution, `--on-error stop|continue`,
  per-operation reporting and no automatic rollback.
- [x] P3-W05: Add tests for dry-run purity, planned-mkdir-then-move, conflict detection, execution
  order, failure handling, idempotent reruns, allowed roots and malformed plans.
- [x] P3-W06: Document the plan schema, dry-run behavior, execution semantics, failure behavior and
  limitations in `docs/usage/cli.md` and `docs/usage/examples.md`.

**Acceptance criteria**

- A plan containing `mkdir` followed by `move` into that directory passes dry-run without creating
  anything.
- `write apply --yes` executes the plan, reports each operation, and never overwrites an existing
  destination.
- A failing operation stops the plan by default and leaves a structured report; `--on-error continue`
  continues only while later operations remain valid.
- The dry-run result is identical whether or not the target directories already exist, as long as the
  plan is valid.
- Existing write commands and tests remain unchanged.

**Phase gate:** The plan format and execution semantics are stable before documentation and QA.

## Phase 4: ODF and OOXML Text Extraction

**Objective:** Let agents read textual content from ODF and OOXML documents so they can classify
files by content, not only by filename and metadata.

- [ ] P4-W01: Add the `odf_text` capability and `OdfProvider.read_content()` for `.odt`, `.ods`,
  `.odp` and `.odg`, using `content.xml` and the standard library.
- [ ] P4-W02: Add the `ooxml_text` capability and `OoxmlProvider.read_content()` for `.docx`,
  `.xlsx` and `.pptx`, using the relevant XML parts and the standard library.
- [ ] P4-W03: Integrate both capabilities with `inspect read`, including truncation,
  `representation: "extracted_text"`, format identifiers and structured failures for malformed,
  encrypted or oversized containers.
- [ ] P4-W04: Register both capabilities in the central registry and update `fs-tool capabilities`.
- [ ] P4-W05: Add tests using the example files plus malformed, empty and oversized containers.
- [ ] P4-W06: Update `docs/usage/cli.md`, `docs/usage/setup.md`,
  `docs/develop/architecture.md` and `docs/usage/examples.md`.

**Acceptance criteria**

- `inspect read` returns text for the example `.odt`, `.ods`, `.docx` and `.pptx` files.
- Output is bounded by `--max-bytes` and never contains raw ZIP/XML bytes.
- Malformed or encrypted containers return a structured capability error.
- `capabilities` lists `odf_text` and `ooxml_text` with correct availability.
- Existing `inspect info` metadata behavior is unchanged.

**Phase gate:** Content extraction is bounded and safe before it is used in the integration test.

## Phase 5: Validation, Documentation and Quality Assurance

**Objective:** Close the remaining correctness/documentation gaps and prove the complete workflow.

- [ ] P5-W01: Validate `--max-depth` and `--max-entries` as non-negative integers; reject negative
  values with exit code 2. Define `--max-depth 0` and `--max-entries 0` behavior and test it.
- [ ] P5-W02: Fix documentation defects: capability counts, `model_directory`, the `--allow-root`
  write example, the safety atomicity wording, the architecture package layout and the output
  envelope wording.
- [ ] P5-W03: Add CLI reference entries and examples for `write apply`, `write rmdir`,
  `verify inventory --match content`, `--parents`, and ODF/OOXML text extraction.
- [ ] P5-W04: Add an integration test that copies `res/example_filesystem_unstructured` to a
  temporary directory, applies a plan with `mkdir`, `move` and `rmdir`, runs
  `verify inventory --match content`, and asserts that the file hash multiset is unchanged and no
  unexpected content exists.
- [ ] P5-W05: Run `make lint`, `make test`, `make precommit` and `make build`; verify the wheel and
  documentation build.
- [ ] P5-W06: Remove the stale `docs/develop/initial-release` data-files entry from
  `pyproject.toml` and verify that the package data matches the current documentation layout.

**Acceptance criteria**

- Negative numeric bounds are rejected consistently.
- Documentation matches the implemented commands, options, counts and safety behavior.
- The integration test proves a multi-step reorganization preserves all file content.
- `make lint`, `make test`, `make precommit` and `make build` pass.
- No unrelated files or pre-existing user changes are included in commits.

**Final phase gate:** The implementation is complete only when code, tests, CLI help and
documentation agree, and the example reorganization passes end to end.

## Dependencies and Ordering

1. Phase 1 must land first because content-set verification is the acceptance mechanism for Phase 3.
2. Phase 2 must land before Phase 3 because plan ergonomics and `rmdir` reduce the number of special
   cases the planner must handle.
3. Phase 3 depends on the operation primitives from Phase 2 but may define its schema in parallel.
4. Phase 4 is independent of Phases 1–3 and can proceed in parallel if capacity allows.
5. Phase 5 depends on all previous phases and must not be marked complete until the integration test
   and all quality gates pass.

## Risks and Mitigations

**Risk: Preflight cannot predict runtime I/O failures.**
Mitigation: execute sequentially, stop by default, report completed/failed/pending operations and
affected paths. Do not claim atomicity.

**Risk: A partially executed plan leaves the filesystem in an intermediate state.**
Mitigation: document that there is no automatic rollback in this increment; provide per-operation
status and affected paths; make dry-run mandatory before `--yes` in the documented workflow.

**Risk: Content-set verification could be misread as proof against hash collisions.**
Mitigation: document that SHA-256 collisions are computationally infeasible and that the check proves
content equality for practical purposes.

**Risk: ODF/OOXML extraction may include only text and not layout.**
Mitigation: document the representation and scope; keep `inspect analyze` structure-only for these
formats in this increment.

**Risk: `write rmdir` could be misused to remove a non-empty directory.**
Mitigation: use `rmdir` semantics, never recursive deletion; preflight the directory and refuse
non-empty directories; require `--yes`.

**Risk: Plan paths could escape allowed roots through symlinks.**
Mitigation: reuse `validate_path` for every source and destination; never follow symlinks; reject
symlink escapes during preflight and execution.

**Risk: Cross-device moves remain unsupported.**
Mitigation: document the limitation and recommend copy plus content-set verification; do not attempt
a hidden delete fallback.

## Open Questions and Deferred Work

- Should `write apply` support automatic rollback of completed operations? Deferred; the current
  design reports partial state instead.
- Should a general `write delete` command be added? Deferred; only empty-directory `rmdir` is in
  scope.
- Should `compare` support `--match content` for two live trees? Deferred; `verify inventory` covers
  the inventory-based workflow.
- Should `inspect analyze` add text-structure analysis for ODF/OOXML? Deferred; `inspect read` is the
  content interface in this increment.
- Exact naming of additive JSON fields may be refined during implementation as long as the documented
  minimum is preserved.

## Execution Notes

- Read `AGENTS.md` and `docs/develop/architecture.md` before changing core code.
- Keep `schema_version` at `1`; add new result fields only as additive, backward-compatible fields.
- Do not stage or modify the pre-existing untracked files: `.idea/fs-tool-cli.iml`,
  `.idea/runConfigurations/`, `.idea/vcs.xml`, `report_cli.md`, `report_cli_compact.md`,
  `report_cli_comparison.md`.
- Use one coherent commit per work package, including the plan checkbox update in that commit.
- Run the relevant focused tests before each commit and the full quality gates at the phase boundary.
## Progress / Handoff

### 2026-11-12 - Phase 1

- Completed P1-W01 through P1-W05: filters run before hashing and tree hashing; content-set verification and documentation are implemented.
- Commits: `86412f5`, `1b83ed0`, `d70d4cb`; pushed to `origin/main`.
- CI run `43273004488` passed for the phase implementation.
- Next: Phase 2, starting with existing-directory destination semantics for `write move` and `write copy`.

### 2026-11-12 - Phase 2

- Completed P2-W01 through P2-W06: existing-directory move/copy destinations, `--parents`, safe `write rmdir`, improved reports, tests and documentation.
- Commits: `bd885e9`, `5b29cdf`; pushed to `origin/main`.
- CI run `43274301680` passed for the phase implementation.
- Next: Phase 3, `write apply` plan execution with in-memory preflight and sequential execution.

### 2026-11-12 - Phase 3

- Completed P3-W01 through P3-W06: plan schema, in-memory preflight, dry-run, sequential execution, failure policies, tests and documentation.
- Commit: `47ba6c4`; pushed to `origin/main`.
- CI run `43275861843` passed for the phase implementation.
- Next: Phase 4, bounded ODF/OOXML text extraction through `inspect read`.
