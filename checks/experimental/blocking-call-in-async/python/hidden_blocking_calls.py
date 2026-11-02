import ast
import re
import sys
from pathlib import Path
from typing import NamedTuple

type FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef
type Conditional = ast.If | ast.While | ast.For | ast.AsyncFor | ast.Match

FUNCTION_NODES = (ast.FunctionDef, ast.AsyncFunctionDef)
SCOPE_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
OWN_RECEIVERS = frozenset({"self", "cls"})
PACKAGE_FILE = "__init__"
ROUTE_DECORATORS = frozenset(
    {"get", "post", "put", "patch", "delete", "head", "options", "trace"}
    | {"route", "api_route", "websocket", "websocket_route"}
    | {"exception_handler", "middleware"}
)
HTTP_CALLS = ("request", "get", "post", "put", "patch", "delete", "head")
BLOCKING_FUNCTIONS = frozenset(
    {"time.sleep", "urllib.request.urlopen", "os.system", "os.waitpid"}
    | {"socket.create_connection", "socket.getaddrinfo"}
    | {"socket.gethostbyname", "socket.gethostbyaddr"}
    | {"subprocess.run", "subprocess.call", "subprocess.check_call"}
    | {"subprocess.check_output", "smtplib.SMTP", "smtplib.SMTP_SSL"}
    | {"ftplib.FTP", "psycopg.connect", "psycopg2.connect"}
    | {"sqlite3.connect", "pymysql.connect", "httpx.stream"}
    | {f"requests.{http_call}" for http_call in HTTP_CALLS}
    | {f"httpx.{http_call}" for http_call in HTTP_CALLS}
)
BLOCKING_BUILTINS = frozenset({"open", "input"})
BLOCKING_METHODS = frozenset(
    {"fetchone", "fetchall", "fetchmany", "executemany", "communicate"}
    | {"read_text", "read_bytes", "write_text", "write_bytes"}
    | {"recv", "recv_into", "recvfrom", "sendall"}
)
BLOCKING_CONTEXT_METHODS = frozenset({"connection", "cursor", "connect"})
BLOCKING_CLIENTS = frozenset(
    {"httpx.Client", "requests.Session", "requests.session"}
)
REDIS_WORD = "redis"
CLIENT_WORDS = frozenset({"redis", "client", "connection", "conn"})
WORD_BOUNDARY = re.compile(r"_+|(?<=[a-z0-9])(?=[A-Z])")
BRANCH_STATEMENTS = (ast.If, ast.While)
LOOP_STATEMENTS = (ast.For, ast.AsyncFor)
CONDITIONAL_STATEMENTS = (ast.If, ast.While, ast.For, ast.AsyncFor, ast.Match)
TRY_STATEMENTS = (ast.Try, ast.TryStar)
EXIT_STATEMENTS = (ast.Return, ast.Raise)
COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
BUILTIN_TYPES = (object, str, bytes, bytearray, int, float)
BUILTIN_CONTAINERS = (list, tuple, dict, set, frozenset)
STUB_DECORATORS = frozenset({"overload", "abstractmethod"})
STUB_ERROR = "NotImplementedError"
CHAIN_ARROW = " -> "


class Binding(NamedTuple):
    qualified_name: str
    in_project: bool


class Module(NamedTuple):
    path: str
    bindings: dict[str, Binding]
    functions: frozenset[str]


class Definition(NamedTuple):
    path: str
    line_number: int
    owner: str
    name: str
    node: FunctionNode


class Reason(NamedTuple):
    label: str
    callee: Definition | None


class HiddenBlockingCall(NamedTuple):
    path: str
    line_number: int
    callee: str
    chain: str


def builtin_method_names() -> frozenset[str]:
    names: set[str] = set()

    for builtin_type in BUILTIN_TYPES + BUILTIN_CONTAINERS:
        names.update(dir(builtin_type))

    return frozenset(names)


BUILTIN_METHODS = builtin_method_names()


def module_names(path: str) -> list[str]:
    parts = list(Path(path).with_suffix("").parts)

    if parts and parts[-1] == PACKAGE_FILE:
        _ = parts.pop()

    names: list[str] = []

    for start in range(len(parts)):
        for end in range(start + 1, len(parts) + 1):
            names.append(".".join(parts[start:end]))

    return names


