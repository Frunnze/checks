import ast
import sys
from pathlib import Path
from typing import NamedTuple

CACHING_DECORATORS = frozenset({"cache", "lru_cache", "cached", "memoize"})
REQUEST_NAMES = frozenset(
    {"request", "current_user", "g", "session", "current_tenant"}
)
REQUEST_CALLS = frozenset(
    {"get_current_user", "get_current_tenant", "get_request", "get_user"}
)
WEB_FRAMEWORKS = frozenset(
    {
        "flask",
        "flask_login",
        "quart",
        "starlette",
        "fastapi",
        "django",
        "werkzeug",
        "bottle",
    }
)
CONTEXT_VARIABLE = "ContextVar"
FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)
CONTEXT_READ = "get"

type Function = ast.FunctionDef | ast.AsyncFunctionDef


class CachedUserData(NamedTuple):
    path: str
    line_number: int
    function: str
    source: str


def last_name(expression: ast.expr) -> str:
    if isinstance(expression, ast.Call):
        return last_name(expression.func)

    if isinstance(expression, ast.Name):
        return expression.id

    if isinstance(expression, ast.Attribute):
        return expression.attr

    return ""


def is_cached(function: Function) -> bool:
    return any(
        last_name(decorator) in CACHING_DECORATORS
        for decorator in function.decorator_list
    )


def assignment_targets(statement: ast.stmt) -> list[ast.expr]:
    if isinstance(statement, ast.Assign):
        return statement.targets

    if isinstance(statement, ast.AnnAssign):
        return [statement.target]

    return []


def context_variables(tree: ast.Module) -> set[str]:
    names: set[str] = set()

    for statement in tree.body:
        value = statement.value if isinstance(statement, ast.Assign) else None

        if isinstance(statement, ast.AnnAssign):
            value = statement.value

        if not isinstance(value, ast.Call):
            continue

        if last_name(value.func) != CONTEXT_VARIABLE:
            continue

        for target in assignment_targets(statement):
            if isinstance(target, ast.Name):
                names.add(target.id)

    return names


def framework_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue

        if node.module.partition(".")[0] not in WEB_FRAMEWORKS:
            continue

        for alias in node.names:
            if alias.name in REQUEST_NAMES:
                names.add(alias.asname or alias.name)

    return names


def parameter_names(function: Function) -> set[str]:
    arguments = function.args
    everyone = [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs]

    return {argument.arg for argument in everyone}


def framework_read(
    node: ast.AST, framework: set[str], parameters: set[str]
) -> str | None:
    if not isinstance(node, ast.Name) or not isinstance(node.ctx, ast.Load):
        return None

    if node.id in framework and node.id not in parameters:
        return node.id

    return None


def context_read(node: ast.AST, context: set[str]) -> str | None:
    if not isinstance(node, ast.Call):
        return None

    if last_name(node.func) in REQUEST_CALLS:
        return ast.unparse(node.func)

    function_part = node.func

    if not isinstance(function_part, ast.Attribute):
        return None

    owner = function_part.value
    reads = function_part.attr == CONTEXT_READ

    if reads and isinstance(owner, ast.Name) and owner.id in context:
        return owner.id

    return None


def request_source(
    function: Function, context: set[str], framework: set[str]
) -> str | None:
    parameters = parameter_names(function)

    for node in ast.walk(function):
        source = framework_read(node, framework, parameters)
        source = source or context_read(node, context)

        if source is not None:
            return source

    return None


class CachesAcrossUsers:
    def find_in(self, paths: list[str]) -> list[CachedUserData]:
        found: list[CachedUserData] = []

        for path in paths:
            tree = ast.parse(Path(path).read_bytes(), path)
            context = context_variables(tree)
            framework = framework_names(tree)

            for node in ast.walk(tree):
                if not isinstance(node, FUNCTIONS):
                    continue

                if not is_cached(node):
                    continue

                source = request_source(node, context, framework)

                if source is not None:
                    found.append(
                        CachedUserData(path, node.lineno, node.name, source)
                    )

        return sorted(found)


source_paths = [line for line in sys.stdin.read().split("\n") if line]

for cached in CachesAcrossUsers().find_in(source_paths):
    location = f"{cached.path}:{cached.line_number}"
    problem = f"{cached.function}() is cached by its arguments but reads"
    detail = f"{cached.source}, so one user's answer is served to the next"
    _ = sys.stdout.write(f"{location}: {problem} {detail}\n")
