import ast
import sys
from pathlib import Path
from typing import NamedTuple

from stateless_definitions import FunctionNode, StatelessDefinition

FUNCTION_NODES = (ast.FunctionDef, ast.AsyncFunctionDef)
GIVEN_DECORATOR = "given"
SOURCE_DIRECTORY = "src"
TESTS_DIRECTORY = "tests"
TEST_PREFIX = "test_"
PROPERTY_MARKER = "_property"


class UntestedDefinition(NamedTuple):
    path: str
    line_number: int
    name: str


class SplitPaths(NamedTuple):
    sources: dict[str, list[Path]]
    tests: dict[str, list[Path]]


class ServiceName:
    def of(self, path: Path) -> str:
        parts = path.parts

        if TESTS_DIRECTORY in parts:
            boundary = parts.index(TESTS_DIRECTORY)
        else:
            boundary = parts.index(SOURCE_DIRECTORY)

        return "/".join(parts[:boundary])


class SourcesAndTests:
    def split(self, paths: list[str]) -> SplitPaths:
        sources: dict[str, list[Path]] = {}
        tests: dict[str, list[Path]] = {}
        service = ServiceName()

        for given_path in paths:
            path = Path(given_path)

            if TESTS_DIRECTORY in path.parts:
                tests.setdefault(service.of(path), []).append(path)
            elif SOURCE_DIRECTORY in path.parts:
                sources.setdefault(service.of(path), []).append(path)

        return SplitPaths(sources, tests)


class PropertyTestNames:
    def collected_from(self, paths: list[Path]) -> set[str]:
        found: set[str] = set()

        for path in paths:
            found.update(self._in_file(path))

        return found

    def _in_file(self, path: Path) -> set[str]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        found: set[str] = set()

        for node in ast.walk(tree):
            if not isinstance(node, FUNCTION_NODES):
                continue

            if self._is_property_test(node):
                found.add(node.name)

        return found

    def _is_property_test(self, node: FunctionNode) -> bool:
        for decorator in node.decorator_list:
            if self._root_name_of(decorator) == GIVEN_DECORATOR:
                return True

        return False

    def _root_name_of(self, decorator: ast.expr) -> str | None:
        if isinstance(decorator, ast.Call):
            return self._root_name_of(decorator.func)

        if isinstance(decorator, ast.Attribute):
            return decorator.attr

        if isinstance(decorator, ast.Name):
            return decorator.id

        return None


class PropertyTestName:
    def expected_for(self, definition: str) -> str:
        return f"{TEST_PREFIX}{definition}{PROPERTY_MARKER}"


class UntestedDefinitions:
    def find_in(self, paths: list[str]) -> list[UntestedDefinition]:
        split = SourcesAndTests().split(paths)
        found: list[UntestedDefinition] = []

        for service, sources in split.sources.items():
            property_tests = PropertyTestNames().collected_from(
                split.tests.get(service, [])
            )

            for path in sources:
                found.extend(self._find_in_file(path, property_tests))

        return sorted(found)

    def _find_in_file(
        self, path: Path, property_tests: set[str]
    ) -> list[UntestedDefinition]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        stateless = StatelessDefinition()
        found: list[UntestedDefinition] = []

        for node in ast.walk(tree):
            if not isinstance(node, FUNCTION_NODES):
                continue

            if stateless.describes_no_behaviour(node):
                continue

            if self._is_covered(node.name, property_tests):
                continue

            found.append(
                UntestedDefinition(str(path), node.lineno, node.name)
            )

        return found

    def _is_covered(self, name: str, property_tests: set[str]) -> bool:
        expected = PropertyTestName().expected_for(name)

        for test_name in property_tests:
            if test_name.startswith(expected):
                return True

        return False


source_paths = sys.stdin.read().split()

for untested in UntestedDefinitions().find_in(source_paths):
    expected = PropertyTestName().expected_for(untested.name) + "*"
    _ = sys.stdout.write(
        f"{untested.path}:{untested.line_number}: {untested.name} "
        f"needs a property test named {expected}\n"
    )
