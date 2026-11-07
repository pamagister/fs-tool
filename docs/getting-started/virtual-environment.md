# Set up a virtual environment

The project uses [uv](https://docs.astral.sh/uv/) for dependency management. `uv sync` creates the
project virtual environment automatically, so manual activation is optional.

## Create the environment

```bash
uv venv
```

By default the environment is created in `.venv` in the project directory.

## Install the project and dependencies

```bash
uv sync --all-groups
```

This installs the package in development mode together with the `dev` and `docs` dependency groups.
Use `uv sync --all-groups --extra metadata` to include the optional PDF metadata dependency.

## Activate the environment

> Note: Replace `.venv` with your environment folder name if you have chosen a different one.

🔹 Windows (PowerShell)

```powershell
.venv\Scripts\Activate.ps1
```

🔹 Windows (CMD)

```cmd
.venv\Scripts\activate.bat
```

🔹 Linux / macOS (Bash/Zsh)

```bash
source .venv/bin/activate
```

## Run commands without activating

`uv run` executes a command inside the project environment without requiring activation:

```bash
uv run fs-tool --help
uv run pytest
uv run ruff check src/ tests/
```

## Deactivate the environment

```bash
deactivate
```

## Troubleshooting

- If `uv run fs-tool` reports that the executable cannot be spawned, run
  `uv run python -m fs_tool` instead or reinstall the project with `uv sync --all-groups`.
- If dependencies are stale after changing `pyproject.toml`, run `uv lock` followed by
  `uv sync --all-groups`.
