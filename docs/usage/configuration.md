# Configuration

fs-tool reads configuration from a single TOML file. The configuration can restrict which
filesystem roots are accessible; it cannot grant access that the command line does not allow.

## Configuration file location

By default, fs-tool reads:

```text
$XDG_CONFIG_HOME/fs-tool/config.toml
```

When `XDG_CONFIG_HOME` is unset, the path is `~/.config/fs-tool/config.toml`.

Pass `--config PATH` to use a different file:

```bash
fs-tool --config ./fs-tool.toml inspect tree ~/Documents
```

A missing configuration file is not an error: the built-in defaults apply. Project-local
configuration files are never loaded automatically.

## Format

The file uses a single `[fs-tool]` table:

```toml
[fs-tool]
allowed_roots = ["/home/user/projects", "/mnt/nas/documents"]
```

| Key | Type | Description |
|---|---|---|
| `allowed_roots` | array of strings | Filesystem roots that fs-tool may access. |

## Allowed roots and precedence

The effective allowed roots are resolved in this order:

1. `--allow-root` values, if supplied; otherwise the default roots (home directory and current
   working directory).
2. `allowed_roots` from the configuration file, intersected with the roots from step 1.
3. The defaults from step 1 when the configuration file does not set `allowed_roots`.

The configuration can therefore only narrow access. A configured root that lies outside the
command-line roots is ignored, so editing a configuration file cannot escalate access beyond
`--allow-root`.

When no command-line roots are given, the configuration is intersected with the default
home-plus-CWD roots. This means a configuration cannot add a root such as `/mnt/nas` on its own:

```toml
# Ignored unless /mnt/nas is also authorized via --allow-root.
[fs-tool]
allowed_roots = ["/mnt/nas", "/home/user/projects"]
```

Access `/mnt/nas` explicitly instead:

```bash
fs-tool --allow-root /mnt/nas inspect tree /mnt/nas
```

## Examples

Limit access to a project directory:

```toml
[fs-tool]
allowed_roots = ["/home/user/projects/fs-tool"]
```

Use a dedicated configuration file in a script:

```bash
fs-tool --config /etc/fs-tool/ci.toml inspect inventory "$PWD" --hash
```

Combine CLI roots with a restricting configuration:

```bash
fs-tool --allow-root /mnt/nas --config ./fs-tool.toml inspect tree /mnt/nas
```

## Validation and errors

- Invalid TOML or an unreadable file is reported as an invalid-argument error (exit code 2).
- `fs-tool.allowed_roots` must be an array of strings.
- Paths are normalized before comparison. Both the normalized path and the symlink-resolved path
  must lie inside an allowed root.
- If the configuration resolves to an empty set of roots, every path is denied.

See [Safety model](safety.md) for the access rules that apply to reads and writes.
