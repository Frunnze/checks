import ast

PATH_MODULE_PREFIX = "pathlib."


def qualified(
    node: ast.AST | None, bindings: dict[str, str] | None = None
) -> str:
    if isinstance(node, ast.Name):
        return (
            bindings.get(node.id, "local:" + node.id)
            if bindings is not None
            else node.id
        )
    if isinstance(node, ast.Attribute):
        if bindings is not None and qualified(node) in bindings:
            return bindings[qualified(node)]
        base = qualified(node.value, bindings)
        return f"{base}.{node.attr}" if base else ""
    if isinstance(node, ast.Call):
        return qualified(node.func, bindings)
    if isinstance(node, ast.Subscript):
        return qualified(node.value, bindings)
    if isinstance(node, ast.BinOp) and bindings is not None:
        return divided_path_type(node, bindings)
    return ""


def divided_path_type(node: ast.BinOp, bindings: dict[str, str]) -> str:
    if not isinstance(node.op, ast.Div):
        return ""
    dividend_type = qualified(node.left, bindings)
    if dividend_type.startswith(PATH_MODULE_PREFIX):
        return dividend_type
    return ""


def annotation_type(
    node: ast.AST | None, bindings: dict[str, str], depth: int = 0
) -> str:
    if node is None or depth > 12:
        return ""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        try:
            node = ast.parse(node.value, mode="eval").body
        except SyntaxError:
            return ""
        return annotation_type(node, bindings, depth + 1)
    if isinstance(node, ast.Subscript):
        wrapper = qualified(node.value, bindings)
        values = (
            node.slice.elts
            if isinstance(node.slice, ast.Tuple)
            else [node.slice]
        )
        if wrapper in {
            "typing.Annotated",
            "typing_extensions.Annotated",
            "typing.Optional",
        }:
            return annotation_type(values[0], bindings, depth + 1)
        if wrapper == "typing.Union":
            return union_type(values, bindings, depth + 1)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return union_type([node.left, node.right], bindings, depth + 1)
    resolved = qualified(node, bindings)
    return resolved if resolved and not resolved.startswith("local:") else ""


def union_type(
    nodes: list[ast.AST], bindings: dict[str, str], depth: int
) -> str:
    types = {
        annotation_type(node, bindings, depth)
        for node in nodes
        if not (isinstance(node, ast.Constant) and node.value is None)
    }
    return next(iter(types)) if len(types) == 1 and "" not in types else ""
