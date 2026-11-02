import ast
import sys
from pathlib import Path
from typing import NamedTuple

ROUTE_METHODS = frozenset(
    {"get", "post", "put", "patch", "delete", "route", "api_route"}
)
JOIN_CALLS = frozenset({"os.path.join", "path.join", "join", "joinpath"})
FILE_CALLS = frozenset(
    {
        "open",
        "read_text",
        "read_bytes",
        "write_text",
        "write_bytes",
        "unlink",
        "rmtree",
        "remove",
        "FileResponse",
        "send_file",
        "send_from_directory",
    }
)
CONTAINMENT_CALLS = frozenset(
    {
        "is_relative_to",
        "relative_to",
        "commonpath",
        "realpath",
        "abspath",
        "resolve",
        "basename",
        "secure_filename",
        "safe_join",
    }
)
SAFE_PARTS = frozenset({"name", "stem"})

type Function = ast.FunctionDef | ast.AsyncFunctionDef


class UncontainedPath(NamedTuple):
    path: str
    line_number: int
    parameter: str
    handler: str


def dotted_name(expression: ast.expr) -> str:
    if isinstance(expression, ast.Name):
        return expression.id

    if isinstance(expression, ast.Attribute):
        owner = dotted_name(expression.value)
        return f"{owner}.{expression.attr}" if owner else expression.attr

    return ""


def last_name(expression: ast.expr) -> str:
    return dotted_name(expression).rpartition(".")[2]


def is_route_handler(function: Function) -> bool:
    for decorator in function.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue

        method = decorator.func
        is_route = isinstance(method, ast.Attribute) and (
            method.attr in ROUTE_METHODS
        )

        if is_route:
            return True

    return False


def parameter_names(function: Function) -> set[str]:
    arguments = function.args
    everyone = [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs]

    return {argument.arg for argument in everyone}


def joined_parameter(node: ast.AST, parameters: set[str]) -> str | None:
    parts: list[ast.expr] = []

    if isinstance(node, ast.Call) and dotted_name(node.func) in JOIN_CALLS:
        parts = node.args[1:]
    elif isinstance(node, ast.Call) and last_name(node.func) in JOIN_CALLS:
        parts = node.args
    elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        parts = [node.right]

    for part in parts:
        if isinstance(part, ast.Name) and part.id in parameters:
            return part.id

    return None


def contains_path(function: Function) -> bool:
    for node in ast.walk(function):
        is_call = isinstance(node, ast.Call)

        if is_call and last_name(node.func) in CONTAINMENT_CALLS:
            return True

        if isinstance(node, ast.Attribute) and node.attr in SAFE_PARTS:
            return True

    return False


def touches_files(function: Function) -> bool:
    for node in ast.walk(function):
        if isinstance(node, ast.Call) and last_name(node.func) in FILE_CALLS:
            return True

    return False


class PathContainments:
    def find_in(self, paths: list[str]) -> list[UncontainedPath]:
        found: list[UncontainedPath] = []

        for path in paths:
            tree = ast.parse(Path(path).read_bytes(), path)

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    found.extend(self._in_handler(path, node))

        return sorted(found)

    def _in_handler(
        self, path: str, function: Function
    ) -> list[UncontainedPath]:
        if not is_route_handler(function) or not touches_files(function):
            return []

        if contains_path(function):
            return []

        parameters = parameter_names(function)
        found: list[UncontainedPath] = []

        for node in ast.walk(function):
            parameter = joined_parameter(node, parameters)

            if parameter is not None:
                line = getattr(node, "lineno", function.lineno)
                found.append(
                    UncontainedPath(path, line, parameter, function.name)
                )

        return found


source_paths = [line for line in sys.stdin.read().split("\n") if line]

for uncontained in PathContainments().find_in(source_paths):
    location = f"{uncontained.path}:{uncontained.line_number}"
    problem = f"{uncontained.handler}() joins the request value"
    detail = f"{uncontained.parameter} onto a folder and opens the result"
    advice = "without checking it stays inside - resolve it and test"
    _ = sys.stdout.write(
        f"{location}: {problem} {detail} {advice} is_relative_to()\n"
    )
