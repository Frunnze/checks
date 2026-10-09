import ast
import sys
from pathlib import Path
from typing import NamedTuple

FUNCTION_NODES = (ast.FunctionDef, ast.AsyncFunctionDef)
SCOPE_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


class NestedDefinition(NamedTuple):
    path: str
    line_number: int
    name: str


class NestedDefinitions:
    def find_in(self, paths: list[str]) -> list[NestedDefinition]:
        found: set[NestedDefinition] = set()

        for path in paths:
            found.update(self._find_in_file(Path(path)))

        return sorted(found)

    def _find_in_file(self, path: Path) -> list[NestedDefinition]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        found: list[NestedDefinition] = []

        for scope in ast.walk(tree):
            if not isinstance(scope, FUNCTION_NODES):
                continue

            for node in self._scopes_directly_in(scope):
                if isinstance(node, FUNCTION_NODES):
                    found.append(
                        NestedDefinition(str(path), node.lineno, node.name)
                    )

        return found

    def _scopes_directly_in(self, scope: ast.AST) -> list[ast.AST]:
        found: list[ast.AST] = []

        for child in ast.iter_child_nodes(scope):
            found.extend(self._scopes_from(child))

        return found

    def _scopes_from(self, node: ast.AST) -> list[ast.AST]:
        if isinstance(node, SCOPE_NODES):
            return [node]

        found: list[ast.AST] = []

        for child in ast.iter_child_nodes(node):
            found.extend(self._scopes_from(child))

        return found


source_paths = sys.stdin.read().split()

for nested in NestedDefinitions().find_in(source_paths):
    _ = sys.stdout.write(
        f"{nested.path}:{nested.line_number}: {nested.name}\n"
    )
