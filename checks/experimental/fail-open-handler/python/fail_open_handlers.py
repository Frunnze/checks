import ast
import re
import sys
from pathlib import Path
from typing import NamedTuple

GRANTING_WORDS = frozenset(
    {
        "allowed",
        "allow",
        "authorized",
        "authorised",
        "authorize",
        "permitted",
        "permit",
        "permission",
        "permissions",
        "access",
        "valid",
        "verify",
        "verified",
        "authentic",
        "authenticated",
        "trusted",
        "granted",
        "can",
    }
)
DENYING_WORDS = frozenset(
    {
        "blocked",
        "banned",
        "revoked",
        "expired",
        "denied",
        "forbidden",
        "throttled",
        "limited",
        "exceeded",
        "exceeds",
        "malicious",
        "suspicious",
        "locked",
        "spam",
    }
)
BOOLEAN = "bool"
WORD_BOUNDARY = re.compile(r"_+|(?<=[a-z0-9])(?=[A-Z])")
FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)

type Function = ast.FunctionDef | ast.AsyncFunctionDef


class FailOpenHandler(NamedTuple):
    path: str
    line_number: int
    function: str
    answer: bool


def words_of(name: str) -> set[str]:
    return {word.lower() for word in WORD_BOUNDARY.split(name) if word}


def permissive_answer(name: str) -> bool | None:
    words = words_of(name)
    grants = bool(words & GRANTING_WORDS)
    denies = bool(words & DENYING_WORDS)

    if grants == denies:
        return None

    return grants


def returned_flag(node: ast.AST) -> bool | None:
    if not isinstance(node, ast.Return) or node.value is None:
        return None

    value = node.value

    if isinstance(value, ast.Constant) and isinstance(value.value, bool):
        return value.value

    return None


def own_nodes(root: ast.AST) -> list[ast.AST]:
    found: list[ast.AST] = []
    pending = list(ast.iter_child_nodes(root))

    while pending:
        node = pending.pop()
        found.append(node)

        if not isinstance(node, FUNCTIONS):
            pending.extend(ast.iter_child_nodes(node))

    return found


def is_predicate(function: Function) -> bool:
    returns = function.returns

    if isinstance(returns, ast.Name) and returns.id == BOOLEAN:
        return True

    return any(returned_flag(node) is not None for node in own_nodes(function))


class FailOpenHandlers:
    def find_in(self, paths: list[str]) -> list[FailOpenHandler]:
        found: list[FailOpenHandler] = []

        for path in paths:
            tree = ast.parse(Path(path).read_bytes(), path)

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    found.extend(self._in_function(path, node))

        return sorted(found)

    def _in_function(
        self, path: str, function: Function
    ) -> list[FailOpenHandler]:
        answer = permissive_answer(function.name)

        if answer is None or not is_predicate(function):
            return []

        found: list[FailOpenHandler] = []

        for node in own_nodes(function):
            if not isinstance(node, ast.ExceptHandler):
                continue

            for inner in own_nodes(node):
                if returned_flag(inner) is answer:
                    line = getattr(inner, "lineno", node.lineno)
                    handler = FailOpenHandler(
                        path, line, function.name, answer
                    )
                    found.append(handler)

        return found


source_paths = [line for line in sys.stdin.read().split("\n") if line]

for handler in FailOpenHandlers().find_in(source_paths):
    location = f"{handler.path}:{handler.line_number}"
    problem = f"{handler.function}() answers {handler.answer} when it fails"
    safe_answer = not handler.answer
    advice = f"so an error lets the request through - return {safe_answer}"
    _ = sys.stdout.write(f"{location}: {problem}, {advice}\n")
