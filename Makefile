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
install: lock     ## Install the project and all dependency groups.
	uv sync --all-groups

.PHONY: lock
lock:             ## Lock dependencies in uv.lock.
	uv lock

.PHONY: fmt
fmt:              ## Format source code and tests (no side effects beyond formatting).
	uv run ruff format src/ tests/
	uv run ruff check src/ tests/ --fix

.PHONY: lint
lint:             ## Run lint and type checks.
	uv run ruff check src/ tests/
	uv run ruff format --check src/ tests/
	uv run mypy src/

.PHONY: test
test:             ## Run the test suite with coverage.
	uv run pytest -v --cov=src -l --tb=short --maxfail=1 tests/
	uv run coverage xml

.PHONY: check
check: fmt lint test  ## Run all quality checks (format, lint, type check, tests).

.PHONY: syncdocs
syncdocs:         ## Sync README.md from docs/index.md.
	@echo "sync documentation ..."
	uv run python ./scripts/update_readme.py

.PHONY: docs
docs: syncdocs    ## Sync documentation and build the mkdocs site.
	@echo "building documentation ..."
	uv run --group docs mkdocs build

.PHONY: build
build:            ## Build sdist and wheel into dist/.
	uv build

.PHONY: clean
clean:            ## Clean unused files and caches.
	@find . -name '*.pyc' -delete
	@find . -name '__pycache__' -prune -exec rm -rf {} +
	@find . -name 'Thumbs.db' -delete
	@find . -name '*~' -delete
	@rm -rf .cache .pytest_cache .mypy_cache build dist *.egg-info htmlcov site .ruff_cache .coverage coverage.xml coverage.html
