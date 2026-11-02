import ast
import sys
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

CLOSEABLE_FACTORIES = frozenset(
    {
        "httpx.Client",
        "httpx.AsyncClient",
        "requests.Session",
        "requests.session",
        "aiohttp.ClientSession",
        "socket.socket",
        "socket.create_connection",
        "sqlite3.connect",
        "psycopg.connect",
        "psycopg2.connect",
        "asyncpg.connect",
        "pymysql.connect",
        "urllib.request.urlopen",
        "subprocess.Popen",
        "tempfile.NamedTemporaryFile",
        "tempfile.TemporaryFile",
        "zipfile.ZipFile",
        "tarfile.open",
        "smtplib.SMTP",
        "smtplib.SMTP_SSL",
        "ftplib.FTP",
        "concurrent.futures.ThreadPoolExecutor",
        "concurrent.futures.ProcessPoolExecutor",
        "open",
    }
)
CLOSING_METHODS = frozenset(
    {
        "close",
        "aclose",
        "shutdown",
        "terminate",
        "kill",
        "quit",
        "communicate",
        "wait",
        "__exit__",
    }
)
FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)
CONTAINERS = (ast.Tuple, ast.List, ast.Set)

type Release = Callable[[ast.AST, str], bool]


class UnclosedResource(NamedTuple):
    path: str
    line_number: int
    name: str
    factory: str


def dotted_name(expression: ast.expr) -> str:
    if isinstance(expression, ast.Name):
        return expression.id

    if isinstance(expression, ast.Attribute):
        return f"{dotted_name(expression.value)}.{expression.attr}"

    return ""


def handed_names(expression: ast.expr | None) -> set[str]:
    if isinstance(expression, ast.Name):
        return {expression.id}

    if isinstance(expression, ast.Await | ast.Starred):
        return handed_names(expression.value)

    names: set[str] = set()

    if isinstance(expression, CONTAINERS):
        for element in expression.elts:
            names |= handed_names(element)

    if isinstance(expression, ast.Dict):
        for value in expression.values:
            names |= handed_names(value)

    return names


def call_arguments(call: ast.Call) -> list[ast.expr]:
    return [*call.args, *(keyword.value for keyword in call.keywords)]


def is_own_method(call: ast.Call, name: str) -> bool:
    function = call.func

    return isinstance(function, ast.Attribute) and (
        dotted_name(function.value) == name
    )


def used_as_context(node: ast.AST, name: str) -> bool:
    if not isinstance(node, ast.With | ast.AsyncWith):
        return False

    for item in node.items:
        context = item.context_expr

        if name in handed_names(context):
            return True

        if isinstance(context, ast.Call) and not is_own_method(context, name):
            for argument in call_arguments(context):
                if name in handed_names(argument):
                    return True

    return False


def refers_to_closing_method(node: ast.AST, name: str) -> bool:
    if not isinstance(node, ast.Attribute) or not isinstance(
        node.ctx, ast.Load
    ):
        return False

    return node.attr in CLOSING_METHODS and dotted_name(node.value) == name


def passed_on(node: ast.AST, name: str) -> bool:
    if not isinstance(node, ast.Call) or is_own_method(node, name):
        return False

    return any(name in handed_names(item) for item in call_arguments(node))


def declared_shared(node: ast.AST, name: str) -> bool:
    return isinstance(node, ast.Global | ast.Nonlocal) and name in node.names


def escapes(node: ast.AST, name: str) -> bool:
    if isinstance(node, ast.Return | ast.Yield | ast.YieldFrom):
        return name in handed_names(node.value)

    if isinstance(node, ast.Assign | ast.AnnAssign):
        return name in handed_names(node.value)

    return False


RELEASES: tuple[Release, ...] = (
    used_as_context,
    refers_to_closing_method,
    passed_on,
    escapes,
    declared_shared,
)


def released(function: ast.AST, name: str) -> bool:
    for node in ast.walk(function):
        for release in RELEASES:
            if release(node, name):
                return True

    return False


def imported_names(tree: ast.Module) -> dict[str, str]:
    names: dict[str, str] = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                local = alias.asname or alias.name
                names[local] = f"{node.module}.{alias.name}"
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names[alias.asname or alias.name] = alias.name

    return names


def assigned_call(node: ast.AST) -> tuple[str, ast.Call] | None:
    if isinstance(node, ast.Assign) and len(node.targets) == 1:
        target = node.targets[0]
    elif isinstance(node, ast.AnnAssign):
        target = node.target
    else:
        return None

    value = node.value

    if isinstance(target, ast.Name) and isinstance(value, ast.Call):
        return target.id, value

    return None


class Factories:
    def __init__(self, imports: dict[str, str]) -> None:
        self._imports: dict[str, str] = imports

    def closeable(self, call: ast.Call) -> str | None:
        written = dotted_name(call.func)
        head, _, rest = written.partition(".")
        resolved = self._imports.get(head, head)

        if rest:
            resolved = f"{resolved}.{rest}"

        return written if resolved in CLOSEABLE_FACTORIES else None


class UnclosedResources:
    def find_in(self, paths: list[str]) -> list[UnclosedResource]:
        found: set[UnclosedResource] = set()

        for path in paths:
            tree = ast.parse(Path(path).read_bytes(), path)
            factories = Factories(imported_names(tree))

            for node in ast.walk(tree):
                if isinstance(node, FUNCTIONS):
                    found.update(self._in_function(path, node, factories))

        return sorted(found)

    def _in_function(
        self, path: str, function: ast.AST, factories: Factories
    ) -> list[UnclosedResource]:
        found: list[UnclosedResource] = []

        for node in ast.walk(function):
            assignment = assigned_call(node)

            if assignment is None:
                continue

            name, call = assignment
            factory = factories.closeable(call)

            if factory is not None and not released(function, name):
                resource = UnclosedResource(path, call.lineno, name, factory)
                found.append(resource)

        return found


source_paths = [line for line in sys.stdin.read().split("\n") if line]

for resource in UnclosedResources().find_in(source_paths):
    location = f"{resource.path}:{resource.line_number}"
    opened = f"{resource.name} = {resource.factory}(...)"
    _ = sys.stdout.write(
        f"{location}: {opened} is never closed, returned or handed on\n"
    )
