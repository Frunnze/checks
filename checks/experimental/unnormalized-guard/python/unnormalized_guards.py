import ast
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import NamedTuple, cast

STRIPPING_METHODS = frozenset({"strip", "lstrip", "rstrip"})
FOLDING_METHODS = frozenset({"lower", "casefold", "upper"})
NORMALIZING_METHODS = STRIPPING_METHODS | FOLDING_METHODS
UPPERCASING_METHOD = "upper"
GUARD_EXITS = (ast.Raise, ast.Return, ast.Continue, ast.Break)
EQUALITY = (ast.Eq,)
TEXT_COMPARISONS = (ast.Eq, ast.NotEq, ast.In, ast.NotIn)
LITERAL_COLLECTIONS = (ast.Set, ast.Tuple, ast.List)
BLOCK_FIELDS = ("body", "orelse", "finalbody")
LENGTH_FUNCTION = "len"
EMPTY_TEXT = ""
EMPTY_LENGTH = 0
NOT_READ = -1

type Block = list[ast.stmt]
type ComparisonOperators = tuple[type[ast.cmpop], ...]


class Casing(NamedTuple):
    name: str
    fold: Callable[[str], str]
    opposite: Callable[[str], str]


LOWERCASE = Casing("lowercase", str.lower, str.upper)
UPPERCASE = Casing("uppercase", str.upper, str.lower)


class Assignment(NamedTuple):
    name: str
    value: ast.expr


class Normalization(NamedTuple):
    normalized: str
    raw: str
    methods: frozenset[str]
    assignment: str


class Comparison(NamedTuple):
    left: ast.expr
    right: ast.expr


class UnnormalizedGuard(NamedTuple):
    path: str
    line_number: int
    reason: str


def assignment_of(statement: ast.stmt) -> Assignment | None:
    if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
        target = statement.targets[0]

        if isinstance(target, ast.Name):
            return Assignment(target.id, statement.value)

        return None

    if not isinstance(statement, ast.AnnAssign) or statement.value is None:
        return None

    if isinstance(statement.target, ast.Name):
        return Assignment(statement.target.id, statement.value)

    return None


def normalizing_method(expression: ast.expr) -> ast.Attribute | None:
    if not isinstance(expression, ast.Call):
        return None

    if expression.args or expression.keywords:
        return None

    method = expression.func

    if not isinstance(method, ast.Attribute):
        return None

    if method.attr not in NORMALIZING_METHODS:
        return None

    return method


def normalization_of(statement: ast.stmt) -> Normalization | None:
    assignment = assignment_of(statement)

    if assignment is None:
        return None

    methods: set[str] = set()
    receiver = assignment.value
    method = normalizing_method(receiver)

    while method is not None:
        methods.add(method.attr)
        receiver = method.value
        method = normalizing_method(receiver)

    if not methods or not isinstance(receiver, ast.Name):
        return None

    if receiver.id == assignment.name:
        return None

    text = f"{assignment.name} = {ast.unparse(assignment.value)}"

    return Normalization(
        assignment.name, receiver.id, frozenset(methods), text
    )


def is_name(expression: ast.expr, name: str) -> bool:
    return isinstance(expression, ast.Name) and expression.id == name


def is_constant(expression: ast.expr, constant: object) -> bool:
    return isinstance(expression, ast.Constant) and (
        expression.value == constant
    )


def is_length_of(expression: ast.expr, name: str) -> bool:
    if not isinstance(expression, ast.Call):
        return False

    if not is_name(expression.func, LENGTH_FUNCTION) or not expression.args:
        return False

    return is_name(expression.args[0], name)


def single_comparison(
    test: ast.expr, operators: ComparisonOperators
) -> Comparison | None:
    if not isinstance(test, ast.Compare) or len(test.ops) != 1:
        return None

    if not isinstance(test.ops[0], operators):
        return None

    return Comparison(test.left, test.comparators[0])


def tests_emptiness(test: ast.expr, name: str) -> bool:
    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        return is_name(test.operand, name)

    comparison = single_comparison(test, EQUALITY)

    if comparison is None:
        return False

    if is_name(comparison.left, name):
        return is_constant(comparison.right, EMPTY_TEXT)

    is_length = is_length_of(comparison.left, name)

    return is_length and is_constant(comparison.right, EMPTY_LENGTH)


def literal_texts(expression: ast.expr) -> list[str]:
    elements = [expression]

    if isinstance(expression, LITERAL_COLLECTIONS):
        elements = expression.elts

    texts: list[str] = []

    for element in elements:
        if not isinstance(element, ast.Constant):
            return []

        if not isinstance(element.value, str):
            return []

        texts.append(element.value)

    return texts


def has_casing(text: str, casing: Casing) -> bool:
    return text == casing.fold(text) and text != casing.opposite(text)


