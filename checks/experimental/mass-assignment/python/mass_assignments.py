import ast
import sys
from pathlib import Path
from typing import NamedTuple

ITEMS = "items"
SET_ATTRIBUTE = "setattr"
INSTANCE_NAMES = frozenset({"self", "cls"})
FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)

type Function = ast.FunctionDef | ast.AsyncFunctionDef


class MassAssignment(NamedTuple):
    path: str
    line_number: int
    source: str
    target: str


def parameter_names(function: Function) -> set[str]:
    arguments = function.args
    everyone = [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs]

    return {argument.arg for argument in everyone}


def items_source(loop: ast.For) -> str | None:
    source = loop.iter

    if not isinstance(source, ast.Call) or source.args:
        return None

    function = source.func
    is_items = isinstance(function, ast.Attribute) and function.attr == ITEMS

    if is_items and isinstance(function, ast.Attribute):
        owner = function.value
        return owner.id if isinstance(owner, ast.Name) else None

    return None


def key_and_value(loop: ast.For) -> tuple[str, str] | None:
    target = loop.target

    if not isinstance(target, ast.Tuple) or len(target.elts) != len("kv"):
        return None

    key, value = target.elts

    if isinstance(key, ast.Name) and isinstance(value, ast.Name):
        return key.id, value.id

    return None


def uses_name(node: ast.AST, name: str) -> bool:
    for item in ast.walk(node):
        if isinstance(item, ast.Name) and item.id == name:
            return True

    return False


def filters_key(loop: ast.For, key: str) -> bool:
    for node in ast.walk(loop):
        is_test = isinstance(node, ast.If | ast.IfExp | ast.Assert)

        if is_test and uses_name(node.test, key):
            return True

        if isinstance(node, ast.comprehension) and uses_name(node, key):
            return True

    return False


def copied_target(statement: ast.stmt, key: str, value: str) -> str | None:
    if not isinstance(statement, ast.Expr):
        return None

    call = statement.value

    if not isinstance(call, ast.Call) or len(call.args) != len("tkv"):
        return None

    function = call.func

    if not isinstance(function, ast.Name) or function.id != SET_ATTRIBUTE:
        return None

    target, written_key, written_value = call.args
    is_copy = (
        isinstance(written_key, ast.Name)
        and written_key.id == key
        and isinstance(written_value, ast.Name)
        and written_value.id == value
    )

    if not is_copy or not isinstance(target, ast.Name):
        return None

    return None if target.id in INSTANCE_NAMES else target.id


class MassAssignments:
    def find_in(self, paths: list[str]) -> list[MassAssignment]:
        found: list[MassAssignment] = []

        for path in paths:
            tree = ast.parse(Path(path).read_bytes(), path)

            for node in ast.walk(tree):
                if isinstance(node, FUNCTIONS):
                    found.extend(self._in_function(path, node))

        return sorted(found)

    def _in_function(
        self, path: str, function: Function
    ) -> list[MassAssignment]:
        parameters = parameter_names(function)
        found: list[MassAssignment] = []

        for node in ast.walk(function):
            if not isinstance(node, ast.For):
                continue

            source = items_source(node)
            names = key_and_value(node)

            if source is None or source not in parameters or names is None:
                continue

            key, value = names

            if filters_key(node, key):
                continue

            for statement in node.body:
                target = copied_target(statement, key, value)

                if target is not None:
                    found.append(
                        MassAssignment(path, node.lineno, source, target)
                    )

        return found


source_paths = [line for line in sys.stdin.read().split("\n") if line]

for assignment in MassAssignments().find_in(source_paths):
    location = f"{assignment.path}:{assignment.line_number}"
    problem = f"every key of {assignment.source} is set on {assignment.target}"
    advice = "so the caller picks which fields change - allow a fixed set"
    _ = sys.stdout.write(f"{location}: {problem}, {advice}\n")
