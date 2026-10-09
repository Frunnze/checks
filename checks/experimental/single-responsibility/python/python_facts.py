import ast
from pathlib import Path

from python_bindings import (
    FUNCTIONS,
    bound_names,
    imports_in,
    local_bindings,
    module_bindings,
    qualified,
    scope_nodes,
)
from python_definition_time import collect_definition_body, direct_scopes
from python_fields import class_fields
from python_metrics import RuntimeMetrics
from python_parsing import parse_python_module
from srp_metrics import CallableFacts


def scope_name(node: ast.AST) -> str:
    if isinstance(node, ast.Lambda):
        return f"<lambda@{node.lineno}:{node.col_offset}>"
    return node.name


def collect_scope(
    node: ast.AST,
    owner: str,
    inherited: dict[str, str],
    globals_: set[str],
    facts: list[CallableFacts],
    owners: list[dict],
    visible: dict[str, str] | None = None,
) -> None:
    scopes = list(direct_scopes(node))
    replaced_names = {
        child.id
        for child in scope_nodes(node)
        if isinstance(child, ast.Name)
        and isinstance(child.ctx, (ast.Store, ast.Del))
    }
    visible = dict(visible or {})
    if not isinstance(node, ast.ClassDef):
        visible.update(
            (child.name, f"{owner}.{child.name}")
            for child in scopes
            if isinstance(child, FUNCTIONS)
            and child.name not in replaced_names
        )
    visible = {
        key: value
        for key, value in visible.items()
        if key not in replaced_names
    }
    member_names = {
        scope_name(child)
        for child in scopes
        if not isinstance(child, ast.ClassDef)
        and scope_name(child) not in replaced_names
    }
    fields = (
        class_fields(node, inherited) if isinstance(node, ast.ClassDef) else {}
    )
    for child in scopes:
        name = f"{owner}.{scope_name(child)}"
        bindings = local_bindings(child, inherited)
        shadowed = set(local_bindings(child, {}))
        available = {
            key: value for key, value in visible.items() if key not in shadowed
        }
        if isinstance(child, ast.ClassDef):
            owners.append(
                {"name": name, "line": child.lineno, "kind": "class"}
            )
            class_body = CallableFacts(
                f"{name}.<class-body>", child.lineno, name, client_only=True
            )
            collector = RuntimeMetrics(
                class_body, dict(bindings), globals_, set(), set()
            )
            facts.append(collect_definition_body(collector, child))
        else:
            arguments = child.args
            parameters = (
                len(arguments.posonlyargs)
                + len(arguments.args)
                + len(arguments.kwonlyargs)
                + (arguments.vararg is not None)
                + (arguments.kwarg is not None)
            )
            method = isinstance(node, ast.ClassDef)
            positional = [*arguments.posonlyargs, *arguments.args]
            instance = (
                method
                and positional
                and not any(
                    qualified(decorator) == "staticmethod"
                    for decorator in getattr(child, "decorator_list", [])
                )
            )
            receivers = {node.name} if method else set()
            if instance:
                parameters -= 1
                receivers.add(positional[0].arg)
                for field, value in fields.items():
                    bindings[f"{positional[0].arg}.{field}"] = value
            item = CallableFacts(
                name,
                child.lineno,
                owner,
                parameters=parameters,
                binding_stable=scope_name(child) not in replaced_names,
            )
            parameter_names = {
                argument.arg
                for argument in (
                    *arguments.posonlyargs,
                    *arguments.args,
                    *arguments.kwonlyargs,
                    arguments.vararg,
                    arguments.kwarg,
                )
                if argument is not None
            }
            replaced = parameter_names | {
                value.id
                for value in scope_nodes(child)
                if isinstance(value, ast.Name)
                and isinstance(value.ctx, ast.Store)
            }
            available.update(
                (nested.name, f"{name}.{nested.name}")
                for nested in direct_scopes(child)
                if isinstance(nested, FUNCTIONS)
                and nested.name not in replaced
            )
            collector = RuntimeMetrics(
                item,
                bindings,
                globals_,
                member_names,
                parameter_names,
                receivers
                - (
                    parameter_names - {positional[0].arg}
                    if instance
                    else parameter_names
                ),
                shadowed,
                method,
                available,
            )
            body = child.body if isinstance(child, FUNCTIONS) else [child.body]
            for statement in body:
                collector.statement(statement)
            facts.append(collector.finish())
        collect_scope(
            child, name, bindings, globals_, facts, owners, available
        )


def python_facts(
    path: Path, exports: dict | None = None
) -> tuple[list[CallableFacts], list[dict]]:
    tree = parse_python_module(path)
    bindings = module_bindings(tree)
    globals_: set[str] = set()
    for statement in tree.body:
        if isinstance(statement, (ast.Assign, ast.AnnAssign, ast.TypeAlias)):
            globals_.update(bound_names(statement))
            for name in bound_names(statement):
                bindings.pop(name, None)
        elif isinstance(statement, (ast.ClassDef, *FUNCTIONS)):
            bindings.pop(statement.name, None)
    facts: list[CallableFacts] = []
    owners = [{"name": "<module>", "line": 1, "kind": "module"}]
    body = CallableFacts("<module-body>", 1, "<module>", client_only=True)
    collector = RuntimeMetrics(body, dict(bindings), globals_, set(), set())
    facts.append(collect_definition_body(collector, tree))
    if exports is not None:
        declarations = {
            statement.name
            for statement in tree.body
            if isinstance(statement, (ast.ClassDef, *FUNCTIONS))
        }
        for name in declarations:
            exports[name] = "<module>." + name
        for name in set(imports_in(tree)) | globals_:
            value = collector.bindings.get(name, "")
            if value and not value.startswith("local:"):
                exports[name] = {"reference": value}
            elif value.removeprefix("local:") in declarations:
                exports[name] = "<module>." + value.removeprefix("local:")
    bindings = {
        name: value
        for name, value in collector.bindings.items()
        if not value.startswith("local:")
    }
    collect_scope(tree, "<module>", bindings, globals_, facts, owners)
    return facts, owners
