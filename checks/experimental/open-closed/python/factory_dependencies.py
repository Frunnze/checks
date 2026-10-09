import ast


def abstract_classes(tree: ast.Module) -> set[str]:
    found: set[str] = set()

    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue

        inherits_abc = any(
            _expression_name(base) in {"ABC", "abc.ABC"}
            for base in node.bases
        )
        has_abstract_method = any(
            isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef))
            and any(
                _expression_name(decorator) in {
                    "abstractmethod",
                    "abc.abstractmethod",
                }
                for decorator in member.decorator_list
            )
            for member in node.body
        )

        if inherits_abc or has_abstract_method:
            found.add(node.name)

    return found


def constructed_dependencies(constructor: ast.FunctionDef) -> set[str]:
    dependencies: set[str] = set()

    for node in ast.walk(constructor):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        if not isinstance(node.value, ast.Call):
            continue
        if not _assigns_to_instance(node):
            continue

        name = _expression_name(node.value.func)

        if name is None:
            continue

        dependency = name.rsplit(".", 1)[-1]

        if dependency[:1].isupper():
            dependencies.add(dependency)

    return dependencies


def _assigns_to_instance(node: ast.Assign | ast.AnnAssign) -> bool:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]

    return any(
        isinstance(target, ast.Attribute)
        and isinstance(target.value, ast.Name)
        and target.value.id == "self"
        for target in targets
    )


def _expression_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        owner = _expression_name(node.value)
        return node.attr if owner is None else f"{owner}.{node.attr}"

    return None
