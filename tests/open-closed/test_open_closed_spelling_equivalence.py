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
