# How to develop on this project

fs-tool welcomes contributions from the community.

These instructions are basically for linux base systems. (Linux, MacOS, BSD, etc.)


## Setting up your own fork of this repo.

- On github interface click on `Fork` button.
- Clone your fork of this repo. `git clone git@github.com:YOUR_GIT_USERNAME/fs-tool.git`
- Enter the directory `cd fs-tool`
- Add upstream repo `git remote add upstream https://github.com/pamagister/fs-tool`

## Setting up your own virtual environment

Run `make virtualenv` to create a virtual environment.
then activate it with `source .venv/bin/activate`.

## Install the project in develop mode

Run `make install` to install the project in develop mode.

## Run the tests to ensure everything is working

Run `make test` to run the tests.

## Create a new branch to work on your contribution

Run `git checkout -b my_contribution`

## Make your changes

Edit the files using your preferred editor. (we recommend PyCharm)

## Format the code

Run `make fmt` to format the code.

## Run the linter

Run `make lint` to run the linter.

## Test your changes

Run `make test` to run the tests.

Review the coverage report and add tests for relevant uncovered behavior.

## Build the docs locally

Run `make docs` to build the docs.

Ensure your new changes are documented.

## Commit your changes

This project uses [conventional git commit messages](https://www.conventionalcommits.org/en/v1.0.0/).

Example: `fix(package): update setup.py arguments 🎉` (emojis are fine too)

## Push your changes to your fork

Run `git push origin my_contribution`

## Submit a pull request

On github interface, click on `Pull Request` button.

Wait CI to run and one of the developers will review your PR.
## Makefile utilities

This project comes with a `Makefile` that contains a number of useful utility.

```bash 
❯ make
Usage: make <target>
Targets:
help:             ## Show the help.
install:          ## Install the project and all dependency groups.
fmt:              ## Format source code and tests.
lint:             ## Run lint, formatting, and type checks.
test:             ## Run tests and generate coverage report.
check:            ## Run formatting, lint, and the test suite.
build:            ## Build the Python sdist and wheel, including docs/ and res/.
release:          ## Check, create, and push a version tag to trigger GitHub release workflows.
docs:             ## Build and sync the documentation.
```

## Making a new release

This project uses [semantic versioning](https://semver.org/) and tags releases with `X.Y.Z`.
The package version is derived from the Git tag. Running `make release` locally runs the checks,
suggests the next patch version, creates the tag, and pushes it. GitHub Actions then builds the
Python distributions, creates the GitHub release, and publishes to PyPI.

PyPI publishing requires a repository secret named `PYPI_API_TOKEN`, generated on
[pypi.org](https://pypi.org/account/).

To trigger a new release all you need to do is.

1. Commit all intended changes and ensure the worktree is clean.
2. Verify your Git author identity with `git config user.name` and `git config user.email`.
3. Run `make release` and confirm or edit the suggested version when prompted.

`make release` does not modify or commit project files. It refuses to release with uncommitted
changes or an invalid/already existing version tag.

### Troubleshooting

#### 🧩 Git Push Authentication Error

If you encounter the following error during `make release` or when pushing manually:

```bash
remote: Invalid username or token. Password authentication is not supported for Git operations.
fatal: Authentication failed for '[https://github.com/](https://github.com/)<user>/<repo>.git/'
```

GitHub no longer supports password-based authentication over HTTPS.  
To fix this, you need to use a **Personal Access Token (PAT)** instead of your password.

**Steps to resolve:**

1. Go to [GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)](https://github.com/settings/tokens).
2. Click **Generate new token (classic)** and select the following scopes:
   - `repo`
   - `workflow` (optional, for triggering GitHub Actions)
3. Copy the generated token — you’ll only see it once.
4. Update your Git remote to include your GitHub username:
   ```bash
   git remote set-url origin https://<YOUR_GITHUB_USERNAME>@github.com/<YOUR_GITHUB_USERNAME>/<YOUR_REPOSITORY>.git
   ```

5. The next time you push, Git will prompt for your password — **paste the token** instead.
6. (Optional) To store credentials for future pushes:

   ```bash
   git config --global credential.helper store
   ```

After this setup, `make release` and manual pushes will work without further authentication errors.
