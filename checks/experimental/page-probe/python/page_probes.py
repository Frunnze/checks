import ast
import sys
from collections import defaultdict
from pathlib import Path
from typing import NamedTuple

PAGE_SIZE_NAMES = frozenset(
    {"limit", "page_size", "per_page", "size", "count"}
)
RECEIVER_NAMES = frozenset({"self", "cls"})
SPLITTING_METHODS = frozenset({"split", "rsplit"})
LENGTH_FUNCTION = "len"
STRICT_EXTRA_ROWS = 1
SCOPE_NODES = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.Lambda,
)

type FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef
type StoredLines = dict[str, list[int]]


class Bound(NamedTuple):
    base: str
    offset: int


class Fetch(NamedTuple):
    rows: str
    line_number: int
    size: Bound
    size_line: int


class LengthCheck(NamedTuple):
    rows: str
    text: str
    threshold: Bound
    extra_rows: int
    line_number: int


class Probe(NamedTuple):
    path: str
    line_number: int
    rows: str
    size: str
    check: str
    place: str
    needed: str


class Binding(NamedTuple):
    rows_parameters: frozenset[str]
    size_bounds: dict[str, Bound]


def integer_value(expression: ast.expr) -> int | None:
    if not isinstance(expression, ast.Constant):
        return None

    number = expression.value

    if isinstance(number, bool) or not isinstance(number, int):
        return None

    return number


def bound_of(expression: ast.expr) -> Bound:
    if not isinstance(expression, ast.BinOp):
        return Bound(ast.unparse(expression), 0)

    is_sum = isinstance(expression.op, ast.Add)
    is_difference = isinstance(expression.op, ast.Sub)
    right_step = integer_value(expression.right)
    left_step = integer_value(expression.left)

    if right_step is not None and (is_sum or is_difference):
        inner = bound_of(expression.left)
        signed_step = right_step if is_sum else -right_step
        return Bound(inner.base, inner.offset + signed_step)

    if left_step is not None and is_sum:
        inner = bound_of(expression.right)
        return Bound(inner.base, inner.offset + left_step)

    return Bound(ast.unparse(expression), 0)


def bound_text(bound: Bound) -> str:
    if bound.offset > 0:
        return f"{bound.base} + {bound.offset}"

    if bound.offset < 0:
        return f"{bound.base} - {-bound.offset}"

    return bound.base


def own_nodes(function: FunctionNode) -> list[ast.AST]:
    found: list[ast.AST] = []
    pending: list[ast.AST] = list(function.body)

    while pending:
        node = pending.pop()

        if isinstance(node, SCOPE_NODES):
            continue

        found.append(node)
        pending.extend(ast.iter_child_nodes(node))

    return found


def callee_name(call: ast.Call) -> str:
    if isinstance(call.func, ast.Name):
        return call.func.id

    if isinstance(call.func, ast.Attribute):
        return call.func.attr

    return ""


def page_sizes(call: ast.Call) -> list[ast.expr]:
    sizes: list[ast.expr] = []

    if callee_name(call) in SPLITTING_METHODS:
        return sizes

    for keyword in call.keywords:
        if keyword.arg in PAGE_SIZE_NAMES:
            sizes.append(keyword.value)

    for argument in call.args:
        if bound_of(argument).base in PAGE_SIZE_NAMES:
            sizes.append(argument)

    return sizes


def fetches_in(function: FunctionNode) -> list[Fetch]:
    fetches: list[Fetch] = []

    for node in own_nodes(function):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue

        target = node.targets[0]

        if not isinstance(target, ast.Name):
            continue

        for call in ast.walk(node.value):
            if not isinstance(call, ast.Call):
                continue

            for size in page_sizes(call):
                last_line = node.end_lineno or node.lineno
                size_bound = bound_of(size)
                fetch = Fetch(target.id, last_line, size_bound, size.lineno)
                fetches.append(fetch)

    return fetches


def measured_rows(expression: ast.expr) -> str | None:
    if not isinstance(expression, ast.Call) or len(expression.args) != 1:
        return None

    callee = expression.func
    measured = expression.args[0]

    if not isinstance(callee, ast.Name) or callee.id != LENGTH_FUNCTION:
        return None

    return measured.id if isinstance(measured, ast.Name) else None


def length_check(
    comparison: ast.Compare,
    pair: tuple[ast.expr, ast.cmpop, ast.expr],
) -> LengthCheck | None:
    left, operator, right = pair
    text = ast.unparse(comparison)
    line_number = comparison.lineno
    rows = measured_rows(left)

    if rows is not None and isinstance(operator, ast.Gt | ast.GtE):
        extra_rows = STRICT_EXTRA_ROWS if isinstance(operator, ast.Gt) else 0
        threshold = bound_of(right)
        return LengthCheck(rows, text, threshold, extra_rows, line_number)

    rows = measured_rows(right)

    if rows is not None and isinstance(operator, ast.Lt | ast.LtE):
        extra_rows = STRICT_EXTRA_ROWS if isinstance(operator, ast.Lt) else 0
        threshold = bound_of(left)
        return LengthCheck(rows, text, threshold, extra_rows, line_number)

    return None


def length_checks_in(function: FunctionNode) -> list[LengthCheck]:
    checks: list[LengthCheck] = []

    for node in own_nodes(function):
        if not isinstance(node, ast.Compare):
            continue

        lefts = [node.left, *node.comparators[:-1]]
        pairs = zip(lefts, node.ops, node.comparators, strict=True)

        for pair in pairs:
            check = length_check(node, pair)

            if check is not None:
                checks.append(check)

    return checks


