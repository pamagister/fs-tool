# Installation

## Requirements

- Python 3.11 or newer.
- [uv](https://docs.astral.sh/uv/) is recommended for development and for isolated CLI installs.

The published package is named **`fs-tool-cli`**; the installed command is **`fs-tool`**.

## 🐍 Install from PyPI

Install the CLI into an isolated environment with `uv`:

```bash
uv tool install fs-tool-cli
```

Alternatively, install it into the active Python environment:

```bash
pip install fs-tool-cli
```

To enable PDF metadata extraction in `fs-tool inspect info --metadata`, install the optional
`metadata` extra:

```bash
uv tool install "fs-tool-cli[metadata]"
# or
pip install "fs-tool-cli[metadata]"
```

The package includes the documentation and the `res/` sample files under `share/fs-tool/` in the
active Python environment's data directory.

### Verify the installation

```bash
fs-tool --version
fs-tool --help
```

### Run the CLI

```bash
fs-tool [OPTIONS] COMMAND [ARGS]
```

See the [command-line interface reference](../usage/cli.md) for all commands and options.

## 👩🏼‍💻 Run from source

### Clone the repository

```bash
git clone https://github.com/pamagister/fs-tool.git
```

### Navigate to the project directory

```bash
cd fs-tool
```

### Install dependencies

```bash
uv sync --all-groups
```

Add the optional metadata dependency when working on PDF metadata support:

```bash
uv sync --all-groups --extra metadata
```

### Run the CLI from source

```bash
uv run fs-tool --help
```

If the console script is not available in the current environment, the module invocation is
equivalent:

```bash
uv run python -m fs_tool --help
```

### Run the checks

```bash
make check
```

See [Contributing](../develop/contributing.md) for the full development workflow.
