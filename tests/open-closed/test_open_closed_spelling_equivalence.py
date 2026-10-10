"""
The open/closed finder must judge a closed dispatch by what it does, not
by how it is spelled. Domain: 3-5 distinct lowercase variant names and a
generated subject parameter, rendered into semantically equivalent
dispatch spellings. Oracle: differential - two spellings that compile to
the same decision must get the same verdict from the finder.

Concrete inputs -> expected outputs:
- input (or-chain spelling, variants ['deck', 'file', 'note']):
      def route(a_kind):
          if a_kind == 'deck' or a_kind == 'file' or a_kind == 'note':
              return 1
          return -1
  output: reported -> ["a.py:1: route compares a_kind to 3 strings:
  deck, file, note"].
- input (falsifying example, same decision written with `in`, now pinned
  as @example):
      def route(a_kind):
          if a_kind in ('deck', 'file', 'note'):
              return 1
          return -1
  output: expected a report, got [].
- input (falsifying example, same dispatch over an Enum axis, pinned as
  @example):
      class Kind(Enum):
          DECK = 'deck'
          FILE = 'file'
          NOTE = 'note'

      def route(a_kind):
          if a_kind == Kind.DECK:
              return 0
          if a_kind == Kind.FILE:
              return 1
          if a_kind == Kind.NOTE:
              return 2
          return -1
  output: expected a report, got [].
"""

from hypothesis import example, given, settings

from open_closed_finder_support import (
    constant_chain,
    enum_chain,
    equality_chain,
    findings_for,
    match_chain,
    membership_chain,
    or_chain,
    subject_names,
    variant_sets,
)

_VARIANTS = ["deck", "file", "note"]
_SUBJECT = "a_kind"


def _verdicts(sources: dict[str, str]) -> dict[str, bool]:
    verdicts: dict[str, bool] = {}

    for label, source in sources.items():
        verdicts[label] = bool(findings_for({"a.py": source}))

    return verdicts


@given(subject=subject_names, variants=variant_sets)
@example(subject=_SUBJECT, variants=_VARIANTS)
@settings(max_examples=150, deadline=None)
def test_membership_dispatch_property_matches_expanded_or_chain(
    subject: str, variants: list[str]
) -> None:
    verdicts = _verdicts(
        {
            "expanded": or_chain(subject, variants),
            "membership": membership_chain(subject, variants),
        }
    )

    assert verdicts["membership"] == verdicts["expanded"]


@given(subject=subject_names, variants=variant_sets)
@example(subject=_SUBJECT, variants=_VARIANTS)
@settings(max_examples=150, deadline=None)
def test_enum_dispatch_property_matches_string_dispatch(
    subject: str, variants: list[str]
) -> None:
    verdicts = _verdicts(
        {
            "strings": equality_chain(subject, variants),
            "enum": enum_chain(subject, variants),
        }
    )

    assert verdicts["enum"] == verdicts["strings"]


@given(subject=subject_names, variants=variant_sets)
@example(subject=_SUBJECT, variants=_VARIANTS)
@settings(max_examples=150, deadline=None)
def test_match_dispatch_property_matches_string_dispatch(
    subject: str, variants: list[str]
) -> None:
    verdicts = _verdicts(
        {
            "strings": equality_chain(subject, variants),
            "match": match_chain(subject, variants),
        }
    )

    assert verdicts["match"] == verdicts["strings"]


@given(subject=subject_names, variants=variant_sets)
@example(subject=_SUBJECT, variants=_VARIANTS)
@settings(max_examples=150, deadline=None)
def test_extracted_constant_dispatch_property_matches_literal_dispatch(
    subject: str, variants: list[str]
) -> None:
    verdicts = _verdicts(
        {
            "literals": equality_chain(subject, variants),
            "constants": constant_chain(subject, variants),
        }
    )

    assert verdicts["constants"] == verdicts["literals"]


