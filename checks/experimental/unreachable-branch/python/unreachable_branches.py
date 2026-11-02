import ast
import builtins
import sys
from pathlib import Path
from typing import NamedTuple

PURE_CALLS = frozenset(
    {"len", "abs", "min", "max", "round", "int", "float", "str", "bool"}
)
TYPE_CHECK = "isinstance"
TYPE_CHECK_ARGUMENTS = 2
CATCH_ALL = "BaseException"
QUALIFIER = "."
LOWER_BOUNDS = (ast.Gt, ast.GtE)
STRICT_BOUNDS = (ast.Gt, ast.Lt)
FLIPPED: dict[type[ast.cmpop], type[ast.cmpop]] = {
    ast.Gt: ast.Lt,
    ast.GtE: ast.LtE,
    ast.Lt: ast.Gt,
    ast.LtE: ast.GtE,
    ast.Eq: ast.Eq,
}

type Number = int | float


class UnreachableBranch(NamedTuple):
    path: str
    line_number: int
    covering_line: int


class Bound(NamedTuple):
    subject: str
    operator: type[ast.cmpop]
    limit: Number


def number_value(expression: ast.expr | None) -> Number | None:
    if not isinstance(expression, ast.Constant):
        return None

    value = expression.value

    if isinstance(value, bool) or not isinstance(value, int | float):
        return None

    return value


def module_assignments(tree: ast.Module) -> list[tuple[str, ast.expr | None]]:
    assignments: list[tuple[str, ast.expr | None]] = []

    for statement in tree.body:
        if isinstance(statement, ast.Assign):
            for target in statement.targets:
                if isinstance(target, ast.Name):
                    assignments.append((target.id, statement.value))
        elif isinstance(statement, ast.AnnAssign) and isinstance(
            statement.target, ast.Name
        ):
            assignments.append((statement.target.id, statement.value))

    return assignments


def number_constants(trees: list[ast.Module]) -> dict[str, Number]:
    values: dict[str, set[Number | None]] = {}

    for tree in trees:
        for name, value in module_assignments(tree):
            values.setdefault(name, set()).add(number_value(value))

    constants: dict[str, Number] = {}

    for name, found in values.items():
        if len(found) == 1:
            value = next(iter(found))

            if value is not None:
                constants[name] = value

    return constants


def type_names(expression: ast.expr) -> list[str]:
    if isinstance(expression, ast.Tuple):
        names: list[str] = []

        for element in expression.elts:
            names.extend(type_names(element))

        return names

    name = dotted_name(expression)

    return [name] if name else []


def dotted_name(expression: ast.expr) -> str:
    if isinstance(expression, ast.Name):
        return expression.id

    if isinstance(expression, ast.Attribute):
        owner = dotted_name(expression.value)
        return f"{owner}.{expression.attr}" if owner else ""

    return ""


def has_impure_call(expression: ast.expr) -> bool:
    for node in ast.walk(expression):
        if not isinstance(node, ast.Call):
            continue

        if not isinstance(node.func, ast.Name):
            return True

        if node.func.id not in PURE_CALLS | {TYPE_CHECK}:
            return True

    return False


def if_chain(statement: ast.If) -> list[ast.If]:
    chain = [statement]
    current = statement

    while len(current.orelse) == 1 and isinstance(current.orelse[0], ast.If):
        current = current.orelse[0]
        chain.append(current)

    return chain


def satisfies(value: Number, bound: Bound) -> bool:
    if bound.operator is ast.Gt:
        return value > bound.limit

    if bound.operator is ast.GtE:
        return value >= bound.limit

    if bound.operator is ast.Lt:
        return value < bound.limit

    if bound.operator is ast.LtE:
        return value <= bound.limit

    return value == bound.limit


