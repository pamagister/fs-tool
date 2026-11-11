# Mission: Inventory Correctness, Performance and CLI Comfort

## Objective

Improve `fs-tool` along three axes without changing its safety model or JSON envelope contract:

1. **Correctness:** Make `inspect inventory` output profiles consistent between JSON and plain text, make `tree_hash` genuinely portable across machines and users, and surface scan truncation and skipped entries.
2. **Performance and usability:** Avoid unnecessary full-entry materialization, add bounded hashing and progress feedback, and provide field selection and filtering for large inventories.
3. **CLI comfort:** Add deterministic sorting, optional symlink following, configurable default ignores, CSV/TSV export, short/negatable verbose flags, and a documented verbose audit for non-entry commands.

The work is split into five phases. Each phase is independently testable, documented and committed. The JSON envelope and `schema_version` remain unchanged at `1`.

## Scope and Traceability

The user selected the following items from the assessment. This plan maps every selected item to a stable work-package ID.

| Selection | Plan ID | Work package |
|---|---|---|
| P1 | C1 | Make `tree_hash` portable and document the algorithm |
| P2 | C2 | Align plain and JSON compact inventory profiles |
| P3 | C3 | Make plain verbose inventory output complete |
| P6 / option "F6" | C4 | Surface skipped entries and scan truncation |
| M1 | I1 | Avoid full-entry materialization in inventory |
| M2 | I2 | Add `--max-hash-bytes` |
| M3 | I3 | Add `--progress` for long inventory scans |
| F1 | I4 | Add `--fields` to `inspect inventory` |
| F9 | I5 | Add extension and size filters to `inspect inventory` |
| F2 | T1 | Add `--sort-by` to traversal commands |
| F3 | T2 | Add `--follow-symlinks` to traversal commands |
| F4 | T3 | Add `--no-default-ignore` |
| F5 | O1 | Add CSV/TSV output for `inspect inventory` |
| F7 | O2 | Add `-v` and `--no-verbose` |
| F8 | O3 | Audit and document verbose behavior for non-entry commands |

### Explicit non-goals

- `--output FILE`, atomic file writing and `--pretty` / `--indent` JSON output. These were listed as possible improvements but were not selected.
- `P4` (globally clarifying the `--verbose` help text) and `P5` (`generated_at` determinism) beyond what the O3 audit requires.
- Changing the JSON envelope structure or bumping `schema_version`.
- Changing write-operation authorization, overwrite protection or the allowed-root safety model.
- Pagination, cursors or a general output limit.
- New output profiles beyond CSV/TSV.
- Cross-platform CI opt-in (`--all`) unless a platform-specific defect requires it.

## Repository and Baseline Context

- Repository: `/home/paul/PycharmProjects/fs-tool`
- Remote: `https://github.com/pamagister/fs-tool.git`
- Branch: `main`
- Baseline commit: `eed077f` (`test(output): ignore volatile access times in position check`)
- Baseline tests: `394 passed` with `uv run pytest -q`
- Baseline lint: `make lint` passes (`ruff check`, `ruff format --check`, `mypy src/`)
- Python target: 3.11
- Dependency tool: `uv`
- Test tool: `pytest`

### Pre-existing untracked files

The following files existed before this mission and must not be staged, modified or committed:

- `.idea/fs-tool-cli.iml`
- `.idea/runConfigurations/`
- `.idea/vcs.xml`
- `report_cli.md`
- `report_cli_compact.md`
- `report_cli_comparison.md`

Stage only files belonging to the current work package. Never use `git add -A` or `git add .`.

### Useful commands

```bash
uv run pytest -q
uv run pytest -q tests/test_inventory.py
make lint
make test
make precommit    # mutating: formats, fixes, runs tests and dependency checks
make build
make syncdocs     # only when docs/index.md changes
```

## Architecture and Decisions

### 1. Keep the internal data model complete

`FilesystemEntry` remains the complete internal representation. All filtering, projection and presentation happen in `output/` and `cli.py`. No core model field may be removed to save output space.

### 2. `tree_hash` algorithm version 2

`tree_hash` must depend only on structure and content. The hash input is the canonical projection of each entry:

- `rel_path`
- `type`
- `extension`
- `size`
- `sha256` (null when `--hash` was not requested)

