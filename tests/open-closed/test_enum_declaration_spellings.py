"""
An enum stays an enum whether it subclasses Enum directly or through a
project base enum, and whatever values its members hold. Domain: an enum
Kind with members deck, file and note, declared with a direct Enum base or
through `class BaseKind(str, Enum)`, its members holding strings, auto()
or integers; dispatched by an if-chain over the members, or by a HANDLERS
and a LABELS registry keyed by them. Oracle: metamorphic - every spelling
gets the verdict of the direct, string-valued enum.

Concrete inputs -> expected outputs:
- input:
      class Kind(str, Enum):
          deck = 'deck'
          file = 'file'
          note = 'note'

      def route(kind):
          if kind == Kind.deck: return 0
          if kind == Kind.file: return 1
          if kind == Kind.note: return 2
  output: reported -> ["m.py:10: route compares kind to 3 enum members:
  Kind.deck, Kind.file, Kind.note"].
- input (falsifying example, pinned as @example): the same with
  `class BaseKind(str, Enum): pass` and `class Kind(BaseKind)`
  output: expected the same report, got [].
- input (falsifying example, pinned as @example): `DECK = auto()`,
  `FILE = auto()`, `NOTE = auto()` with
      HANDLERS = {Kind.DECK: open_deck, Kind.FILE: open_file,
                  Kind.NOTE: open_note}
      LABELS = {Kind.DECK: 'Deck', Kind.FILE: 'File', Kind.NOTE: 'Note'}
  output: expected "m.py:10: Kind behavior is split across 2 registries in
  1 file: HANDLERS, LABELS", got [].
"""

import subprocess
import sys
from pathlib import Path

import pytest
from hypothesis import example, given, settings
from hypothesis import strategies as st

from open_closed_finder_support import FINDER_DIRECTORY

FINDER = FINDER_DIRECTORY / "variant_dispatches.py"
MEMBERS = ("deck", "file", "note")
BASE_ENUM = "class BaseKind(str, Enum):\n    pass\n\n\n"
DECLARATIONS = {
    "direct": "class Kind(str, Enum):\n",
    "base_enum": BASE_ENUM + "class Kind(BaseKind):\n",
}
VALUES = {
    "string": "'{member}'",
    "auto": "auto()",
    "integer": "{index}",
}


def _enum_module(declaration: str, value: str, upper: bool) -> str:
    members = ""

    for index, member in enumerate(MEMBERS):
        name = member.upper() if upper else member
        member_value = VALUES[value].format(member=member, index=index)
        members += f"    {name} = {member_value}\n"

    return (
        "from enum import Enum, auto\n\n\n"
        f"{DECLARATIONS[declaration]}{members}\n\n"
    )


def _comparison_chain() -> str:
    branches = "".join(
        f"    if kind == Kind.{member}:\n        return {index}\n"
        for index, member in enumerate(MEMBERS)
    )

    return f"def route(kind):\n{branches}    return -1\n"


def _registries() -> str:
    handlers = ", ".join(
        f"Kind.{member.upper()}: open_{member}" for member in MEMBERS
    )
    labels = ", ".join(
        f"Kind.{member.upper()}: '{member.title()}'" for member in MEMBERS
    )

    return f"HANDLERS = {{{handlers}}}\nLABELS = {{{labels}}}\n"


def _findings(root: Path, source: str) -> list[str]:
    _ = (root / "m.py").write_text(source, encoding="utf-8")
    finished = subprocess.run(
        [sys.executable, str(FINDER)],
        input="m.py",
        capture_output=True,
        text=True,
        check=True,
        cwd=root,
    )

    return [line.split(": ", 1)[1] for line in finished.stdout.splitlines()]


@given(declaration=st.sampled_from(sorted(DECLARATIONS)))
@example(declaration="base_enum")
@settings(max_examples=4, deadline=None)
def test_enum_comparisons_property_keep_the_verdict_of_a_direct_enum(
    tmp_path_factory: pytest.TempPathFactory, declaration: str
) -> None:
    root = tmp_path_factory.mktemp("comparisons")
    source = _enum_module(declaration, "string", False) + _comparison_chain()

    assert _findings(root, source) == [
        (
            "route compares kind to 3 enum members: Kind.deck, Kind.file, "
            "Kind.note"
        )
    ]


@given(
    declaration=st.sampled_from(sorted(DECLARATIONS)),
    value=st.sampled_from(sorted(VALUES)),
)
@example(declaration="direct", value="auto")
@example(declaration="direct", value="integer")
@example(declaration="base_enum", value="string")
@settings(max_examples=8, deadline=None)
def test_enum_registries_property_keep_the_verdict_of_string_members(
    tmp_path_factory: pytest.TempPathFactory,
    declaration: str,
    value: str,
) -> None:
    root = tmp_path_factory.mktemp("registries")
    source = _enum_module(declaration, value, True) + _registries()

    assert _findings(root, source) == [
        (
            "Kind behavior is split across 2 registries in 1 file: "
            "HANDLERS, LABELS"
        )
    ]
