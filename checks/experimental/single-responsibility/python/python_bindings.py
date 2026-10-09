import ast
from collections.abc import Iterator

from python_qualified_names import annotation_type, qualified
from srp_effects import is_catalogued_client

SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)
FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)
CLIENT_FACTORY_OPERATIONS = frozenset(
    {
        "open",
        "connect",
        "cursor",
        "from_url",
        "client",
        "resource",
        "create_engine",
        "create_async_engine",
        "create_connection",
    }
)
RETURNED_TYPE_SUFFIX = "()"


def scope_nodes(node: ast.AST) -> Iterator[ast.AST]:
    for child in ast.iter_child_nodes(node):
        yield child
        if not isinstance(child, SCOPES):
            yield from scope_nodes(child)


def imports_in(node: ast.AST) -> dict[str, str]:
    bindings: dict[str, str] = {}
    for child in scope_nodes(node):
        if isinstance(child, ast.Import):
            for alias in child.names:
                bindings[alias.asname or alias.name.split(".")[0]] = (
                    alias.name if alias.asname else alias.name.split(".")[0]
                )
        elif isinstance(child, ast.ImportFrom):
            prefix = "." * child.level + (child.module or "")
            for alias in child.names:
                separator = "." if child.module else ""
                bindings[alias.asname or alias.name] = (
                    f"{prefix}{separator}{alias.name}"
                )
    return bindings


def bound_names(node: ast.AST) -> set[str]:
    return {
        child.id
        for child in ast.walk(node)
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store)
    }


def capture_name(node: ast.AST) -> str:
    if isinstance(node, (ast.ExceptHandler, ast.MatchAs, ast.MatchStar)):
        return node.name or ""
    if isinstance(node, ast.MatchMapping):
        return node.rest or ""
    return ""


def returned_type_bindings(
    node: ast.AST, bindings: dict[str, str]
) -> dict[str, str]:
    returned_types: dict[str, str] = {}
    for child in scope_nodes(node):
        if not isinstance(child, FUNCTIONS):
            continue
        returned_type = annotation_type(child.returns, bindings)
        if is_catalogued_client(returned_type):
            returned_types[child.name + RETURNED_TYPE_SUFFIX] = returned_type
    return returned_types


def module_bindings(tree: ast.Module) -> dict[str, str]:
    bindings = {"open": "builtins.open", **imports_in(tree)}
    returned_types = returned_type_bindings(tree, bindings)
    return {**bindings, **returned_types}


def local_bindings(
    node: ast.AST, inherited: dict[str, str]
) -> dict[str, str]:
    bindings = dict(inherited)
    for child in scope_nodes(node):
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
            bindings[child.id] = "local:" + child.id
        elif isinstance(child, (ast.ClassDef, *FUNCTIONS)):
            bindings[child.name] = "local:" + child.name
        elif name := capture_name(child):
            bindings[name] = "local:" + name
    if isinstance(node, (*FUNCTIONS, ast.Lambda)):
        arguments = (
            *node.args.posonlyargs,
            *node.args.args,
            *node.args.kwonlyargs,
            node.args.vararg,
            node.args.kwarg,
        )
        for argument in arguments:
            if argument is not None:
                bindings[argument.arg] = "local:" + argument.arg
                annotation = annotation_type(argument.annotation, inherited)
                if annotation:
                    bindings[argument.arg] = annotation
    bindings.update(imports_in(node))
    bindings.update(returned_type_bindings(node, bindings))
    return bindings


def called_client_type(call: ast.Call, bindings: dict[str, str]) -> str:
    returned_type_key = qualified(call.func) + RETURNED_TYPE_SUFFIX
    if returned_type_key in bindings:
        return bindings[returned_type_key]
    resolved = qualified(call, bindings)
    operation = resolved.rsplit(".", 1)[-1]
    if operation[:1].isupper() or operation in CLIENT_FACTORY_OPERATIONS:
        return resolved
    return ""


def assigned_value(value: ast.AST | None, bindings: dict[str, str]) -> str:
    if isinstance(value, ast.Await):
        return assigned_value(value.value, bindings)
    if isinstance(value, ast.Subscript) and qualified(
        value.value, bindings
    ) in {
        "typing.Annotated",
        "typing_extensions.Annotated",
        "typing.Optional",
        "typing.Union",
    }:
        return annotation_type(value, bindings)
    if isinstance(value, ast.Call):
        return called_client_type(value, bindings)
    return qualified(value, bindings)


def bind_assignment(node: ast.AST, bindings: dict[str, str]) -> None:
    if isinstance(node, ast.Assign):
        targets, value = node.targets, node.value
    elif isinstance(node, ast.AnnAssign):
        targets, value = [node.target], node.value
    elif isinstance(node, ast.TypeAlias):
        targets, value = [node.name], node.value
    elif isinstance(node, ast.withitem):
        targets, value = [node.optional_vars], node.context_expr
    else:
        return
    resolved = assigned_value(value, bindings)
    if isinstance(node, ast.AnnAssign):
        resolved = annotation_type(node.annotation, bindings) or resolved
    for target in targets:
        if isinstance(target, (ast.Name, ast.Attribute)):
            name = qualified(target)
            bindings[name] = resolved or "local:" + name


def is_docstring(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )
