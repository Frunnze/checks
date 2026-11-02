import ast
import builtins
import sys
from pathlib import Path
from typing import NamedTuple

EXCEPTION_SUFFIXES = ("Error", "Exception", "Exit", "Interrupt")
DISCARD_NAME = "_"
TEST_FOLDERS = frozenset({"test", "tests", "_tests"})
TEST_PREFIX = "test_"
TEST_SUFFIX = "_test.py"


class UnraisedException(NamedTuple):
    path: str
    line_number: int
    exception: str


def last_name(expression: ast.expr) -> str:
    if isinstance(expression, ast.Name):
        return expression.id

    if isinstance(expression, ast.Attribute):
        return expression.attr

    return ""


def is_builtin_exception(name: str) -> bool:
    candidate: object = getattr(builtins, name, None)

    if not isinstance(candidate, type):
        return False

    is_warning = issubclass(candidate, Warning)

    return issubclass(candidate, BaseException) and not is_warning


def is_test_file(path: str) -> bool:
    parts = Path(path).parts
    name = parts[-1]
    in_test_folder = any(part in TEST_FOLDERS for part in parts[:-1])

    return in_test_folder or name.startswith(TEST_PREFIX) or (
        name.endswith(TEST_SUFFIX)
    )


def looks_like_exception(name: str) -> bool:
    is_class_name = name[:1].isupper()
    named_like_one = is_class_name and name.endswith(EXCEPTION_SUFFIXES)

    return named_like_one or is_builtin_exception(name)


class ExceptionNames:
    def __init__(self, trees: list[ast.Module]) -> None:
        self._bases: dict[str, set[str]] = {}

        for tree in trees:
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    bases = {last_name(base) for base in node.bases}
                    self._bases.setdefault(node.name, set()).update(bases)

    def is_exception(self, name: str) -> bool:
        return name[:1].isupper() and self._derives(name, set())

    def _derives(self, name: str, seen: set[str]) -> bool:
        if looks_like_exception(name):
            return True

        seen.add(name)

        for base in self._bases.get(name, set()):
            if base not in seen and self._derives(base, seen):
                return True

        return False


def discarded_call(statement: ast.stmt) -> ast.Call | None:
    value: ast.expr | None = None

    if isinstance(statement, ast.Expr):
        value = statement.value
    elif isinstance(statement, ast.Assign) and len(statement.targets) == 1:
        target = statement.targets[0]
        is_discard = isinstance(target, ast.Name) and target.id == DISCARD_NAME
        value = statement.value if is_discard else None

    return value if isinstance(value, ast.Call) else None


class UnraisedExceptions:
    def find_in(self, paths: list[str]) -> list[UnraisedException]:
        trees = [ast.parse(Path(path).read_bytes(), path) for path in paths]
        names = ExceptionNames(trees)
        found: list[UnraisedException] = []

        for path, tree in zip(paths, trees, strict=True):
            if is_test_file(path):
                continue

            for node in ast.walk(tree):
                if not isinstance(node, ast.stmt):
                    continue

                call = discarded_call(node)

                if call is None:
                    continue

                if not names.is_exception(last_name(call.func)):
                    continue

                exception = ast.unparse(call.func)
                found.append(UnraisedException(path, node.lineno, exception))

        return sorted(found)


source_paths = [line for line in sys.stdin.read().split("\n") if line]

for unraised in UnraisedExceptions().find_in(source_paths):
    location = f"{unraised.path}:{unraised.line_number}"
    problem = f"{unraised.exception}(...) is built but never raised"
    _ = sys.stdout.write(f"{location}: {problem} - add raise\n")
