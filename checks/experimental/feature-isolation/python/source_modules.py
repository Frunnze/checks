import ast
from pathlib import Path

PackageChain = tuple[str, ...]


class SourceModule:
    def __init__(self, source_directory: Path) -> None:
        parts = source_directory.parts
        self._prefixes: list[str] = []

        for start in range(len(parts)):
            self._prefixes.append(".".join(parts[start:]) + ".")

    def of(self, module: str) -> str:
        for prefix in self._prefixes:
            if module.startswith(prefix):
                return module.removeprefix(prefix)

        return module


class RelativeSegments:
    def of(
        self, node: ast.ImportFrom, package: PackageChain
    ) -> list[str] | None:
        climbed = node.level - 1

        if climbed > len(package):
            return None

        segments = list(package[: len(package) - climbed])

        if node.module is not None:
            segments.extend(node.module.split("."))

        return segments