def dotted_name(expression: ast.expr) -> str:
    if isinstance(expression, ast.Name):
        return expression.id

    if isinstance(expression, ast.Attribute):
        receiver = dotted_name(expression.value)
        return f"{receiver}.{expression.attr}" if receiver else ""

    return ""


def import_bindings(
    tree: ast.Module, project_modules: frozenset[str]
) -> dict[str, Binding]:
    bindings: dict[str, Binding] = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname is None:
                    root = alias.name.partition(".")[0]
                    bindings[root] = Binding(root, root in project_modules)
                else:
                    in_project = alias.name in project_modules
                    bindings[alias.asname] = Binding(alias.name, in_project)
        elif isinstance(node, ast.ImportFrom):
            source = node.module or ""
            in_project = node.level > 0 or source in project_modules

            for alias in node.names:
                qualified = f"{source}.{alias.name}" if source else alias.name
                bound = alias.asname or alias.name
                bindings[bound] = Binding(qualified, in_project)

    return bindings


def qualified_name(expression: ast.expr, module: Module) -> str | None:
    root, dot, rest = dotted_name(expression).partition(".")
    binding = module.bindings.get(root)

    if binding is None:
        return None

    return f"{binding.qualified_name}{dot}{rest}"


def is_stub_statement(statement: ast.stmt) -> bool:
    if isinstance(statement, ast.Pass):
        return True

    if isinstance(statement, ast.Expr) and isinstance(
        statement.value, ast.Constant
    ):
        return True

    if isinstance(statement, ast.Raise) and statement.exc is not None:
        raised = statement.exc
        error = raised.func if isinstance(raised, ast.Call) else raised
        return dotted_name(error) == STUB_ERROR

    return False


def is_stub(function: FunctionNode) -> bool:
    for decorator in function.decorator_list:
        if dotted_name(decorator).rpartition(".")[2] in STUB_DECORATORS:
            return True

    return all(is_stub_statement(statement) for statement in function.body)


def is_request_handler(function: FunctionNode) -> bool:
    if not isinstance(function, ast.AsyncFunctionDef):
        return False

    for decorator in function.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue

        if dotted_name(decorator.func).rpartition(".")[2] in ROUTE_DECORATORS:
            return True

    return False


def own_nodes(function: FunctionNode) -> list[ast.AST]:
    found: list[ast.AST] = []
    pending: list[ast.AST] = list(function.body)

    while pending:
        node = pending.pop()

        if not isinstance(node, SCOPE_NODES):
            found.append(node)
            pending.extend(ast.iter_child_nodes(node))

    return found


def own_calls(function: FunctionNode) -> list[ast.Call]:
    calls: list[ast.Call] = []

    for node in own_nodes(function):
        if isinstance(node, ast.Call):
            calls.append(node)

    return calls


def awaited_calls(function: FunctionNode) -> set[ast.Call]:
    awaited: set[ast.Call] = set()

    for node in own_nodes(function):
        if isinstance(node, ast.Await) and isinstance(node.value, ast.Call):
            awaited.add(node.value)

    return awaited


def returns_within(statements: list[ast.stmt]) -> bool:
    pending: list[ast.AST] = list(statements)

    while pending:
        node = pending.pop()

        if isinstance(node, ast.Return):
            return True

        if not isinstance(node, SCOPE_NODES):
            pending.extend(ast.iter_child_nodes(node))

    return False


def evaluated_children(node: ast.AST) -> list[ast.AST]:
    if isinstance(node, ast.Lambda):
        return []

    if isinstance(node, ast.BoolOp):
        return [node.values[0]]

    if isinstance(node, ast.IfExp):
        return [node.test]

    if isinstance(node, COMPREHENSIONS):
        return [node.generators[0].iter]

    return list(ast.iter_child_nodes(node))


def evaluated_calls(expression: ast.expr) -> list[ast.Call]:
    calls: list[ast.Call] = []
    pending: list[ast.AST] = [expression]

    while pending:
        node = pending.pop()

        if isinstance(node, ast.Call):
            calls.append(node)

        pending.extend(evaluated_children(node))

    return calls


