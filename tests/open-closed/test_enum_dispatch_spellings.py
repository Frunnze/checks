"""
A dispatch over enum members is closed wherever the enum is declared and
however it is imported, so nesting the enum inside a class or importing it
under another name must keep the verdict. Domain: 3-5 distinct lowercase
names rendered as upper, lower or title case members of a scanned Enum.
Oracle: metamorphic - the nested and the aliased spellings must get the
verdict of the top-level, plainly imported spelling.

Concrete inputs -> expected outputs:
- input (top-level enum):
      class Status(Enum):
          PENDING = 'pending'
          PAID = 'paid'
          SHIPPED = 'shipped'

      def label(order):
          if order.status == Status.PENDING: ...
          if order.status == Status.PAID: ...
          if order.status == Status.SHIPPED: ...
  output: reported -> ["m.py:10: label compares order.status to 3 enum
  members: Status.PAID, Status.PENDING, Status.SHIPPED"].
- input (falsifying example, the same enum nested as Order.Status and
  compared as Order.Status.PAID, now pinned as @example):
  output: expected the same report, got [].
- input (falsifying example, `from app.kinds import Kind as UnitKind`
  with members deck, file and note compared as UnitKind.deck, pinned as
  @example):
  output: expected "route.py:4: route compares kind to 3 enum members",
  got [].
"""

from hypothesis import example, given, settings
from hypothesis import strategies as st

from open_closed_finder_support import IDENTIFIERS, findings_for

_MEMBERS = st.lists(
    IDENTIFIERS.filter(lambda name: name not in {"true", "false", "none"}),
    min_size=3,
    max_size=5,
    unique=True,
)
_CASES = st.sampled_from(["upper", "lower", "title"])
_ENUM_IMPORT = "from enum import Enum\n\n\n"


def _spelled(names: list[str], case: str) -> list[str]:
    spellings = {
        "upper": [name.upper() for name in names],
        "lower": list(names),
        "title": [name.title() for name in names],
    }

    return spellings[case]


def _enum(name: str, members: list[str], indent: str) -> str:
    values = "".join(
        f"{indent}    {member} = {member.lower()!r}\n" for member in members
    )

    return f"{indent}class {name}(Enum):\n{values}"


def _dispatch(
    header: str, subject: str, owner: str, members: list[str]
) -> str:
    branches = "".join(
        f"    if {subject} == {owner}.{member}:\n        return {index}\n"
        for index, member in enumerate(members)
    )

    return f"{header}{branches}    return -1\n"


def _messages(reports: list[str]) -> list[str]:
    return [report.split(": ", 1)[1] for report in reports]


@given(names=_MEMBERS, case=_CASES)
@example(names=["pending", "paid", "shipped"], case="upper")
@settings(max_examples=100, deadline=None)
def test_enum_dispatch_property_ignores_nesting_the_enum_in_a_class(
    names: list[str], case: str
) -> None:
    members = _spelled(names, case)
    top_level = (
        _ENUM_IMPORT
        + _enum("Status", members, "")
        + "\n\n"
        + _dispatch("def label(order):\n", "order.status", "Status", members)
    )
    nested = (
        f"{_ENUM_IMPORT}class Order:\n"
        + _enum("Status", members, "    ")
        + "\n\n"
        + _dispatch(
            "def label(order):\n", "order.status", "Order.Status", members
        )
    )
    expected = findings_for({"m.py": top_level})

    assert expected
    assert _messages(findings_for({"m.py": nested})) == _messages(expected)


@given(names=_MEMBERS, case=_CASES)
@example(names=["deck", "file", "note"], case="lower")
@settings(max_examples=100, deadline=None)
def test_enum_dispatch_property_ignores_an_import_alias(
    names: list[str], case: str
) -> None:
    members = _spelled(names, case)
    kinds = _ENUM_IMPORT + _enum("Kind", members, "")
    plain = _dispatch(
        "from app.kinds import Kind\n\n\ndef route(kind):\n",
        "kind",
        "Kind",
        members,
    )
    aliased = _dispatch(
        "from app.kinds import Kind as UnitKind\n\n\ndef route(kind):\n",
        "kind",
        "UnitKind",
        members,
    )
    package = {"app/__init__.py": "", "app/kinds.py": kinds}
    expected = findings_for({**package, "app/route.py": plain})
    found = findings_for({**package, "app/route.py": aliased})

    assert expected
    assert [report.rsplit(":", 1)[0] for report in found] == [
        report.rsplit(":", 1)[0] for report in expected
    ]
