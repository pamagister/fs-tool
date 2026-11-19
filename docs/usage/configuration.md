# Configuration

fs-tool reads configuration from a single TOML file. Without command-line roots, the
configuration is authoritative for read access and may include roots outside the home and CWD
directories. Command-line roots take precedence and replace the configured roots.

## Configuration file location

By default, fs-tool reads a platform-specific file:

| Platform | Default path |
|---|---|
| Linux | `$XDG_CONFIG_HOME/fs-tool/config.toml` or `~/.config/fs-tool/config.toml` |
| macOS | `~/Library/Application Support/fs-tool/config.toml` |
| Windows | `%APPDATA%\fs-tool\config.toml` |

Pass `--config PATH` to use a different file:

```bash
fs-tool --config ./fs-tool.toml inspect tree ~/Documents
```

Run `fs-tool --show-config` to print the resolved configuration, including the file that was
loaded and the effective read/write roots.

A missing configuration file is not an error: the built-in defaults apply. Project-local
configuration files are never loaded automatically.

## Format

The file uses a single `[fs-tool]` table:

```toml
[fs-tool]
allowed_roots = ["/home/user/projects", "/mnt/nas/documents"]
write_roots = ["/home/user/sorted"]
allow_manipulate_originals = false
```

| Key | Type | Description |
|---|---|---|
| `allowed_roots` | array of strings | Filesystem roots that fs-tool may read. |
| `write_roots` | array of strings | Roots that may receive new writes. Must be within `allowed_roots`. Defaults to `allowed_roots`. |
| `allow_manipulate_originals` | boolean | Allow destructive operations outside `write_roots`. Default: `false`. |

Unknown keys in the `[fs-tool]` table are rejected with an invalid-argument error.

## Allowed roots and precedence

The effective read roots are resolved in this order:

1. `--allow-root` values, if supplied. They replace the configured roots.
2. `allowed_roots` from the configuration file, when no `--allow-root` is given.
3. The default roots (home directory and current working directory) otherwise.

`write_roots` defaults to the effective `allowed_roots` and must be a subset of them. A
configuration that names a write root outside the allowed roots is rejected.

## Originals protection

Destructive operations (`write move`, `write rmdir`, and `write apply` with `move` or `rmdir`)
outside `write_roots` are refused with exit code 3 unless
`allow_manipulate_originals = true` is set in the configuration file. `--yes` does not override
this policy. Non-destructive writes such as `write copy` and `write mkdir` may target
`write_roots` without the flag. See [Safety model](safety.md).

## Examples

Limit access to a project directory and protect originals outside the sorted output:

```toml
[fs-tool]
allowed_roots = ["/home/user/projects/fs-tool"]
write_roots = ["/home/user/projects/fs-tool/sorted"]
allow_manipulate_originals = false
```

Use a dedicated configuration file in a script:

```bash
fs-tool --config /etc/fs-tool/ci.toml inspect inventory "$PWD" --hash
```

Override configured roots explicitly for one invocation:

```bash
fs-tool --allow-root /mnt/nas --config ./fs-tool.toml inspect tree /mnt/nas
```

Inspect the effective configuration:

```bash
fs-tool --show-config
```

## Validation and errors

- Invalid TOML or an unreadable file is reported as an invalid-argument error (exit code 2).
- `fs-tool.allowed_roots` must be an array of strings.
- Paths are normalized before comparison. Both the normalized path and the symlink-resolved path
  must lie inside an allowed root.
- If the configuration resolves to an empty set of roots, every path is denied.

See [Safety model](safety.md) for the access rules that apply to reads and writes.