def range_inside(inner: Bound, outer: Bound) -> bool:
    if inner.operator is ast.Eq:
        return satisfies(inner.limit, outer)

    inner_is_lower = inner.operator in LOWER_BOUNDS

    if outer.operator is ast.Eq or inner_is_lower != (
        outer.operator in LOWER_BOUNDS
    ):
        return False

    if inner.limit == outer.limit:
        return inner.operator in STRICT_BOUNDS or (
            outer.operator not in STRICT_BOUNDS
        )

    if inner_is_lower:
        return inner.limit > outer.limit

    return inner.limit < outer.limit


def base_names(owner: ast.ClassDef) -> list[str]:
    names: list[str] = []

    for base in owner.bases:
        for name in type_names(base):
            names.append(name.rpartition(QUALIFIER)[2])

    return names


class TypeHierarchy:
    def __init__(self, trees: list[ast.Module]) -> None:
        self._bases: dict[str, list[str]] = {}
        self._ambiguous: set[str] = set()

        for tree in trees:
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    self._define(node.name, base_names(node))

    def _define(self, name: str, bases: list[str]) -> None:
        if name in self._bases and self._bases[name] != bases:
            self._ambiguous.add(name)

        self._bases[name] = bases

    def covers(self, later: list[str], earlier: list[str]) -> bool:
        if not later or not earlier:
            return False

        return all(self._covered(child, earlier) for child in later)

    def _covered(self, child: str, parents: list[str]) -> bool:
        for parent in parents:
            if self._is_subclass(child, parent, set()):
                return True

        return False

    def _is_subclass(self, child: str, parent: str, seen: set[str]) -> bool:
        if child == parent:
            return True

        if QUALIFIER in child or QUALIFIER in parent:
            return False

        if child in self._ambiguous:
            return False

        builtin_child = getattr(builtins, child, None)
        builtin_parent = getattr(builtins, parent, None)

        if isinstance(builtin_child, type) and isinstance(
            builtin_parent, type
        ):
            return issubclass(builtin_child, builtin_parent)

        seen.add(child)

        for base in self._bases.get(child, []):
            if base not in seen and self._is_subclass(base, parent, seen):
                return True

        return False


class Implications:
    def __init__(
        self, constants: dict[str, Number], hierarchy: TypeHierarchy
    ) -> None:
        self._constants: dict[str, Number] = constants
        self._hierarchy: TypeHierarchy = hierarchy

    def implies(self, later: ast.expr, earlier: ast.expr) -> bool:
        if isinstance(later, ast.BoolOp) and isinstance(later.op, ast.And):
            for conjunct in later.values:
                if self.implies(conjunct, earlier):
                    return True

        if isinstance(earlier, ast.BoolOp) and isinstance(earlier.op, ast.Or):
            for disjunct in earlier.values:
                if self.implies(later, disjunct):
                    return True

        if ast.dump(later) == ast.dump(earlier):
            is_constant = isinstance(later, ast.Constant)
            return not is_constant and not has_impure_call(later)

        return (
            self._bound_implies(later, earlier)
            or self._type_implies(later, earlier)
            or containment_implies(later, earlier)
        )

    def _limit(self, expression: ast.expr) -> Number | None:
        if isinstance(expression, ast.Name):
            return self._constants.get(expression.id)

        if isinstance(expression, ast.UnaryOp) and isinstance(
            expression.op, ast.USub
        ):
            limit = self._limit(expression.operand)
            return None if limit is None else -limit

        return number_value(expression)

    def _bound(self, test: ast.expr) -> Bound | None:
        if not isinstance(test, ast.Compare) or len(test.ops) != 1:
            return None

        operator = type(test.ops[0])

        if operator not in FLIPPED:
            return None

        left_limit = self._limit(test.left)
        right_limit = self._limit(test.comparators[0])

        if right_limit is not None and left_limit is None:
            subject, limit = test.left, right_limit
        elif left_limit is not None and right_limit is None:
            subject, limit = test.comparators[0], left_limit
            operator = FLIPPED[operator]
        else:
            return None

        if has_impure_call(subject):
            return None

        return Bound(ast.dump(subject), operator, limit)

    def _bound_implies(self, later: ast.expr, earlier: ast.expr) -> bool:
        later_bound = self._bound(later)
        earlier_bound = self._bound(earlier)

        if later_bound is None or earlier_bound is None:
            return False

        if later_bound.subject != earlier_bound.subject:
            return False

        return range_inside(later_bound, earlier_bound)

    def _type_implies(self, later: ast.expr, earlier: ast.expr) -> bool:
        later_check = type_check(later)
        earlier_check = type_check(earlier)

        if later_check is None or earlier_check is None:
            return False

        if ast.dump(later_check.args[0]) != ast.dump(earlier_check.args[0]):
            return False

        return self._hierarchy.covers(
            type_names(later_check.args[1]), type_names(earlier_check.args[1])
        )


