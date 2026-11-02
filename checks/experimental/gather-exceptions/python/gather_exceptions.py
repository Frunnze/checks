import ast
import re
import sys
from collections.abc import Iterable, Iterator
from collections.abc import Set as AbstractSet
from enum import Enum
from pathlib import Path
from typing import NamedTuple

EXCEPTION_TYPES = frozenset({"BaseException", "Exception"})
ONLY_EXCEPTION = frozenset({"Exception"})
GATHER = "gather"
RETURN_EXCEPTIONS = "return_exceptions"
TYPE_ALIAS = "TypeAlias"
INSTANCE_TEST = "isinstance"
INSTANCE_TEST_ARGUMENTS = 2
ZIP = "zip"
ENUMERATE = "enumerate"
ENUMERATED_PAIR = 2
ENUMERATED_ITEM = 1
EARLY_EXITS = (ast.Continue, ast.Return, ast.Raise)
WORD = re.compile(r"\w+")
TYPED_PROBLEM = (
    "{name} is typed to hold exceptions, but gather without"
    " return_exceptions=True raises the first one instead of returning it"
    " - pass return_exceptions=True or drop the exception from the type"
)
NARROW_PROBLEM = (
    "{name} comes from gather(return_exceptions=True), which also returns"
    " BaseException such as CancelledError, and testing only Exception"
    " passes it on as a result - test BaseException instead"
)

type FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef
type LoopNode = ast.For | ast.comprehension
type Statements = list[ast.stmt]
type AliasDefinitions = dict[str, list[ast.expr]]


class Gathering(Enum):
    RAISES = "raises"
    RETURNS = "returns"
    UNKNOWN = "unknown"


class Gathered(NamedTuple):
    line_number: int
    name: str
    annotation: ast.expr | None
    gathering: Gathering


class ExceptionTest(NamedTuple):
    call: ast.Call
    subject: str


class GatherMisuse(NamedTuple):
    path: str
    line_number: int
    name: str
    problem: str


def parse(path: str) -> ast.Module:
    return ast.parse(Path(path).read_bytes(), path)


def last_name(expression: ast.expr) -> str | None:
    if isinstance(expression, ast.Name):
        return expression.id

    if isinstance(expression, ast.Attribute):
        return expression.attr

    return None


def annotation_words(annotation: ast.expr) -> Iterator[str]:
    for node in ast.walk(annotation):
        if isinstance(node, ast.Name):
            yield node.id
        elif isinstance(node, ast.Attribute):
            yield node.attr
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield from WORD.findall(node.value)


def holds_exceptions(word: str, aliases: AbstractSet[str]) -> bool:
    return word in EXCEPTION_TYPES or word in aliases


def mentions_exception(
    annotation: ast.expr, aliases: AbstractSet[str]
) -> bool:
    words = annotation_words(annotation)

    return any(holds_exceptions(word, aliases) for word in words)


def alias_definition(statement: ast.stmt) -> tuple[str, ast.expr] | None:
    if isinstance(statement, ast.TypeAlias):
        return statement.name.id, statement.value

    if not isinstance(statement, ast.AnnAssign) or statement.value is None:
        return None

    if not isinstance(statement.target, ast.Name):
        return None

    if last_name(statement.annotation) != TYPE_ALIAS:
        return None

    return statement.target.id, statement.value


def add_alias_definitions(
    tree: ast.Module, definitions: AliasDefinitions
) -> None:
    for statement in tree.body:
        definition = alias_definition(statement)

        if definition is not None:
            name, value = definition
            definitions.setdefault(name, []).append(value)


def exception_aliases(definitions: AliasDefinitions) -> frozenset[str]:
    holding: set[str] = set()
    is_growing = True

    while is_growing:
        is_growing = False

        for name, values in definitions.items():
            if name in holding:
                continue

            if any(mentions_exception(value, holding) for value in values):
                holding.add(name)
                is_growing = True

    return frozenset(holding)


def keyword_gathering(value: ast.expr) -> Gathering:
    if not isinstance(value, ast.Constant):
        return Gathering.UNKNOWN

    if value.value is True:
        return Gathering.RETURNS

    if value.value is False:
        return Gathering.RAISES

    return Gathering.UNKNOWN


