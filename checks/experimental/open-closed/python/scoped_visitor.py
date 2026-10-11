import ast


class ScopedVisitor(ast.NodeVisitor):
    def __init__(self, root: ast.AST) -> None:
        self._root = root

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if node is self._root:
            self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if node is self._root:
            self.generic_visit(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        if node is self._root:
            self.generic_visit(node)

    def visit_ClassDef(self, _node: ast.ClassDef) -> None:
        return


class BoundNames(ScopedVisitor):
    def __init__(self, root: ast.AST) -> None:
        super().__init__(root)
        self.names: set[str] = set()

    def visit_arg(self, node: ast.arg) -> None:
        self.names.add(node.arg)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Store):
            self.names.add(node.id)


def bound_names(scope: ast.AST) -> set[str]:
    visitor = BoundNames(scope)
    visitor.visit(scope)

    return visitor.names