Excluded fields: `name`, `path`, `target`, timestamps, `mode`, `owner`, `mime_type`, `is_symlink`, `dev_ino`, `metadata`.

Rationale:

- `mode`, `owner` and `mime_type` are environment-dependent and break cross-machine portability.
- `target` may contain absolute paths and is not needed for a structure/content hash.
- `name` is redundant with `rel_path`.
- `is_symlink` is represented by `type == "symlink"`.

Consequences:

- Changing file permissions, ownership, MIME database or symlink target does not change `tree_hash`.
- Changing file content, size, path or type does change `tree_hash`.
- `tree_hash` remains independent of the output profile (`--fields`, compact, verbose).
- `schema_version` stays `1`. The algorithm change is documented as tree-hash algorithm version 2 in `docs/usage/output.md`; no new envelope field is introduced.

### 3. One field-selection path

`inspect inventory` supports three modes:

| Mode | Fields |
|---|---|
| Default | Compact profile: `rel_path`, `type`, `extension`, `size`, `modified`, plus `sha256` with `--hash` |
| `--verbose` | All non-path entry fields |
| `--fields a,b,c` | Exactly the requested fields, in the requested order |

`--fields` is explicit and wins over both the compact profile and `--verbose`. `--verbose` without `--fields` returns all non-path fields. `path` is never returned by `inspect inventory`.

### 4. Filtering is part of the inventory scope

`--extension`, `--min-size` and `--max-size` are applied after traversal and before hashing and `tree_hash`. They define the inventory scope:

- `count` counts the returned (filtered) entries.
- `tree_hash` covers the filtered entry set.
- `skipped` counts traversal-level ignores only, not filter removals.
- `filtered` counts entries removed by the explicit filters and is included in the inventory result when greater than zero.

Filters never change `complete` or exit codes. A filter is not an error.

### 5. Hashing is bounded and non-fatal when limited

`--max-hash-bytes` skips hashing for files larger than the limit:

- The entry keeps `sha256: null`.
- A warning `HASH_SKIPPED` is added to the envelope with the file path and size.
- `complete` stays `true` because the scan itself succeeded.
- `tree_hash` is still calculated, using `null` for the skipped hash.
- Without `--max-hash-bytes`, behavior is unchanged.

### 6. Symlink following is opt-in and root-contained

`--follow-symlinks` is opt-in. When enabled:

- The symlink target is resolved and must stay inside one of the configured allowed roots.
- A target outside the allowed roots is reported as an error and skipped.
- Cycles are detected by `(st_dev, st_ino)` and skipped.
- Broken links are reported as errors and skipped.
- `target` is `null` for followed entries because the entry is presented as its target.

### 7. Sorting is deterministic

`--sort-by` supports `name` (default), `size`, `modified` and `extension`. Sorting is applied per directory (pre-order traversal). Ties are broken by `name` to keep output deterministic.

### 8. CSV/TSV is inventory-only

`--format csv` and `--format tsv` are accepted by `inspect inventory` only. Other commands reject these values with `INVALID_ARGUMENT` and exit code `2`.

CSV/TSV respects the selected entry profile:

- Default: compact fields plus `sha256` when requested.
- `--verbose`: all non-path fields.
- `--fields`: the requested fields.

The first row is a header. Values are escaped with the standard `csv` module. Errors and warnings go to stderr; stdout contains only the table.

### 9. Verbose is presentation-only

`--verbose` must never trigger additional `stat`, directory reads, hashing or content analysis. For non-entry commands, verbose may only expose data that the command already collected. If no additional data exists, output is unchanged and this is documented.

## Implementation Phases

## Phase 1: Output Correctness

**Objective:** Fix the inconsistencies identified in the `--verbose` and inventory review before adding new features.

