import ast
import re
import sys
from itertools import pairwise
from pathlib import Path
from typing import NamedTuple, cast

WORD = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")
ABSOLUTE = "abs()"
ABSOLUTE_FUNCTION = "abs"
PLUS_ONE = "+ 1"
MINUS_ONE = "- 1"
STEP = 1
STATEMENT_BLOCKS = ("body", "orelse", "finalbody")
BLOCK_HOLDERS = (ast.stmt, ast.Module, ast.excepthandler, ast.match_case)
SKIPPED_FIELDS = frozenset({"ctx", "type_comment"})
ASSIGNMENTS = (ast.Assign, ast.AnnAssign, ast.AugAssign)
SHOWN_LENGTH = 60
CUT_MARK = "..."
AXES = frozenset(
    frozenset(pair)
    for pair in (
        ("x", "y"),
        ("row", "column"),
        ("rows", "columns"),
        ("row", "col"),
        ("rows", "cols"),
        ("width", "height"),
        ("top", "left"),
        ("bottom", "right"),
        ("horizontal", "vertical"),
        ("w", "h"),
        ("xs", "ys"),
        ("dx", "dy"),
        ("cx", "cy"),
    )
)
OPPOSITES = frozenset(
    frozenset(pair)
    for pair in (
        ("first", "last"),
        ("start", "end"),
        ("begin", "end"),
        ("min", "max"),
        ("lower", "upper"),
        ("low", "high"),
        ("head", "tail"),
        ("previous", "next"),
        ("prev", "next"),
        ("before", "after"),
        ("above", "below"),
        ("top", "bottom"),
        ("left", "right"),
        ("lo", "hi"),
        ("near", "far"),
        ("inner", "outer"),
    )
)

type Assignment = ast.Assign | ast.AnnAssign | ast.AugAssign
type Side = ast.stmt | ast.expr
type WordPairs = set[frozenset[str]]


class Unwrapping(NamedTuple):
    wrapper: ast.expr
    inner: ast.expr
    label: str


class UnevenTwin(NamedTuple):
    path: str
    line_number: int
    statement: str
    label: str
    twin_line_number: int


def words_of(name: str) -> list[str]:
    return [match.group().lower() for match in WORD.finditer(name)]


def differing_words(original: str, renamed: str) -> WordPairs:
    old_words = words_of(original)
    new_words = words_of(renamed)

    if len(old_words) != len(new_words):
        joined = (" ".join(old_words), " ".join(new_words))
        return {frozenset(joined)}

    return {
        frozenset((old, new))
        for old, new in zip(old_words, new_words, strict=True)
        if old != new
    }


class Correspondence:
    def __init__(self, unwrapping: Unwrapping) -> None:
        self._unwrapping: Unwrapping = unwrapping
        self._forward: dict[str, str] = {}
        self._backward: dict[str, str] = {}

    def renamed_pairs(self) -> WordPairs:
        pairs: WordPairs = set()

        for original, renamed in self._forward.items():
            if original != renamed:
                pairs.update(differing_words(original, renamed))

        return pairs

    def matches(self, value: object, other: object) -> bool:
        if isinstance(value, list):
            items = cast("list[object]", value)
            return isinstance(other, list) and self._lists_match(
                items, cast("list[object]", other)
            )

        if isinstance(value, ast.AST):
            return isinstance(other, ast.AST) and self._nodes_match(
                value, other
            )

        return value == other

    def _lists_match(self, items: list[object], others: list[object]) -> bool:
        if len(items) != len(others):
            return False

        return all(
            self.matches(item, other)
            for item, other in zip(items, others, strict=True)
        )

    def _nodes_match(self, node: ast.AST, other: ast.AST) -> bool:
        if node is self._unwrapping.wrapper:
            node = self._unwrapping.inner

        if type(node) is not type(other):
            return False

        if isinstance(node, ast.Name) and isinstance(other, ast.Name):
            return self._bind(node.id, other.id)

        if isinstance(node, ast.Attribute):
            return self._attributes_match(node, cast("ast.Attribute", other))

        if isinstance(node, ast.Constant) and isinstance(other, ast.Constant):
            return node.value == other.value

        return self._fields_match(node, other)

    def _attributes_match(
        self, attribute: ast.Attribute, other: ast.Attribute
    ) -> bool:
        same_name = self._bind(attribute.attr, other.attr)

        return same_name and self._nodes_match(attribute.value, other.value)

    def _fields_match(self, node: ast.AST, other: ast.AST) -> bool:
        fields: list[tuple[str, object]] = list(ast.iter_fields(node))
        other_fields: list[tuple[str, object]] = list(ast.iter_fields(other))

        for (name, value), (_, other_value) in zip(
            fields, other_fields, strict=True
        ):
            if name not in SKIPPED_FIELDS and not self.matches(
                value, other_value
            ):
                return False

        return True

    def _bind(self, name: str, other: str) -> bool:
        forward = self._forward.setdefault(name, other)
        backward = self._backward.setdefault(other, name)

        return forward == other and backward == name


