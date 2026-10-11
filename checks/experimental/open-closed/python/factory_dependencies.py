import ast

_ABSTRACT_BASES = {"ABC", "abc.ABC", "Protocol", "typing.Protocol"}
_SEQUENCE_NODES = (ast.Tuple, ast.List)

AssignedPair = tuple[ast.expr, ast.expr | None]


def abstract_classes(tree: ast.Module) -> set[str]:
    found: set[str] = set()

    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue

        inherits_abstract_base = any(
            _expression_name(base) in _ABSTRACT_BASES for base in node.bases
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

        if inherits_abstract_base or has_abstract_method:
            found.add(node.name)

    return found


def constructed_dependencies(constructor: ast.FunctionDef) -> set[str]:
    dependencies: set[str] = set()

    for node in ast.walk(constructor):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue

        for target, value in _assigned_pairs(node):
            if not isinstance(value, ast.Call):
                continue
            if not _is_instance_attribute(target):
                continue

            name = _expression_name(value.func)

            if name is None:
                continue

            dependency = name.rsplit(".", 1)[-1]

            if dependency[:1].isupper():
                dependencies.add(dependency)

    return dependencies


def _assigned_pairs(node: ast.Assign | ast.AnnAssign) -> list[AssignedPair]:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    pairs: list[AssignedPair] = []

    for target in targets:
        pairs.extend(_unpacked(target, node.value))

    return pairs


def _unpacked(target: ast.expr, value: ast.expr | None) -> list[AssignedPair]:
    if (
        not isinstance(target, _SEQUENCE_NODES)
        or not isinstance(value, _SEQUENCE_NODES)
        or len(target.elts) != len(value.elts)
    ):
        return [(target, value)]

    pairs: list[AssignedPair] = []

    for element, element_value in zip(target.elts, value.elts, strict=True):
        pairs.extend(_unpacked(element, element_value))

    return pairs


def _is_instance_attribute(target: ast.expr) -> bool:
    return (
        isinstance(target, ast.Attribute)
        and isinstance(target.value, ast.Name)
        and target.value.id == "self"
    )


def _expression_name(node: ast.expr) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        owner = _expression_name(node.value)
        return node.attr if owner is None else f"{owner}.{node.attr}"

    return None
