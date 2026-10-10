import ast
import sys
from collections import defaultdict
from pathlib import Path
from typing import NamedTuple

from source_modules import PackageChain, RelativeSegments, SourceModule

SHARED_PACKAGE = "shared"
SHARED_PREFIX = f"{SHARED_PACKAGE}."
FEATURES_PACKAGE = "features"
MINIMUM_FEATURES = 2


class LonelyModule(NamedTuple):
    path: str
    features: tuple[str, ...]


class ModuleName:
    def __init__(self, source_directory: Path) -> None:
        self._source_directory = source_directory

    def of(self, path: Path) -> str:
        trail = path.relative_to(self._source_directory).parts
        dotted = ".".join(trail).removesuffix(".py")

        return dotted.removesuffix(".__init__")


class OwningFeature:
    def __init__(self, source_directory: Path) -> None:
        self._features_directory = source_directory / FEATURES_PACKAGE

    def of(self, path: Path) -> str | None:
        if not path.is_relative_to(self._features_directory):
            return None

        return path.relative_to(self._features_directory).parts[0]


class SharedImports:
    def __init__(
        self, source_module: SourceModule, package: PackageChain
    ) -> None:
        self._source_module = source_module
        self._package = package
        self._relative = RelativeSegments()

    def in_(self, tree: ast.Module) -> set[str]:
        found: set[str] = set()

        for node in ast.walk(tree):
            for module in self._modules_of(node):
                if module.split(".")[0] == SHARED_PACKAGE:
                    found.add(module)

        return found

    def _modules_of(self, node: ast.AST) -> list[str]:
        if isinstance(node, ast.ImportFrom):
            return self._from_imported(node)

        if isinstance(node, ast.Import):
            return [self._source_module.of(alias.name) for alias in node.names]

        return []

    def _from_imported(self, node: ast.ImportFrom) -> list[str]:
        if node.level:
            return self._relatively_imported(node)

        if node.module is None:
            return []

        return [
            self._source_module.of(f"{node.module}.{alias.name}")
            for alias in node.names
        ]

    def _relatively_imported(self, node: ast.ImportFrom) -> list[str]:
        base = self._relative.of(node, self._package)

        if base is None:
            return []

        return [".".join([*base, alias.name]) for alias in node.names]


class ImportedModule:
    def owners(self, imported: str, known: set[str]) -> list[str]:
        found: list[str] = []
        candidate = imported

        while candidate:
            if candidate in known:
                found.append(candidate)

            candidate = candidate.rpartition(".")[0]

        return found


class LonelyModules:
    def __init__(self, source_directory: Path) -> None:
        self._source_directory = source_directory
        self._source_module = SourceModule(source_directory)
        self._module_name = ModuleName(source_directory)
        self._owning_feature = OwningFeature(source_directory)

    def find_in(self, paths: list[str]) -> list[LonelyModule]:
        modules = {self._module_name.of(Path(p)): p for p in paths}
        shared = {name for name in modules if name.startswith(SHARED_PREFIX)}
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
        tree = ast.parse(path.read_bytes(), filename=str(path))
        feature = self._owning_feature.of(path)
        owning = ImportedModule()
        package = path.relative_to(self._source_directory).parts[:-1]
        imports = SharedImports(self._source_module, package)

        for imported in imports.in_(tree):
            for owner in owning.owners(imported, shared):
                if feature is not None:
                    callers[owner].add(feature)
                elif self._module_name.of(path) != owner:
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


source_directory = Path(sys.argv[1])
source_paths = [line for line in sys.stdin.read().split("\n") if line]

for lonely in LonelyModules(source_directory).find_in(source_paths):
    if lonely.features:
        reason = f"only {lonely.features[0]} imports it"
    else:
        reason = "no feature imports it"

    _ = sys.stdout.write(f"{lonely.path}: {reason}\n")
