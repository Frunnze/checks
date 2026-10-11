"""
Registries keyed by the members of one enum split that enum's behaviour
however the keys reach the enum, so importing the module instead of the
class, or nesting the enum in a class, must keep the verdict. Domain: 3-5
distinct lowercase member names of a string Enum in app/kinds.py and two
registries in app/registries.py keyed by its members. Oracle: metamorphic -
every key spelling must get the verdict of `from app.kinds import Kind`.

Concrete inputs -> expected outputs:
- input (`from app.kinds import Kind`, members DECK, FILE and NOTE):
      HANDLERS = {Kind.DECK: open_deck, Kind.FILE: open_file,
                  Kind.NOTE: open_note}
      LABELS = {Kind.DECK: 'Deck', Kind.FILE: 'File', Kind.NOTE: 'Note'}
  output: reported -> ["registries.py:16: Kind behavior is split across 2
  registries in 1 file: HANDLERS, LABELS"].
- input (falsifying example, `from app import kinds` with keys spelled
  kinds.Kind.DECK, now pinned as @example):
  output: expected the same report, got [].
- input (falsifying example, the enum nested as Unit.Kind and imported
  with `from app.kinds import Unit`, pinned as @example):
  output: expected the same report, got [].
"""

from hypothesis import example, given, settings
from hypothesis import strategies as st

from open_closed_finder_support import IDENTIFIERS, findings_for

_MEMBERS = st.lists(IDENTIFIERS, min_size=3, max_size=5, unique=True)
_SPELLINGS = {
    "from app import kinds": "kinds.Kind",
    "import app.kinds as kinds": "kinds.Kind",
    "import app.kinds": "app.kinds.Kind",
    "from app.kinds import Unit": "Unit.Kind",
}
_PLAIN = "from app.kinds import Kind"


def _kinds_module(names: list[str], nested: bool) -> str:
    indent = "    " if nested else ""
    members = "".join(
        f"{indent}    {name.upper()} = {name!r}\n" for name in names
    )
    owner = "class Unit:\n" if nested else ""

    return (
        f"from enum import Enum\n\n\n{owner}"
        f"{indent}class Kind(Enum):\n{members}"
    )


def _modules(names: list[str], import_line: str) -> dict[str, str]:
    owner = _SPELLINGS.get(import_line, "Kind")
    handlers = "".join(
        f"def open_{name}(unit):\n    return {index}\n\n\n"
        for index, name in enumerate(names)
    )
    entries = ", ".join(
        f"{owner}.{name.upper()}: open_{name}" for name in names
    )
    labels = ", ".join(
        f"{owner}.{name.upper()}: {name.title()!r}" for name in names
    )

    return {
        "app/__init__.py": "",
        "app/kinds.py": _kinds_module(names, owner == "Unit.Kind"),
        "app/registries.py": (
            f"{import_line}\n\n\n{handlers}"
            f"HANDLERS = {{{entries}}}\nLABELS = {{{labels}}}\n"
        ),
    }


def _fragmentation(reports: list[str]) -> list[str]:
    return [report.split(" behavior", 1)[1] for report in reports]


@given(names=_MEMBERS, import_line=st.sampled_from(sorted(_SPELLINGS)))
@example(names=["deck", "file", "note"], import_line="from app import kinds")
@example(
    names=["deck", "file", "note"], import_line="from app.kinds import Unit"
)
@settings(max_examples=100, deadline=None)
def test_enum_keyed_registry_property_ignores_the_key_spelling(
    names: list[str], import_line: str
) -> None:
    expected = findings_for(_modules(names, _PLAIN))
    found = findings_for(_modules(names, import_line))

    assert expected
    assert _fragmentation(found) == _fragmentation(expected)
