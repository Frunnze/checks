import ast


def literal_annotation(node: ast.AST) -> set[str] | None:
    if not isinstance(node, ast.Subscript):
        return None
    if expression_name(node.value).rsplit(".", 1)[-1] != "Literal":
        return None

    values = (
        node.slice.elts
        if isinstance(node.slice, ast.Tuple)
        else [node.slice]
    )
    domain = {
        value.value
        for value in values
        if isinstance(value, ast.Constant) and isinstance(value.value, str)
    }

    return domain if len(domain) == len(values) else None


def assigned_name(node: ast.Assign | ast.AnnAssign) -> str | None:
    if isinstance(node, ast.AnnAssign):
        return node.target.id if isinstance(node.target, ast.Name) else None
    if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
        return None

    return node.targets[0].id


def string_value(
    node: ast.AST | None, constants: dict[str, str]
) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return constants.get(node.id)

    return None


def inherits_from(owner: ast.ClassDef, names: set[str]) -> bool:
    return any(
        expression_name(base).rsplit(".", 1)[-1] in names
        for base in owner.bases
    )


def expression_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        owner = expression_name(node.value)
        return f"{owner}.{node.attr}" if owner else node.attr

    return ""
