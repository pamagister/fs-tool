# Command Line Interface

Command line options for fs_tool

```bash
fs-tool [OPTIONS] <input>
```

For development from a source checkout, the equivalent module invocation is:

```bash
python -m fs_tool [OPTIONS] <input>
```

## Options

| Option                | Type | Description                                       | Default    | Choices       |
|-----------------------|------|---------------------------------------------------|------------|---------------|
| --config              | str  | Path to configuration file                        | -          | -             |
| -v, --verbose         | bool | Enable debug logging                              | False      | [True, False] |
| -q, --quiet           | bool | Show warnings and errors only                     | False      | [True, False] |
| `input`               | str  | Path to input (file or folder)                    | *required* | -             |
| `--output`            | str  | Path to output destination                        | *required* | -             |
| `--min_dist`          | int  | Maximum distance between two waypoints            | 25         | -             |
| `--extract_waypoints` | bool | Extract starting points of each track as waypoint | True       | [True, False] |
| `--elevation`         | bool | Include elevation data in waypoints               | True       | [True, False] |


## Examples


### 1. Basic usage

```bash
fs-tool input
```

### 2. With verbose logging

```bash
fs-tool -v input
fs-tool --verbose input
```

### 3. With quiet mode

```bash
fs-tool -q input
fs-tool --quiet input
```

### 4. With output parameter

```bash
fs-tool --output  input
```

### 5. With min_dist parameter

```bash
fs-tool --min_dist 25 input
```

### 6. With extract_waypoints parameter

```bash
fs-tool --extract_waypoints True input
```

### Developer usage

```bash
python -m fs_tool --help
python -m fs_tool input
```

# More parameter

For your specific projects that inherit from the library, 
you can add more parameters to the CLI and config file 
by creating your own ConfigManager subclass 
and adding more ConfigParameter instances. 
The documentation generator will automatically include them 
in the generated documentation.