def gathering(expression: ast.expr) -> Gathering | None:
    call = expression

    if isinstance(expression, ast.Await):
        call = expression.value

    if not isinstance(call, ast.Call) or last_name(call.func) != GATHER:
        return None

    for keyword in call.keywords:
        if keyword.arg == RETURN_EXCEPTIONS:
            return keyword_gathering(keyword.value)

    if any(keyword.arg is None for keyword in call.keywords):
        return Gathering.UNKNOWN

    return Gathering.RAISES


def gathered(node: ast.AST) -> Gathered | None:
    if isinstance(node, ast.Assign) and len(node.targets) == 1:
        target, value, annotation = node.targets[0], node.value, None
    elif isinstance(node, ast.AnnAssign) and node.value is not None:
        target, value, annotation = node.target, node.value, node.annotation
    else:
        return None

    mode = gathering(value)

    if mode is None or not isinstance(target, ast.Name):
        return None

    return Gathered(node.lineno, target.id, annotation, mode)


def exception_only_test(node: ast.AST) -> ExceptionTest | None:
    if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
        return None

    if node.func.id != INSTANCE_TEST:
        return None

    if len(node.args) != INSTANCE_TEST_ARGUMENTS:
        return None

    subject, types = node.args
    type_names = frozenset(
        name.id for name in ast.walk(types) if isinstance(name, ast.Name)
    )

    if not isinstance(subject, ast.Name) or type_names != ONLY_EXCEPTION:
        return None

    return ExceptionTest(node, subject.id)


def is_name(expression: ast.expr, name: str) -> bool:
    return isinstance(expression, ast.Name) and expression.id == name


def zipped_items(
    arguments: list[ast.expr], elements: list[ast.expr], collection: str
) -> list[ast.expr]:
    if len(arguments) != len(elements):
        return []

    return [
        element
        for argument, element in zip(arguments, elements, strict=True)
        if is_name(argument, collection)
    ]


def enumerated_items(
    arguments: list[ast.expr], elements: list[ast.expr], collection: str
) -> list[ast.expr]:
    if not arguments or not is_name(arguments[0], collection):
        return []

    if len(elements) != ENUMERATED_PAIR:
        return []

    return [elements[ENUMERATED_ITEM]]


def item_targets(loop: LoopNode, collection: str) -> list[ast.expr]:
    iterable = loop.iter

    if is_name(iterable, collection):
        return [loop.target]

    if not isinstance(iterable, ast.Call):
        return []

    if not isinstance(loop.target, ast.Tuple | ast.List):
        return []

    if is_name(iterable.func, ZIP):
        return zipped_items(iterable.args, loop.target.elts, collection)

    if is_name(iterable.func, ENUMERATE):
        return enumerated_items(iterable.args, loop.target.elts, collection)

    return []


def item_names(loops: list[LoopNode], collection: str) -> set[str]:
    names = {collection}

    for loop in loops:
        for target in item_targets(loop, collection):
            for node in ast.walk(target):
                if isinstance(node, ast.Name):
                    names.add(node.id)

    return names


def child_blocks(node: ast.AST) -> list[Statements]:
    if isinstance(node, ast.If | ast.For | ast.AsyncFor | ast.While):
        return [node.body, node.orelse]

    if isinstance(node, ast.Try | ast.TryStar):
        return [node.body, node.orelse, node.finalbody]

    if isinstance(
        node,
        ast.FunctionDef
        | ast.AsyncFunctionDef
        | ast.ClassDef
        | ast.With
        | ast.AsyncWith
        | ast.ExceptHandler
        | ast.match_case,
    ):
        return [node.body]

    return []


def statements_after(
    function: FunctionNode, statement: ast.stmt
) -> Statements:
    for node in ast.walk(function):
        for block in child_blocks(node):
            for index, candidate in enumerate(block):
                if candidate is statement:
                    return block[index + 1:]

    return []


def reads_name(roots: Iterable[ast.AST], name: str) -> bool:
    for root in roots:
        for node in ast.walk(root):
            if not isinstance(node, ast.Name) or node.id != name:
                continue

            if isinstance(node.ctx, ast.Load):
                return True

    return False


