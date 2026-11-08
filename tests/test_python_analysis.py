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


def argv_analyze(source: Path, *extra: str) -> list[str]:
    return ["--allow-root", str(source.parent), "inspect", "analyze", str(source), *extra]


def analyze_json(source: Path, *extra: str) -> tuple[int, dict]:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = main(argv_analyze(source, *extra))
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


def test_analyze_instance_attributes(tmp_path: Path) -> None:
    """Instance attributes assigned to self are captured."""
    path = write_py(
        tmp_path,
        "instance.py",
        """\
class Counter:
    total: int = 0

    def __init__(self, start: int) -> None:
        self.value = start
        self.items: list[int] = []

    def reset(self) -> None:
        self.value = 0
""",
    )

    result = analyze_python_file(path)
    assert result is not None
    cls = result.classes[0]
    class_attributes = [a for a in cls.attributes if a.is_class_attribute]
    instance_attributes = [a for a in cls.attributes if not a.is_class_attribute]
    assert [a.name for a in class_attributes] == ["total"]
    assert sorted(a.name for a in instance_attributes) == ["items", "value", "value"]
    assert all(a.line > 0 for a in instance_attributes)


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


def test_cli_analyze_on_python_file(tmp_path: Path) -> None:
    """``inspect analyze`` includes Python AST analysis."""
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

    code, data = analyze_json(path)
    assert code == EXIT_SUCCESS
    assert data["success"] is True
    analyses = data["result"]["analyses"]
    assert [item["capability"] for item in analyses] == ["python_ast"]
    analysis = analyses[0]
    assert analysis["status"] == "available"
    py = analysis["data"]
    assert py["docstring"] == "Module docstring."
    assert len(py["functions"]) == 1
    assert py["functions"][0]["name"] == "add"
    assert py["functions"][0]["docstring"] == "Add two numbers."
    assert py["functions"][0]["returns"] == "int"


def test_cli_info_does_not_report_python_analysis(tmp_path: Path) -> None:
    """Python AST output belongs to ``analyze``, not ``info``."""
    path = write_py(tmp_path, "example.py", "def add(a, b):\n    return a + b\n")

    code, data = info_json(path, "--metadata")
    assert code == EXIT_SUCCESS
    assert data["result"]["metadata"] is None
    assert data["result"]["metadata_result"] is None


def test_cli_analyze_on_non_python_file(tmp_path: Path) -> None:
    """Text structure analysis does not include Python AST output."""
    path = tmp_path / "notes.txt"
    path.write_text("hello\n")

    code, data = analyze_json(path)
    assert code == EXIT_SUCCESS
    analyses = data["result"]["analyses"]
    assert [item["capability"] for item in analyses] == ["text_structure"]
    assert "python_ast" not in {item["capability"] for item in analyses}


def test_cli_analyze_plain_output_python(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Plain output shows Python analysis results."""
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
            "analyze",
            str(path),
        ]
    )
    assert code == EXIT_SUCCESS
    output = capsys.readouterr().out
    assert "python_ast [available]" in output
    assert "def add(a, b) -> int at line 1" in output


# -------------------------------------------------------------------
# Size limit constant
# -------------------------------------------------------------------


def test_size_limit_is_positive() -> None:
    """The size limit constant is a positive integer."""
    assert MAX_PYTHON_ANALYSIS_SIZE > 0


def test_analyze_relative_imports(tmp_path: Path) -> None:
    """Relative imports keep their leading dots."""
    path = write_py(
        tmp_path,
        "relative.py",
        """\
from . import sibling
from ..package import thing
from .module import value
""",
    )

    result = analyze_python_file(path)
    assert result is not None
    assert result.imports == [
        "from . import sibling",
        "from ..package import thing",
        "from .module import value",
    ]


def test_analyze_instance_attributes_ignore_nested_scopes(tmp_path: Path) -> None:
    """Attributes assigned to another scope's ``self`` are not captured."""
    path = write_py(
        tmp_path,
        "nested_scope.py",
        """\
class Outer:
    def method(self):
        self.outer = 1

        def inner():
            self.inner = 2

        class Nested:
            def method(self):
                self.nested = 3
""",
    )

    result = analyze_python_file(path)
    assert result is not None
    cls = result.classes[0]
    instance_attributes = [a for a in cls.attributes if not a.is_class_attribute]
    assert [a.name for a in instance_attributes] == ["outer"]


def test_analyze_instance_attributes_from_tuple_targets(tmp_path: Path) -> None:
    """Tuple and starred assignment targets are captured."""
    path = write_py(
        tmp_path,
        "tuple_targets.py",
        """\
class Multi:
    def __init__(self):
        self.a, self.b = 1, 2
        self.c, *self.rest = [1, 2, 3]
""",
    )

    result = analyze_python_file(path)
    assert result is not None
    cls = result.classes[0]
    names = sorted(a.name for a in cls.attributes if not a.is_class_attribute)
    assert names == ["a", "b", "c", "rest"]
