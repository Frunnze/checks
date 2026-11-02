import ast
import re
import sys
from pathlib import Path
from typing import NamedTuple

ACTION_VERBS = frozenset(
    {
        "save",
        "store",
        "write",
        "send",
        "publish",
        "deliver",
        "notify",
        "upload",
        "delete",
        "remove",
        "cancel",
        "stop",
        "kill",
        "terminate",
        "revoke",
        "charge",
        "refund",
        "pay",
        "commit",
        "apply",
        "sync",
        "submit",
        "enqueue",
        "release",
    }
)
BOOLEAN = "bool"
WORD_BOUNDARY = re.compile(r"_+|(?<=[a-z0-9])(?=[A-Z])")
SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)

type Function = ast.FunctionDef | ast.AsyncFunctionDef


class MaskedFailure(NamedTuple):
    path: str
    line_number: int
    function: str


def leading_verb(name: str) -> str:
    words = [word.lower() for word in WORD_BOUNDARY.split(name) if word]

    return words[0] if words else ""


def own_nodes(root: ast.AST) -> list[ast.AST]:
    found: list[ast.AST] = []
    pending = list(ast.iter_child_nodes(root))

    while pending:
        node = pending.pop()
        found.append(node)

        if not isinstance(node, SCOPES):
            pending.extend(ast.iter_child_nodes(node))

    return found


def returns_flag(node: ast.AST, *, flag: bool) -> bool:
    if not isinstance(node, ast.Return):
        return False

    value = node.value

    return isinstance(value, ast.Constant) and value.value is flag


def reports_success(function: Function) -> bool:
    returns = function.returns

    if isinstance(returns, ast.Name) and returns.id == BOOLEAN:
        return True

    return any(
        returns_flag(node, flag=False) for node in own_nodes(function)
    )


def performs_action(handler: ast.ExceptHandler) -> bool:
    for node in own_nodes(handler):
        if not isinstance(node, ast.Call):
            continue

        function = node.func
        name = function.attr if isinstance(function, ast.Attribute) else ""
        name = function.id if isinstance(function, ast.Name) else name

        if leading_verb(name.lstrip("_")) in ACTION_VERBS:
            return True

    return False


class FailuresAsSuccess:
    def find_in(self, paths: list[str]) -> list[MaskedFailure]:
        found: list[MaskedFailure] = []

        for path in paths:
            tree = ast.parse(Path(path).read_bytes(), path)

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    found.extend(self._in_function(path, node))

        return sorted(found)

    def _in_function(
        self, path: str, function: Function
    ) -> list[MaskedFailure]:
        is_action = leading_verb(function.name.lstrip("_")) in ACTION_VERBS

        if not is_action or not reports_success(function):
            return []

        found: list[MaskedFailure] = []

        for node in own_nodes(function):
            if not isinstance(node, ast.ExceptHandler):
                continue

            if performs_action(node):
                continue

            for inner in own_nodes(node):
                if returns_flag(inner, flag=True):
                    line = getattr(inner, "lineno", node.lineno)
                    found.append(MaskedFailure(path, line, function.name))

        return found


source_paths = [line for line in sys.stdin.read().split("\n") if line]

for masked in FailuresAsSuccess().find_in(source_paths):
    location = f"{masked.path}:{masked.line_number}"
    problem = f"{masked.function}() answers True from an except"
    effect = "so callers believe the failed action worked - return False"
    _ = sys.stdout.write(f"{location}: {problem}, {effect}\n")
