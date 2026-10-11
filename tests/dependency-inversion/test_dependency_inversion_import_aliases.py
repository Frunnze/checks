"""
Importing a collaborator under another name still builds the same class,
so an aliased import must not hide the construction. Domain: generated
collaborator and alias names, the collaborator a repository class with
public behaviour in app/repositories.py and the service constructing it in
app/service.py. Oracle: metamorphic - the aliased import must get the
verdict of the plain import.

Concrete inputs -> expected outputs:
- input (plain import):
      from app.repositories import SqlunitRepository

      class UnitService:
          def __init__(self):
              self.repository = SqlunitRepository()
  output: reported -> ["service.py:5: UnitService constructs its own
  collaborators instead of receiving them: SqlunitRepository"].
- input (falsifying example, the same class imported as UnitStore and
  built as UnitStore(), now pinned as @example):
  output: expected the same report, got [].
"""

from dependency_inversion_support import findings_for, repository_module
from hypothesis import example, given, settings
from open_closed_finder_support import IDENTIFIERS


def _modules(
    collaborator: str, import_line: str, built: str
) -> dict[str, str]:
    return {
        "app/__init__.py": "",
        "app/repositories.py": repository_module(collaborator),
        "app/service.py": (
            f"{import_line}\n\n\nclass UnitService:\n"
            "    def __init__(self):\n"
            f"        self.repository = {built}()\n"
            "    def run(self):\n        return None\n"
        ),
    }


@given(name=IDENTIFIERS, alias=IDENTIFIERS)
@example(name="sqlunit", alias="unit")
@settings(max_examples=100, deadline=None)
def test_constructed_collaborators_property_ignores_an_import_alias(
    name: str, alias: str
) -> None:
    collaborator = f"{name.title()}Repository"
    local = f"{alias.title()}Store"
    plain = _modules(
        collaborator,
        f"from app.repositories import {collaborator}",
        collaborator,
    )
    aliased = _modules(
        collaborator,
        f"from app.repositories import {collaborator} as {local}",
        local,
    )
    expected = findings_for(plain)

    assert expected
    assert findings_for(aliased) == expected