def casing_of(methods: frozenset[str]) -> Casing:
    if UPPERCASING_METHOD in methods:
        return UPPERCASE

    return LOWERCASE


def compares_folded_text(test: ast.expr, name: str, casing: Casing) -> bool:
    comparison = single_comparison(test, TEXT_COMPARISONS)

    if comparison is None or not is_name(comparison.left, name):
        return False

    texts = literal_texts(comparison.right)

    return bool(texts) and all(has_casing(text, casing) for text in texts)


def guard_conditions(statement: ast.stmt) -> list[ast.expr]:
    if not isinstance(statement, ast.If):
        return []

    if not isinstance(statement.body[-1], GUARD_EXITS):
        return []

    if isinstance(statement.test, ast.BoolOp):
        return statement.test.values

    return [statement.test]


def name_used_as(node: ast.AST, context: type[ast.expr_context]) -> str:
    if isinstance(node, ast.Name) and isinstance(node.ctx, context):
        return node.id

    return ""


def binds_any(statement: ast.stmt, names: frozenset[str]) -> bool:
    nodes = ast.walk(statement)

    return any(name_used_as(node, ast.Store) in names for node in nodes)


def reads(statement: ast.stmt, name: str) -> bool:
    nodes = ast.walk(statement)

    return any(name_used_as(node, ast.Load) == name for node in nodes)


def last_reading_index(block: Block, start: int, name: str) -> int:
    last_index = NOT_READ

    for index in range(start, len(block)):
        if reads(block[index], name):
            last_index = index

    return last_index


def stripped_reason(normalization: Normalization) -> str:
    raw = normalization.raw
    normalized = normalization.normalized

    return (
        f"the guard tests {raw} for emptiness but the code goes on with"
        f" {normalization.assignment} - a whitespace-only {raw} passes; test"
        f" {normalized} instead"
    )


def folded_reason(normalization: Normalization, casing: Casing) -> str:
    raw = normalization.raw
    normalized = normalization.normalized

    return (
        f"the guard compares {raw} with {casing.name} text but the code"
        f" goes on with {normalization.assignment} - other casings of {raw}"
        " slip past;"
        f" compare {normalized} instead"
    )


def condition_reason(
    condition: ast.expr, normalization: Normalization
) -> str | None:
    methods = normalization.methods
    raw = normalization.raw

    if methods & STRIPPING_METHODS and tests_emptiness(condition, raw):
        return stripped_reason(normalization)

    casing = casing_of(methods)

    if methods & FOLDING_METHODS and compares_folded_text(
        condition, raw, casing
    ):
        return folded_reason(normalization, casing)

    return None


class BlockGuards:
    def __init__(self, path: str, block: Block) -> None:
        self._path: str = path
        self._block: Block = block
        self.found: list[UnnormalizedGuard] = []

    def check(self) -> None:
        for index, statement in enumerate(self._block):
            normalization = normalization_of(statement)

            if normalization is not None:
                self._check_guards_after(index, normalization)

    def _check_guards_after(
        self, index: int, normalization: Normalization
    ) -> None:
        names = frozenset({normalization.raw, normalization.normalized})
        start = index + 1
        last_read = last_reading_index(
            self._block, start, normalization.normalized
        )

        for later_index in range(start, len(self._block)):
            later = self._block[later_index]

            if binds_any(later, names):
                return

            if later_index < last_read:
                self._check_guard(later, normalization)

    def _check_guard(
        self, statement: ast.stmt, normalization: Normalization
    ) -> None:
        for condition in guard_conditions(statement):
            reason = condition_reason(condition, normalization)

            if reason is not None:
                guard = UnnormalizedGuard(self._path, condition.lineno, reason)
                self.found.append(guard)


def statement_block(node: ast.AST, field: str) -> Block:
    block: object = getattr(node, field, None)

    if not isinstance(block, list):
        return []

    statements: Block = []

    for statement in cast("list[object]", block):
        if isinstance(statement, ast.stmt):
            statements.append(statement)

    return statements


def statement_blocks(tree: ast.AST) -> Iterator[Block]:
    for node in ast.walk(tree):
        for field in BLOCK_FIELDS:
            block = statement_block(node, field)

            if block:
                yield block


class UnnormalizedGuards:
    def find_in(self, paths: list[str]) -> list[UnnormalizedGuard]:
        found: set[UnnormalizedGuard] = set()

        for path in paths:
            tree = ast.parse(Path(path).read_bytes(), path)

            for block in statement_blocks(tree):
                guards = BlockGuards(path, block)
                guards.check()
                found.update(guards.found)

        return sorted(found)


source_paths = [line for line in sys.stdin.read().split("\n") if line]

for guard in UnnormalizedGuards().find_in(source_paths):
    location = f"{guard.path}:{guard.line_number}"
    _ = sys.stdout.write(f"{location}: {guard.reason}\n")
