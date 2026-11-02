import ast
import sys
from pathlib import Path
from typing import NamedTuple

COMMIT = "commit"
WRITES = frozenset(
    {"execute", "executemany", "add", "add_all", "merge", "delete", "flush"}
)
FUNCTION_TYPES = ast.FunctionDef | ast.AsyncFunctionDef


class SplitCommit(NamedTuple):
    path: str
    line_number: int
    receiver: str
    final_line: int


def statement_call(statement: ast.stmt) -> ast.expr | None:
    if isinstance(statement, ast.Expr | ast.Assign):
        expression = statement.value
    else:
        return None

    if isinstance(expression, ast.Await):
        return expression.value

    return expression


def committed_receiver(statement: ast.stmt) -> str | None:
    call = statement_call(statement)

    if not isinstance(call, ast.Call):
        return None

    function = call.func

    if isinstance(function, ast.Attribute) and function.attr == COMMIT:
        return ast.unparse(function.value)

    return None


def writes_in(statement: ast.stmt) -> bool:
    for node in ast.walk(statement):
        if not isinstance(node, ast.Call):
            continue

        function = node.func

        if isinstance(function, ast.Attribute) and function.attr in WRITES:
            return True

    return False


def nested_blocks(statement: ast.stmt) -> list[list[ast.stmt]]:
    if isinstance(statement, ast.If | ast.For | ast.AsyncFor | ast.While):
        return [statement.body, statement.orelse]

    if isinstance(statement, ast.Try | ast.TryStar):
        handlers = [handler.body for handler in statement.handlers]
        ends = [statement.orelse, statement.finalbody]
        return [statement.body, *ends, *handlers]

    if isinstance(statement, ast.Match):
        return [case.body for case in statement.cases]

    if isinstance(statement, ast.With | ast.AsyncWith | ast.ClassDef):
        return [statement.body]

    if isinstance(statement, FUNCTION_TYPES):
        return [statement.body]

    return []


class Transactions:
    def __init__(self, path: str) -> None:
        self._path: str = path
        self.found: list[SplitCommit] = []

    def scan(self, statements: list[ast.stmt]) -> None:
        commit_lines: dict[str, int] = {}
        written: set[str] = set()

        for statement in statements:
            receiver = committed_receiver(statement)

            if receiver is not None:
                self._commit(receiver, statement.lineno, commit_lines, written)
                continue

            if writes_in(statement):
                written.update(commit_lines)

            for block in nested_blocks(statement):
                self.scan(block)

    def _commit(
        self,
        receiver: str,
        line_number: int,
        commit_lines: dict[str, int],
        written: set[str],
    ) -> None:
        if receiver in written:
            first_line = commit_lines[receiver]
            split = SplitCommit(self._path, first_line, receiver, line_number)
            self.found.append(split)

        commit_lines[receiver] = line_number
        written.discard(receiver)


class SplitCommits:
    def find_in(self, paths: list[str]) -> list[SplitCommit]:
        found: set[SplitCommit] = set()

        for path in paths:
            tree = ast.parse(Path(path).read_bytes(), path)
            transactions = Transactions(path)
            transactions.scan(tree.body)
            found.update(transactions.found)

        return sorted(found)


source_paths = [line for line in sys.stdin.read().split("\n") if line]

for split in SplitCommits().find_in(source_paths):
    location = f"{split.path}:{split.line_number}"
    problem = f"{split.receiver}.commit() saves part of the change"
    rest = f"the rest is committed on line {split.final_line}"
    _ = sys.stdout.write(f"{location}: {problem} - {rest}\n")
