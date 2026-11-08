# Welcome to fs-tool

fs-tool is a lightweight, secure and agent-friendly command-line application for analyzing,
organizing and restructuring local filesystems. It provides a reliable interface for inspecting
directory structures, understanding file contents and metadata, identifying duplicates, comparing
directory trees, and performing controlled file operations.

[![Github CI Status](https://github.com/pamagister/fs-tool/actions/workflows/main.yml/badge.svg)](https://github.com/pamagister/fs-tool/actions)
[![GitHub release](https://img.shields.io/github/v/release/pamagister/fs-tool)](https://github.com/pamagister/fs-tool/releases)
[![Read the Docs](https://readthedocs.org/projects/fs-tool/badge/?version=stable)](https://fs-tool.readthedocs.io/en/stable/)
[![License](https://img.shields.io/github/license/pamagister/fs-tool)](https://github.com/pamagister/fs-tool/blob/main/LICENSE)
[![GitHub issues](https://img.shields.io/github/issues/pamagister/fs-tool)](https://github.com/pamagister/fs-tool/issues)
[![PyPI](https://img.shields.io/pypi/v/fs-tool)](https://pypi.org/project/fs-tool-cli/)
[![Downloads](https://pepy.tech/badge/fs-tool)](https://pepy.tech/project/fs-tool-cli/)

## Documentation

- [Command-line interface](usage/cli.md) — commands, options and exit codes.
- [Configuration](usage/configuration.md) — TOML configuration and allowed roots.
- [Output formats](usage/output.md) — JSON envelope and human-readable output.
- [Safety model](usage/safety.md) — access restrictions, symlinks and write protection.
- [Examples](usage/examples.md) — practical inspection, analysis and write workflows.
- [Architecture](develop/architecture.md) — layers, modules and data model.
- [Contributing](develop/contributing.md) — development setup, checks and conventions.
- [Funding](funding/funding.md) — how to support the project.

## Quick start

Install the published package and inspect a directory:

```bash
uv tool install fs-tool-cli
fs-tool inspect tree ~/Documents --plain
```

From a source checkout:

```bash
git clone https://github.com/pamagister/fs-tool.git
cd fs-tool
uv sync --all-groups
uv run fs-tool --help
```

## Project Vision

fs-tool should be useful both for interactive human users and for automated workflows. Its primary
purpose is to provide a reliable interface for inspecting directory structures, understanding file
contents and metadata, identifying duplicates, comparing directory trees, and performing controlled
file operations.

The primary use cases are:

- Understanding existing directory structures.
- Creating structured filesystem inventories.
- Collecting file metadata and identifying file types.
- Analyzing selected file formats and source code.
- Finding duplicate files.
- Comparing directory structures and file contents.
- Copying, moving and renaming files and directories.
- Verifying the integrity of filesystem operations.

## Guiding Principle

**The agent makes decisions; fs-tool provides the information and executes filesystem operations
safely and deterministically.**

The application must remain independent of any particular AI agent, MCP implementation or external
automation framework.

## Design Philosophy

- Prefer simplicity over unnecessary abstraction.
- Keep the Python filesystem core independent of the CLI.
- Use structured JSON output as the primary interface.
- Provide readable human-oriented output as an alternative.
- Make filesystem operations predictable, transparent and verifiable.
- Never silently overwrite or delete user data.
- Require explicit authorization for potentially risky operations.
- Favor deterministic results and reproducible inventories.
- Keep dependencies minimal.

## Scope

The initial release focuses exclusively on the filesystem CLI and its underlying Python library.
Agent orchestration, autonomous planning, MCP adapters and advanced LLM integrations are future
extensions and must not unnecessarily influence the initial architecture.
