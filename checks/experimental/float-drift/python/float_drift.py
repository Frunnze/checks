import ast
import sys
from decimal import Decimal
from pathlib import Path
from typing import NamedTuple

STEPS = (ast.Add, ast.Sub)
COMPARISONS = (ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq, ast.NotEq)
OWNERS = (ast.ClassDef, ast.Module)

type Owner = ast.ClassDef | ast.Module


class DriftingTotal(NamedTuple):
    path: str
    line_number: int
    total: str
    step: str
    comparison_line: int


class Step(NamedTuple):
    line_number: int
    amount: str


def is_inexact_float(value: object) -> bool:
    if not isinstance(value, float):
        return False

    return Decimal(repr(value)) != Decimal(value)


def float_constants(owner: Owner) -> dict[str, float]:
    constants: dict[str, float] = {}

    for statement in owner.body:
        value: ast.expr | None = None
        targets: list[ast.expr] = []

        if isinstance(statement, ast.Assign):
            value, targets = statement.value, statement.targets
        elif isinstance(statement, ast.AnnAssign):
            value, targets = statement.value, [statement.target]

        if isinstance(value, ast.Constant) and isinstance(value.value, float):
            for target in targets:
                if isinstance(target, ast.Name):
                    constants[target.id] = value.value

    return constants


def step_value(step: ast.expr, constants: dict[str, float]) -> object:
    if isinstance(step, ast.Constant):
        return step.value

    if isinstance(step, ast.Name):
        return constants.get(step.id)

    if isinstance(step, ast.Attribute):
        return constants.get(step.attr)

    return None


def compared_operands(comparison: ast.Compare) -> list[ast.expr]:
    if not isinstance(comparison.ops[0], COMPARISONS):
        return []

    return [comparison.left, *comparison.comparators]


class OwnedTotals:
    def __init__(self, owner: Owner, constants: dict[str, float]) -> None:
        self.steps: dict[str, Step] = {}
        self.comparisons: dict[str, int] = {}

        for node in ast.walk(owner):
            if isinstance(node, ast.AugAssign) and isinstance(node.op, STEPS):
                if is_inexact_float(step_value(node.value, constants)):
                    step = Step(node.lineno, ast.unparse(node.value))
                    self.steps[ast.unparse(node.target)] = step
            elif isinstance(node, ast.Compare):
                for operand in compared_operands(node):
                    text = ast.unparse(operand)
                    _ = self.comparisons.setdefault(text, node.lineno)


class FloatDrift:
    def find_in(self, paths: list[str]) -> list[DriftingTotal]:
        found: set[DriftingTotal] = set()

        for path in paths:
            tree = ast.parse(Path(path).read_bytes(), path)
            module_constants = float_constants(tree)

            for node in ast.walk(tree):
                if isinstance(node, OWNERS):
                    constants = module_constants | float_constants(node)
                    totals = OwnedTotals(node, constants)
                    found.update(self._in_owner(path, totals))

        return sorted(found)

    def _in_owner(
        self, path: str, owner: OwnedTotals
    ) -> list[DriftingTotal]:
        found: list[DriftingTotal] = []

        for total, step in owner.steps.items():
            comparison_line = owner.comparisons.get(total)

            if comparison_line is not None:
                found.append(
                    DriftingTotal(
                        path,
                        step.line_number,
                        total,
                        step.amount,
                        comparison_line,
                    )
                )

        return found


source_paths = [line for line in sys.stdin.read().split("\n") if line]

for drifting in FloatDrift().find_in(source_paths):
    location = f"{drifting.path}:{drifting.line_number}"
    problem = f"{drifting.total} steps by {drifting.step}"
    reason = "which a binary float cannot hold exactly"
    where = f"and is compared on line {drifting.comparison_line}"
    _ = sys.stdout.write(f"{location}: {problem}, {reason}, {where}\n")
