import ast
import sys
from pathlib import Path
from typing import NamedTuple

WRITING_METHODS = frozenset(
    {
        "post",
        "create",
        "send",
        "sendmail",
        "send_message",
        "charge",
        "publish",
        "insert",
        "insert_one",
        "enqueue",
        "apply_async",
        "delay",
    }
)
TIMEOUT_MARK = "Timeout"
CATCH_ALL = frozenset({"Exception", "BaseException"})
IDEMPOTENCY_MARK = "idempotency"
LOOPS = (ast.For, ast.AsyncFor, ast.While)
LEAVES = (ast.Raise, ast.Return, ast.Break)


class DuplicatingRetry(NamedTuple):
    path: str
    line_number: int
    call: str


def last_name(expression: ast.expr) -> str:
    if isinstance(expression, ast.Name):
        return expression.id

    if isinstance(expression, ast.Attribute):
        return expression.attr

    return ""


def caught_names(handler: ast.ExceptHandler) -> list[str]:
    if handler.type is None:
        return ["BaseException"]

    if isinstance(handler.type, ast.Tuple):
        return [last_name(element) for element in handler.type.elts]

    return [last_name(handler.type)]


def catches_timeouts(handler: ast.ExceptHandler) -> bool:
    for name in caught_names(handler):
        if TIMEOUT_MARK in name or name in CATCH_ALL:
            return True

    return False


def retries(handler: ast.ExceptHandler) -> bool:
    return all(not isinstance(node, LEAVES) for node in ast.walk(handler))


def leaves_on_success(attempt: ast.Try) -> bool:
    for statement in [*attempt.body, *attempt.orelse]:
        for node in ast.walk(statement):
            if isinstance(node, ast.Return | ast.Break):
                return True

    return False


def writing_call(statements: list[ast.stmt]) -> ast.Call | None:
    for statement in statements:
        for node in ast.walk(statement):
            if not isinstance(node, ast.Call):
                continue

            function = node.func
            is_write = isinstance(function, ast.Attribute) and (
                function.attr in WRITING_METHODS
            )

            if is_write and IDEMPOTENCY_MARK not in ast.unparse(node).lower():
                return node

    return None


class DuplicatingRetries:
    def find_in(self, paths: list[str]) -> list[DuplicatingRetry]:
        found: list[DuplicatingRetry] = []

        for path in paths:
            tree = ast.parse(Path(path).read_bytes(), path)

            for node in ast.walk(tree):
                if isinstance(node, LOOPS):
                    found.extend(self._in_loop(path, node))

        return sorted(set(found))

    def _in_loop(
        self, path: str, loop: ast.For | ast.AsyncFor | ast.While
    ) -> list[DuplicatingRetry]:
        found: list[DuplicatingRetry] = []

        for statement in loop.body:
            if not isinstance(statement, ast.Try):
                continue

            call = writing_call(statement.body)

            if call is None or not leaves_on_success(statement):
                continue

            for handler in statement.handlers:
                if catches_timeouts(handler) and retries(handler):
                    text = ast.unparse(call.func)
                    found.append(DuplicatingRetry(path, call.lineno, text))

        return found


source_paths = [line for line in sys.stdin.read().split("\n") if line]

for retry in DuplicatingRetries().find_in(source_paths):
    location = f"{retry.path}:{retry.line_number}"
    problem = f"{retry.call}() is retried after a timeout"
    effect = "it may already have run, so the retry repeats it"
    advice = "send an idempotency key or do not retry timeouts"
    _ = sys.stdout.write(f"{location}: {problem}, but {effect} - {advice}\n")
