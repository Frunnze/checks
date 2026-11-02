import ast
import importlib
import re
import sys
from pathlib import Path
from typing import NamedTuple, Protocol, cast

REGEX_MODULES = frozenset({"re", "regex"})
REGEX_FUNCTIONS = frozenset(
    {
        "compile",
        "match",
        "fullmatch",
        "search",
        "findall",
        "finditer",
        "sub",
        "subn",
        "split",
    }
)
REPEAT_PARTS = 3


class SubPattern(Protocol):
    data: list[tuple[object, object]]


class RegexParser(Protocol):
    def parse(self, pattern: str) -> SubPattern: ...


class RegexConstants(Protocol):
    MAX_REPEAT: object
    MIN_REPEAT: object
    MAXREPEAT: object
    SUBPATTERN: object
    BRANCH: object
    AT: object
    ASSERT: object
    ASSERT_NOT: object


PARSER_MODULE = cast("object", importlib.import_module("re._parser"))
CODES_MODULE = cast("object", importlib.import_module("re._constants"))
PARSER = cast("RegexParser", PARSER_MODULE)
CODES = cast("RegexConstants", CODES_MODULE)
REPEATS = (CODES.MAX_REPEAT, CODES.MIN_REPEAT)
ZERO_WIDTH = (CODES.AT, CODES.ASSERT, CODES.ASSERT_NOT)

type Item = tuple[object, object]


class Repeat(NamedTuple):
    minimum: object
    maximum: object
    body: list[Item]


class CatastrophicRegex(NamedTuple):
    path: str
    line_number: int
    pattern: str


def parts_of(argument: object) -> tuple[object, ...]:
    if isinstance(argument, tuple | list):
        return tuple(cast("tuple[object, ...] | list[object]", argument))

    return ()


def items_of(subpattern: object) -> list[Item]:
    return cast("SubPattern", subpattern).data


def repeat_of(item: Item) -> Repeat | None:
    operation, argument = item
    parts = parts_of(argument)

    if operation not in REPEATS or len(parts) != REPEAT_PARTS:
        return None

    return Repeat(parts[0], parts[1], items_of(parts[2]))


def group_body(item: Item) -> list[Item] | None:
    operation, argument = item
    parts = parts_of(argument)

    if operation != CODES.SUBPATTERN or not parts:
        return None

    return items_of(parts[-1])


def branches_of(item: Item) -> list[list[Item]]:
    operation, argument = item
    parts = parts_of(argument)

    if operation != CODES.BRANCH or not parts:
        return []

    return [items_of(branch) for branch in parts_of(parts[-1])]


def can_be_empty(item: Item) -> bool:
    repeat = repeat_of(item)

    if repeat is not None:
        return repeat.minimum == 0 or all(map(can_be_empty, repeat.body))

    body = group_body(item)

    if body is not None:
        return all(map(can_be_empty, body))

    branches = branches_of(item)

    if branches:
        return any(all(map(can_be_empty, branch)) for branch in branches)

    return item[0] in ZERO_WIDTH


def flattened(items: list[Item]) -> list[Item]:
    found: list[Item] = []

    for item in items:
        body = group_body(item)
        found.extend(flattened(body) if body is not None else [item])

    return found


def is_unbounded(item: Item) -> bool:
    repeat = repeat_of(item)

    return repeat is not None and repeat.maximum == CODES.MAXREPEAT


def is_ambiguous(body: list[Item]) -> bool:
    items = flattened(body)

    for position, item in enumerate(items):
        others = items[:position] + items[position + 1 :]

        if is_unbounded(item) and all(map(can_be_empty, others)):
            return True

    return False


def nested_bodies(item: Item) -> list[list[Item]]:
    repeat = repeat_of(item)

    if repeat is not None:
        return [repeat.body]

    body = group_body(item)

    if body is not None:
        return [body]

    return branches_of(item)


def has_nested_repeat(items: list[Item]) -> bool:
    for item in items:
        repeat = repeat_of(item)

        unbounded = repeat is not None and is_unbounded(item)

        if unbounded and repeat is not None and is_ambiguous(repeat.body):
            return True

        if any(map(has_nested_repeat, nested_bodies(item))):
            return True

    return False


def is_catastrophic(pattern: str) -> bool:
    try:
        parsed = PARSER.parse(pattern)
    except re.error:
        return False

    return has_nested_repeat(parsed.data)


def string_constants(tree: ast.Module) -> dict[str, str]:
    constants: dict[str, str] = {}

    for statement in tree.body:
        if not isinstance(statement, ast.Assign):
            continue

        value = statement.value

        if not isinstance(value, ast.Constant) or not isinstance(
            value.value, str
        ):
            continue

        for target in statement.targets:
            if isinstance(target, ast.Name):
                constants[target.id] = value.value

    return constants


def regex_argument(call: ast.Call) -> ast.expr | None:
    function = call.func

    if not isinstance(function, ast.Attribute) or not call.args:
        return None

    module = function.value
    is_regex_module = isinstance(module, ast.Name) and (
        module.id in REGEX_MODULES
    )

    if is_regex_module and function.attr in REGEX_FUNCTIONS:
        return call.args[0]

    return None


def pattern_of(
    argument: ast.expr | None, constants: dict[str, str]
) -> str | None:
    if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
        return argument.value

    if isinstance(argument, ast.Name):
        return constants.get(argument.id)

    return None


class CatastrophicRegexes:
    def find_in(self, paths: list[str]) -> list[CatastrophicRegex]:
        found: list[CatastrophicRegex] = []

        for path in paths:
            tree = ast.parse(Path(path).read_bytes(), path)
            constants = string_constants(tree)

            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue

                pattern = pattern_of(regex_argument(node), constants)

                if pattern is not None and is_catastrophic(pattern):
                    regex = CatastrophicRegex(path, node.lineno, pattern)
                    found.append(regex)

        return sorted(found)


source_paths = [line for line in sys.stdin.read().split("\n") if line]

for regex in CatastrophicRegexes().find_in(source_paths):
    location = f"{regex.path}:{regex.line_number}"
    problem = f"{regex.pattern!r} nests repeats that can split one text"
    effect = "many ways, so a long non-matching input backtracks for ages"
    _ = sys.stdout.write(f"{location}: {problem} {effect}\n")
