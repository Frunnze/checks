import ast
import copy
import sys
from pathlib import Path
from typing import NamedTuple, override

SELF_CANCELLING = (ast.Sub, ast.Div, ast.FloorDiv, ast.Mod)
NAMED_PARTS = (ast.Attribute, ast.Subscript)
CHAINED = (ast.Add, ast.Mult, ast.BitOr, ast.BitAnd)
PAIR_CALLS = frozenset({"min", "max"})
TEST_FOLDERS = frozenset({"test", "tests"})
TEST_PREFIX = "test_"
TEST_SUFFIX = "_test.py"
SERIES_LENGTH = 3
PAIR_ARGUMENTS = 2
INDEX_HOLE = "_index_"
IMPURE = (ast.Call, ast.Await, ast.NamedExpr, ast.Yield, ast.YieldFrom)



class CopiedOperand(NamedTuple):
    path: str
    line_number: int
    expression: str
    reason: str


def is_pure(expression: ast.expr) -> bool:
    return not any(isinstance(node, IMPURE) for node in ast.walk(expression))


def same(first: ast.expr, second: ast.expr) -> bool:
    return is_pure(first) and ast.dump(first) == ast.dump(second)


def same_part(first: ast.expr, second: ast.expr) -> bool:
    return isinstance(first, NAMED_PARTS) and same(first, second)


def breaks_progression(indexes: list[int]) -> int | None:
    start = indexes[0]
    expected = list(range(start, start + len(indexes)))
    breaks = [
        position
        for position, index in enumerate(indexes)
        if index != expected[position]
    ]

    if len(breaks) != 1:
        return None

    position = breaks[0]
    repeats_previous = indexes[position] == indexes[position - 1]

    if repeats_previous and expected[position] not in indexes:
        return position

    return None


def chain_operands(operation: ast.BinOp) -> list[ast.expr]:
    operands: list[ast.expr] = []

    for side in (operation.left, operation.right):
        is_same_chain = isinstance(side, ast.BinOp) and isinstance(
            side.op, type(operation.op)
        )

        if is_same_chain and isinstance(side, ast.BinOp):
            operands.extend(chain_operands(side))
        else:
            operands.append(side)

    return operands


class IndexHoles(ast.NodeTransformer):
    def __init__(self) -> None:
        self.indexes: list[int] = []

    @override
    def visit_Subscript(self, node: ast.Subscript) -> ast.AST:
        index = node.slice

        if isinstance(index, ast.Constant) and isinstance(index.value, int):
            self.indexes.append(index.value)
            node.slice = ast.Name(INDEX_HOLE, ast.Load())

        _ = self.generic_visit(node)
        return node


class Indexed(NamedTuple):
    shape: str
    indexes: tuple[int, ...]


def indexed(expression: ast.expr) -> Indexed:
    holes = IndexHoles()
    wrapper = ast.Expression(body=copy.deepcopy(expression))
    _ = holes.generic_visit(wrapper)
    shape = ast.dump(wrapper.body)

    return Indexed(shape, tuple(holes.indexes))


def repeated_in_series(operands: list[ast.expr]) -> ast.expr | None:
    by_shape: dict[str, list[tuple[ast.expr, int]]] = {}

    for operand in operands:
        if not is_pure(operand):
            continue

        facts = indexed(operand)

        if len(facts.indexes) == 1:
            entry = (operand, facts.indexes[0])
            by_shape.setdefault(facts.shape, []).append(entry)

    for members in by_shape.values():
        if len(members) < SERIES_LENGTH:
            continue

        position = breaks_progression([index for _, index in members])

        if position is not None:
            return members[position][0]

    return None


def is_test_file(path: str) -> bool:
    parts = Path(path).parts
    name = parts[-1]
    in_test_folder = any(part in TEST_FOLDERS for part in parts[:-1])

    return in_test_folder or name.startswith(TEST_PREFIX) or (
        name.endswith(TEST_SUFFIX)
    )


class CopiedOperands(ast.NodeVisitor):
    def __init__(self, path: str) -> None:
        self._path: str = path
        self._checks_cancelling: bool = not is_test_file(path)
        self.found: list[CopiedOperand] = []

    @override
    def visit_BinOp(self, node: ast.BinOp) -> None:
        cancels = self._checks_cancelling and isinstance(
            node.op, SELF_CANCELLING
        )

        if cancels and same_part(node.left, node.right):
            self._add(node, "both operands are the same")

        if isinstance(node.op, CHAINED):
            self._check_series(chain_operands(node))

        self.generic_visit(node)

    @override
    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        for position, value in enumerate(node.values):
            later = node.values[position + 1 :]

            if any(same(value, other) for other in later):
                self._add(node, "it tests the same condition twice")
                break

        self.generic_visit(node)

    @override
    def visit_Call(self, node: ast.Call) -> None:
        function = node.func
        is_pair_call = isinstance(function, ast.Name) and (
            function.id in PAIR_CALLS
        )

        pair = node.args if len(node.args) == PAIR_ARGUMENTS else []

        if is_pair_call and pair and same_part(pair[0], pair[1]):
            self._add(node, "both arguments are the same")

        self.generic_visit(node)

    def _check_series(self, operands: list[ast.expr]) -> None:
        repeated = repeated_in_series(operands)

        if repeated is not None:
            reason = "its siblings step through indexes but it repeats one"
            self._add(repeated, reason)

    def _add(self, node: ast.expr, reason: str) -> None:
        expression = ast.unparse(node)
        operand = CopiedOperand(self._path, node.lineno, expression, reason)
        self.found.append(operand)


class CopiedOperandFinder:
    def find_in(self, paths: list[str]) -> list[CopiedOperand]:
        found: set[CopiedOperand] = set()

        for path in paths:
            tree = ast.parse(Path(path).read_bytes(), path)
            operands = CopiedOperands(path)
            operands.visit(tree)
            found.update(operands.found)

        return sorted(found)


source_paths = [line for line in sys.stdin.read().split("\n") if line]

for copied in CopiedOperandFinder().find_in(source_paths):
    location = f"{copied.path}:{copied.line_number}"
    _ = sys.stdout.write(
        f"{location}: {copied.expression} - {copied.reason}\n"
    )
