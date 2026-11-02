import ast
import re
import sys
from pathlib import Path
from typing import NamedTuple, override

UNIT_WORDS = {
    "ns": "ns",
    "nanoseconds": "ns",
    "us": "us",
    "microseconds": "us",
    "ms": "ms",
    "millis": "ms",
    "milliseconds": "ms",
    "s": "s",
    "sec": "s",
    "secs": "s",
    "seconds": "s",
    "mins": "min",
    "minutes": "min",
    "hrs": "h",
    "hours": "h",
    "days": "d",
    "bytes": "B",
    "kb": "KB",
    "kib": "KB",
    "kilobytes": "KB",
    "mb": "MB",
    "mib": "MB",
    "megabytes": "MB",
    "gb": "GB",
    "gib": "GB",
    "gigabytes": "GB",
}
SECONDS = "s"
NANOSECONDS = "ns"
FACTOR_WORDS = frozenset({"per", "in", "to"})
UNIT_NAME_WORDS = 2
BARE_UNIT_NAMES = frozenset({"seconds", "milliseconds", "minutes", "hours"})
SECONDS_CALLS = frozenset({"time.time", "time.monotonic", "time.perf_counter"})
NANOSECONDS_CALLS = frozenset(
    {"time.time_ns", "time.monotonic_ns", "time.perf_counter_ns"}
)
SECONDS_METHODS = frozenset({"timestamp", "total_seconds"})
SLEEP_CALLS = frozenset({"time.sleep", "asyncio.sleep"})
KNOWN_UNIT_KEYS = {
    "ex": SECONDS,
    "px": "ms",
    "exat": SECONDS,
    "pxat": "ms",
    "countdown": SECONDS,
    "time_limit": SECONDS,
    "soft_time_limit": SECONDS,
    "socket_timeout": SECONDS,
    "socket_connect_timeout": SECONDS,
    "connect_timeout": SECONDS,
    "keepalives_idle": SECONDS,
    "keepalives_interval": SECONDS,
    "tcp_user_timeout": "ms",
    "statement_timeout": "ms",
    "lock_timeout": "ms",
    "idle_in_transaction_session_timeout": "ms",
}
COMPARISONS = (ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq, ast.NotEq)
SUMS = (ast.Add, ast.Sub)
WORD_BOUNDARY = re.compile(r"_+|(?<=[a-z0-9])(?=[A-Z])")

type FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef


class UnitMismatch(NamedTuple):
    path: str
    line_number: int
    value: str
    value_unit: str
    place: str
    place_unit: str


class Place(NamedTuple):
    description: str
    unit: str | None


def unit_of_name(name: str) -> str | None:
    words = [word.lower() for word in WORD_BOUNDARY.split(name) if word]

    if len(words) == 1 and words[0] in BARE_UNIT_NAMES:
        return UNIT_WORDS[words[0]]

    if len(words) < UNIT_NAME_WORDS:
        return None

    if any(word in FACTOR_WORDS for word in words[:-1]):
        return None

    return UNIT_WORDS.get(words[-1])


def dotted_name(expression: ast.expr) -> str:
    if isinstance(expression, ast.Name):
        return expression.id

    if isinstance(expression, ast.Attribute):
        return f"{dotted_name(expression.value)}.{expression.attr}"

    return ""


def call_unit(call: ast.Call) -> str | None:
    callee = dotted_name(call.func)

    if callee in SECONDS_CALLS:
        return SECONDS

    if callee in NANOSECONDS_CALLS:
        return NANOSECONDS

    if isinstance(call.func, ast.Attribute):
        if call.func.attr in SECONDS_METHODS:
            return SECONDS

        return unit_of_name(call.func.attr)

    if isinstance(call.func, ast.Name):
        return unit_of_name(call.func.id)

    return None


def sum_unit(operation: ast.BinOp) -> str | None:
    left = unit_of(operation.left)
    right = unit_of(operation.right)

    if left == right:
        return left

    if left is None and isinstance(operation.left, ast.Constant):
        return right

    if right is None and isinstance(operation.right, ast.Constant):
        return left

    return None


def choice_unit(choice: ast.IfExp) -> str | None:
    body_unit = unit_of(choice.body)

    if body_unit == unit_of(choice.orelse):
        return body_unit

    return None