def is_negation_of(condition: ast.expr, call: ast.Call) -> bool:
    if not isinstance(condition, ast.UnaryOp):
        return False

    return isinstance(condition.op, ast.Not) and condition.operand is call


def exits_early(statements: Statements) -> bool:
    return bool(statements) and isinstance(statements[-1], EARLY_EXITS)


class FunctionFacts(NamedTuple):
    function: FunctionNode
    gathered: list[Gathered]
    tests: list[ExceptionTest]
    loops: list[LoopNode]
    branches: list[ast.If]


def function_facts(function: FunctionNode) -> FunctionFacts:
    facts = FunctionFacts(function, [], [], [], [])

    for node in ast.walk(function):
        assignment = gathered(node)
        test = exception_only_test(node)

        if assignment is not None:
            facts.gathered.append(assignment)

        if test is not None:
            facts.tests.append(test)

        if isinstance(node, ast.For | ast.comprehension):
            facts.loops.append(node)

        if isinstance(node, ast.If):
            facts.branches.append(node)

    return facts


def branch_uses_result(
    facts: FunctionFacts, branch: ast.If, test: ExceptionTest
) -> bool:
    if is_negation_of(branch.test, test.call):
        return reads_name(branch.body, test.subject)

    if branch.test is not test.call:
        return False

    if reads_name(branch.orelse, test.subject):
        return True

    if not exits_early(branch.body):
        return False

    later = statements_after(facts.function, branch)

    return reads_name(later, test.subject)


def filters_exceptions_out(loop: LoopNode, test: ExceptionTest) -> bool:
    if not isinstance(loop, ast.comprehension):
        return False

    return any(is_negation_of(condition, test.call) for condition in loop.ifs)


def used_when_not_exception(
    facts: FunctionFacts, test: ExceptionTest
) -> bool:
    for branch in facts.branches:
        if branch_uses_result(facts, branch, test):
            return True

    return any(filters_exceptions_out(loop, test) for loop in facts.loops)


class GatheredResults:
    def __init__(self, path: str, aliases: frozenset[str]) -> None:
        self._path: str = path
        self._aliases: frozenset[str] = aliases
        self.found: list[GatherMisuse] = []

    def check(self, function: FunctionNode) -> None:
        facts = function_facts(function)

        for assignment in facts.gathered:
            if assignment.gathering is Gathering.RAISES:
                self._check_raising(assignment)
            elif assignment.gathering is Gathering.RETURNS:
                self._check_returning(assignment, facts)

    def _check_raising(self, assignment: Gathered) -> None:
        if assignment.annotation is None:
            return

        if mentions_exception(assignment.annotation, self._aliases):
            self._report(assignment.line_number, assignment, TYPED_PROBLEM)

    def _check_returning(
        self, assignment: Gathered, facts: FunctionFacts
    ) -> None:
        names = item_names(facts.loops, assignment.name)
        line_numbers = [
            test.call.lineno
            for test in facts.tests
            if test.subject in names and used_when_not_exception(facts, test)
        ]

        if line_numbers:
            self._report(min(line_numbers), assignment, NARROW_PROBLEM)

    def _report(
        self, line_number: int, assignment: Gathered, problem: str
    ) -> None:
        self.found.append(
            GatherMisuse(self._path, line_number, assignment.name, problem)
        )


class GatherExceptions:
    def find_in(self, paths: list[str]) -> list[GatherMisuse]:
        definitions: AliasDefinitions = {}

        for path in paths:
            add_alias_definitions(parse(path), definitions)

        aliases = exception_aliases(definitions)
        found: set[GatherMisuse] = set()

        for path in paths:
            results = GatheredResults(path, aliases)

            for node in ast.walk(parse(path)):
                if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    results.check(node)

            found.update(results.found)

        return sorted(found)


source_paths = [line for line in sys.stdin.read().split("\n") if line]

for misuse in GatherExceptions().find_in(source_paths):
    location = f"{misuse.path}:{misuse.line_number}"
    message = misuse.problem.format(name=misuse.name)
    _ = sys.stdout.write(f"{location}: {message}\n")
