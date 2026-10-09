import ast

DUNDER_AFFIX = "__"
ROUTE_VERBS = (
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "head",
    "options",
    "websocket",
)

FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef


class StatelessDefinition:
    def describes_no_behaviour(self, node: FunctionNode) -> bool:
        return (
            self._is_dunder(node)
            or self._is_route_handler(node)
            or self._is_stub(node)
        )

    def _is_dunder(self, node: FunctionNode) -> bool:
        return node.name.startswith(DUNDER_AFFIX) and node.name.endswith(
            DUNDER_AFFIX
        )

    def _is_route_handler(self, node: FunctionNode) -> bool:
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue

            called = decorator.func

            if (
                isinstance(called, ast.Attribute)
                and called.attr in ROUTE_VERBS
            ):
                return True

        return False

    def _is_stub(self, node: FunctionNode) -> bool:
        for statement in self._beyond_the_docstring(node):
            if not isinstance(statement, ast.Pass):
                return self._is_ellipsis(statement)

        return True

    def _beyond_the_docstring(self, node: FunctionNode) -> list[ast.stmt]:
        body = node.body
        opening = body[0]

        if isinstance(opening, ast.Expr) and isinstance(
            opening.value, ast.Constant
        ):
            if isinstance(opening.value.value, str):
                return body[1:]

        return body

    def _is_ellipsis(self, statement: ast.stmt) -> bool:
        if not isinstance(statement, ast.Expr):
            return False

        value = statement.value

        return isinstance(value, ast.Constant) and value.value is Ellipsis
