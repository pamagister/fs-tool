# Filesystem Organization Skill

DRAFT! DO NOT USE YET!

## Purpose

Use `fs-tool` to analyze, plan and safely reorganize local filesystems.

The agent is responsible for understanding the data and making organizational decisions. `fs-tool` is responsible for executing controlled filesystem operations.

## General Workflow

### 1. Understand

- Identify the target directory and accessible filesystem roots.
- Inspect the existing directory structure.
- Generate an inventory where appropriate.
- Examine file metadata, types, sizes and timestamps.
- Inspect file contents selectively when necessary.
- Identify duplicates, inconsistencies and poorly named files.

### 2. Analyze

- Understand the apparent purpose and relationships of files.
- Identify logical groups and organizational opportunities.
- Distinguish confirmed information from assumptions.
- Avoid moving files based on filenames alone when relevant metadata is available.

### 3. Plan

- Propose a consistent target directory structure.
- Map existing files and directories to their intended destinations.
- Identify renaming requirements and potential conflicts.
- Preserve existing information and avoid unnecessary changes.
- Present the proposed changes before execution.

### 4. Validate

- Check all source and destination paths.
- Identify naming conflicts and duplicate content.
- Verify that the proposed operations are supported.
- Generate and inspect a dry-run before execution.

### 5. Execute

- Use `fs-tool` for filesystem modifications.
- Obtain the required authorization for write and rename operations.
- Never overwrite or delete data without explicit authorization.
- Execute operations in manageable batches.
- Record relevant operation results.

### 6. Verify

- Compare the resulting filesystem with the intended target structure.
- Verify copied or moved files using hashes where appropriate.
- Identify missing, unexpected or changed files.
- Report incomplete operations and unresolved conflicts.

## Guiding Principles

- Preserve data integrity above all else.
- Prefer understandable structures over unnecessary complexity.
- Never guess when information can be inspected.
- Keep the user informed about significant decisions.
- Make all modifications traceable and verifiable.