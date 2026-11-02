import ast
import re
import sys
from pathlib import Path
from typing import NamedTuple

type Scope = ast.Module | ast.FunctionDef | ast.AsyncFunctionDef

SCOPE_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
FUNCTION_NODES = (ast.FunctionDef, ast.AsyncFunctionDef)
TRY_STATEMENTS = (ast.Try, ast.TryStar)
WITH_STATEMENTS = (ast.With, ast.AsyncWith)
CALL_STATEMENTS = (ast.Expr, ast.Assign, ast.AnnAssign)
WORD_BOUNDARY = re.compile(r"_+|(?<=[a-z0-9])(?=[A-Z])")
CATCH_ALL_TYPES = frozenset({"Exception", "BaseException"})
INTERRUPT_TYPES = frozenset(
    {"CancelledError", "Cancelled", "KeyboardInterrupt", "SystemExit"}
    | {"GeneratorExit"}
)
SOCKET_ERRORS = frozenset(
    {"socket.error", "socket.timeout", "socket.gaierror", "socket.herror"}
    | {"select.error", "os.error", "ssl.SSLError", "SSLError"}
    | {"ConnectionError"}
)
OS_ERROR_ALIASES = frozenset({"IOError", "EnvironmentError"})
BUILTINS_MODULE = "builtins"
CLEANUP_VERBS = frozenset(
    {"release", "unlock", "close", "aclose", "rollback", "abort"}
    | {"cleanup", "cancel", "discard", "delete", "remove", "unlink"}
    | {"rmtree", "shutdown", "terminate", "kill", "reset", "disconnect"}
)
ACQUIRE_VERBS = frozenset(
    {"acquire", "lock", "reserve", "claim", "checkout", "begin", "start"}
    | {"open", "connect", "create", "spawn", "popen", "submit", "schedule"}
    | {"enqueue", "mkdir", "makedirs", "mkdtemp", "mkstemp", "register"}
    | {"subscribe", "insert", "execute", "save", "write", "upload"}
)


class NarrowCleanupHandler(NamedTuple):
    path: str
    line_number: int
    caught: str
    cleanup: str


def operating_system_errors() -> frozenset[str]:
    names: set[str] = set(SOCKET_ERRORS | OS_ERROR_ALIASES)
    pending: list[type[OSError]] = [OSError]

    while pending:
        error = pending.pop()
        pending.extend(error.__subclasses__())

        if error.__module__ == BUILTINS_MODULE:
            names.add(error.__name__)

    return frozenset(names)


OPERATING_SYSTEM_ERRORS = operating_system_errors()


def dotted_name(expression: ast.expr) -> str:
    if isinstance(expression, ast.Name):
        return expression.id

    if isinstance(expression, ast.Attribute):
        receiver = dotted_name(expression.value)
        return f"{receiver}.{expression.attr}" if receiver else expression.attr

    return ast.unparse(expression)


def first_word(name: str) -> str:
    words = [word.lower() for word in WORD_BOUNDARY.split(name) if word]
    return words[0] if words else ""


def called_name(call: ast.Call) -> str:
    return dotted_name(call.func).rpartition(".")[2]


def caught_types(handler: ast.ExceptHandler) -> list[str]:
    if handler.type is None:
        return []

    if isinstance(handler.type, ast.Tuple):
        return [dotted_name(element) for element in handler.type.elts]

    return [dotted_name(handler.type)]


def catches_everything(handler: ast.ExceptHandler) -> bool:
    if handler.type is None:
        return True

    for caught in caught_types(handler):
        if caught.rpartition(".")[2] in CATCH_ALL_TYPES:
            return True

    return False


def is_exempt_type(caught: str) -> bool:
    if caught in OPERATING_SYSTEM_ERRORS:
        return True

    last = caught.rpartition(".")[2]
    return last in OPERATING_SYSTEM_ERRORS or last in INTERRUPT_TYPES


def catches_only_exempt_types(handler: ast.ExceptHandler) -> bool:
    return all(is_exempt_type(caught) for caught in caught_types(handler))


def reraises(handler: ast.ExceptHandler) -> bool:
    last = handler.body[-1]

    if not isinstance(last, ast.Raise) or last.cause is not None:
        return False

    if last.exc is None:
        return True

    return isinstance(last.exc, ast.Name) and last.exc.id == handler.name


