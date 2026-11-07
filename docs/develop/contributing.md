# How to develop on this project

fs-tool welcomes contributions from the community. The instructions below target Linux, macOS and
BSD; the Python code itself also runs on Windows.

## Set up your own fork

- Click **Fork** on the GitHub interface.
- Clone your fork: `git clone git@github.com:YOUR_GIT_USERNAME/fs-tool.git`
- Enter the directory: `cd fs-tool`
- Add the upstream repository: `git remote add upstream https://github.com/pamagister/fs-tool`

## Set up the environment

The project uses [uv](https://docs.astral.sh/uv/) for dependency management.

```bash
make install
```

`make install` locks dependencies and runs `uv sync --all-groups`, which installs the package in
development mode together with the `dev` and `docs` dependency groups. Activate the environment
only if you want to run tools directly:

```bash
source .venv/bin/activate
```

See [Set up a virtual environment](../getting-started/virtual-environment.md) for platform-specific
activation commands.

## Run the checks

```bash
make test    # pytest with coverage
make fmt     # ruff format and ruff check --fix
make lint    # ruff check, format check, mypy
make check   # fmt, lint and test
```

Run the relevant check before opening a pull request. Tests must be deterministic. Add or update
tests for behavior changes, bug fixes and important edge cases; mock external dependencies only
when necessary and never weaken a test just to make it pass.

## Create a branch

```bash
git checkout -b my_contribution
```

## Make your changes

Edit the files with your preferred editor. Keep changes focused and follow the conventions below.

## Naming conventions

Use underscores and `snake_case` inside Python code:

- Importable package directories: `src/fs_tool`.
- Module filenames: `python_analysis.py`, `verification.py`.
- Variables, functions and methods: `calculate_total()`, `allowed_roots`.

Use hyphens and `kebab-case` outside Python code:

- PyPI project name: `fs-tool-cli`.
- Repository and root folder: `fs-tool`.
- CLI command names: `fs-tool`, `inspect`, `write`.
- Documentation folders and Markdown files: `getting-started/install.md`.

| Context | Convention | Example |
|---|---|---|
| Internal Python name | underscores | `fs_tool` |
| PyPI / project name | hyphens | `fs-tool-cli` |
| Module filename | underscores | `python_analysis.py` |
| Repository / root folder | hyphens | `fs-tool/` |
| Docs folders and files | hyphens | `getting-started/install.md` |
| CLI commands | hyphens | `fs-tool` |

## Format the code

```bash
make fmt
```

## Run the linter and type checker

```bash
make lint
```

This runs `ruff check`, `ruff format --check` and `mypy` in strict mode.

## Test your changes

```bash
make test
```

Review the coverage report and add tests for relevant uncovered behavior.

## Documentation

Documentation lives in `docs/` and is built with MkDocs. Use `make docs` to sync and build it
locally.

`README.md` is generated from `docs/index.md` and must never be edited directly. Change
`docs/index.md` and run:

```bash
make syncdocs
```

The script updates relative links so that they point to the `docs/` paths used in the repository
README.

Update the relevant page when behavior, commands, options or configuration change. Add navigation
entries in the nearest `.nav.yml` file when creating a new page.

## Commit your changes

This project uses [conventional commit messages](https://www.conventionalcommits.org/en/v1.0.0/).

Example: `fix(package): update setup.py arguments`

## Push and open a pull request

```bash
git push origin my_contribution
```

On GitHub, open a pull request. Wait for CI to run; a developer will review the changes.

## Makefile utilities

```text
make help         Show available targets.
make install      Lock dependencies and install all dependency groups.
make fmt          Format source code and tests.
make lint         Run lint, formatting and type checks.
make test         Run tests and generate a coverage report.
make check        Run formatting, lint and the test suite.
make build        Build the sdist and wheel, including docs/ and res/.
make syncdocs     Regenerate README.md from docs/index.md.
make docs         Sync and build the documentation.
make release      Check, create and push a version tag.
```

## Making a new release

This project uses [semantic versioning](https://semver.org/) and tags releases with `X.Y.Z`. The
package version is derived from the Git tag. `make release` runs the checks, suggests the next patch
version, creates the tag and pushes it. GitHub Actions then builds the distributions, creates the
GitHub release and publishes to PyPI.

PyPI publishing requires a repository secret named `PYPI_API_TOKEN`, generated on
[pypi.org](https://pypi.org/account/).

To trigger a release:

1. Commit all intended changes and ensure the worktree is clean.
2. Verify your Git identity with `git config user.name` and `git config user.email`.
3. Run `make release` and confirm or edit the suggested version.

`make release` does not modify or commit project files. It refuses to release with uncommitted
changes or an invalid or already existing version tag.

### Troubleshooting: Git push authentication

If a push fails with:

```text
remote: Invalid username or token. Password authentication is not supported for Git operations.
fatal: Authentication failed for 'https://github.com/<user>/<repo>.git/'
```

GitHub no longer supports password authentication over HTTPS. Use a personal access token (PAT):

1. Open [GitHub → Settings → Developer settings → Personal access tokens](https://github.com/settings/tokens).
2. Generate a token with the `repo` scope, plus `workflow` if you need to trigger GitHub Actions.
3. Copy the token; it is shown only once.
4. Include your username in the remote URL:
   ```bash
   git remote set-url origin https://<YOUR_GITHUB_USERNAME>@github.com/<YOUR_GITHUB_USERNAME>/fs-tool.git
   ```
5. Paste the token when Git prompts for a password.
6. Optionally store credentials:
   ```bash
   git config --global credential.helper store
   ```
