import ast

from ocp_findings import (
    EQUALITY_NODES,
    MAXIMUM_VARIANTS,
    MEMBERSHIP_NODES,
)
from scoped_visitor import ScopedVisitor


class StringComparisons(ScopedVisitor):
    def __init__(
        self, root: ast.AST, constants: dict[str, str] | None = None
    ) -> None:
        super().__init__(root)
        self._subjects: dict[str, tuple[str, set[str]]] = {}
        self._constants = constants or {}

    def collected(self) -> list[tuple[str, str, tuple[str, ...]]]:
        return self.with_at_least(MAXIMUM_VARIANTS + 1)

    def with_at_least(
        self, minimum_variants: int
    ) -> list[tuple[str, str, tuple[str, ...]]]:
        found: list[tuple[str, str, tuple[str, ...]]] = []

        for key, (subject, variants) in self._subjects.items():
            if len(variants) >= minimum_variants:
                found.append((key, subject, tuple(sorted(variants))))

        return sorted(found)

    def visit_Compare(self, node: ast.Compare) -> None:
        if len(node.ops) == 1 and isinstance(node.ops[0], EQUALITY_NODES):
            self._record_comparison(node.left, node.comparators[0])
        elif len(node.ops) == 1 and isinstance(node.ops[0], MEMBERSHIP_NODES):
            self._record_membership(node.left, node.comparators[0])

        self.generic_visit(node)

    def visit_Match(self, node: ast.Match) -> None:
        for match_case in node.cases:
            for pattern in ast.walk(match_case.pattern):
                if not isinstance(pattern, ast.MatchValue):
                    continue

                variant = self._string_from(pattern.value)

                if variant is not None:
                    self._record(node.subject, variant)

        self.generic_visit(node)

    def _record_comparison(self, left: ast.expr, right: ast.expr) -> None:
        left_string = self._string_from(left)
        right_string = self._string_from(right)

        if left_string is not None and right_string is None:
            self._record(right, left_string)
        elif right_string is not None and left_string is None:
            self._record(left, right_string)

    def _record_membership(
        self, subject: ast.expr, container: ast.expr
    ) -> None:
        if not isinstance(container, (ast.Tuple, ast.List, ast.Set)):
            return

        for element in container.elts:
            variant = self._string_from(element)

            if variant is not None:
                self._record(subject, variant)

    def _record(self, subject: ast.expr, variant: str) -> None:
        key = ast.dump(subject, include_attributes=False)
        display, variants = self._subjects.setdefault(
            key, (ast.unparse(subject), set())
        )
        variants.add(variant)
        self._subjects[key] = (display, variants)

    def _string_from(self, node: ast.expr) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        if isinstance(node, ast.Name):
            return self._constants.get(node.id)

        return None
