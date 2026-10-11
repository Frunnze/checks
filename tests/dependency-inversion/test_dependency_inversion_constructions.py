import pytest
from dependency_inversion_support import findings_for, repository_module

_GENERIC_BASE = (
    "from typing import Generic, TypeVar\n"
    "ModelT = TypeVar('ModelT')\n"
    "class BaseRepository(Generic[ModelT]):\n"
    "    def get(self, key):\n        return None\n"
)


def _service(constructor_line: str) -> str:
    return (
        "class UnitService:\n"
        "    def __init__(self):\n"
        f"        {constructor_line}\n"
        "    def run(self):\n        return None\n"
    )


@pytest.mark.parametrize(
    "base", ["BaseRepository[User]", "BaseRepository['User']"]
)
def test_flags_a_collaborator_inheriting_behavior_from_a_generic_base(
    base: str,
) -> None:
    modules = {
        "base.py": _GENERIC_BASE,
        "repositories.py": (
            "class User:\n    pass\n"
            f"class UserRepository({base}):\n    model = User\n"
        ),
        "service.py": _service("self.repository = UserRepository()"),
    }

    assert findings_for(modules) == [
        (
            "service.py:2: UnitService constructs its own collaborators "
            "instead of receiving them: UserRepository"
        )
    ]


@pytest.mark.parametrize(
    "assignment",
    [
        "self.repository, self.cache = SqlRepository(), {}",
        "[self.cache, self.repository] = [{}, SqlRepository()]",
        "(self.repository, self.cache), self.size = (SqlRepository(), {}), 0",
    ],
)
def test_flags_a_collaborator_constructed_in_an_unpacked_assignment(
    assignment: str,
) -> None:
    modules = {
        "repository.py": repository_module("SqlRepository"),
        "service.py": _service(assignment),
    }

    assert findings_for(modules) == [
        (
            "service.py:2: UnitService constructs its own collaborators "
            "instead of receiving them: SqlRepository"
        )
    ]