def renamed_pairs(
    unwrapping: Unwrapping, value: object, other: object
) -> WordPairs:
    correspondence = Correspondence(unwrapping)

    if not correspondence.matches(value, other):
        return set()

    return correspondence.renamed_pairs()


def unwrapping_of(node: ast.AST) -> Unwrapping | None:
    if isinstance(node, ast.Call) and is_absolute_call(node):
        return Unwrapping(node, node.args[0], ABSOLUTE)

    if not isinstance(node, ast.BinOp) or not is_step(node.right):
        return None

    if isinstance(node.op, ast.Add):
        return Unwrapping(node, node.left, PLUS_ONE)

    if isinstance(node.op, ast.Sub):
        return Unwrapping(node, node.left, MINUS_ONE)

    return None


def is_absolute_call(call: ast.Call) -> bool:
    function = call.func
    is_absolute = isinstance(function, ast.Name) and (
        function.id == ABSOLUTE_FUNCTION
    )

    return is_absolute and len(call.args) == 1 and not call.keywords


def is_step(expression: ast.expr) -> bool:
    return isinstance(expression, ast.Constant) and expression.value == STEP


def subscripted_nodes(side: ast.AST) -> set[int]:
    inside: set[int] = set()

    for node in ast.walk(side):
        if isinstance(node, ast.Subscript):
            inside.update(id(child) for child in ast.walk(node.slice))

    return inside


def single_comparison(side: ast.AST) -> ast.Compare | None:
    node = side.value if isinstance(side, ast.Assign | ast.AnnAssign) else side

    if isinstance(node, ast.Compare) and len(node.comparators) == 1:
        return node

    return None


def shares_bound(
    wrapped: ast.AST, plain: ast.AST, unwrapping: Unwrapping
) -> bool:
    first = single_comparison(wrapped)
    second = single_comparison(plain)

    if first is None or second is None:
        return False

    difference = unwrapping.inner
    is_difference = isinstance(difference, ast.BinOp) and isinstance(
        difference.op, ast.Sub
    )

    if first.left is not unwrapping.wrapper or not is_difference:
        return False

    first_bound = ast.unparse(first.comparators[0])

    return first_bound == ast.unparse(second.comparators[0])


def crosses_axes(pairs: WordPairs) -> bool:
    has_axis = any(pair in AXES for pair in pairs)

    return has_axis and not any(pair in OPPOSITES for pair in pairs)


def assignment_sides(
    statement: Assignment,
) -> tuple[list[ast.expr], ast.expr | None]:
    if isinstance(statement, ast.Assign):
        return statement.targets, statement.value

    return [statement.target], statement.value


def both_sides_cross(
    wrapped: Assignment, plain: Assignment, unwrapping: Unwrapping
) -> bool:
    wrapped_targets, wrapped_value = assignment_sides(wrapped)
    plain_targets, plain_value = assignment_sides(plain)
    targets = renamed_pairs(unwrapping, wrapped_targets, plain_targets)
    values = renamed_pairs(unwrapping, wrapped_value, plain_value)
    target_axis = any(pair in AXES for pair in targets)

    return target_axis and any(pair in AXES for pair in values)


