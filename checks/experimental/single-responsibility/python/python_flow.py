"""Conservative statement dependencies, not a full program-dependence graph."""

import ast

from python_bindings import SCOPES, is_docstring, qualified


class FlowNames(ast.NodeVisitor):
    def __init__(self) -> None:
        self.reads: set[str] = set()
        self.writes: set[str] = set()

    def visit(self, node: ast.AST) -> None:
        if not isinstance(node, SCOPES) and not is_docstring(node):
            super().visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            self.reads.add(node.id)
        elif isinstance(node.ctx, ast.Store):
            self.writes.add(node.id)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        name = qualified(node)
        if isinstance(node.ctx, ast.Store):
            self.writes.add(name)
        else:
            self.reads.add(name)
        if qualified(node.value) not in {"self", "cls"}:
            self.visit(node.value)

    def visit_Subscript(self, node: ast.Subscript) -> None:
        if isinstance(node.ctx, ast.Store):
            self.writes.add(qualified(node.value))
        self.visit(node.value)
        self.visit(node.slice)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self.reads.add(qualified(node.target))
        self.visit(node.target)
        self.visit(node.value)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.visit(node.target)
        if node.value is not None:
            self.visit(node.value)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Attribute):
            # A receiver may be mutated. Over-approximation preserves possible
            # dependencies and can lower confidence; it never executes code.
            receiver = qualified(node.func.value)
            if receiver:
                self.reads.add(receiver)
                self.writes.add(receiver)
            self.visit(node.func.value)
        for argument in (*node.args, *(keyword.value for keyword in node.keywords)):
            self.visit(argument)


def statement_flow(node: ast.AST, calls: set[str]) -> dict:
    names = FlowNames()
    names.visit(node)
    return {
        "line": getattr(node, "lineno", 0),
        "reads": sorted(names.reads),
        "writes": sorted(names.writes),
        "calls": sorted(calls),
        "compound": isinstance(
            node,
            (
                ast.If,
                ast.For,
                ast.AsyncFor,
                ast.While,
                ast.Try,
                ast.TryStar,
                ast.With,
                ast.AsyncWith,
                ast.Match,
            ),
        ),
    }
