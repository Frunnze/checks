import sys
import tempfile
from pathlib import Path

from open_closed_finder_support import written_paths
from typescript_finder_support import CHECKS

FINDER_DIRECTORY = CHECKS / "experimental" / "dependency-inversion" / "python"

if str(FINDER_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(FINDER_DIRECTORY))

from collaborator_classes import collaborator_names, wires_dependencies
from constructed_collaborators import constructed_collaborators
from dependency_inversion_findings import (
    ConstructedCollaborator,
    message_for,
)

__all__ = [
    "ConstructedCollaborator",
    "collaborator_names",
    "findings_for",
    "message_for",
    "repository_module",
    "service_owning",
    "wires_dependencies",
]


def findings_for(modules: dict[str, str]) -> list[str]:
    with tempfile.TemporaryDirectory() as directory:
        paths = written_paths(Path(directory), modules)

        return [
            f"{Path(finding.path).name}:{finding.line_number}: "
            f"{message_for(finding)}"
            for finding in constructed_collaborators(paths)
        ]


def repository_module(name: str = "SqlUnitRepository") -> str:
    return (
        f"class {name}:\n"
        "    def fetch(self, unit_id):\n        return unit_id\n"
    )


def service_owning(owner: str, constructions: list[str]) -> str:
    assignments = "".join(
        f"        self.dependency_{index} = {construction}()\n"
        for index, construction in enumerate(constructions)
    )

    return (
        f"class {owner}:\n"
        "    def __init__(self):\n"
        f"{assignments}"
        "    def run(self):\n        return None\n"
    )
