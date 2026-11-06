"""Tests for Python AST analysis (plan.md Phase 6, P6-T01..P6-T04).

Verifies that :func:`fs_tool.core.analysis.python_analysis.analyze_python_file`
correctly extracts modules, functions, classes, methods, signatures,
attributes, and optional docstrings without importing or executing the
source.
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from fs_tool.cli import EXIT_SUCCESS, main
from fs_tool.core.analysis.python_analysis import (
    MAX_PYTHON_ANALYSIS_SIZE,
    analyze_python_file,
    module_to_dict,
)


def write_py(tmp_path: Path, name: str, source: str) -> Path:
    """Write a Python source file and return its path."""
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return path


def argv_info(source: Path, *extra: str) -> list[str]:
    return ["--allow-root", str(source.parent), "inspect", "info", str(source), *extra]


def info_json(source: Path, *extra: str) -> tuple[int, dict]:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = main(argv_info(source, *extra))
    return code, json.loads(buffer.getvalue())


# -------------------------------------------------------------------
# analyze_python_file unit tests
# -------------------------------------------------------------------


def test_analyze_basic_module(tmp_path: Path) -> None:
    """A simple module with imports, functions, and a class."""
    path = write_py(
        tmp_path,
        "basic.py",
        """\
import os
from sys import path


def greet(name: str) -> str:
    'Say hello.'
    return f"Hello, {name}"


class Point:
    x: int = 0
    y: int = 0
""",
    )

    result = analyze_python_file(path)
    assert result is not None
    assert result.path == str(path)
    assert "os" in result.imports
    assert "from sys import path" in result.imports
    assert len(result.functions) == 1
    assert result.functions[0].name == "greet"
    assert result.functions[0].args == ["name"]
    assert result.functions[0].returns == "str"
    assert result.functions[0].docstring == "Say hello."
    assert len(result.classes) == 1
    assert result.classes[0].name == "Point"


def test_analyze_without_docstrings(tmp_path: Path) -> None:
    """Docstrings are omitted when include_docstrings=False."""
    path = write_py(
        tmp_path,
        "nodoc.py",
        """\
def func():
    'This is a docstring.'
    pass
""",
    )

    with_docstrings = analyze_python_file(path, include_docstrings=True)
    assert with_docstrings is not None
    assert with_docstrings.functions[0].docstring == "This is a docstring."

    without_docstrings = analyze_python_file(path, include_docstrings=False)
    assert without_docstrings is not None
    assert without_docstrings.functions[0].docstring is None


def test_analyze_async_functions(tmp_path: Path) -> None:
    """Async functions are flagged correctly."""
    path = write_py(
        tmp_path,
        "async.py",
        """\
async def fetch(url: str) -> bytes:
    pass


def sync() -> None:
    pass
""",
    )

    result = analyze_python_file(path)
    assert result is not None
    assert result.functions[0].is_async is True
    assert result.functions[0].name == "fetch"
    assert result.functions[1].is_async is False
    assert result.functions[1].name == "sync"


def test_analyze_class_with_methods(tmp_path: Path) -> None:
    """Classes contain their methods and attributes."""
    path = write_py(
        tmp_path,
        "methods.py",
        """\
class Calculator:
    'A simple calculator.'

    PI: float = 3.14

    def add(self, a: int, b: int) -> int:
        return a + b

    async def mul_async(self, a: int, b: int) -> int:
        return a * b
""",
    )

    result = analyze_python_file(path)
    assert result is not None
    assert len(result.classes) == 1
    cls = result.classes[0]
    assert cls.name == "Calculator"
    assert cls.docstring == "A simple calculator."
    assert len(cls.methods) == 2
    assert cls.methods[0].name == "add"
    assert cls.methods[0].args == ["self", "a", "b"]
    assert cls.methods[0].returns == "int"
    assert cls.methods[1].name == "mul_async"
    assert cls.methods[1].is_async is True
    assert len(cls.attributes) == 1
    assert cls.attributes[0].name == "PI"
    assert cls.attributes[0].is_class_attribute is True


def test_analyze_decorators(tmp_path: Path) -> None:
    """Decorators are captured on functions and classes."""
    path = write_py(
        tmp_path,
        "deco.py",
        """\
@decorator1
@decorator2(arg)
def my_func(x: int) -> None:
    pass


@dataclass
class MyClass:
    pass
