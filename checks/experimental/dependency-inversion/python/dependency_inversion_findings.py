from typing import NamedTuple


class ConstructedCollaborator(NamedTuple):
    path: str
    line_number: int
    owner_name: str
    collaborators: tuple[str, ...]


def message_for(finding: ConstructedCollaborator) -> str:
    names = ", ".join(finding.collaborators)

    return (
        f"{finding.owner_name} constructs its own collaborators instead "
        f"of receiving them: {names}"
    )
