# Initial release

This section records the architecture, functional specification and implementation history of the
first fs-tool release. It documents how the initial scope was defined and tracked rather than
serving as end-user documentation.

## Documents

- [Plan](plan.md) — architecture, binding decisions, CLI contract, functional requirements and
  phase milestones.
- [Tasklist](tasklist.md) — task breakdown per phase, current status and work log.

## Status

Phases 0 to 6 are complete. Phase 7 (Documentation and Release) is in progress: the documentation
set has been restructured and expanded, and the test and lint gates pass. Installation testing on
Kubuntu and the release itself remain open.

## Phase overview

| Phase | Focus | Milestone |
|---|---|---|
| 0 | Project foundation and baseline | Working CLI with help, version and consistent JSON responses; `make check` green. |
| 1 | Filesystem core and safety | Reusable, tested filesystem core. |
| 2 | Inspection commands | Complete read-only filesystem inspection. |
| 3 | Search and analysis | Reliable analysis and integrity verification. |
| 4 | Filesystem operations | Safe and verifiable modifications. |
| 5 | Output and presentation | Consistent machine-readable and human-readable interfaces. |
| 6 | Additional metadata and analysis | Extended file understanding without executing content. |
| 7 | Documentation and release | First stable release. |

## How the release was tracked

The plan defines the binding decisions (D1–D8), CLI contract, output envelope, safety rules and
functional requirements. The tasklist breaks those requirements into tasks with acceptance
criteria and records completed work in the work log.

The implementation workflow was:

1. Inspect the existing code and specification.
2. Implement the smallest complete change.
3. Add or extend tests for behavior and edge cases.
4. Run `make check` and fix regressions.
5. Update the tasklist and commit.

The initial release focuses exclusively on the CLI and its underlying Python library. Agent
orchestration, MCP adapters and other integrations are out of scope and must not shape the core
architecture.

## Related documentation

- [Architecture](../architecture.md) — current implementation structure.
- [Contributing](../contributing.md) — development setup, checks and conventions.
- [Command-line interface](../../usage/cli.md) — user-facing command reference.