- [ ] C1-W01: Change `_compute_tree_hash` to hash only `rel_path`, `type`, `extension`, `size` and `sha256` using a canonical, sorted representation.
- [ ] C1-W02: Update the `_compute_tree_hash` docstring and `docs/usage/output.md` to describe tree-hash algorithm version 2 and its field set.
- [ ] C1-W03: Add tests proving that `mode`, `owner`, `mime_type` and symlink target changes do not alter `tree_hash`, while content, size, path and type changes do.
- [ ] C2-W01: Extend the plain compact inventory line to include `modified` and `extension` in addition to `rel_path`, `type`, `size` and optional `sha256`.
- [ ] C2-W02: Update `docs/usage/output.md` and `docs/usage/cli.md` so the plain compact profile matches the JSON compact profile.
- [ ] C2-W03: Add plain-output tests for the new compact inventory line.
- [ ] C3-W01: Add a complete plain verbose renderer for inventory that includes `null` and `false` values for all non-path fields not already shown on the compact line.
- [ ] C3-W02: Document that plain verbose inventory is complete for the entry representation, while tree and find keep their existing human-oriented detail behavior.
- [ ] C3-W03: Add tests for `sha256: null`, `is_symlink: false`, `target: null` and `metadata: null` in plain verbose inventory output.

**Acceptance criteria**

- `tree_hash` is stable across machines, users, permission changes, ownership changes and MIME database changes for identical content and structure.
- `tree_hash` changes when content, size, path or type changes.
- Plain compact inventory shows the same information as JSON compact inventory.
- Plain verbose inventory shows every non-path field, including null and false values.
- Existing JSON schema version remains `1`.
- Existing tests and `make lint` pass.

**Phase gate:** Output profiles are consistent and the tree hash matches its documented definition.

## Phase 2: Traversal Core Extensions

**Objective:** Add the traversal capabilities required by later inventory and CLI work.

- [ ] T1-W01: Extend `SortBy` and `traverse()` with `size`, `modified` and `extension` sorting, including deterministic `name` tie-breaking.
- [ ] T1-W02: Add `--sort-by` to `inspect tree`, `inspect inventory` and `find`.
- [ ] T1-W03: Add tests for every sort key, tie-breaking and interaction with `--max-entries`.
- [ ] T2-W01: Add root-containment validation for followed symlinks in `traverse()` or a shared traversal helper.
- [ ] T2-W02: Add `--follow-symlinks` to `inspect tree`, `inspect inventory` and `find`.
- [ ] T2-W03: Add tests for following internal symlinks, rejecting external targets, cycle detection and broken links.
- [ ] T3-W01: Add `use_default_ignores` to `traverse()` so the default ignore list can be disabled.
- [ ] T3-W02: Add `--no-default-ignore` to `inspect tree`, `inspect inventory`, `find`, `duplicates` and `compare`.
- [ ] T3-W03: Add tests proving default ignores are active by default and disabled on request, while `--ignore-dir` and `--ignore-pattern` still apply.

**Acceptance criteria**

- All sort modes produce deterministic, documented order.
- `--follow-symlinks` never escapes the allowed roots.
- `--no-default-ignore` includes previously ignored directories such as `.git` when explicitly requested.
- Existing traversal behavior remains unchanged when the new options are not used.
- All existing traversal, tree, inventory, find, duplicates and compare tests pass.

**Phase gate:** Traversal options are stable and safe before inventory features depend on them.

## Phase 3: Inventory Features and Performance

**Objective:** Make inventory output cheaper to produce and more useful for large or filtered datasets.

- [ ] I1-W01: Refactor `inspect_inventory` so compact output is built directly from `FilesystemEntry` objects without materializing all full entry dictionaries.
- [ ] I1-W02: Compute `tree_hash` from a canonical lightweight projection of the selected entries, independent of the output profile.
- [ ] I1-W03: Add tests proving compact and verbose output remain equivalent to the previous behavior and that `tree_hash` is profile-independent.
- [ ] I2-W01: Add `--max-hash-bytes` to `inspect inventory`, accepting the existing size syntax.
- [ ] I2-W02: Add `HASH_SKIPPED` warnings for files above the limit and keep `complete` true.
- [ ] I2-W03: Add tests for files below, at and above the limit, including `tree_hash` behavior.
- [ ] I3-W01: Add `--progress` to `inspect inventory`, writing periodic progress lines to stderr only.
- [ ] I3-W02: Add tests proving stdout JSON and plain output are unchanged by `--progress`.
- [ ] I4-W01: Add `--fields` to `inspect inventory` with validation of allowed field names and stable output order.
- [ ] I4-W02: Define and test the interaction between `--fields`, `--verbose` and the compact profile.
- [ ] I4-W03: Prove `--fields` does not change `tree_hash`.
- [ ] I5-W01: Add `--extension`, `--min-size` and `--max-size` filters to `inspect inventory`.
- [ ] I5-W02: Add the `filtered` count to the inventory result and plain output when filters remove entries.
- [ ] I5-W03: Add tests for filter combinations, directories, count, `tree_hash` and `complete`.
- [ ] C4-W01: Add `truncated` to `TraversalResult` and set it when `--max-entries` stops the scan.
- [ ] C4-W02: Add `skipped` and `truncated` to the inventory result and plain output.
- [ ] C4-W03: Add tests distinguishing truncation from inaccessible entries and from ignored entries.

