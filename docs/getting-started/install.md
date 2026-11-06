# Installation


## 🐍 PyPI

Install the CLI from [PyPI](https://pypi.org/):

```bash
pip install fs-tool
```

The package includes the `docs/` documentation and `res/` sample files under
`share/fs-tool/` in the active Python environment's data directory.

### Run the CLI

```bash
fs-tool [OPTIONS] path/to/file
```

## 👩🏼‍💻 Run from source

### Clone the repository

```bash
git clone
```

### Navigate to the project directory

```bash
cd fs-tool
```

### Install dependencies

```bash
uv sync --all-groups
```

### Run the CLI from source

```bash
uv run fs-tool [OPTIONS] path/to/file
```