""",
    )

    result = analyze_python_file(path)
    assert result is not None
    assert result.functions[0].decorators == ["decorator1", "decorator2"]
    assert result.classes[0].decorators == ["dataclass"]


def test_analyze_non_python_file_returns_none(tmp_path: Path) -> None:
    """Non-.py files return None."""
    path = write_py(tmp_path, "notes.txt", "hello world\n")
    assert analyze_python_file(path) is None


def test_analyze_syntax_error_returns_none(tmp_path: Path) -> None:
    """Files that fail to parse return None."""
    path = write_py(tmp_path, "broken.py", "def unfinished(\n")
    assert analyze_python_file(path) is None


def test_analyze_empty_file(tmp_path: Path) -> None:
    """An empty Python file produces an empty module."""
    path = write_py(tmp_path, "empty.py", "")
    result = analyze_python_file(path)
    assert result is not None
    assert result.docstring is None
    assert result.imports == []
    assert result.functions == []
    assert result.classes == []


def test_analyze_module_docstring(tmp_path: Path) -> None:
    """Module-level docstring is captured."""
    path = write_py(
        tmp_path,
        "moddoc.py",
        """\
'This is the module docstring.'


def unused() -> None:
    pass
""",
    )

    result = analyze_python_file(path)
    assert result is not None
    assert result.docstring == "This is the module docstring."


def test_analyze_function_signatures(tmp_path: Path) -> None:
    """Function signatures include args, return type, and decorators."""
    path = write_py(
        tmp_path,
        "sigs.py",
        """\
from typing import List


@staticmethod
def process(items: List[str], threshold: int = 0) -> List[str]:
    pass
""",
    )

    result = analyze_python_file(path)
    assert result is not None
    func = result.functions[0]
    assert func.args == ["items", "threshold"]
    assert func.returns == "List[str]"
    assert func.decorators == ["staticmethod"]


def test_analyze_size_limit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Files exceeding the size limit return None."""
    from fs_tool.core.analysis import python_analysis as pa

    path = write_py(tmp_path, "large.py", "x = 1\n")
    monkeypatch.setattr(pa, "MAX_PYTHON_ANALYSIS_SIZE", 0)
    assert analyze_python_file(path) is None


# -------------------------------------------------------------------
# module_to_dict unit tests
# -------------------------------------------------------------------


def test_module_to_dict_is_serializable(tmp_path: Path) -> None:
    """module_to_dict output can be round-tripped through JSON."""
    path = write_py(
        tmp_path,
        "sig.py",
        """\
def foo(a: int) -> str:
    'Doc.'
    return str(a)
""",
    )

    result = analyze_python_file(path)
    assert result is not None
    data = module_to_dict(result)
    json_str = json.dumps(data)
    restored = json.loads(json_str)
    assert restored["functions"][0]["name"] == "foo"
    assert restored["functions"][0]["docstring"] == "Doc."


# -------------------------------------------------------------------
# CLI integration tests
# -------------------------------------------------------------------


def test_cli_info_metadata_on_python_file(tmp_path: Path) -> None:
    """--metadata on a .py file includes Python AST analysis."""
    path = write_py(
        tmp_path,
        "example.py",
        """\
'Module docstring.'


def add(a: int, b: int) -> int:
    'Add two numbers.'
    return a + b
""",
    )

    code, data = info_json(path, "--metadata")
    assert code == EXIT_SUCCESS
    assert data["success"] is True
    metadata = data["result"]["metadata"]
    assert metadata is not None
    assert "python" in metadata
    py = metadata["python"]
    assert py["docstring"] == "Module docstring."
    assert len(py["functions"]) == 1
    assert py["functions"][0]["name"] == "add"
    assert py["functions"][0]["docstring"] == "Add two numbers."
    assert py["functions"][0]["returns"] == "int"


def test_cli_info_metadata_on_non_python_file(tmp_path: Path) -> None:
    """--metadata on a non-.py file does not include python key."""
    path = tmp_path / "notes.txt"
    path.write_text("hello\n")

    code, data = info_json(path, "--metadata")
    assert code == EXIT_SUCCESS
    assert data["result"]["metadata"] is None


def test_cli_info_plain_output_python(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Plain output shows Python analysis metadata."""
    path = write_py(
        tmp_path,
        "example.py",
        """\
def add(a: int, b: int) -> int:
    return a + b
""",
    )

    code = main(
        [
            "--allow-root",
            str(tmp_path),
            "--plain",
            "inspect",
            "info",
            str(path),
            "--metadata",
        ]
    )
    assert code == EXIT_SUCCESS
    output = capsys.readouterr().out
    assert "python analysis:" in output
    assert "def add(a, b) -> int at line 1" in output


# -------------------------------------------------------------------
# Size limit constant
# -------------------------------------------------------------------


def test_size_limit_is_positive() -> None:
    """The size limit constant is a positive integer."""
    assert MAX_PYTHON_ANALYSIS_SIZE > 0
