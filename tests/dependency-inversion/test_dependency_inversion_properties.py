import ast
import keyword

from dependency_inversion_support import (
    ConstructedCollaborator,
    collaborator_names,
    findings_for,
    message_for,
    repository_module,
    service_owning,
    wires_dependencies,
)
from hypothesis import assume, given
from hypothesis import strategies as st
from open_closed_finder_support import IDENTIFIERS
from python_structure_types import Module

_CLASS_NAMES = IDENTIFIERS.map(lambda name: name.title()).filter(
    lambda name: not keyword.iskeyword(name)
)
_OWNER_NAMES = _CLASS_NAMES.filter(
    lambda name: not wires_dependencies("service.py", name)
)


@given(owner=_OWNER_NAMES, collaborator=_CLASS_NAMES)
def test_constructed_collaborators_property_reports_only_construction(
    owner: str, collaborator: str
) -> None:
    assume(owner != collaborator)

    constructing = findings_for(
        {
            "collaborator.py": repository_module(collaborator),
            "service.py": service_owning(owner, [collaborator]),
        }
    )
    injected = (
        f"class {owner}:\n"
        f"    def __init__(self, dependency_0):\n"
        f"        self.dependency_0 = dependency_0\n"
        "    def run(self):\n        return None\n"
    )
    receiving = findings_for(
        {
            "collaborator.py": repository_module(collaborator),
            "service.py": injected,
        }
    )

    assert len(constructing) == 1
    assert collaborator in constructing[0]
    assert receiving == []


@given(name=_CLASS_NAMES, method=IDENTIFIERS)
def test_collaborator_names_property_needs_public_behavior(
    name: str, method: str
) -> None:
    behaving = _module_with(
        f"class {name}:\n    def {method}(self):\n        return None\n"
    )
    silent = _module_with(
        f"class {name}:\n    def _{method}(self):\n        return None\n"
    )

    assert name in collaborator_names(behaving)
    assert name not in collaborator_names(silent)


@given(
    owner=_CLASS_NAMES,
    collaborators=st.lists(_CLASS_NAMES, min_size=1, max_size=4, unique=True),
)
def test_message_for_property_names_the_owner_and_collaborators(
    owner: str, collaborators: list[str]
) -> None:
    finding = ConstructedCollaborator(
        "service.py", 2, owner, tuple(sorted(collaborators))
    )
    message = message_for(finding)

    assert owner in message
    assert all(collaborator in message for collaborator in collaborators)


@given(name=_CLASS_NAMES, suffix=st.sampled_from(["Factory", "Builder"]))
def test_wires_dependencies_property_exempts_composition_owners(
    name: str, suffix: str
) -> None:
    assert wires_dependencies("service.py", f"{name}{suffix}")
    assert wires_dependencies("app_factory.py", name)


def _module_with(source: str) -> list[Module]:
    return [Module("module.py", ast.parse(source), {})]
