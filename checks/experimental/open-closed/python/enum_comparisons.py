import ast

from ocp_findings import EQUALITY_NODES, MAXIMUM_VARIANTS
from scoped_visitor import ScopedVisitor


class EnumComparisons(ScopedVisitor):
    def __init__(self, root: ast.AST) -> None:
        super().__init__(root)
        self._subjects: dict[str, tuple[str, dict[str, set[str]]]] = {}

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
        if len(node.ops) == 1 and isinstance(node.ops[0], EQUALITY_NODES):
            self._record_comparison(node.left, node.comparators[0])

        self.generic_visit(node)

    def visit_Match(self, node: ast.Match) -> None:
        for match_case in node.cases:
            for pattern in ast.walk(match_case.pattern):
                if isinstance(pattern, ast.MatchValue):
                    self._record(node.subject, pattern.value)

        self.generic_visit(node)

    def _record_comparison(self, left: ast.expr, right: ast.expr) -> None:
        if member_reference(right) is not None:
            self._record(left, right)
        elif member_reference(left) is not None:
            self._record(right, left)

    def _record(self, subject: ast.expr, member: ast.expr) -> None:
        reference = member_reference(member)

        if reference is None:
            return

        owner, name = reference
        key = ast.dump(subject, include_attributes=False)
        display, owners = self._subjects.setdefault(
            key, (ast.unparse(subject), {})
        )
        owners.setdefault(owner, set()).add(name)
        self._subjects[key] = (display, owners)


def member_reference(node: ast.expr) -> tuple[str, str] | None:
    if not isinstance(node, ast.Attribute):
        return None
    if not isinstance(node.value, ast.Name):
        return None
    if not node.attr.isupper():
        return None

    return node.value.id, node.attr
