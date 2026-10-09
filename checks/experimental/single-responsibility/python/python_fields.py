import ast

from python_bindings import (
    FUNCTIONS,
    annotation_type,
    assigned_value,
    bind_assignment,
    local_bindings,
    returned_type_bindings,
    scope_nodes,
)
from python_qualified_names import qualified


def class_fields(
    node: ast.ClassDef, inherited: dict[str, str]
) -> dict[str, str]:
    method_returned_types = returned_type_bindings(node, inherited)
    fields: dict[str, str] = dict(method_returned_types)
    declared: set[str] = set()
    for statement in node.body:
        if isinstance(statement, ast.AnnAssign) and isinstance(
            statement.target, ast.Name
        ):
            resolved = annotation_type(statement.annotation, inherited)
            if resolved:
                fields[statement.target.id] = resolved
                declared.add(statement.target.id)
        elif isinstance(statement, ast.Assign):
            resolved = assigned_value(statement.value, inherited)
            if resolved and not resolved.startswith("local:"):
                for target in statement.targets:
                    if isinstance(target, ast.Name):
                        fields[target.id] = resolved
    for method in node.body:
        if not isinstance(method, FUNCTIONS) or method.name != "__init__":
            continue
        positional = [*method.args.posonlyargs, *method.args.args]
        if not positional:
            continue
        receiver = positional[0].arg + "."
        bindings = local_bindings(method, inherited)
        for returned_key, returned_type in method_returned_types.items():
            bindings[receiver + returned_key] = returned_type
        for statement in method.body:
            bind_assignment(statement, bindings)
        for name, value in bindings.items():
            if (
                name.startswith(receiver)
                and name.count(".") == 1
                and not value.startswith("local:")
            ):
                fields.setdefault(name[len(receiver) :], value)
    for method in node.body:
        if not isinstance(method, FUNCTIONS):
            continue
        positional = [*method.args.posonlyargs, *method.args.args]
        if not positional:
            continue
        receiver = positional[0].arg
        direct_targets = (
            {
                id(target)
                for statement in method.body
                if isinstance(statement, (ast.Assign, ast.AnnAssign))
                for target in (
                    statement.targets
                    if isinstance(statement, ast.Assign)
                    else [statement.target]
                )
            }
            if method.name == "__init__"
            else set()
        )
        for child in scope_nodes(method):
            if (
                isinstance(child, ast.Attribute)
                and isinstance(child.ctx, (ast.Store, ast.Del))
                and qualified(child.value) == receiver
                and id(child) not in direct_targets
                and child.attr not in declared
            ):
                fields.pop(child.attr, None)
    return fields
