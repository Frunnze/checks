"""Collect runtime structure, excluding annotations and nested scopes."""

import ast

from python_bindings import (
    SCOPES,
    bind_assignment,
    capture_name,
    is_docstring,
    qualified,
)
from python_flow import statement_flow
from srp_metrics import CallableFacts

BRANCHES = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.ExceptHandler,
    ast.IfExp,
    ast.comprehension,
)
NESTING = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.Try,
    ast.TryStar,
    ast.With,
    ast.AsyncWith,
    ast.Match,
    ast.IfExp,
)


class RuntimeMetrics:
    def __init__(
        self,
        facts: CallableFacts,
        bindings: dict[str, str],
        globals_: set[str],
        members: set[str],
        parameters: set[str],
        receivers: set[str] | None = None,
        shadowed: set[str] | None = None,
        method: bool = False,
        visible: dict[str, str] | None = None,
    ) -> None:
        self.facts = facts
        self.bindings = bindings
        self.globals = globals_
        self.members = members
        self.parameters = parameters
        self.receivers = receivers or set()
        self.shadowed = shadowed or set()
        self.method = method
        self.visible = visible or {}
        self.calls: set[str] = set()
        self.resources: set[str] = set()
        self.links: set[str] = set()
        self.locals: set[str] = set()
        self.lines: set[int] = set()
        self.references: set[str] = set()
        self.foreign_data: set[str] = set()
        self.call_targets: set[str] = set()
        self.block_calls: set[str] = set()
        self.block_links: set[str] = set()

    def statement(self, node: ast.AST) -> None:
        self.block_calls.clear()
        self.block_links.clear()
        self.visit(node)
        if not isinstance(node, (*SCOPES, ast.TypeAlias)) and not is_docstring(node):
            self.facts.flow.append(
                {
                    **statement_flow(node, self.block_calls),
                    "links": sorted(self.block_links),
                }
            )

    def visit(self, node: ast.AST, depth: int = 0) -> None:
        if isinstance(node, SCOPES) or is_docstring(node):
            return
        if isinstance(node, ast.TypeAlias):
            bind_assignment(node, self.bindings)
            return
        if name := capture_name(node):
            self.bindings[name] = "local:" + name
        if hasattr(node, "lineno"):
            self.lines.add(node.lineno)
        if isinstance(node, ast.stmt) and not isinstance(node, ast.Pass):
            self.facts.statements += 1
        if isinstance(node, BRANCHES):
            self.facts.complexity += 1
        if isinstance(node, ast.BoolOp):
            self.facts.complexity += len(node.values) - 1
        if isinstance(node, ast.comprehension):
            self.facts.complexity += len(node.ifs)
        if isinstance(node, ast.Match):
            self.facts.complexity += max(0, len(node.cases) - 1)
            self.facts.complexity += sum(case.guard is not None for case in node.cases)
        if isinstance(node, NESTING):
            depth += 1
            self.facts.nesting = max(self.facts.nesting, depth)
        if isinstance(node, ast.Call):
            self.record_call(node)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            self.record_reference(node)
        if isinstance(node, ast.Attribute):
            raw = qualified(node)
            parts = raw.split(".")
            receivers = self.receivers - self.locals
            if (
                len(parts) >= 2
                and parts[0] in receivers
                and parts[1] not in self.members
            ):
                self.resources.add("field:" + parts[1])
            resolved = qualified(node, self.bindings)
            if (
                isinstance(node.ctx, ast.Load)
                and (resolved.startswith("local:") or parts[0] in self.parameters)
                and (parts[0] not in receivers or len(parts) > 2)
            ):
                self.foreign_data.add(raw)
            if resolved and not resolved.startswith("local:"):
                self.references.add(resolved)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            self.locals.add(node.id)
        # Annotations and decorators are declarations, not method behavior.
        for field, value in ast.iter_fields(node):
            if field in {"annotation", "returns", "type_comment"}:
                continue
            children = value if isinstance(value, list) else [value]
            for child in children:
                if isinstance(child, ast.AST):
                    self.visit(child, depth)
        # The right-hand side still reads the binding being replaced.
        bind_assignment(node, self.bindings)

    def record_call(self, node: ast.Call) -> None:
        call = qualified(node.func, self.bindings)
        if call:
            self.calls.add(call)
            self.block_calls.add(call)
        raw = qualified(node.func)
        self.call_targets.add(raw)
        parts = raw.split(".")
        member = parts[-1]
        internal = (
            len(parts) == 1 and not self.method and member not in self.shadowed
        ) or (
            len(parts) == 2
            and parts[0] in self.receivers - self.locals
            and raw not in self.bindings
        )
        if member in self.members and internal:
            link = f"{self.facts.owner}.{member}"
            self.links.add(link)
            self.block_links.add(link)
        local = call.removeprefix("local:") if call.startswith("local:") else ""
        if local in self.visible and local not in self.locals:
            link = self.visible[local]
            self.links.add(link)
            self.block_links.add(link)

    def record_reference(self, node: ast.Name) -> None:
        resolved = self.bindings.get(node.id, "")
        if resolved and not resolved.startswith(("builtins.", "local:")):
            self.references.add(resolved)
            self.resources.add("dependency:" + resolved.lstrip(".").split(".")[0])
        elif node.id in self.globals and node.id not in self.bindings:
            self.resources.add("global:" + node.id)

    def finish(self) -> CallableFacts:
        self.facts.lines = len(self.lines)
        self.facts.locals = len(self.locals)
        self.facts.calls = sorted(self.calls)
        self.facts.resources = sorted(self.resources)
        self.facts.links = sorted(self.links)
        self.facts.references = sorted(self.references)
        self.facts.foreign_data = sorted(self.foreign_data - self.call_targets)
        return self.facts