def conditional_parts(
    statement: Conditional,
) -> tuple[ast.expr, list[ast.stmt]]:
    if isinstance(statement, BRANCH_STATEMENTS):
        return statement.test, statement.body + statement.orelse

    if isinstance(statement, LOOP_STATEMENTS):
        return statement.iter, statement.body + statement.orelse

    bodies: list[ast.stmt] = []

    for case in statement.cases:
        bodies.extend(case.body)

    return statement.subject, bodies


def name_words(name: str) -> list[str]:
    return [word.lower() for word in WORD_BOUNDARY.split(name) if word]


class AlwaysRun:
    def __init__(self) -> None:
        self.expressions: list[ast.expr] = []
        self.contexts: list[ast.withitem] = []

    def calls(self) -> list[ast.Call]:
        calls: list[ast.Call] = []

        for expression in self.expressions:
            calls.extend(evaluated_calls(expression))

        return calls

    def collect(self, statements: list[ast.stmt]) -> bool:
        return all(self._falls_through(statement) for statement in statements)

    def _falls_through(self, statement: ast.stmt) -> bool:
        if isinstance(statement, ast.With):
            return self._enter(statement)

        if isinstance(statement, TRY_STATEMENTS):
            return self._try(statement)

        if isinstance(statement, CONDITIONAL_STATEMENTS):
            head, bodies = conditional_parts(statement)
            self.expressions.append(head)
            return not returns_within(bodies)

        if not isinstance(statement, SCOPE_NODES):
            for child in ast.iter_child_nodes(statement):
                if isinstance(child, ast.expr):
                    self.expressions.append(child)

        return not isinstance(statement, EXIT_STATEMENTS)

    def _enter(self, statement: ast.With) -> bool:
        for item in statement.items:
            self.expressions.append(item.context_expr)
            self.contexts.append(item)

        return self.collect(statement.body)

    def _try(self, statement: ast.Try | ast.TryStar) -> bool:
        body_falls_through = self.collect(statement.body)
        finally_falls_through = self.collect(statement.finalbody)
        handled = list(statement.orelse)

        for handler in statement.handlers:
            handled.extend(handler.body)

        if returns_within(handled):
            return False

        return body_falls_through and finally_falls_through


def always_run(function: FunctionNode) -> AlwaysRun:
    collector = AlwaysRun()
    _ = collector.collect(function.body)
    return collector


def is_builtin_io(name: str, module: Module) -> bool:
    if name not in BLOCKING_BUILTINS:
        return False

    return name not in module.bindings and name not in module.functions


def is_redis_client(receiver: ast.expr, module: Module) -> bool:
    name = dotted_name(receiver)
    binding = module.bindings.get(name.partition(".")[0])

    if not name or (binding is not None and not binding.in_project):
        return False

    words = name_words(name.rpartition(".")[2])
    return REDIS_WORD in words and words[-1] in CLIENT_WORDS


def blocking_call(call: ast.Call, module: Module) -> str | None:
    function = call.func
    qualified = qualified_name(function, module)

    if qualified in BLOCKING_FUNCTIONS:
        return f"{qualified}()"

    if isinstance(function, ast.Name) and is_builtin_io(function.id, module):
        return f"{function.id}()"

    if not isinstance(function, ast.Attribute):
        return None

    if function.attr in BLOCKING_METHODS:
        return f".{function.attr}()"

    if is_redis_client(function.value, module):
        return f"redis .{function.attr}()"

    return None


def blocking_context(item: ast.withitem, module: Module) -> str | None:
    expression = item.context_expr

    if not isinstance(expression, ast.Call):
        return None

    function = expression.func
    qualified = qualified_name(function, module)

    if qualified in BLOCKING_CLIENTS:
        return f"with {qualified}()"

    if (
        isinstance(function, ast.Attribute)
        and function.attr in BLOCKING_CONTEXT_METHODS
    ):
        return f"with .{function.attr}()"

    return None


