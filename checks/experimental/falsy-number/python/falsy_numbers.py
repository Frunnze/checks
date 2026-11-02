import ast
import sys
from pathlib import Path
from typing import NamedTuple

ORDERINGS = (ast.Lt, ast.LtE, ast.Gt, ast.GtE)
NONE_NAMES = frozenset({"None", "Optional"})
NUMBER_TYPES = frozenset({"int", "float", "Decimal", "Fraction", "complex"})
NUMBER_CALLS = frozenset(
    {"len", "abs", "sum", "min", "max", "round", "int", "float", "Decimal"}
)
FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)
SELF = "self"


class FalsyNumber(NamedTuple):
    path: str
    line_number: int
    test: str
    subject: str


def mentions_none(annotation: ast.expr | None) -> bool:
    if annotation is None:
        return False

    for node in ast.walk(annotation):
        if isinstance(node, ast.Constant) and node.value is None:
            return True

        if isinstance(node, ast.Name) and node.id in NONE_NAMES:
            return True

    return False


def mentions_number(annotation: ast.expr | None) -> bool:
    if annotation is None:
        return False

    for node in ast.walk(annotation):
        if isinstance(node, ast.Name) and node.id in NUMBER_TYPES:
            return True

        if isinstance(node, ast.Attribute) and node.attr in NUMBER_TYPES:
            return True

    return False


def is_number_value(expression: ast.expr | None) -> bool:
    if isinstance(expression, ast.Constant):
        value = expression.value
        return isinstance(value, int | float) and not isinstance(value, bool)

    if isinstance(expression, ast.BinOp | ast.UnaryOp):
        return True

    if isinstance(expression, ast.Call):
        function = expression.func
        name = function.id if isinstance(function, ast.Name) else ""
        return name in NUMBER_CALLS

    return False


def is_none(expression: ast.expr | None) -> bool:
    return isinstance(expression, ast.Constant) and expression.value is None


def parameters(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[ast.arg]:
    arguments = function.args

    return [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs]


class ScopeFacts:
    def __init__(self, scope: ast.AST) -> None:
        self.maybe_none: set[str] = set()
        self.numbers: set[str] = set()

        if isinstance(scope, FUNCTIONS):
            for parameter in parameters(scope):
                self._annotated(parameter.arg, parameter.annotation)

        for node in ast.walk(scope):
            if isinstance(node, ast.AnnAssign):
                target = ast.unparse(node.target)
                self._annotated(target, node.annotation)
                self._assigned([target], node.value)
            elif isinstance(node, ast.Assign):
                targets = [ast.unparse(target) for target in node.targets]
                self._assigned(targets, node.value)

        if isinstance(scope, ast.ClassDef):
            self.maybe_none |= {f"{SELF}.{name}" for name in self.maybe_none}
            self.numbers |= {f"{SELF}.{name}" for name in self.numbers}

    def is_optional_number(self, name: str) -> bool:
        return name in self.maybe_none and name in self.numbers

    def _annotated(self, name: str, annotation: ast.expr | None) -> None:
        if mentions_none(annotation):
            self.maybe_none.add(name)

        if mentions_number(annotation):
            self.numbers.add(name)

    def _assigned(self, names: list[str], value: ast.expr | None) -> None:
        if is_none(value):
            self.maybe_none.update(names)

        if is_number_value(value):
            self.numbers.update(names)


def ordered_subjects(comparison: ast.expr) -> set[str]:
    if not isinstance(comparison, ast.Compare):
        return set()

    if not all(isinstance(operator, ORDERINGS) for operator in comparison.ops):
        return set()

    operands = [comparison.left, *comparison.comparators]

    return {ast.unparse(operand) for operand in operands}


def negated(operand: ast.expr) -> str | None:
    if isinstance(operand, ast.UnaryOp) and isinstance(operand.op, ast.Not):
        return ast.unparse(operand.operand)

    return None


class FalsyNumbers:
    def find_in(self, paths: list[str]) -> list[FalsyNumber]:
        found: set[FalsyNumber] = set()

        for path in paths:
            tree = ast.parse(Path(path).read_bytes(), path)

            for scope in ast.walk(tree):
                if isinstance(scope, (*FUNCTIONS, ast.ClassDef)):
                    found.update(self._in_scope(path, scope))

        return sorted(found)

    def _in_scope(self, path: str, scope: ast.AST) -> list[FalsyNumber]:
        facts = ScopeFacts(scope)
        found: list[FalsyNumber] = []

        for node in ast.walk(scope):
            if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
                found.extend(self._in_condition(path, node, facts))

        return found

    def _in_condition(
        self, path: str, condition: ast.BoolOp, facts: ScopeFacts
    ) -> list[FalsyNumber]:
        compared: set[str] = set()

        for operand in condition.values:
            compared |= ordered_subjects(operand)

        found: list[FalsyNumber] = []

        for operand in condition.values:
            subject = negated(operand)

            if subject in compared and facts.is_optional_number(subject):
                test = ast.unparse(operand)
                falsy = FalsyNumber(path, operand.lineno, test, subject)
                found.append(falsy)

        return found


source_paths = [line for line in sys.stdin.read().split("\n") if line]

for falsy in FalsyNumbers().find_in(source_paths):
    location = f"{falsy.path}:{falsy.line_number}"
    problem = f"`{falsy.test}` treats 0 like None"
    reason = f"but {falsy.subject} is compared as a number beside it"
    _ = sys.stdout.write(f"{location}: {problem} {reason}\n")