def steps_differ(
    wrapped: ast.AST, plain: ast.AST, unwrapping: Unwrapping
) -> bool:
    pairs = renamed_pairs(unwrapping, wrapped, plain)

    if not crosses_axes(pairs):
        return False

    if isinstance(wrapped, ASSIGNMENTS) and isinstance(plain, ASSIGNMENTS):
        return both_sides_cross(wrapped, plain, unwrapping)

    return True


def absolutes_differ(
    wrapped: ast.AST, plain: ast.AST, unwrapping: Unwrapping
) -> bool:
    if not renamed_pairs(unwrapping, wrapped, plain):
        return False

    return shares_bound(wrapped, plain, unwrapping)


def lacks_wrapper(wrapped: ast.AST, plain: ast.AST) -> Unwrapping | None:
    subscripted: set[int] | None = None

    for node in ast.walk(wrapped):
        unwrapping = unwrapping_of(node)

        if unwrapping is None:
            continue

        if unwrapping.label == ABSOLUTE:
            if absolutes_differ(wrapped, plain, unwrapping):
                return unwrapping

            continue

        if subscripted is None:
            subscripted = subscripted_nodes(wrapped)

        if id(node) in subscripted:
            continue

        if steps_differ(wrapped, plain, unwrapping):
            return unwrapping

    return None


def statement_blocks(node: ast.AST) -> list[list[ast.stmt]]:
    blocks: list[list[ast.stmt]] = []

    for field in STATEMENT_BLOCKS:
        block: object = getattr(node, field, None)

        if isinstance(block, list):
            blocks.append(cast("list[ast.stmt]", block))

    return blocks


def assignment_pairs(node: ast.AST) -> list[tuple[Side, Side]]:
    found: list[tuple[Side, Side]] = []

    for block in statement_blocks(node):
        for first, second in pairwise(block):
            if isinstance(first, ASSIGNMENTS) and type(first) is type(second):
                found.append((first, second))

    return found


def parallel_pairs(tree: ast.Module) -> list[tuple[Side, Side]]:
    found: list[tuple[Side, Side]] = []

    for node in ast.walk(tree):
        if isinstance(node, BLOCK_HOLDERS):
            found.extend(assignment_pairs(node))
        elif isinstance(node, ast.BoolOp):
            found.extend(pairwise(node.values))

    return found


def shortened(text: str) -> str:
    if len(text) <= SHOWN_LENGTH:
        return text

    return text[: SHOWN_LENGTH - len(CUT_MARK)] + CUT_MARK


def uneven_twin(path: str, first: Side, second: Side) -> UnevenTwin | None:
    for wrapped, plain in ((first, second), (second, first)):
        unwrapping = lacks_wrapper(wrapped, plain)

        if unwrapping is not None:
            return UnevenTwin(
                path,
                plain.lineno,
                shortened(ast.unparse(plain)),
                unwrapping.label,
                wrapped.lineno,
            )

    return None


class UnevenTwins:
    def find_in(self, paths: list[str]) -> list[UnevenTwin]:
        found: dict[tuple[str, int], UnevenTwin] = {}

        for path in paths:
            tree = ast.parse(Path(path).read_bytes(), path)

            for first, second in parallel_pairs(tree):
                twin = uneven_twin(path, first, second)

                if twin is not None:
                    location = (twin.path, twin.line_number)
                    _ = found.setdefault(location, twin)

        return sorted(found.values())


source_paths = [line for line in sys.stdin.read().split("\n") if line]

for uneven in UnevenTwins().find_in(source_paths):
    location = f"{uneven.path}:{uneven.line_number}"
    twin = f"its twin on line {uneven.twin_line_number}"
    lacks = f"{uneven.statement} lacks the {uneven.label} of {twin}"
    fix = f"add the {uneven.label} here or drop it from the twin"
    _ = sys.stdout.write(f"{location}: {lacks} - {fix}\n")
