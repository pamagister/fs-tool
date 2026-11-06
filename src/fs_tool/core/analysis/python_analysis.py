"""Python source analysis via AST (plan.md Phase 6, section 9.1).

Analyzes Python source files using the :mod:`ast` module without
importing or executing them. Identifies modules, functions, classes,
methods, function signatures, class attributes, instance attributes,
and optional docstrings. Size-limited to avoid analyzing very large
files.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Maximum file size for Python source analysis (1 MiB) to avoid
# analyzing excessively large files.
MAX_PYTHON_ANALYSIS_SIZE = 1024 * 1024


@dataclass(frozen=True)
class PythonFunction:
    """A function or method definition found in Python source."""

    name: str
    line: int
    end_line: int | None
    args: list[str]
    returns: str | None
    decorators: list[str]
    docstring: str | None
    is_async: bool


@dataclass(frozen=True)
class PythonAttribute:
    """An attribute (class or instance) found in Python source."""

    name: str
    line: int
    is_class_attribute: bool


@dataclass(frozen=True)
class PythonClass:
    """A class definition found in Python source."""

    name: str
    line: int
    end_line: int | None
    bases: list[str]
    decorators: list[str]
    docstring: str | None
    methods: list[PythonFunction]
    attributes: list[PythonAttribute]


@dataclass(frozen=True)
class PythonModule:
    """The result of analyzing a Python source file."""

    path: str
    docstring: str | None
    imports: list[str]
    functions: list[PythonFunction]
    classes: list[PythonClass]


def _format_decorator(node: ast.expr) -> str:
    """Render a decorator expression as a short string."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_format_decorator(node.value)}.{node.attr}"
    if isinstance(node, ast.Call):
        return _format_decorator(node.func)
    return ""


def _format_import(node: ast.AST) -> str:
    """Render an import statement as a short string."""
    if isinstance(node, ast.Import):
        return ", ".join(alias.name for alias in node.names)
    if isinstance(node, ast.ImportFrom):
        module = node.module or ""
        names = ", ".join(alias.name for alias in node.names)
        return f"from {module} import {names}"
    return ""


def _extract_args(node: ast.arguments) -> list[str]:
    """Extract argument names from a function's arguments node."""
    args: list[str] = []
    for arg in node.posonlyargs:
        args.append(arg.arg)
    for arg in node.args:
        args.append(arg.arg)
    if node.vararg:
        args.append(f"*{node.vararg.arg}")
    for arg in node.kwonlyargs:
        args.append(arg.arg)
    if node.kwarg:
        args.append(f"**{node.kwarg.arg}")
    return args


def _extract_returns(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    """Extract the return annotation as a string, if present."""
    if node.returns is None:
        return None
    try:
        return ast.unparse(node.returns)
    except Exception:  # pragma: no cover - defensive on odd AST nodes
        return None


def _extract_docstring(body: list[ast.stmt], include_docstrings: bool) -> str | None:
    """Return the module/class/function docstring if present and enabled."""
    if not include_docstrings or not body:
        return None
    first = body[0]
    if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
        if isinstance(first.value.value, str):
            return first.value.value
    return None


def _extract_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    include_docstrings: bool,
) -> PythonFunction:
    """Extract a function or method definition from an AST node."""
    return PythonFunction(
        name=node.name,
        line=node.lineno,
        end_line=getattr(node, "end_lineno", None),
        args=_extract_args(node.args),
        returns=_extract_returns(node),
        decorators=[_format_decorator(d) for d in node.decorator_list],
        docstring=_extract_docstring(node.body, include_docstrings),
        is_async=isinstance(node, ast.AsyncFunctionDef),
    )


def _extract_class(
    node: ast.ClassDef,
    include_docstrings: bool,
) -> PythonClass:
    """Extract a class definition from an AST node, including methods
    and class-level attributes."""
    methods: list[PythonFunction] = []
    attributes: list[PythonAttribute] = []

    for item in node.body:
        if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
            methods.append(_extract_function(item, include_docstrings))
        elif isinstance(item, ast.AnnAssign) and item.target is not None:
            if isinstance(item.target, ast.Name):
                attributes.append(
                    PythonAttribute(
                        name=item.target.id,
                        line=item.lineno,
                        is_class_attribute=True,
                    )
                )
        elif isinstance(item, ast.Assign):
            for target in item.targets:
                if isinstance(target, ast.Name):
                    attributes.append(
                        PythonAttribute(
                            name=target.id,
                            line=item.lineno,
                            is_class_attribute=True,
                        )
                    )

    bases = [ast.unparse(base) for base in node.bases]

    return PythonClass(
        name=node.name,
        line=node.lineno,
        end_line=getattr(node, "end_lineno", None),
        bases=bases,
        decorators=[_format_decorator(d) for d in node.decorator_list],
        docstring=_extract_docstring(node.body, include_docstrings),
        methods=methods,
        attributes=attributes,
    )


def analyze_python_file(
    path: Path,
    *,
    include_docstrings: bool = True,
) -> PythonModule | None:
    """Analyze a Python source file using the AST.

    Returns a :class:`PythonModule` or ``None`` if the file is not a
    Python file, is too large, cannot be read, or fails to parse.

    The file is never imported or executed: only its source text is
    parsed by :func:`ast.parse`.
    """
    if path.suffix.lower() != ".py":
        return None
    try:
        size = path.stat().st_size
    except OSError:
        return None
    if size > MAX_PYTHON_ANALYSIS_SIZE:
        return None
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return None

    imports: list[str] = []
    functions: list[PythonFunction] = []
    classes: list[PythonClass] = []

    docstring = _extract_docstring(tree.body, include_docstrings)

    for node in tree.body:
        if isinstance(node, ast.Import | ast.ImportFrom):
            imports.append(_format_import(node))
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            functions.append(_extract_function(node, include_docstrings))
        elif isinstance(node, ast.ClassDef):
            classes.append(_extract_class(node, include_docstrings))

    return PythonModule(
        path=str(path),
        docstring=docstring,
        imports=imports,
        functions=functions,
        classes=classes,
    )


def module_to_dict(module: PythonModule) -> dict[str, Any]:
    """Convert a :class:`PythonModule` to a JSON-serializable dict."""
    return {
        "path": module.path,
        "docstring": module.docstring,
        "imports": module.imports,
        "functions": [
            {
                "name": f.name,
                "line": f.line,
                "end_line": f.end_line,
                "args": f.args,
                "returns": f.returns,
                "decorators": f.decorators,
                "docstring": f.docstring,
                "is_async": f.is_async,
            }
            for f in module.functions
        ],
        "classes": [
            {
                "name": c.name,
                "line": c.line,
                "end_line": c.end_line,
                "bases": c.bases,
                "decorators": c.decorators,
                "docstring": c.docstring,
                "methods": [
                    {
                        "name": m.name,
                        "line": m.line,
                        "end_line": m.end_line,
                        "args": m.args,
                        "returns": m.returns,
                        "decorators": m.decorators,
                        "docstring": m.docstring,
                        "is_async": m.is_async,
                    }
                    for m in c.methods
                ],
                "attributes": [
                    {
                        "name": a.name,
                        "line": a.line,
                        "is_class_attribute": a.is_class_attribute,
                    }
                    for a in c.attributes
                ],
            }
            for c in module.classes
        ],
    }