def stored_lines(function: FunctionNode) -> StoredLines:
    lines: StoredLines = defaultdict(list)

    for node in own_nodes(function):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            lines[node.id].append(node.lineno)

    return lines


def call_arguments(
    call: ast.Call, callee: FunctionNode
) -> dict[str, ast.expr]:
    parameters = [*callee.args.posonlyargs, *callee.args.args]
    names = [parameter.arg for parameter in parameters]
    is_method_call = isinstance(call.func, ast.Attribute)

    if is_method_call and names and names[0] in RECEIVER_NAMES:
        names = names[1:]

    arguments: dict[str, ast.expr] = {}

    for name, argument in zip(names, call.args, strict=False):
        if isinstance(argument, ast.Starred):
            break

        arguments[name] = argument

    for keyword in call.keywords:
        if keyword.arg is not None:
            arguments[keyword.arg] = keyword.value

    return arguments


def binding_of(
    call: ast.Call, callee: FunctionNode, fetch: Fetch
) -> Binding:
    rows_parameters: set[str] = set()
    size_bounds: dict[str, Bound] = {}

    for name, argument in call_arguments(call, callee).items():
        if isinstance(argument, ast.Name) and argument.id == fetch.rows:
            rows_parameters.add(name)

        argument_bound = bound_of(argument)

        if argument_bound.base == fetch.size.base:
            size_bounds[name] = argument_bound

    return Binding(frozenset(rows_parameters), size_bounds)


class ProjectFunctions:
    def __init__(self, trees: list[ast.Module]) -> None:
        self._by_name: defaultdict[str, list[FunctionNode]] = (
            defaultdict(list)
        )

        for tree in trees:
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    self._by_name[node.name].append(node)

    def called(self, call: ast.Call) -> FunctionNode | None:
        candidates = self._by_name.get(callee_name(call), [])
        return candidates[0] if len(candidates) == 1 else None


class FunctionProbes:
    def __init__(
        self, path: str, function: FunctionNode, project: ProjectFunctions
    ) -> None:
        self._path: str = path
        self._function: FunctionNode = function
        self._project: ProjectFunctions = project
        self._stored: StoredLines = stored_lines(function)

    def probes(self) -> list[Probe]:
        found: list[Probe] = []

        for fetch in fetches_in(self._function):
            found.extend(self._local_probes(fetch))
            found.extend(self._callee_probes(fetch))

        return found

    def _local_probes(self, fetch: Fetch) -> list[Probe]:
        found: list[Probe] = []

        for check in length_checks_in(self._function):
            if check.rows != fetch.rows:
                continue

            if check.threshold.base != fetch.size.base:
                continue

            if not self._unchanged(fetch, check.line_number):
                continue

            needed = check.threshold.offset + check.extra_rows
            place = f"on line {check.line_number}"
            found.extend(self._probe(fetch, check, place, needed))

        return found

    def _callee_probes(self, fetch: Fetch) -> list[Probe]:
        found: list[Probe] = []

        for node in own_nodes(self._function):
            if not isinstance(node, ast.Call):
                continue

            callee = self._project.called(node)

            if callee is None or not self._unchanged(fetch, node.lineno):
                continue

            binding = binding_of(node, callee, fetch)
            found.extend(self._probes_in_callee(fetch, callee, binding))

        return found

    def _probes_in_callee(
        self, fetch: Fetch, callee: FunctionNode, binding: Binding
    ) -> list[Probe]:
        found: list[Probe] = []
        reassigned = stored_lines(callee)

        for check in length_checks_in(callee):
            size = binding.size_bounds.get(check.threshold.base)

            if check.rows not in binding.rows_parameters or size is None:
                continue

            if check.rows in reassigned or check.threshold.base in reassigned:
                continue

            needed = size.offset + check.threshold.offset + check.extra_rows
            place = f"in {callee.name}()"
            found.extend(self._probe(fetch, check, place, needed))

        return found

    def _unchanged(self, fetch: Fetch, line_number: int) -> bool:
        if line_number <= fetch.line_number:
            return False

        for name in (fetch.rows, fetch.size.base):
            for stored_line in self._stored.get(name, []):
                if fetch.line_number < stored_line <= line_number:
                    return False

        return True

    def _probe(
        self, fetch: Fetch, check: LengthCheck, place: str, needed: int
    ) -> list[Probe]:
        if fetch.size.offset >= needed:
            return []

        needed_bound = Bound(fetch.size.base, needed)
        probe = Probe(
            self._path,
            fetch.size_line,
            fetch.rows,
            bound_text(fetch.size),
            check.text,
            place,
            bound_text(needed_bound),
        )
        return [probe]


class PageProbes:
    def find_in(self, paths: list[str]) -> list[Probe]:
        trees: dict[str, ast.Module] = {}

        for path in paths:
            trees[path] = ast.parse(Path(path).read_bytes(), path)

        project = ProjectFunctions(list(trees.values()))
        found: set[Probe] = set()

        for path, tree in trees.items():
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    probes = FunctionProbes(path, node, project).probes()
                    found.update(probes)

        return sorted(found)


source_paths = [line for line in sys.stdin.read().split("\n") if line]

for probe in PageProbes().find_in(source_paths):
    location = f"{probe.path}:{probe.line_number}"
    limit = f"{probe.rows} holds at most {probe.size} items"
    check = f"{probe.check} {probe.place} is never true"
    advice = f"fetch {probe.needed} to see whether more exist"
    _ = sys.stdout.write(f"{location}: {limit}, so {check} - {advice}\n")
