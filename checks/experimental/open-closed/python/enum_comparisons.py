import ast

from match_patterns import subject_patterns
from ocp_findings import (
    CONTAINER_NODES,
    IDENTITY_NODES,
    MAXIMUM_VARIANTS,
    MEMBERSHIP_NODES,
)
from python_ast_values import enum_classes, expression_name
from scoped_visitor import ScopedVisitor

_MEMBER_VALUE = "value"


class EnumComparisons(ScopedVisitor):
    def __init__(
        self, root: ast.AST, enums: dict[str, set[str]] | None = None
    ) -> None:
        super().__init__(root)
        self._subjects: dict[str, tuple[str, dict[str, set[str]]]] = {}
        self._enums = enums or {}

    def collected(self) -> list[tuple[str, tuple[str, ...]]]:
        found: list[tuple[str, tuple[str, ...]]] = []

        for subject, owners in self._subjects.values():
            for owner, members in owners.items():
                if len(members) > MAXIMUM_VARIANTS:
                    qualified = sorted(
                        f"{owner}.{member}" for member in members
                    )
                    found.append((subject, tuple(qualified)))

        return sorted(found)

    def visit_Compare(self, node: ast.Compare) -> None:
        if len(node.ops) == 1 and isinstance(node.ops[0], IDENTITY_NODES):
            self._record_comparison(node.left, node.comparators[0])
        elif len(node.ops) == 1 and isinstance(node.ops[0], MEMBERSHIP_NODES):
            self._record_membership(node.left, node.comparators[0])

        self.generic_visit(node)

    def visit_Match(self, node: ast.Match) -> None:
        for match_case in node.cases:
            for pattern in subject_patterns(match_case.pattern):
                if isinstance(pattern, ast.MatchValue):
                    self._record(node.subject, pattern.value)

        self.generic_visit(node)

    def _record_comparison(self, left: ast.expr, right: ast.expr) -> None:
        if member_reference(right, self._enums) is not None:
            self._record(left, right)
        elif member_reference(left, self._enums) is not None:
            self._record(right, left)

    def _record_membership(
        self, subject: ast.expr, container: ast.expr
    ) -> None:
        if not isinstance(container, CONTAINER_NODES):
            return

        for element in container.elts:
            self._record(subject, element)

    def _record(self, subject: ast.expr, member: ast.expr) -> None:
        reference = member_reference(member, self._enums)

        if reference is None or isinstance(subject, ast.Constant):
            return

        owner, name = reference
        key = ast.dump(subject, include_attributes=False)
        display, owners = self._subjects.setdefault(
            key, (ast.unparse(subject), {})
        )
        owners.setdefault(owner, set()).add(name)
        self._subjects[key] = (display, owners)


def enum_members(trees: list[ast.Module]) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}

    for tree in trees:
        for owner in enum_classes(tree):
            members = found.setdefault(owner.name, set())

            for statement in owner.body:
                if isinstance(statement, ast.Assign):
                    members.update(
                        target.id
                        for target in statement.targets
                        if isinstance(target, ast.Name)
                    )

    return found


def member_reference(
    node: ast.expr, enums: dict[str, set[str]]
) -> tuple[str, str] | None:
    if not isinstance(node, ast.Attribute):
        return None
    if node.attr == _MEMBER_VALUE and isinstance(node.value, ast.Attribute):
        return member_reference(node.value, enums)

    enum_name = expression_name(node.value).rsplit(".", 1)[-1]

    if node.attr in enums.get(enum_name, set()):
        return enum_name, node.attr
    if not isinstance(node.value, ast.Name):
        return None
    if not node.attr.isupper():
        return None

    return node.value.id, node.attr
