import ast
import sys
from pathlib import Path
from typing import NamedTuple

MAC_MODULE = "hmac"
MAC_FACTORIES = frozenset({"new"})
MAC_FUNCTIONS = frozenset({"digest"})
DIGEST_METHODS = frozenset({"digest", "hexdigest"})
EQUALITIES = (ast.Eq, ast.NotEq)
SCOPES = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef)


class MacComparison(NamedTuple):
    path: str
    line_number: int
    mac: str


def dotted_name(expression: ast.expr) -> str:
    if isinstance(expression, ast.Name):
        return expression.id

    if isinstance(expression, ast.Attribute):
        owner = dotted_name(expression.value)
        return f"{owner}.{expression.attr}" if owner else ""

    return ""


def mac_aliases(tree: ast.Module) -> set[str]:
    aliases: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == MAC_MODULE:
                    aliases.add(alias.asname or alias.name)

    return aliases


class MacValues:
    def __init__(self, scope: ast.AST, aliases: set[str]) -> None:
        self._aliases: set[str] = aliases
        self._names: set[str] = set()
        self._mac_objects: set[str] = set()

        for node in own_nodes(scope):
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                self._remember(node.targets[0], node.value)

    def is_mac(self, expression: ast.expr) -> bool:
        if isinstance(expression, ast.Name):
            return expression.id in self._names

        if not isinstance(expression, ast.Call):
            return False

        function = expression.func
        callee = dotted_name(function)
        module, _, name = callee.rpartition(".")

        if module in self._aliases and name in MAC_FUNCTIONS:
            return True

        if not isinstance(function, ast.Attribute):
            return False

        is_digest = function.attr in DIGEST_METHODS

        return is_digest and self._is_mac_object(function.value)

    def _is_mac_object(self, expression: ast.expr) -> bool:
        if isinstance(expression, ast.Name):
            return expression.id in self._mac_objects

        if not isinstance(expression, ast.Call):
            return False

        module, _, name = dotted_name(expression.func).rpartition(".")

        return module in self._aliases and name in MAC_FACTORIES

    def _remember(self, target: ast.expr, value: ast.expr) -> None:
        if not isinstance(target, ast.Name):
            return

        if self.is_mac(value):
            self._names.add(target.id)
        elif self._is_mac_object(value):
            self._mac_objects.add(target.id)


def own_nodes(scope: ast.AST) -> list[ast.AST]:
    found: list[ast.AST] = []
    pending = list(ast.iter_child_nodes(scope))

    while pending:
        node = pending.pop()
        found.append(node)

        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            pending.extend(ast.iter_child_nodes(node))

    found.sort(key=lambda node: getattr(node, "lineno", 0))
    return found


class MacComparisons:
    def find_in(self, paths: list[str]) -> list[MacComparison]:
        found: set[MacComparison] = set()

        for path in paths:
            tree = ast.parse(Path(path).read_bytes(), path)
            aliases = mac_aliases(tree)

            if not aliases:
                continue

            for scope in ast.walk(tree):
                if isinstance(scope, SCOPES):
                    values = MacValues(scope, aliases)
                    found.update(self._in_scope(path, scope, values))

        return sorted(found)

    def _in_scope(
        self, path: str, scope: ast.AST, values: MacValues
    ) -> list[MacComparison]:
        found: list[MacComparison] = []

        for node in own_nodes(scope):
            if not isinstance(node, ast.Compare):
                continue

            operands = [node.left, *node.comparators]
            equality = all(isinstance(item, EQUALITIES) for item in node.ops)
            macs = [item for item in operands if values.is_mac(item)]

            if equality and macs:
                mac = ast.unparse(macs[0])
                found.append(MacComparison(path, node.lineno, mac))

        return found


source_paths = [line for line in sys.stdin.read().split("\n") if line]

for comparison in MacComparisons().find_in(source_paths):
    location = f"{comparison.path}:{comparison.line_number}"
    problem = f"{comparison.mac} is an HMAC compared with =="
    advice = "which leaks how much matched - use hmac.compare_digest()"
    _ = sys.stdout.write(f"{location}: {problem}, {advice}\n")
