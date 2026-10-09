import ast


def string_constants(tree: ast.Module) -> dict[str, str]:
    found: dict[str, str] = {}

    for statement in tree.body:
        if isinstance(statement, ast.Assign):
            _record_assignment(found, statement.targets, statement.value)
        elif isinstance(statement, ast.AnnAssign):
            _record_assignment(found, (statement.target,), statement.value)

    return found


def _record_assignment(
    found: dict[str, str], targets: tuple[ast.expr, ...] | list[ast.expr],
    value: ast.expr | None,
) -> None:
    if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
        return

    for target in targets:
        if isinstance(target, ast.Name):
            found[target.id] = value.value