def direct_blocking(collected: AlwaysRun, module: Module) -> str | None:
    for item in collected.contexts:
        label = blocking_context(item, module)

        if label is not None:
            return label

    for call in collected.calls():
        label = blocking_call(call, module)

        if label is not None:
            return label

    return None


def display_name(definition: Definition) -> str:
    if definition.owner:
        return f"{definition.owner}.{definition.name}"

    return definition.name


def called_name(call: ast.Call) -> str:
    if isinstance(call.func, ast.Attribute):
        return call.func.attr

    return dotted_name(call.func)


def all_coroutines(candidates: list[Definition]) -> bool:
    return all(
        isinstance(candidate.node, ast.AsyncFunctionDef)
        for candidate in candidates
    )


def definitions_in(
    path: str, statements: list[ast.stmt], owner: str
) -> list[Definition]:
    found: list[Definition] = []

    for statement in statements:
        if isinstance(statement, ast.ClassDef):
            found.extend(definitions_in(path, statement.body, statement.name))
        elif isinstance(statement, FUNCTION_NODES) and not is_stub(statement):
            found.append(
                Definition(
                    path, statement.lineno, owner, statement.name, statement
                )
            )

    return found


class Resolver:
    def __init__(
        self, modules: dict[str, Module], definitions: list[Definition]
    ) -> None:
        self._modules: dict[str, Module] = modules
        self._by_name: dict[str, list[Definition]] = {}

        for definition in definitions:
            named = self._by_name.setdefault(definition.name, [])
            named.append(definition)

    def candidates(
        self, call: ast.Call, caller: Definition
    ) -> list[Definition]:
        module = self._modules[caller.path]
        function = call.func

        if isinstance(function, ast.Name):
            return self._named(function.id, module)

        if isinstance(function, ast.Attribute):
            return self._attribute(function, module, caller.owner)

        return []

    def _functions_named(self, name: str) -> list[Definition]:
        return [
            definition
            for definition in self._by_name.get(name, [])
            if not definition.owner
        ]

    def _named(self, name: str, module: Module) -> list[Definition]:
        if name in module.functions:
            return [
                definition
                for definition in self._functions_named(name)
                if definition.path == module.path
            ]

        binding = module.bindings.get(name)

        if binding is None or not binding.in_project:
            return []

        original = binding.qualified_name.rpartition(".")[2]
        return self._functions_named(original)

    def _attribute(
        self, function: ast.Attribute, module: Module, owner: str
    ) -> list[Definition]:
        named = self._by_name.get(function.attr, [])
        receiver = dotted_name(function.value)

        if receiver in OWN_RECEIVERS and owner:
            return self._own_method(named, module, owner)

        if function.attr in BUILTIN_METHODS:
            return []

        binding = module.bindings.get(receiver.partition(".")[0])

        if binding is not None and not binding.in_project:
            return []

        return named

    def _own_method(
        self, named: list[Definition], module: Module, owner: str
    ) -> list[Definition]:
        own = [
            definition
            for definition in named
            if definition.path == module.path and definition.owner == owner
        ]

        if own:
            return own

        return [definition for definition in named if definition.owner]


class BlockingFunctions:
    def __init__(
        self,
        modules: dict[str, Module],
        definitions: list[Definition],
        resolver: Resolver,
    ) -> None:
        self._synchronous: list[Definition] = [
            definition
            for definition in definitions
            if isinstance(definition.node, ast.FunctionDef)
        ]
        self._modules: dict[str, Module] = modules
        self._resolver: Resolver = resolver
        self._reasons: dict[Definition, Reason] = {}

    def settle(self) -> None:
        callees = {
            definition: self._callees(definition)
            for definition in self._synchronous
        }

        for definition in self._synchronous:
            module = self._modules[definition.path]
            label = direct_blocking(always_run(definition.node), module)

            if label is not None:
                self._reasons[definition] = Reason(label, None)

        changed = True

        while changed:
            changed = False

            for definition in self._synchronous:
                if definition in self._reasons:
                    continue

                reason = self._reason(callees[definition])

                if reason is not None:
                    self._reasons[definition] = reason
                    changed = True

    def blocking(self, candidates: list[Definition]) -> bool:
        if not candidates:
            return False

        return all(candidate in self._reasons for candidate in candidates)

    def chain(self, definition: Definition) -> str:
        steps: list[str] = []
        visited: set[Definition] = set()
        current: Definition | None = definition

        while current is not None and current not in visited:
            visited.add(current)
            steps.append(display_name(current))
            reason = self._reasons[current]

            if reason.callee is None:
                steps.append(reason.label)

            current = reason.callee

        return CHAIN_ARROW.join(steps)

    def _callees(self, definition: Definition) -> list[list[Definition]]:
        callees: list[list[Definition]] = []

        for call in always_run(definition.node).calls():
            candidates = self._resolver.candidates(call, definition)
            others = [
                candidate
                for candidate in candidates
                if candidate != definition
            ]
            callees.append(others)

        return callees

    def _reason(self, callees: list[list[Definition]]) -> Reason | None:
        for candidates in callees:
            if self.blocking(candidates):
                callee = candidates[0]
                return Reason(display_name(callee), callee)

        return None


