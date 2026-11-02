import ast
import re
import sys
from pathlib import Path
from typing import NamedTuple

DOTTED_VERSION = re.compile(r"\d+(\.\d+)+")
ORDERINGS = (ast.Lt, ast.LtE, ast.Gt, ast.GtE)
TEXT_CALLS = frozenset({"str", "repr"})
NUMBER_CALLS = frozenset({"len", "sum", "int", "float", "round", "abs"})
VERSION_TEXTS = frozenset({"__version__", "sys.version", "platform.release"})
VERSION_CALLS = frozenset({"platform.python_version", "platform.release"})

type Number = int | float


class TextualComparison(NamedTuple):
    path: str
    line_number: int
    text: str


def dotted_name(expression: ast.expr) -> str:
    if isinstance(expression, ast.Name):
        return expression.id

    if isinstance(expression, ast.Attribute):
        return f"{dotted_name(expression.value)}.{expression.attr}"

    return ""


def is_number_literal(expression: ast.expr | None) -> bool:
    if isinstance(expression, ast.Constant):
        value = expression.value
        return isinstance(value, int | float) and not isinstance(value, bool)

    if isinstance(expression, ast.UnaryOp):
        return is_number_literal(expression.operand)

    if isinstance(expression, ast.BinOp):
        return is_number_literal(expression.left) and is_number_literal(
            expression.right
        )

    return False


def number_constants(tree: ast.Module) -> set[str]:
    names: set[str] = set()

    for statement in tree.body:
        if isinstance(statement, ast.Assign):
            targets = statement.targets
        elif isinstance(statement, ast.AnnAssign):
            targets = [statement.target]
        else:
            continue

        if is_number_literal(statement.value):
            names.update(
                target.id for target in targets if isinstance(target, ast.Name)
            )

    return names


class TextKinds:
    def __init__(self, numbers: set[str]) -> None:
        self._numbers: set[str] = numbers

    def number_as_text(self, expression: ast.expr) -> bool:
        if not isinstance(expression, ast.Call) or len(expression.args) != 1:
            return False

        if dotted_name(expression.func) not in TEXT_CALLS:
            return False

        return self._is_number(expression.args[0])

    def raw_version(self, expression: ast.expr) -> bool:
        if isinstance(expression, ast.Call):
            return dotted_name(expression.func) in VERSION_CALLS

        name = dotted_name(expression)

        return name in VERSION_TEXTS or name.endswith(".__version__")

    def _is_number(self, expression: ast.expr) -> bool:
        if is_number_literal(expression):
            return True

        if isinstance(expression, ast.Name):
            return expression.id in self._numbers

        if isinstance(expression, ast.BinOp):
            return True

        return isinstance(expression, ast.Call) and (
            dotted_name(expression.func) in NUMBER_CALLS
        )


def is_version_literal(expression: ast.expr) -> bool:
    return (
        isinstance(expression, ast.Constant)
        and isinstance(expression.value, str)
        and DOTTED_VERSION.fullmatch(expression.value) is not None
    )


def ordered_pairs(comparison: ast.Compare) -> list[tuple[ast.expr, ast.expr]]:
    pairs: list[tuple[ast.expr, ast.expr]] = []
    left = comparison.left

    for operator, right in zip(
        comparison.ops, comparison.comparators, strict=True
    ):
        if isinstance(operator, ORDERINGS):
            pairs.append((left, right))

        left = right

    return pairs


class TextualNumberComparisons:
    def find_in(self, paths: list[str]) -> list[TextualComparison]:
        found: list[TextualComparison] = []

        for path in paths:
            tree = ast.parse(Path(path).read_bytes(), path)
            kinds = TextKinds(number_constants(tree))

            for node in ast.walk(tree):
                if isinstance(node, ast.Compare):
                    found.extend(self._in_comparison(path, node, kinds))

        return sorted(found)

    def _in_comparison(
        self, path: str, comparison: ast.Compare, kinds: TextKinds
    ) -> list[TextualComparison]:
        found: list[TextualComparison] = []

        for left, right in ordered_pairs(comparison):
            for side, other in ((left, right), (right, left)):
                version = is_version_literal(side) and kinds.raw_version(other)

                if kinds.number_as_text(side) or version:
                    text = ast.unparse(side)
                    found.append(
                        TextualComparison(path, comparison.lineno, text)
                    )

        return found


source_paths = [line for line in sys.stdin.read().split("\n") if line]

for comparison in TextualNumberComparisons().find_in(source_paths):
    location = f"{comparison.path}:{comparison.line_number}"
    reason = "is text, so < and > order it character by character"
    advice = "('10' < '9') - compare numbers or parsed versions"
    message = f"{comparison.text} {reason} {advice}"
    _ = sys.stdout.write(f"{location}: {message}\n")
