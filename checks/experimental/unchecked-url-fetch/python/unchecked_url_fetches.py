import ast
import re
import sys
from pathlib import Path
from typing import NamedTuple

ROUTE_METHODS = frozenset(
    {"get", "post", "put", "patch", "delete", "route", "api_route"}
)
CLIENT_MODULES = frozenset({"requests", "httpx", "aiohttp", "urllib"})
FETCH_METHODS = frozenset(
    {"get", "post", "put", "patch", "delete", "head", "request", "stream"}
)
URL_OPENERS = frozenset({"urlopen"})
CHECK_WORDS = frozenset(
    {"valid", "validate", "allowed", "allowlist", "safe", "public", "ssrf"}
)
WORD_BOUNDARY = re.compile(r"_+|(?<=[a-z0-9])(?=[A-Z])")

type Function = ast.FunctionDef | ast.AsyncFunctionDef


class UncheckedFetch(NamedTuple):
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


def is_route_handler(function: Function) -> bool:
    for decorator in function.decorator_list:
        method = decorator.func if isinstance(decorator, ast.Call) else None

        if isinstance(method, ast.Attribute) and method.attr in ROUTE_METHODS:
            return True

    return False


def parameter_names(function: Function) -> set[str]:
    arguments = function.args
    everyone = [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs]

    return {argument.arg for argument in everyone}


def is_client_call(expression: ast.expr | None) -> bool:
    if not isinstance(expression, ast.Call):
        return False

    return dotted_name(expression.func).partition(".")[0] in CLIENT_MODULES


def client_names(function: Function) -> set[str]:
    names: set[str] = set(CLIENT_MODULES)

    for node in ast.walk(function):
        if isinstance(node, ast.Assign) and is_client_call(node.value):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.withitem):
            alias = node.optional_vars

            if is_client_call(node.context_expr) and isinstance(
                alias, ast.Name
            ):
                names.add(alias.id)

    return names


def is_outgoing_fetch(call: ast.Call, clients: set[str]) -> bool:
    callee = dotted_name(call.func)
    owner = callee.partition(".")[0]
    method = callee.rpartition(".")[2]

    if method in URL_OPENERS:
        return True

    return owner in clients and method in FETCH_METHODS


def fetched_url(call: ast.Call) -> ast.expr | None:
    for keyword in call.keywords:
        if keyword.arg == "url":
            return keyword.value

    is_generic = dotted_name(call.func).endswith(".request")
    position = 1 if is_generic else 0

    return call.args[position] if len(call.args) > position else None


def checks_url(function: Function) -> bool:
    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue

        name = dotted_name(node.func).rpartition(".")[2]
        words = {word.lower() for word in WORD_BOUNDARY.split(name) if word}

        if words & CHECK_WORDS:
            return True

    return False


class UncheckedUrlFetches:
    def find_in(self, paths: list[str]) -> list[UncheckedFetch]:
        found: list[UncheckedFetch] = []

        for path in paths:
            tree = ast.parse(Path(path).read_bytes(), path)

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    found.extend(self._in_handler(path, node))

        return sorted(found)

    def _in_handler(
        self, path: str, function: Function
    ) -> list[UncheckedFetch]:
        if not is_route_handler(function) or checks_url(function):
            return []

        parameters = parameter_names(function)
        clients = client_names(function)
        found: list[UncheckedFetch] = []

        for node in ast.walk(function):
            if not isinstance(node, ast.Call):
                continue

            if not is_outgoing_fetch(node, clients):
                continue

            url = fetched_url(node)

            if isinstance(url, ast.Name) and url.id in parameters:
                found.append(
                    UncheckedFetch(path, node.lineno, url.id, function.name)
                )

        return found


source_paths = [line for line in sys.stdin.read().split("\n") if line]

for fetch in UncheckedUrlFetches().find_in(source_paths):
    location = f"{fetch.path}:{fetch.line_number}"
    problem = f"{fetch.handler}() fetches the request value {fetch.parameter}"
    advice = "as a URL unchecked, so callers reach internal hosts"
    _ = sys.stdout.write(f"{location}: {problem} {advice}\n")
