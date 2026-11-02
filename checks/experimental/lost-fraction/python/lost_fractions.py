import ast
import sys
from pathlib import Path
from typing import NamedTuple

TRUNCATING_CALLS = frozenset({"int", "math.floor", "math.trunc", "floor"})
SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module)
FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)


class LostFraction(NamedTuple):
    path: str
    line_number: int
    whole: str
    fraction: str


def dotted_name(expression: ast.expr) -> str:
    if isinstance(expression, ast.Name):
        return expression.id

    if isinstance(expression, ast.Attribute):
        return f"{dotted_name(expression.value)}.{expression.attr}"

    return ""


def is_true_division(expression: ast.expr) -> bool:
    return isinstance(expression, ast.BinOp) and isinstance(
        expression.op, ast.Div
    )


def is_truncation(expression: ast.expr) -> bool:
    if isinstance(expression, ast.BinOp):
        return isinstance(expression.op, ast.FloorDiv)

    return (
        isinstance(expression, ast.Call)
        and len(expression.args) == 1
        and dotted_name(expression.func) in TRUNCATING_CALLS
        and is_true_division(expression.args[0])
    )


def assignments(body: list[ast.stmt]) -> list[tuple[ast.expr, ast.expr]]:
    found: list[tuple[ast.expr, ast.expr]] = []

    for statement in body:
        if isinstance(statement, ast.Assign):
            for target in statement.targets:
                found.append((target, statement.value))
        elif isinstance(statement, ast.AnnAssign) and statement.value:
            found.append((statement.target, statement.value))

    return found


def fraction_constants(tree: ast.Module) -> dict[str, float]:
    constants: dict[str, float] = {}

    for target, value in assignments(tree.body):
        if not isinstance(target, ast.Name):
            continue

        if isinstance(value, ast.Constant) and isinstance(value.value, float):
            constants[target.id] = value.value

    return constants


def own_nodes(scope: ast.AST) -> list[ast.AST]:
    found: list[ast.AST] = []
    pending = list(ast.iter_child_nodes(scope))

    while pending:
        node = pending.pop()

        if isinstance(node, FUNCTIONS):
            continue

        found.append(node)
        pending.extend(ast.iter_child_nodes(node))

    return found


class Scope:
    def __init__(
        self, nodes: list[ast.AST], constants: dict[str, float]
    ) -> None:
        self._constants: dict[str, float] = constants
        self._truncated: set[str] = set()

        for node in nodes:
            if isinstance(node, ast.Assign) and is_truncation(node.value):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self._truncated.add(target.id)

    def is_whole(self, operand: ast.expr) -> bool:
        if is_truncation(operand):
            return True

        return isinstance(operand, ast.Name) and operand.id in self._truncated

    def has_fraction(self, operand: ast.expr) -> bool:
        value: object = None

        if isinstance(operand, ast.Constant):
            value = operand.value
        elif isinstance(operand, ast.Name):
            value = self._constants.get(operand.id)

        return isinstance(value, float) and not value.is_integer()


class LostFractions:
    def find_in(self, paths: list[str]) -> list[LostFraction]:
        found: set[LostFraction] = set()

        for path in paths:
            tree = ast.parse(Path(path).read_bytes(), path)
            constants = fraction_constants(tree)

            for node in ast.walk(tree):
                if isinstance(node, SCOPES):
                    nodes = own_nodes(node)
                    scope = Scope(nodes, constants)
                    found.update(self._in_nodes(path, nodes, scope))

        return sorted(found)

    def _in_nodes(
        self, path: str, nodes: list[ast.AST], scope: Scope
    ) -> list[LostFraction]:
        found: list[LostFraction] = []

        for node in nodes:
            if not isinstance(node, ast.Compare):
                continue

            operands = [node.left, *node.comparators]
            wholes = [item for item in operands if scope.is_whole(item)]
            fractions = [
                item for item in operands if scope.has_fraction(item)
            ]

            if wholes and fractions:
                whole = ast.unparse(wholes[0])
                fraction = ast.unparse(fractions[0])
                found.append(LostFraction(path, node.lineno, whole, fraction))

        return found


source_paths = [line for line in sys.stdin.read().split("\n") if line]

for lost in LostFractions().find_in(source_paths):
    location = f"{lost.path}:{lost.line_number}"
    problem = f"{lost.whole} has lost its fraction"
    _ = sys.stdout.write(
        f"{location}: {problem} but is compared with {lost.fraction}\n"
    )
