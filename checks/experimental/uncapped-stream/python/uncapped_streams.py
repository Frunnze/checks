import ast
import sys
from pathlib import Path
from typing import NamedTuple

CHUNK_ITERATORS = frozenset(
    {
        "iter_bytes",
        "aiter_bytes",
        "iter_raw",
        "aiter_raw",
        "iter_text",
        "aiter_text",
        "iter_lines",
        "aiter_lines",
        "iter_content",
        "iter_chunked",
        "iter_any",
        "iter_chunks",
    }
)
COLLECTING_METHODS = frozenset({"append", "extend"})
STOPS = (ast.Break, ast.Raise, ast.Return, ast.Compare)

type Loop = ast.For | ast.AsyncFor


class UncappedStream(NamedTuple):
    path: str
    line_number: int
    collector: str


def reads_chunks(loop: Loop) -> bool:
    source = loop.iter

    if isinstance(source, ast.Await):
        source = source.value

    if not isinstance(source, ast.Call):
        return False

    function = source.func

    return (
        isinstance(function, ast.Attribute)
        and function.attr in CHUNK_ITERATORS
    )


def uses_name(expression: ast.AST, name: str) -> bool:
    for node in ast.walk(expression):
        if isinstance(node, ast.Name) and node.id == name:
            return True

    return False


def added_to(statement: ast.stmt, chunk: str) -> str | None:
    if not isinstance(statement, ast.AugAssign):
        return None

    if isinstance(statement.op, ast.Add) and uses_name(statement.value, chunk):
        return ast.unparse(statement.target)

    return None


def collected_into(statement: ast.stmt, chunk: str) -> str | None:
    if not isinstance(statement, ast.Expr):
        return None

    call = statement.value

    if isinstance(call, ast.Await):
        call = call.value

    if not isinstance(call, ast.Call):
        return None

    function = call.func

    if not isinstance(function, ast.Attribute):
        return None

    if function.attr not in COLLECTING_METHODS:
        return None

    if any(uses_name(argument, chunk) for argument in call.args):
        return ast.unparse(function.value)

    return None


def has_stop(loop: Loop) -> bool:
    for statement in loop.body:
        for node in ast.walk(statement):
            if isinstance(node, STOPS):
                return True

    return False


def collector_of(loop: Loop) -> str | None:
    if not isinstance(loop.target, ast.Name) or not reads_chunks(loop):
        return None

    if has_stop(loop):
        return None

    chunk = loop.target.id

    for statement in loop.body:
        collector = added_to(statement, chunk)
        collector = collector or collected_into(statement, chunk)

        if collector is not None:
            return collector

    return None


class UncappedStreams:
    def find_in(self, paths: list[str]) -> list[UncappedStream]:
        found: list[UncappedStream] = []

        for path in paths:
            tree = ast.parse(Path(path).read_bytes(), path)

            for node in ast.walk(tree):
                if not isinstance(node, ast.For | ast.AsyncFor):
                    continue

                collector = collector_of(node)

                if collector is not None:
                    stream = UncappedStream(path, node.lineno, collector)
                    found.append(stream)

        return sorted(found)


source_paths = [line for line in sys.stdin.read().split("\n") if line]

for stream in UncappedStreams().find_in(source_paths):
    location = f"{stream.path}:{stream.line_number}"
    problem = f"every chunk goes into {stream.collector}"
    _ = sys.stdout.write(
        f"{location}: {problem} with no size check inside the loop\n"
    )