def named_unit(expression: ast.expr) -> str | None:
    if isinstance(expression, ast.Name | ast.Attribute):
        return unit_of_name(dotted_name(expression).rpartition(".")[2])

    if isinstance(expression, ast.Subscript):
        key = string_key(expression.slice)
        return None if key is None else key_unit(key)

    return None


def unit_of(expression: ast.expr) -> str | None:
    if isinstance(expression, ast.Name | ast.Attribute | ast.Subscript):
        return named_unit(expression)

    if isinstance(expression, ast.Call):
        return call_unit(expression)

    if isinstance(expression, ast.UnaryOp):
        return unit_of(expression.operand)

    if isinstance(expression, ast.BinOp) and isinstance(expression.op, SUMS):
        return sum_unit(expression)

    if isinstance(expression, ast.IfExp):
        return choice_unit(expression)

    return None


def key_unit(key: str) -> str | None:
    if key in KNOWN_UNIT_KEYS:
        return KNOWN_UNIT_KEYS[key]

    return unit_of_name(key)


def string_key(expression: ast.expr | None) -> str | None:
    if isinstance(expression, ast.Constant) and isinstance(
        expression.value, str
    ):
        return expression.value

    return None


class Mismatches(ast.NodeVisitor):
    def __init__(self, path: str) -> None:
        self._path: str = path
        self._results: list[Place] = []
        self.found: list[UnitMismatch] = []

    @override
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    @override
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    @override
    def visit_Return(self, node: ast.Return) -> None:
        if node.value is not None and self._results:
            self._check(node.value, self._results[-1])

        self.generic_visit(node)

    @override
    def visit_Compare(self, node: ast.Compare) -> None:
        left = node.left

        for operator, right in zip(node.ops, node.comparators, strict=True):
            if isinstance(operator, COMPARISONS):
                self._check_pair(left, right)

            left = right

        self.generic_visit(node)

    @override
    def visit_BinOp(self, node: ast.BinOp) -> None:
        if isinstance(node.op, SUMS):
            self._check_pair(node.left, node.right)

        self.generic_visit(node)

    @override
    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._check_pair(target, node.value)

        self.generic_visit(node)

    @override
    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self._check_pair(node.target, node.value)

        self.generic_visit(node)

    @override
    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        if isinstance(node.op, SUMS):
            self._check_pair(node.target, node.value)

        self.generic_visit(node)

    @override
    def visit_Call(self, node: ast.Call) -> None:
        callee = dotted_name(node.func)

        if callee in SLEEP_CALLS and node.args:
            self._check(node.args[0], Place(f"{callee}()", SECONDS))

        for keyword in node.keywords:
            if keyword.arg is not None:
                place = Place(f"{keyword.arg}=", key_unit(keyword.arg))
                self._check(keyword.value, place)

        self.generic_visit(node)

    @override
    def visit_Dict(self, node: ast.Dict) -> None:
        for key, value in zip(node.keys, node.values, strict=True):
            name = string_key(key)

            if name is not None:
                self._check(value, Place(repr(name), key_unit(name)))

        self.generic_visit(node)

    def _visit_function(self, node: FunctionNode) -> None:
        result = Place(f"the result of {node.name}()", unit_of_name(node.name))
        self._results.append(result)
        self.generic_visit(node)
        _ = self._results.pop()

    def _check_pair(self, place: ast.expr, value: ast.expr) -> None:
        self._check(value, Place(ast.unparse(place), unit_of(place)))

    def _check(self, value: ast.expr, place: Place) -> None:
        value_unit = unit_of(value)

        if place.unit is None or value_unit is None:
            return

        if place.unit == value_unit:
            return

        self.found.append(
            UnitMismatch(
                self._path,
                value.lineno,
                ast.unparse(value),
                value_unit,
                place.description,
                place.unit,
            )
        )


class UnitMismatches:
    def find_in(self, paths: list[str]) -> list[UnitMismatch]:
        found: set[UnitMismatch] = set()

        for path in paths:
            tree = ast.parse(Path(path).read_bytes(), path)
            mismatches = Mismatches(path)
            mismatches.visit(tree)
            found.update(mismatches.found)

        return sorted(found)


source_paths = [line for line in sys.stdin.read().split("\n") if line]

for mismatch in UnitMismatches().find_in(source_paths):
    location = f"{mismatch.path}:{mismatch.line_number}"
    value = f"{mismatch.value} is in {mismatch.value_unit}"
    place = f"{mismatch.place} is in {mismatch.place_unit}"
    _ = sys.stdout.write(f"{location}: {value} but {place}\n")
