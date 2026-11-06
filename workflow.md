# fs-tool – Autonomous Development Workflow

This document describes the end-to-end workflow used to implement `fs-tool`
phases, one task at a time. It is referenced by `AGENTS.md` and `tasklist.md`.

---

## Guiding Rules

- Make the smallest correct change that solves the task.
- Preserve existing architecture, conventions, formatting and style.
- Do not refactor or clean up unrelated code.
- Write tests for filesystem operations and safety-critical behavior.
- Never silently overwrite or delete user data.
- Require explicit authorization for potentially risky operations.
- JSON is the primary interface; Plain is a human-oriented alternative.
- Allowed Roots default: Home + CWD. Anything else requires `--allow-root`.
- Output default: `auto` (TTY → Plain, pipe → JSON).

---

## Per-Task Loop

For every task in `tasklist.md`:

1. **Pick the next open task** in the current phase (top-down order).
2. **Inspect** the relevant code, tests, configuration and plan sections.
3. **Plan** the smallest change; note acceptance criteria from the task.
4. **Implement** the change (code, tests, docs as needed).
5. **Verify**: run `make check` or the targeted pytest invocation; fix failures.
6. **Commit** with a conventional message, including the issue reference:
   ```
   <type>[optional scope]: <description>

   [optional body]

   Fixes #<number>
   ```
7. **Update `tasklist.md`**: mark the task `[x]`, add a Work Log entry.

### Commit cadence

- After every task: one commit.
- After **3–6 commits** or at the end of a phase: `git push`.
- After push: monitor GitHub Actions with `gh run list` and `gh run view <run-id>`.
- If CI fails: fix locally, commit, push again, re-monitor.
- Only start the next phase when the current phase is complete and CI is green.

### Issue usage

- One GitHub Issue per phase.
- Phase 0 uses existing issue #2 ("Cleanup legacy stuff").
- Reference the issue in every commit belonging to that phase.
- Close the issue when the phase milestone is reached and CI is green.

---

## Phase Gates

A phase is complete when:

- All its tasks in `tasklist.md` are `[x]`.
- The phase milestone from `plan.md` is reached.
- `make check` is green locally.
- CI is green on all matrix jobs.
- The phase issue is closed.

---

## Context Compaction

At the end of each phase (or when the context becomes large):

1. Update `tasklist.md` Work Log with a summary of what was done.
2. Summarize open questions, next task, and any CI quirks.
3. Hand off to the next session with that summary.

---

## Stop Conditions

Stop and ask before proceeding when any of the following occurs:

- Destructive or irreversible decision (e.g. adding `delete` functionality).
- Unclear public interface or CLI contract.
- Missing credentials needed for CI/PyPI release.
- CI fails repeatedly and the error cannot be reproduced locally.
- Changes would be required outside this repository.
