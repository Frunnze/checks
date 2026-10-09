import ast
import sys
from pathlib import Path
from typing import NamedTuple

FEATURES_PACKAGE = "features"
FEATURES_PREFIX = f"{FEATURES_PACKAGE}."
FEATURES_DIRECTORY = ("src", "features")
ESCAPING_LEVEL = 2

PackageChain = tuple[str, ...]


class CrossFeatureImport(NamedTuple):
    path: str
    line_number: int
    imported: str


class FeatureLocation(NamedTuple):
    root: Path
    chain: PackageChain


class FeatureRoot:
    def of(self, path: Path) -> FeatureLocation | None:
        parts = path.parts
        depth = len(FEATURES_DIRECTORY)

        for index in range(len(parts) - depth):
            if parts[index : index + depth] != FEATURES_DIRECTORY:
                continue

            root = Path(*parts[: index + depth])

            return FeatureLocation(root, parts[index + depth : -1])

        return None


class FeatureSegments:
    def of(self, module: str) -> list[str] | None:
        if module == FEATURES_PACKAGE:
            return []

        if module.startswith(FEATURES_PREFIX):
            return module[len(FEATURES_PREFIX) :].split(".")

        return None


class ImportedChain:
    def under(self, root: Path, segments: list[str]) -> PackageChain:
        if not segments:
            return ()

        chain = [segments[0]]
        here = root / segments[0]

        for segment in segments[1:]:
            here = here / segment

            if not here.is_dir():
                break

            chain.append(segment)

        return tuple(chain)


class SiblingCrossing:
    def between(
        self, importer: PackageChain, imported: PackageChain
    ) -> str | None:
        if self._is_prefix(importer, imported):
            return None

        if self._is_prefix(imported, importer):
            return None

        divergence = self._shared_depth(importer, imported)

        return FEATURES_PREFIX + ".".join(imported[: divergence + 1])

    def _is_prefix(self, shorter: PackageChain, longer: PackageChain) -> bool:
        return longer[: len(shorter)] == shorter

    def _shared_depth(
        self, importer: PackageChain, imported: PackageChain
    ) -> int:
        depth = 0

        for mine, theirs in zip(importer, imported, strict=False):
            if mine != theirs:
                break

            depth += 1

        return depth


class CrossedFeature:
    def __init__(self, location: FeatureLocation) -> None:
        self.location: FeatureLocation = location
        self.segments: FeatureSegments = FeatureSegments()
        self.chain_of: ImportedChain = ImportedChain()
        self.crossing: SiblingCrossing = SiblingCrossing()

    def by(self, node: ast.Import | ast.ImportFrom) -> list[str]:
        if isinstance(node, ast.ImportFrom):
            return self._by_from_import(node)

        return self._by_plain_import(node)

    def _by_from_import(self, node: ast.ImportFrom) -> list[str]:
        if node.level >= ESCAPING_LEVEL:
            return ["." * node.level + (node.module or "")]

        if node.level or node.module is None:
            return []

        base = self.segments.of(node.module)

        if base is None:
            return []

        return self._crossings(
            [base + [alias.name] for alias in node.names]
        )

    def _by_plain_import(self, node: ast.Import) -> list[str]:
        reached: list[list[str]] = []

        for alias in node.names:
            segments = self.segments.of(alias.name)

            if segments is not None:
                reached.append(segments)

        return self._crossings(reached)

    def _crossings(self, reached: list[list[str]]) -> list[str]:
        found: list[str] = []

        for segments in reached:
            imported = self.chain_of.under(self.location.root, segments)
            crossed = self.crossing.between(self.location.chain, imported)

            if crossed is not None:
                found.append(crossed)

        return found


class CrossFeatureImports:
    def find_in(self, paths: list[str]) -> list[CrossFeatureImport]:
        found: set[CrossFeatureImport] = set()

        for path in paths:
            found.update(self._find_in_file(Path(path)))

        return sorted(found)

    def _find_in_file(self, path: Path) -> list[CrossFeatureImport]:
        location = FeatureRoot().of(path)

        if location is None or not location.chain:
            return []

        tree = ast.parse(path.read_text(encoding="utf-8"))

        return self._crossings_in(tree, path, CrossedFeature(location))

    def _crossings_in(
        self, tree: ast.Module, path: Path, crossed: CrossedFeature
    ) -> list[CrossFeatureImport]:
        found: list[CrossFeatureImport] = []

        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue

            for imported in crossed.by(node):
                found.append(
                    CrossFeatureImport(str(path), node.lineno, imported)
                )

        return found


source_paths = sys.stdin.read().split()

for crossing in CrossFeatureImports().find_in(source_paths):
    _ = sys.stdout.write(
        f"{crossing.path}:{crossing.line_number}: {crossing.imported}\n"
    )
