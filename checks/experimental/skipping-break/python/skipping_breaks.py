import ast
import sys
from pathlib import Path
from typing import NamedTuple

GROWING_METHODS = frozenset(
    {"append", "add", "extend", "update", "insert", "appendleft", "setdefault"}
)
LITERAL_COLLECTIONS = (ast.Tuple, ast.List, ast.Set)
FIXED_ELEMENTS = (ast.Constant, ast.Starred)
EXCLUDED_VALUES_MINIMUM = 2
SEEN_REASON = "was already seen"
EXCLUDED_REASON = "is one of the excluded values"

type FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef
type LoopNode = ast.For | ast.AsyncFor


class SkippingBreak(NamedTuple):
    path: str
    line_number: int
    item: str
    reason: str


class Membership(NamedTuple):
    item: ast.expr
    container: ast.expr


class GuardedBreak(NamedTuple):
    test: ast.expr
    line_number: int


def grown_collection(node: ast.AST) -> ast.expr | None:
    if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Store):
        return node.value

    if not isinstance(node, ast.Call):
        return None

    method = node.func

    if not isinstance(method, ast.Attribute):
        return None

    if method.attr not in GROWING_METHODS:
        return None

    return method.value


def grown_names(loop: LoopNode) -> set[str]:
    grown: set[str] = set()

    for node in ast.walk(loop):
        collection = grown_collection(node)

        if isinstance(collection, ast.Name):
            grown.add(collection.id)

    return grown


def bound_names(function: FunctionNode) -> set[str]:
    names: set[str] = set()

    for node in ast.walk(function):
        if isinstance(node, ast.arg):
            names.add(node.arg)

        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)

    return names


def guarded_break(statement: ast.stmt) -> GuardedBreak | None:
    if not isinstance(statement, ast.If) or statement.orelse:
        return None

    if len(statement.body) != 1:
        return None

    stop = statement.body[0]

    if not isinstance(stop, ast.Break):
        return None

    return GuardedBreak(statement.test, stop.lineno)


def alternatives(test: ast.expr) -> list[ast.expr]:
    if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.Or):
        return test.values

    return [test]


def membership_of(test: ast.expr) -> Membership | None:
    if not isinstance(test, ast.Compare) or len(test.ops) != 1:
        return None

    if not isinstance(test.ops[0], ast.In):
        return None

    return Membership(test.left, test.comparators[0])


def mentions_any(expression: ast.expr, names: set[str]) -> bool:
    for node in ast.walk(expression):
        if isinstance(node, ast.Name) and node.id in names:
            return True

    return False


def is_excluded_value(element: ast.expr, bound: set[str]) -> bool:
    return not isinstance(element, FIXED_ELEMENTS) and mentions_any(
        element, bound
    )


def lists_excluded_values(container: ast.expr, bound: set[str]) -> bool:
    if not isinstance(container, LITERAL_COLLECTIONS):
        return False

    if len(container.elts) < EXCLUDED_VALUES_MINIMUM:
        return False

    return all(is_excluded_value(element, bound) for element in container.elts)


def membership_reason(
    membership: Membership, grown: set[str], bound: set[str]
) -> str | None:
    container = membership.container

    if isinstance(container, ast.Name) and container.id in grown:
        return SEEN_REASON

    if lists_excluded_values(container, bound):
        return EXCLUDED_REASON

    return None


class FunctionBreaks:
    def __init__(self, path: str, function: FunctionNode) -> None:
        self._path: str = path
        self._function: FunctionNode = function
        self._bound: set[str] = bound_names(function)
        self.found: list[SkippingBreak] = []

    def check(self) -> None:
        for node in ast.walk(self._function):
            if isinstance(node, ast.For | ast.AsyncFor):
                self._check_loop(node)

    def _check_loop(self, loop: LoopNode) -> None:
        grown = grown_names(loop)

        for statement in loop.body[:-1]:
            stop = guarded_break(statement)

            if stop is not None:
                self._check_break(stop, grown)

    def _check_break(self, stop: GuardedBreak, grown: set[str]) -> None:
        for alternative in alternatives(stop.test):
            membership = membership_of(alternative)

            if membership is None:
                continue

            reason = membership_reason(membership, grown, self._bound)

            if reason is not None:
                item = ast.unparse(membership.item)
                found = SkippingBreak(
                    self._path, stop.line_number, item, reason
                )
                self.found.append(found)
                return


def outermost_functions(tree: ast.Module) -> list[FunctionNode]:
    functions: list[FunctionNode] = []
    pending: list[ast.AST] = [tree]

    while pending:
        node = pending.pop()

        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            functions.append(node)
        else:
            pending.extend(ast.iter_child_nodes(node))

    return functions


class SkippingBreaks:
    def find_in(self, paths: list[str]) -> list[SkippingBreak]:
        found: set[SkippingBreak] = set()

        for path in paths:
            tree = ast.parse(Path(path).read_bytes(), path)

            for function in outermost_functions(tree):
                breaks = FunctionBreaks(path, function)
                breaks.check()
                found.update(breaks.found)

        return sorted(found)


source_paths = [line for line in sys.stdin.read().split("\n") if line]

for skipping in SkippingBreaks().find_in(source_paths):
    location = f"{skipping.path}:{skipping.line_number}"
    problem = f"break ends the whole loop when {skipping.item}"
    effect = f"{skipping.reason}, so the items after it are never looked at"
    fix = "use continue to skip only this one"
    _ = sys.stdout.write(f"{location}: {problem} {effect} - {fix}\n")