def _enum_module(variants: list[str]) -> str:
    members = "".join(
        f"    {variant.upper()} = {variant!r}\n" for variant in variants
    )

    return f"from enum import Enum\n\n\nclass Kind(Enum):\n{members}\n\n"


def _node_classes(variants: list[str]) -> str:
    return "".join(
        f"class {variant.title()}Node:\n    pass\n\n\n" for variant in variants
    )


def _guarded_route(subject: str, condition: str) -> str:
    return (
        f"def route({subject}):\n"
        f"    if {condition}:\n        return 1\n"
        "    return -1\n"
    )


@given(subject=subject_names, variants=variant_sets)
@example(subject=_SUBJECT, variants=_VARIANTS)
@settings(max_examples=60, deadline=None)
def test_enum_dispatch_property_identity_matches_equality(
    subject: str, variants: list[str]
) -> None:
    equality = enum_chain(subject, variants)
    verdicts = _verdicts(
        {
            "equality": equality,
            "identity": equality.replace(" == Kind.", " is Kind."),
        }
    )

    assert verdicts["identity"] == verdicts["equality"]


@given(subject=subject_names, variants=variant_sets)
@example(subject=_SUBJECT, variants=_VARIANTS)
@settings(max_examples=60, deadline=None)
def test_enum_dispatch_property_membership_matches_or_chain(
    subject: str, variants: list[str]
) -> None:
    members = [f"Kind.{variant.upper()}" for variant in variants]
    expanded = " or ".join(f"{subject} == {member}" for member in members)
    contained = f"{subject} in ({', '.join(members)})"
    verdicts = _verdicts(
        {
            "expanded": _enum_module(variants)
            + _guarded_route(subject, expanded),
            "membership": _enum_module(variants)
            + _guarded_route(subject, contained),
        }
    )

    assert verdicts["membership"] == verdicts["expanded"]


@given(subject=subject_names, variants=variant_sets)
@example(subject=_SUBJECT, variants=_VARIANTS)
@settings(max_examples=60, deadline=None)
def test_type_dispatch_property_isinstance_union_matches_tuple(
    subject: str, variants: list[str]
) -> None:
    names = [f"{variant.title()}Node" for variant in variants]
    tupled = f"isinstance({subject}, ({', '.join(names)}))"
    unioned = f"isinstance({subject}, {' | '.join(names)})"
    classes = _node_classes(variants)

    assert findings_for(
        {"a.py": classes + _guarded_route(subject, unioned)}
    ) == findings_for({"a.py": classes + _guarded_route(subject, tupled)})


@given(subject=subject_names, variants=variant_sets)
@example(subject=_SUBJECT, variants=_VARIANTS)
@settings(max_examples=60, deadline=None)
def test_type_dispatch_property_membership_matches_identity_chain(
    subject: str, variants: list[str]
) -> None:
    names = [f"{variant.title()}Node" for variant in variants]
    chained = " or ".join(f"type({subject}) is {name}" for name in names)
    contained = f"type({subject}) in ({', '.join(names)})"
    classes = _node_classes(variants)

    assert findings_for(
        {"a.py": classes + _guarded_route(subject, contained)}
    ) == findings_for({"a.py": classes + _guarded_route(subject, chained)})


@given(variants=variant_sets)
@example(variants=_VARIANTS)
@settings(max_examples=60, deadline=None)
def test_literal_axis_property_type_statement_matches_assignment(
    variants: list[str],
) -> None:
    values = ", ".join(repr(variant) for variant in variants)
    entries = ", ".join(f"{variant!r}: len" for variant in variants)
    registries = (
        f"ENDPOINTS: dict[Channel, object] = {{{entries}}}\n"
        f"LABELS: dict[Channel, object] = {{{entries}}}\n"
    )
    header = "from typing import Literal\n"
    assigned = f"{header}Channel = Literal[{values}]\n{registries}"
    declared = f"{header}type Channel = Literal[{values}]\n{registries}"

    assert findings_for({"p.py": declared}) == findings_for(
        {"p.py": assigned}
    )