class RequestHandlers:
    def __init__(
        self, definitions: list[Definition], resolver: Resolver
    ) -> None:
        self._definitions: list[Definition] = definitions
        self._resolver: Resolver = resolver

    def reachable(self) -> list[Definition]:
        pending = [
            definition
            for definition in self._definitions
            if is_request_handler(definition.node)
        ]
        reached: set[Definition] = set()

        while pending:
            definition = pending.pop()

            if definition not in reached:
                reached.add(definition)
                pending.extend(self._coroutines_called_by(definition))

        return sorted(reached)

    def _coroutines_called_by(
        self, definition: Definition
    ) -> list[Definition]:
        coroutines: list[Definition] = []

        for call in own_calls(definition.node):
            candidates = self._resolver.candidates(call, definition)

            if candidates and all_coroutines(candidates):
                coroutines.extend(candidates)

        return coroutines


class HiddenBlockingCalls:
    def find_in(self, paths: list[str]) -> list[HiddenBlockingCall]:
        trees = {
            path: ast.parse(Path(path).read_bytes(), path) for path in paths
        }
        project_modules: set[str] = set()

        for path in paths:
            project_modules.update(module_names(path))

        known_modules = frozenset(project_modules)
        modules: dict[str, Module] = {}
        definitions: list[Definition] = []

        for path, tree in trees.items():
            modules[path] = self._module(path, tree, known_modules)
            definitions.extend(definitions_in(path, tree.body, ""))

        resolver = Resolver(modules, definitions)
        blocking = BlockingFunctions(modules, definitions, resolver)
        blocking.settle()
        found: set[HiddenBlockingCall] = set()

        for handler in RequestHandlers(definitions, resolver).reachable():
            found.update(self._blocking_calls(handler, resolver, blocking))

        return sorted(found)

    def _blocking_calls(
        self,
        handler: Definition,
        resolver: Resolver,
        blocking: BlockingFunctions,
    ) -> list[HiddenBlockingCall]:
        awaited = awaited_calls(handler.node)
        found: list[HiddenBlockingCall] = []

        for call in own_calls(handler.node):
            candidates = resolver.candidates(call, handler)

            if call in awaited or not blocking.blocking(candidates):
                continue

            found.append(
                HiddenBlockingCall(
                    handler.path,
                    call.lineno,
                    called_name(call),
                    blocking.chain(candidates[0]),
                )
            )

        return found

    def _module(
        self, path: str, tree: ast.Module, project_modules: frozenset[str]
    ) -> Module:
        functions = frozenset(
            statement.name
            for statement in tree.body
            if isinstance(statement, FUNCTION_NODES)
        )
        bindings = import_bindings(tree, project_modules)
        return Module(path, bindings, functions)


source_paths = [line for line in sys.stdin.read().split("\n") if line]

for hidden in HiddenBlockingCalls().find_in(source_paths):
    location = f"{hidden.path}:{hidden.line_number}"
    problem = f"{hidden.callee}() blocks the event loop of a request handler"
    fix = "await it through asyncio.to_thread() or a threadpool"
    _ = sys.stdout.write(f"{location}: {problem} ({hidden.chain}) - {fix}\n")
