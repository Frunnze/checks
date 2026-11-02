import ast
import re
import sys
from pathlib import Path
from typing import NamedTuple

OWNER_WORDS = frozenset(
    {"user", "owner", "account", "tenant", "org", "organization", "workspace"}
)
IDENTITY_SUFFIX = "id"
EXECUTE_METHODS = frozenset({"execute", "fetch", "fetchrow", "fetchval"})
FILTERED_STATEMENT = re.compile(
    r"^\s*(select|update|delete)\b.*\bwhere\b", re.IGNORECASE | re.DOTALL
)
WORD_BOUNDARY = re.compile(r"_+|(?<=[a-z0-9])(?=[A-Z])")
IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
PLACEHOLDER = " ? "

type Function = ast.FunctionDef | ast.AsyncFunctionDef


class UnscopedQuery(NamedTuple):
    path: str
    line_number: int
    owner: str
    function: str


def words_of(name: str) -> list[str]:
    return [word.lower() for word in WORD_BOUNDARY.split(name) if word]


def is_owner_identity(name: str) -> bool:
    words = words_of(name)

    if len(words) < len("xy") or words[-1] != IDENTITY_SUFFIX:
        return False

    return words[-2] in OWNER_WORDS


def owner_parameters(function: Function) -> list[str]:
    arguments = function.args
    everyone = [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs]

    return [item.arg for item in everyone if is_owner_identity(item.arg)]


def text_of(expression: ast.expr) -> str | None:
    if isinstance(expression, ast.Constant) and isinstance(
        expression.value, str
    ):
        return expression.value

    if isinstance(expression, ast.JoinedStr):
        parts: list[str] = []

        for value in expression.values:
            is_text = isinstance(value, ast.Constant)
            text = value.value if is_text else PLACEHOLDER
            parts.append(text if isinstance(text, str) else PLACEHOLDER)

        return "".join(parts)

    return None


def mentions_owner(sql: str) -> bool:
    for match in IDENTIFIER.finditer(sql):
        if OWNER_WORDS & set(words_of(match.group())):
            return True

    return False


def uses_name(node: ast.AST, name: str) -> bool:
    for item in ast.walk(node):
        if isinstance(item, ast.Name) and item.id == name:
            return True

    return False


class UnscopedQueries:
    def find_in(self, paths: list[str]) -> list[UnscopedQuery]:
        found: list[UnscopedQuery] = []

        for path in paths:
            tree = ast.parse(Path(path).read_bytes(), path)

            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    found.extend(self._in_function(path, node))

        return sorted(found)

    def _in_function(
        self, path: str, function: Function
    ) -> list[UnscopedQuery]:
        owners = owner_parameters(function)

        if not owners:
            return []

        found: list[UnscopedQuery] = []

        for node in ast.walk(function):
            if not isinstance(node, ast.Call) or not node.args:
                continue

            method = node.func

            if not isinstance(method, ast.Attribute):
                continue

            if method.attr not in EXECUTE_METHODS:
                continue

            sql = text_of(node.args[0])

            if sql is None or not FILTERED_STATEMENT.search(sql):
                continue

            if mentions_owner(sql):
                continue

            if any(uses_name(node, owner) for owner in owners):
                continue

            found.append(
                UnscopedQuery(path, node.lineno, owners[0], function.name)
            )

        return found


source_paths = [line for line in sys.stdin.read().split("\n") if line]

for query in UnscopedQueries().find_in(source_paths):
    location = f"{query.path}:{query.line_number}"
    problem = f"{query.function}() receives {query.owner} but this query"
    effect = "never filters by it, so any caller reaches any row"
    _ = sys.stdout.write(f"{location}: {problem} {effect}\n")