def own_nodes(statements: list[ast.stmt]) -> list[ast.AST]:
    found: list[ast.AST] = []
    pending: list[ast.AST] = list(statements)

    while pending:
        node = pending.pop()

        if not isinstance(node, SCOPE_NODES):
            found.append(node)
            pending.extend(ast.iter_child_nodes(node))

    return found


def statement_call(statement: ast.stmt) -> ast.Call | None:
    if not isinstance(statement, CALL_STATEMENTS):
        return None

    value = statement.value

    if isinstance(value, ast.Await):
        value = value.value

    return value if isinstance(value, ast.Call) else None


def unconditional_calls(statements: list[ast.stmt]) -> list[ast.Call]:
    calls: list[ast.Call] = []

    for statement in statements:
        if isinstance(statement, WITH_STATEMENTS):
            calls.extend(unconditional_calls(statement.body))
        elif isinstance(statement, TRY_STATEMENTS):
            calls.extend(unconditional_calls(statement.body))
            calls.extend(unconditional_calls(statement.finalbody))
        else:
            call = statement_call(statement)

            if call is not None:
                calls.append(call)

    return calls


def cleanup_call(handler: ast.ExceptHandler) -> str | None:
    for call in unconditional_calls(handler.body[:-1]):
        name = called_name(call)

        if first_word(name) in CLEANUP_VERBS:
            return name

    return None


def acquire_lines(nodes: list[ast.AST]) -> list[int]:
    lines: list[int] = []

    for node in nodes:
        if not isinstance(node, ast.Call):
            continue

        if first_word(called_name(node)) in ACQUIRE_VERBS:
            lines.append(node.lineno)

    return lines


def is_narrow(handler: ast.ExceptHandler) -> bool:
    if catches_everything(handler) or catches_only_exempt_types(handler):
        return False

    return reraises(handler)


def handlers_to_check(
    statement: ast.Try | ast.TryStar,
) -> list[ast.ExceptHandler]:
    if statement.finalbody:
        return []

    for handler in statement.handlers:
        if catches_everything(handler):
            return []

    return [handler for handler in statement.handlers if is_narrow(handler)]


def scopes_in(tree: ast.Module) -> list[Scope]:
    scopes: list[Scope] = [tree]

    for node in ast.walk(tree):
        if isinstance(node, FUNCTION_NODES):
            scopes.append(node)

    return scopes


class NarrowCleanupHandlers:
    def find_in(self, paths: list[str]) -> list[NarrowCleanupHandler]:
        found: set[NarrowCleanupHandler] = set()

        for path in paths:
            tree = ast.parse(Path(path).read_bytes(), path)

            for scope in scopes_in(tree):
                found.update(self._find_in_scope(path, scope))

        return sorted(found)

    def _find_in_scope(
        self, path: str, scope: Scope
    ) -> list[NarrowCleanupHandler]:
        nodes = own_nodes(scope.body)
        acquired = acquire_lines(nodes)
        found: list[NarrowCleanupHandler] = []

        for node in nodes:
            if not isinstance(node, TRY_STATEMENTS):
                continue

            if any(line < node.lineno for line in acquired):
                found.extend(self._narrow_handlers(path, node))

        return found

    def _narrow_handlers(
        self, path: str, statement: ast.Try | ast.TryStar
    ) -> list[NarrowCleanupHandler]:
        found: list[NarrowCleanupHandler] = []

        for handler in handlers_to_check(statement):
            cleanup = cleanup_call(handler)

            if cleanup is not None:
                caught = ", ".join(caught_types(handler))
                found.append(
                    NarrowCleanupHandler(path, handler.lineno, caught, cleanup)
                )

        return found


source_paths = [line for line in sys.stdin.read().split("\n") if line]

for narrow in NarrowCleanupHandlers().find_in(source_paths):
    location = f"{narrow.path}:{narrow.line_number}"
    problem = (
        f"except {narrow.caught} runs {narrow.cleanup}() and re-raises,"
        " but any other exception skips it"
    )
    fix = "catch BaseException or move the cleanup to finally"
    _ = sys.stdout.write(f"{location}: {problem} - {fix}\n")
