import ast
import sys
from collections import defaultdict
from pathlib import Path
from typing import NamedTuple

SHARED_PACKAGE = "shared"
FEATURES_PACKAGE = "features"
MINIMUM_FEATURES = 2


class LonelyModule(NamedTuple):
    path: str
    features: tuple[str, ...]


class ModuleName:
    def of(self, path: Path) -> str:
        parts = path.parts
        index = parts.index("src")
        trail = parts[index + 1 :]
        dotted = ".".join(trail).removesuffix(".py")

        return dotted.removesuffix(".__init__")


class OwningFeature:
    def of(self, path: Path) -> str | None:
        parts = path.parts

        if FEATURES_PACKAGE not in parts:
            return None

        index = parts.index(FEATURES_PACKAGE)

        if index + 1 >= len(parts):
            return None

        return parts[index + 1]


class SharedImports:
    def in_(self, tree: ast.Module) -> set[str]:
        found: set[str] = set()

        for node in ast.walk(tree):
            for module in self._modules_of(node):
                if module.split(".")[0] == SHARED_PACKAGE:
                    found.add(module)

        return found

    def _modules_of(self, node: ast.AST) -> list[str]:
        if isinstance(node, ast.ImportFrom):
            return [] if node.level else [node.module or ""]

        if isinstance(node, ast.Import):
            return [alias.name for alias in node.names]

        return []


class ImportedModule:
    def owning(self, imported: str, known: set[str]) -> str | None:
        candidate = imported

        while candidate:
            if candidate in known:
                return candidate

            candidate = candidate.rpartition(".")[0]

        return None


class LonelyModules:
    def find_in(self, paths: list[str]) -> list[LonelyModule]:
        modules = {ModuleName().of(Path(p)): p for p in paths}
        shared = {
            name for name in modules if name.split(".")[0] == SHARED_PACKAGE
        }
        callers: dict[str, set[str]] = defaultdict(set)
        kept: set[str] = set()

        for path in paths:
            self._record(Path(path), shared, callers, kept)

        return self._lonely(shared, modules, callers, kept)

    def _record(
        self,
        path: Path,
        shared: set[str],
        callers: dict[str, set[str]],
        kept: set[str],
    ) -> None:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        feature = OwningFeature().of(path)
        owning = ImportedModule()

        for imported in SharedImports().in_(tree):
            owner = owning.owning(imported, shared)

            if owner is None:
                continue

            if feature is not None:
                callers[owner].add(feature)
            elif ModuleName().of(path) != owner:
                kept.add(owner)

    def _lonely(
        self,
        shared: set[str],
        modules: dict[str, str],
        callers: dict[str, set[str]],
        kept: set[str],
    ) -> list[LonelyModule]:
        found: list[LonelyModule] = []

        for name in sorted(shared):
            if name in kept:
                continue

            features = callers[name]

            if len(features) >= MINIMUM_FEATURES:
                continue

            found.append(LonelyModule(modules[name], tuple(sorted(features))))

        return found


source_paths = sys.stdin.read().split()

for lonely in LonelyModules().find_in(source_paths):
    if lonely.features:
        reason = f"only {lonely.features[0]} imports it"
    else:
        reason = "no feature imports it"

    _ = sys.stdout.write(f"{lonely.path}: {reason}\n")
