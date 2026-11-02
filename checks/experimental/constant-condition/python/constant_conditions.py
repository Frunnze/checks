import ast
import sys
from pathlib import Path
from typing import NamedTuple

IMPURE = (ast.Call, ast.Await, ast.NamedExpr, ast.Yield, ast.YieldFrom)


class ConstantCondition(NamedTuple):
    path: str
    line_number: int
    condition: str
    outcome: str


class Test(NamedTuple):
    subject: str
    value: object


def is_pure(expression: ast.expr) -> bool:
    return not any(isinstance(node, IMPURE) for node in ast.walk(expression))


def literal(expression: ast.expr) -> ast.Constant | None:
    if isinstance(expression, ast.Constant):
        return expression

    if not isinstance(expression, ast.UnaryOp):
        return None

    operand = expression.operand
    is_negative = isinstance(expression.op, ast.USub)

    if not is_negative or not isinstance(operand, ast.Constant):
        return None

    value = operand.value

    if isinstance(value, bool) or not isinstance(value, int | float):
        return None

    return ast.Constant(-value)


def constant_test(
    expression: ast.expr, operator: type[ast.cmpop]
) -> Test | None:
    if not isinstance(expression, ast.Compare) or len(expression.ops) != 1:
        return None

    if not isinstance(expression.ops[0], operator):
        return None

    left = expression.left
    right = expression.comparators[0]
    right_literal = literal(right)
    left_literal = literal(left)

    if right_literal is not None and left_literal is None and is_pure(left):
        return Test(ast.dump(left), right_literal.value)

    if left_literal is not None and right_literal is None and is_pure(right):
        return Test(ast.dump(right), left_literal.value)

    return None


def contradicts(tests: list[Test]) -> bool:
    values_by_subject: dict[str, set[object]] = {}

    for test in tests:
        values = values_by_subject.setdefault(test.subject, set())
        values.add(test.value)

        if len(values) > 1:
            return True

    return False


class ConstantConditions:
    def find_in(self, paths: list[str]) -> list[ConstantCondition]:
        found: list[ConstantCondition] = []

        for path in paths:
            tree = ast.parse(Path(path).read_bytes(), path)

            for node in ast.walk(tree):
                if isinstance(node, ast.BoolOp):
                    finding = self._outcome(path, node)

                    if finding is not None:
                        found.append(finding)

        return sorted(found)

    def _outcome(
        self, path: str, condition: ast.BoolOp
    ) -> ConstantCondition | None:
        if isinstance(condition.op, ast.Or):
            operator: type[ast.cmpop] = ast.NotEq
            outcome = "always true"
        else:
            operator = ast.Eq
            outcome = "always false"

        tests: list[Test] = []

        for value in condition.values:
            test = constant_test(value, operator)

            if test is not None:
                tests.append(test)

        if not contradicts(tests):
            return None

        text = ast.unparse(condition)
        return ConstantCondition(path, condition.lineno, text, outcome)


source_paths = [line for line in sys.stdin.read().split("\n") if line]

for condition in ConstantConditions().find_in(source_paths):
    location = f"{condition.path}:{condition.line_number}"
    problem = f"{condition.condition} is {condition.outcome}"
    advice = "- swap and/or, or use in / not in"
    _ = sys.stdout.write(f"{location}: {problem} {advice}\n")