**Acceptance criteria**

- Compact inventory no longer builds the full entry dictionary list.
- `tree_hash` is identical across compact, verbose and `--fields` output.
- Hash limits produce warnings, not failures.
- Progress output never contaminates stdout.
- Field selection and filtering are deterministic, validated and documented.
- `skipped` and `truncated` are visible in JSON and plain output.

**Phase gate:** Inventory features are complete and do not regress verification compatibility.

## Phase 4: CLI Comfort and Verbose Audit

**Objective:** Make the CLI easier to use and ensure `--verbose` is consistently documented.

- [ ] O1-W01: Add `csv` and `tsv` format handling for `inspect inventory`, including header, escaping and profile-aware columns.
- [ ] O1-W02: Reject `csv` and `tsv` for all other commands with `INVALID_ARGUMENT` and exit code `2`.
- [ ] O1-W03: Add tests for CSV/TSV output, quoting, commas in filenames, profile selection and error handling.
- [ ] O2-W01: Add `-v` as a short form and `--no-verbose` as a negation to the global verbose option.
- [ ] O2-W02: Update global-option hoisting so `-v` and `--no-verbose` work before and after the command.
- [ ] O2-W03: Add tests for `-v`, `--no-verbose`, precedence and option positions.
- [ ] O3-W01: Audit `duplicates`, `compare`, `verify`, `inspect info`, `inspect analyze`, `inspect read`, `capabilities` and `setup` for verbose behavior.
- [ ] O3-W02: Expose only already-collected data in verbose mode; do not add filesystem access.
- [ ] O3-W03: Update the `--verbose` help text to describe its effect on entry collections and its no-op behavior elsewhere.
- [ ] O3-W04: Add tests proving verbose does not change output or trigger additional filesystem access for non-entry commands.

**Acceptance criteria**

- CSV/TSV export works for inventory and is rejected elsewhere with a clear error.
- `-v` and `--no-verbose` behave like the long forms in both positions.
- Verbose behavior for every command is documented and matches the implementation.
- No command performs additional filesystem work because of `--verbose`.
- All existing tests and `make lint` pass.

**Phase gate:** CLI behavior is consistent, discoverable and safe.

## Phase 5: Documentation, Integration and Quality Assurance

**Objective:** Make code, CLI help, tests and documentation agree, and verify the complete package.

- [ ] D1-W01: Update `docs/usage/cli.md` with all new options, examples, validation rules and exit codes.
- [ ] D2-W01: Update `docs/usage/output.md` with the compact, verbose, `--fields`, filtered, skipped, truncated, warning and CSV/TSV representations.
- [ ] D3-W01: Update `docs/usage/safety.md` with the `--follow-symlinks` root-containment and cycle rules.
- [ ] D4-W01: Update `docs/usage/examples.md` with inventory, filtering, hashing, CSV and verification examples.
- [ ] D5-W01: Update `docs/develop/architecture.md` with traversal sorting, symlink policy, inventory field projection, tree-hash algorithm version 2 and CSV rendering.
- [ ] D6-W01: Run the full test suite and confirm the baseline plus all new tests pass.
- [ ] D7-W01: Run `make lint` and `make precommit`.
- [ ] D8-W01: Build the package and run an end-to-end smoke test through the installed entry point.
- [ ] D9-W01: Update the progress and handoff section of this plan.

**Acceptance criteria**

