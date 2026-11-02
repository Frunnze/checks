import ast
import re
import sys
from pathlib import Path
from typing import NamedTuple

EXECUTE = "execute"
SINGLE_ROW_METHODS = frozenset({"fetchone", "first", "scalar", "one_or_none"})
ORDERED_SELECT = re.compile(
    r"\bselect\b.*\border\s+by\b", re.IGNORECASE | re.DOTALL
)
ROW_LIMIT = re.compile(
    r"\blimit\b|\bfetch\s+(first|next)\b|\btop\s*\(?\d", re.IGNORECASE
)
PLACEHOLDER = " ? "
FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)


class UnboundedFetch(NamedTuple):
    path: str
    line_number: int
    fetch_line: int


class MethodCall(NamedTuple):
    receiver: str
    method: str
    call: ast.Call


def is_unbounded_ordered_select(sql: str) -> bool:
    return bool(ORDERED_SELECT.search(sql)) and not ROW_LIMIT.search(sql)


def method_call(node: ast.AST) -> MethodCall | None:
    if isinstance(node, ast.Await):
        node = node.value

    if not isinstance(node, ast.Call):
        return None

    function = node.func

    if not isinstance(function, ast.Attribute):
        return None

    return MethodCall(ast.unparse(function.value), function.attr, node)


def end_position(call: MethodCall) -> tuple[int, int]:
    return call.call.end_lineno or 0, call.call.end_col_offset or 0


def assigned_names(function: ast.AST) -> dict[int, str]:
    names: dict[int, str] = {}

    for node in ast.walk(function):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue

        value = node.value

        if isinstance(value, ast.Await):
            value = value.value

        if isinstance(node.targets[0], ast.Name):
            names[id(value)] = node.targets[0].id

    return names


class SqlText:
    def __init__(self, tree: ast.Module) -> None:
        self._constants: dict[str, str] = {}

        for statement in tree.body:
            if not isinstance(statement, ast.Assign):
                continue

            text = self.of(statement.value)

            for target in statement.targets:
                if text is not None and isinstance(target, ast.Name):
                    self._constants[target.id] = text

    def of(self, expression: ast.expr | None) -> str | None:
        if isinstance(expression, ast.Constant):
            value = expression.value
            return value if isinstance(value, str) else None

        if isinstance(expression, ast.Name):
            return self._constants.get(expression.id)

        if isinstance(expression, ast.JoinedStr):
            return self._formatted(expression)

        if isinstance(expression, ast.BinOp) and isinstance(
            expression.op, ast.Add
        ):
            return self._concatenated(expression)

        if isinstance(expression, ast.Call) and expression.args:
            return self.of(expression.args[0])

        return None

    def _formatted(self, expression: ast.JoinedStr) -> str:
        parts: list[str] = []

        for value in expression.values:
            text = self.of(value) if isinstance(value, ast.Constant) else None
            parts.append(PLACEHOLDER if text is None else text)

        return "".join(parts)

    def _concatenated(self, expression: ast.BinOp) -> str | None:
        left = self.of(expression.left)
        right = self.of(expression.right)

        if left is None or right is None:
            return None

        return left + right


class FunctionQueries:
    def __init__(self, function: ast.AST, sql_text: SqlText) -> None:
        self._sql_text: SqlText = sql_text
        self._assigned: dict[int, str] = assigned_names(function)
        self._unbounded: dict[str, int] = {}
        self.calls: list[MethodCall] = []

        for node in ast.walk(function):
            call = method_call(node)

            if call is not None:
                self.calls.append(call)

        self.calls.sort(key=end_position)

    def unbounded_line(self, call: MethodCall) -> int | None:
        if call.method == EXECUTE and call.call.args:
            self._remember(call)
            return None

        if call.method in SINGLE_ROW_METHODS:
            return self._unbounded.get(call.receiver)

        return None

    def _remember(self, call: MethodCall) -> None:
        sql = self._sql_text.of(call.call.args[0])
        results = [call.receiver, ast.unparse(call.call)]
        assigned = self._assigned.get(id(call.call))

        if assigned is not None:
            results.append(assigned)

        for result in results:
            if sql is not None and is_unbounded_ordered_select(sql):
                self._unbounded[result] = call.call.lineno
            else:
                _ = self._unbounded.pop(result, None)


class UnboundedFetches:
    def find_in(self, paths: list[str]) -> list[UnboundedFetch]:
        found: set[UnboundedFetch] = set()

        for path in paths:
            tree = ast.parse(Path(path).read_bytes(), path)
            sql_text = SqlText(tree)

            for node in ast.walk(tree):
                if isinstance(node, FUNCTIONS):
                    queries = FunctionQueries(node, sql_text)
                    found.update(self._in_function(path, queries))

        return sorted(found)

    def _in_function(
        self, path: str, queries: FunctionQueries
    ) -> list[UnboundedFetch]:
        found: list[UnboundedFetch] = []

        for call in queries.calls:
            executed_line = queries.unbounded_line(call)

            if executed_line is not None:
                fetch = UnboundedFetch(path, executed_line, call.call.lineno)
                found.append(fetch)

        return found


source_paths = [line for line in sys.stdin.read().split("\n") if line]

for fetch in UnboundedFetches().find_in(source_paths):
    location = f"{fetch.path}:{fetch.line_number}"
    problem = "this ordered query has no LIMIT"
    keep = f"line {fetch.fetch_line} keeps only one row"
    _ = sys.stdout.write(f"{location}: {problem} but {keep}\n")