def type_check(test: ast.expr) -> ast.Call | None:
    if not isinstance(test, ast.Call):
        return None

    if len(test.args) != TYPE_CHECK_ARGUMENTS:
        return None

    if not isinstance(test.func, ast.Name) or test.func.id != TYPE_CHECK:
        return None

    if has_impure_call(test.args[0]):
        return None

    return test


def single_comparison(
    test: ast.expr, operator: type[ast.cmpop]
) -> tuple[str, str] | None:
    if not isinstance(test, ast.Compare) or len(test.ops) != 1:
        return None

    if not isinstance(test.ops[0], operator) or has_impure_call(test):
        return None

    return ast.dump(test.left), ast.dump(test.comparators[0])


def containment_implies(later: ast.expr, earlier: ast.expr) -> bool:
    equal = single_comparison(later, ast.Eq)
    contained = single_comparison(earlier, ast.In)

    if equal is None or contained is None:
        return False

    return set(equal) == set(contained)


def handled_types(handler: ast.ExceptHandler) -> list[str]:
    if handler.type is None:
        return [CATCH_ALL]

    return type_names(handler.type)


class UnreachableBranches:
    def find_in(self, paths: list[str]) -> list[UnreachableBranch]:
        trees = [ast.parse(Path(path).read_bytes(), path) for path in paths]
        hierarchy = TypeHierarchy(trees)
        implications = Implications(number_constants(trees), hierarchy)
        found: set[UnreachableBranch] = set()

        for path, tree in zip(paths, trees, strict=True):
            for node in ast.walk(tree):
                if isinstance(node, ast.If):
                    found.update(self._in_chain(path, node, implications))
                elif isinstance(node, ast.Try):
                    found.update(self._in_handlers(path, node, hierarchy))

        return sorted(found)

    def _in_chain(
        self, path: str, statement: ast.If, implications: Implications
    ) -> list[UnreachableBranch]:
        found: list[UnreachableBranch] = []
        chain = if_chain(statement)

        for position, branch in enumerate(chain):
            for earlier in chain[:position]:
                if implications.implies(branch.test, earlier.test):
                    covering_line = earlier.test.lineno
                    found.append(
                        UnreachableBranch(
                            path, branch.test.lineno, covering_line
                        )
                    )
                    break

        return found

    def _in_handlers(
        self, path: str, statement: ast.Try, hierarchy: TypeHierarchy
    ) -> list[UnreachableBranch]:
        found: list[UnreachableBranch] = []

        for position, handler in enumerate(statement.handlers):
            handled = handled_types(handler)

            for earlier in statement.handlers[:position]:
                if hierarchy.covers(handled, handled_types(earlier)):
                    found.append(
                        UnreachableBranch(path, handler.lineno, earlier.lineno)
                    )
                    break

        return found


source_paths = [line for line in sys.stdin.read().split("\n") if line]

for branch in UnreachableBranches().find_in(source_paths):
    location = f"{branch.path}:{branch.line_number}"
    reason = f"line {branch.covering_line} already takes all its cases"
    _ = sys.stdout.write(f"{location}: this branch never runs - {reason}\n")
