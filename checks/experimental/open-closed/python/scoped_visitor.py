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
