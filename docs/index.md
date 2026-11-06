# Welcome to fs-tool

fs-tool is a lightweight, secure and agent-friendly command-line application for analyzing, 
organizing and restructuring local filesystems. 
Its primary purpose is to provide an interface for inspecting directory structures, 
understanding file contents and metadata, identifying duplicates, comparing directory trees, 
and performing file operations.

[![Github CI Status](https://github.com/pamagister/fs-tool/actions/workflows/main.yml/badge.svg)](https://github.com/pamagister/fs-tool/actions)
[![GitHub release](https://img.shields.io/github/v/release/pamagister/fs-tool)](https://github.com/pamagister/fs-tool/releases)
[![Read the Docs](https://readthedocs.org/projects/fs-tool/badge/?version=stable)](https://fs-tool.readthedocs.io/en/stable/)
[![License](https://img.shields.io/github/license/pamagister/fs-tool)](https://github.com/pamagister/fs-tool/blob/main/LICENSE)
[![GitHub issues](https://img.shields.io/github/issues/pamagister/fs-tool)](https://github.com/pamagister/fs-tool/issues)
[![PyPI](https://img.shields.io/pypi/v/fs-tool)](https://pypi.org/project/fs-tool/)
[![Downloads](https://pepy.tech/badge/fs-tool)](https://pepy.tech/project/fs-tool/)


## Project Vision

`fs-tool` is a lightweight, secure and agent-friendly command-line application for analyzing, organizing and restructuring local filesystems.

Its primary purpose is to provide a reliable interface for inspecting directory structures, understanding file contents and metadata, identifying duplicates, comparing directory trees, and performing controlled file operations.

The tool should be useful both for interactive human users and for automated workflows.

## Guiding Principle

**The agent makes decisions; fs-tool provides the information and executes filesystem operations safely and deterministically.**

The application must remain independent of any particular AI agent, MCP implementation or external automation framework.

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

## Future Agentic Workflow

The long-term vision is to enable AI agents, especially OpenCode, to organize complex directory structures autonomously under controlled conditions.

A typical workflow:

1. Inspect and inventory the existing filesystem.
2. Analyze filenames, metadata, file types and contents where appropriate.
3. Identify duplicates, inconsistencies and organizational opportunities.
4. Propose a target directory structure.
5. Generate a concrete restructuring plan.
6. Validate the plan and identify potential conflicts.
7. Execute approved operations using fs-tool.
8. Verify the resulting filesystem against the original inventory and intended changes.

The agent is responsible for reasoning, planning and deciding what should happen. The CLI is responsible for executing individual operations safely and reporting their results.

## Development Rules

- Python >=3.11, managed with `uv`.
- Use Typer for the CLI.
- Use type hints and clear module boundaries.
- Prefer Python standard-library functionality where practical.
- Follow PEP 8 and use four spaces for indentation.
- Keep line length at approximately 100 characters.
- Write tests for filesystem operations and safety-critical behavior.
- Document CLI commands and their JSON output schemas.
- Do not introduce MCP-specific dependencies into the core application.

## Scope

The initial implementation focuses exclusively on the filesystem CLI.

Agent orchestration, autonomous planning, MCP adapters and advanced LLM integrations are future extensions and must not unnecessarily influence the initial architecture.