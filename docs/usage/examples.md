# Examples

Practical workflows using the fs-tool CLI. Commands use `--plain` for readable terminal output and
JSON for scripting.

## Inspect a directory

```bash
fs-tool inspect tree ~/Projects/fs-tool --plain
```

Limit the depth and ignore build artifacts:

```bash
fs-tool inspect tree ~/Projects --max-depth 3 \
  --ignore-dir node_modules --ignore-pattern '*.pyc' --plain
```

Inspect a single file and its format metadata, including its hash:

```bash
fs-tool inspect info ~/Documents/report.pdf --hash
```

Analyze Python source without importing or running it:

```bash
fs-tool inspect analyze src/fs_tool/cli.py --hash --plain
```

Extract the Markdown heading structure for a document:

```bash
fs-tool inspect analyze docs/index.md --plain
```

Report PDF page sizes and orientation:

```bash
fs-tool inspect analyze ~/Documents/report.pdf --plain
```

Read the first 4 KiB of a text file:

```bash
fs-tool inspect read ~/notes/todo.md --max-bytes 4096 --plain
```

Extract text from a PDF:

```bash
fs-tool inspect read ~/Documents/report.pdf --plain
```

## Find files

Find large log files:

```bash
fs-tool find /var/log --type file --extension log --min-size 10M --plain
```

Combine filters; all conditions must match:

```bash
fs-tool find ~/Downloads --type file --name '*.zip' \
  --modified-after 2026-01-01 --max-depth 2 --plain
```

Find recently changed Python files:

```bash
fs-tool find ~/Projects --extension .py --modified-after 2026-10-01 --plain
```

## Inventory and verify

Create a portable inventory with hashes:

```bash
fs-tool inspect inventory ~/Projects/fs-tool --hash --tree-hash > inventory.json
```

Verify the directory later:

```bash
fs-tool verify inventory inventory.json ~/Projects/fs-tool --plain
```

A successful verification exits with code 0. Differences exit with code 1. An incomplete scan exits
with code 5.

Compare two directory trees directly:

```bash
fs-tool compare ~/Projects/fs-tool ~/Backups/fs-tool --plain
```

## Find duplicates

```bash
fs-tool duplicates ~/Pictures --min-size 1M --plain
```

Include empty files:

```bash
fs-tool duplicates ~/Documents --include-empty --plain
```

Extract duplicate paths with `jq`:

```bash
fs-tool duplicates ~/Pictures --json \
  | jq -r '.result.duplicate_groups[].files[]'
```

## Safe write operations

Preview a copy first:

```bash
fs-tool write copy ~/Projects/fs-tool ~/Backups/fs-tool-2026-11-07 --dry-run --plain
```

Review the reported paths, then execute:

```bash
fs-tool write copy ~/Projects/fs-tool ~/Backups/fs-tool-2026-11-07 --yes --plain
```

Create a directory hierarchy:

```bash
fs-tool write mkdir ~/Projects/new-project/src --parents --dry-run
fs-tool write mkdir ~/Projects/new-project/src --parents --yes
```

Rename a file (requires `--allow-rename` because the filename changes):

```bash
fs-tool write move ~/Downloads/report.pdf ~/Downloads/report-2026.pdf --allow-rename --dry-run
fs-tool write move ~/Downloads/report.pdf ~/Downloads/report-2026.pdf --allow-rename --yes
```

Copy a tree that contains symlinks, skipping the links:

```bash
fs-tool write copy ~/Projects/site ~/Backups/site --symlinks skip --dry-run
```

## Agent and scripting workflow

JSON is the default when stdout is not a terminal, so a command can be piped directly:

```bash
fs-tool inspect inventory "$PWD" --hash --tree-hash > inventory.json
fs-tool verify inventory inventory.json "$PWD"
```

Check the envelope instead of relying on exit codes alone:

```bash
fs-tool find ~/Downloads --type file --name '*.tmp' \
  | jq '{success, complete, count: .result.count}'
```

Inspect which analyses ran and which prerequisites are missing:

```bash
fs-tool inspect analyze src/fs_tool/cli.py \
  | jq '{supported, analyses: [.result.analyses[] | {capability, status}]}'
```

Stop on incomplete results in a shell script:

```bash
result=$(fs-tool find ~/data --max-entries 10000)

if [ "$(printf '%s' "$result" | jq -r '.complete')" != "true" ]; then
  echo "Scan was incomplete; narrow the scope or raise --max-entries." >&2
  exit 1
fi

printf '%s' "$result" | jq -r '.result.entries[].rel_path'
```

## Capability discovery and setup

Discover every supported capability and which prerequisites are missing:

```bash
fs-tool capabilities --plain
fs-tool capabilities --json | jq '.result.capabilities[] | {id, available, next_steps}'
```

Check and prepare optional dependencies without changing the Python environment:

```bash
fs-tool setup pdf
fs-tool setup image
```

Download and verify the YOLO object-detection model (explicit setup only; nothing is downloaded
automatically):

```bash
fs-tool setup yolo
```

Prepare every setup target at once; one failing target does not stop the others:

```bash
fs-tool setup --all
```

Replace only an invalid existing model file:

```bash
fs-tool setup yolo --force
```

Use a custom model directory:

```bash
FS_TOOL_MODEL_DIR=/mnt/models/fs-tool fs-tool setup yolo
```

## Working with large trees

Bound traversal to keep runtimes predictable:

```bash
fs-tool inspect tree /mnt/data --max-depth 2 --max-entries 50000 --plain
```

When a bound is hit, the command returns partial results with `complete: false` and exits with
code 5. Increase the limit or narrow the starting path before relying on the result.

## Using another allowed root

By default only home and the current working directory are accessible:

```bash
fs-tool --allow-root /mnt/nas inspect tree /mnt/nas --max-depth 2 --plain
```

The same applies to write destinations:

```bash
fs-tool --allow-root /mnt/nas write copy ~/Projects/site /mnt/nas/site --dry-run
```

See [Safety model](safety.md) for the full access rules.
