.ONESHELL:
SHELL := /bin/bash
PYTHONIOENCODING := utf-8

.PHONY: help
help:             ## Show the help.
	@echo "Usage: make <target>"
	@echo ""
	@echo "Targets:"
	@fgrep "##" Makefile | fgrep -v fgrep


.PHONY: show
show:             ## Show the current environment.
	@echo "Current environment:"
	uv venv info

.PHONY: install
install:          ## Install the project in dev mode.
	$(MAKE) lock
	uv sync --all-groups

.PHONY: lock
lock:             ## Lock dependencies in uv.lock.
	uv lock

.PHONY: precommit
precommit: check  ## Run formatting, lint, and tests before committing.

.PHONY: fmt
fmt:              ## Format source code and tests.
	uv run ruff format src/ tests/
	uv run ruff check src/ tests/ --fix

.PHONY: lint
lint:             ## Run lint, formatting, and type checks.
	uv run ruff check src/ tests/
	uv run ruff format --check src/ tests/
	uv run mypy src/

.PHONY: test
test:             ## Run tests and generate coverage report.
	uv run pytest -v --cov=fs_tool -l --tb=short --maxfail=1 tests/
	uv run coverage xml

.PHONY: check
check: fmt lint test  ## Run formatting, lint, and the test suite.

.PHONY: build
build:            ## Build the Python sdist and wheel, including docs/ and res/.
	uv build

.PHONY: clean
clean:            ## Clean unused files.
	@find ./ -name '*.pyc' -exec rm -f {} \;
	@find ./ -name '__pycache__' -exec rm -rf {} \;
	@find ./ -name 'Thumbs.db' -exec rm -f {} \;
	@find ./ -name '*~' -exec rm -f {} \;
	@rm -rf .cache
	@rm -rf .pytest_cache
	@rm -rf .mypy_cache
	@rm -rf build
	@rm -rf dist
	@rm -rf site
	@rm -rf *.egg-info
	@rm -rf htmlcov
	@rm -rf .tox/
	@rm -rf docs/_build

.PHONY: virtualenv
virtualenv:       ## Create a virtual environment.
	uv venv

.PHONY: release
release:          ## Check, create, and push a version tag to trigger GitHub release workflows.
	set -euo pipefail
	$(MAKE) check
	if [[ -n "$$(git status --porcelain --untracked-files=no)" ]]; then \
		echo "Commit or discard all working-tree changes before releasing." >&2; \
		exit 1; \
	fi
	CURRENT_TAG=$$(git describe --tags --abbrev=0 2>/dev/null || true)
	if [[ -z "$$CURRENT_TAG" ]]; then \
		NEXT_VERSION="0.1.0"; \
	else \
		CURRENT_VERSION="$${CURRENT_TAG#v}"; \
		if [[ ! "$$CURRENT_VERSION" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$$ ]]; then \
			echo "Latest tag '$$CURRENT_TAG' is not a semantic X.Y.Z version." >&2; \
			exit 1; \
		fi; \
		IFS=. read -r MAJOR MINOR PATCH <<< "$$CURRENT_VERSION"; \
		NEXT_VERSION="$$MAJOR.$$MINOR.$$((PATCH + 1))"; \
	fi
	read -e -i "$$NEXT_VERSION" -p "New release version [$$NEXT_VERSION]: " NEW_VERSION
	NEW_VERSION="$${NEW_VERSION:-$$NEXT_VERSION}"
	NEW_VERSION="$${NEW_VERSION#v}"
	if [[ ! "$$NEW_VERSION" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$$ ]]; then \
		echo "Release version must use semantic X.Y.Z format." >&2; \
		exit 1; \
	fi
	if git rev-parse -q --verify "refs/tags/$$NEW_VERSION" >/dev/null; then \
		echo "Tag '$$NEW_VERSION' already exists." >&2; \
		exit 1; \
	fi
	git tag "$$NEW_VERSION"
	git push origin HEAD "$$NEW_VERSION"
	echo "Pushed tag $$NEW_VERSION; GitHub Actions will build and publish the release."

.PHONY: syncdocs
syncdocs:         ## Sync the documentation.
	@echo "sync documentation ..."
	@uv run ./scripts/update_readme.py

.PHONY: docs
docs:             ## Build and sync the documentation.
	$(MAKE) syncdocs
	uv run --group docs mkdocs build
