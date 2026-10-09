import ast

from ocp_findings import MAXIMUM_VARIANTS, TYPE_EQUALITY_NODES
from scoped_visitor import ScopedVisitor

PRIMITIVE_TYPES = {
    "bool",
    "bytes",
    "complex",
    "dict",
    "float",
    "frozenset",
    "int",
    "list",
    "object",
    "set",
    "str",
    "tuple",
}


class ConcreteTypeComparisons(ScopedVisitor):
    def __init__(self, root: ast.AST) -> None:
        super().__init__(root)
        self._subjects: dict[str, tuple[str, set[str]]] = {}

    def collected(self) -> list[tuple[str, tuple[str, ...]]]:
        found: list[tuple[str, tuple[str, ...]]] = []

        for subject, concrete_types in self._subjects.values():
            if len(concrete_types) > MAXIMUM_VARIANTS:
                found.append((subject, tuple(sorted(concrete_types))))

        return sorted(found)

    def visit_Call(self, node: ast.Call) -> None:
        if (
            isinstance(node.func, ast.Name)
            and node.func.id == "isinstance"
            and len(node.args) >= 2
        ):
            for concrete_type in self._types_from(node.args[1]):
                self._record(node.args[0], concrete_type)

        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        if len(node.ops) == 1 and isinstance(node.ops[0], TYPE_EQUALITY_NODES):
            left_subject = self._type_call_subject(node.left)
            right_subject = self._type_call_subject(node.comparators[0])
            left_type = self._type_name(node.left)
            right_type = self._type_name(node.comparators[0])

            if left_subject is not None and right_type is not None:
                self._record(left_subject, right_type)
            elif right_subject is not None and left_type is not None:
                self._record(right_subject, left_type)

        self.generic_visit(node)

    def visit_Match(self, node: ast.Match) -> None:
        for match_case in node.cases:
            for pattern in ast.walk(match_case.pattern):
                if isinstance(pattern, ast.MatchClass):
                    concrete_type = self._type_name(pattern.cls)

                    if concrete_type is not None:
                        self._record(node.subject, concrete_type)

        self.generic_visit(node)

    def _record(self, subject: ast.expr, concrete_type: str) -> None:
        if concrete_type.rsplit(".", 1)[-1] in PRIMITIVE_TYPES:
            return

        key = ast.dump(subject, include_attributes=False)
        display, concrete_types = self._subjects.setdefault(
            key, (ast.unparse(subject), set())
        )
        concrete_types.add(concrete_type)
        self._subjects[key] = (display, concrete_types)

    def _types_from(self, node: ast.expr) -> tuple[str, ...]:
        candidates = node.elts if isinstance(node, ast.Tuple) else (node,)
        found = []

        for candidate in candidates:
            concrete_type = self._type_name(candidate)

            if concrete_type is not None:
                found.append(concrete_type)

        return tuple(found)

    def _type_call_subject(self, node: ast.expr) -> ast.expr | None:
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "type"
            and len(node.args) == 1
        ):
            return node.args[0]

        return None

    def _type_name(self, node: ast.expr) -> str | None:
        return ast.unparse(node) if isinstance(node, (ast.Name, ast.Attribute)) else None