- Documentation matches the implemented behavior for every new option.
- CLI help is sufficient to discover the new options.
- JSON examples show the correct fields and `schema_version: 1`.
- `make lint`, the full test suite, `make precommit` and `make build` pass.
- No unrelated files or pre-existing user changes are included in commits.
- GitHub Actions CI is green for the pushed phase commits.

**Final phase gate:** The implementation is complete only when code, tests, CLI help and documentation consistently reflect the agreed behavior and CI is green.

## Dependencies and Ordering

1. Phase 1 must land first because it changes the output contract and tree-hash definition that later phases rely on.
2. Phase 2 must land before Phase 3 because inventory sorting, symlink handling and ignore behavior use the traversal core.
3. Phase 3 must land before Phase 4 because CSV export uses the final field-selection and filtering behavior.
4. Phase 4 must land before Phase 5 so documentation describes the final CLI surface.
5. Each work package is committed separately with its tests and any required documentation update.

## Risks and Mitigations

**Risk: Changing `tree_hash` invalidates existing hash comparisons.**

Mitigation: Document the algorithm change as version 2, add regression tests for the exact field set, and keep `schema_version` at `1`. Consumers that compare hashes across versions must regenerate inventories; this is stated in the documentation.

**Risk: Sorting by size or modification time changes traversal performance and memory.**

Mitigation: Sort per directory, keep traversal iterative where possible, and add tests for large directory trees. Do not collect the entire tree in memory just to sort globally.

**Risk: Following symlinks escapes the allowed roots.**

Mitigation: Resolve every followed target and verify containment against the configured allowed roots before descending. Add explicit security tests for internal, external, broken and cyclic links.

**Risk: Filters and field selection change `tree_hash` unexpectedly.**

Mitigation: Define `tree_hash` over the filtered canonical entry set and document it. Add tests proving `--fields` does not affect the hash while filters do.

**Risk: CSV export enables formula injection when opened in spreadsheet software.**

Mitigation: Use the standard `csv` module with correct quoting and document the risk. Do not silently rewrite user filenames; if mitigation is required, add a separate opt-in later.

**Risk: Verbose mode accidentally triggers filesystem work.**

Mitigation: Keep verbose in the presentation layer. Audit non-entry commands and add monkeypatch tests that fail on unexpected `stat` or `open` calls.

**Risk: New options interact badly with existing global flags.**

Mitigation: Add focused tests for option positions, `--json`, `--plain`, `--format`, `--allow-root` and `--config`.

## Tracking

GitHub issues are created before Phase 1 and recorded here. One issue per phase. The issue number is added to the commit message as `Refs #N`.

| Phase | Issue | Title |
|---|---|---|
| Phase 1 | #19 | Inventory output correctness and portable tree hash |
| Phase 2 | #20 | Traversal sorting, symlink following and ignore overrides |
| Phase 3 | #21 | Inventory field selection, filtering, hashing and progress |
| Phase 4 | #22 | CSV/TSV output, verbose flags and verbose audit |
| Phase 5 | #23 | Documentation, integration and quality assurance |

## Progress / Handoff

### 2026-11-11 - Plan created

- Plan file created at `docs/develop/dev-increments/v3-features-plan.md`.
- No implementation changes have been made yet.
- Baseline commit: `eed077f`.
- Baseline tests: `394 passed`.
- Baseline lint: `make lint` passes.
- Next action: create the five phase issues, record their numbers in the tracking table, then start C1-W01.

### Handoff notes for an autonomous agent

- Read `AGENTS.md` and `docs/develop/architecture.md` before changing core code.
- Follow the repository Python style: Python 3.11, 4-space indentation, double quotes, 100-character lines, type hints on public functions.
- Keep `FilesystemEntry` complete. Filtering belongs in the output layer.
- Do not change `schema_version`.
- Do not stage the pre-existing untracked files listed above.
- Use Conventional Commits. Example: `fix(inventory): make tree hash portable across machines`.
- One coherent commit per work package. Include the plan checkbox update in the same commit.
- Push after 3-6 coherent commits or at a phase boundary. Monitor GitHub Actions until a definitive result.
- If CI fails, inspect the logs, reproduce locally, fix, commit, push and monitor again.
- Do not mark a phase complete until its work packages, tests, documentation, commit, push and CI are all complete.