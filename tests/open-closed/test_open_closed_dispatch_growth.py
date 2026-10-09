"""
A closed dispatch only gets worse as variants are added, and reversing or
negating a comparison does not change which variants it selects between.
Domain: 3-5 distinct lowercase variant names plus one more, over string,
enum and membership dispatch spellings, with the comparison written left
to right, Yoda style, or negated. Oracle: monotonicity (a longer chain
over the same subject stays reported) and the metamorphic relation
"reversing the operands preserves the decision".

Concrete inputs -> expected outputs:
- input (3 variants, then the same chain with 'wide' appended):
      def route(a_kind):
          if a_kind == 'deck':
              return 0
          if a_kind == 'file':
              return 1
          if a_kind == 'note':
              return 2
          return -1
  output: reported with 3 variants -> still reported with 4
  ["a.py:1: route compares a_kind to 4 strings: deck, file, note, wide"].
- input (Yoda spelling of the same 3-variant chain):
      def route(a_kind):
          if 'deck' == a_kind:
              return 0
          if 'file' == a_kind:
              return 1
          if 'note' == a_kind:
              return 2
          return -1
  output: reported -> ["a.py:1: route compares a_kind to 3 strings:
  deck, file, note"], matching the left-to-right spelling.
"""

from hypothesis import example, given, settings
from hypothesis import strategies as st

from open_closed_finder_support import (
    IDENTIFIERS,
    enum_chain,
    equality_chain,
    findings_for,
    membership_chain,
    subject_names,
    variant_sets,
)

_VARIANTS = ["deck", "file", "note"]
_EXTRA = "wide"
_SUBJECT = "a_kind"


@st.composite
def _axis_with_extra(draw: st.DrawFn) -> tuple[list[str], str]:
    variants = draw(variant_sets)
    extra = draw(IDENTIFIERS.filter(lambda name: name not in variants))

    return variants, extra


def _yoda_chain(subject: str, variants: list[str]) -> str:
    branches = "".join(
        f"    if {variant!r} == {subject}:\n        return {index}\n"
        for index, variant in enumerate(variants)
    )

    return f"def route({subject}):\n{branches}    return -1\n"


def _negated_chain(subject: str, variants: list[str]) -> str:
    branches = "".join(
        f"    if {subject} != {variant!r}:\n        return {index}\n"
        for index, variant in enumerate(variants)
    )

    return f"def route({subject}):\n{branches}    return -1\n"


@given(axis=_axis_with_extra())
@example(axis=(_VARIANTS, _EXTRA))
@settings(max_examples=250, deadline=None)
def test_string_dispatch_property_stays_reported_as_variants_grow(
    axis: tuple[list[str], str],
) -> None:
    variants, extra = axis
    shorter = findings_for({"a.py": equality_chain(_SUBJECT, variants)})
    longer = findings_for(
        {"a.py": equality_chain(_SUBJECT, [*variants, extra])}
    )

    assert not shorter or longer


@given(axis=_axis_with_extra())
@example(axis=(_VARIANTS, _EXTRA))
@settings(max_examples=250, deadline=None)
def test_enum_dispatch_property_stays_reported_as_members_grow(
    axis: tuple[list[str], str],
) -> None:
    variants, extra = axis
    shorter = findings_for({"a.py": enum_chain(_SUBJECT, variants)})
    longer = findings_for({"a.py": enum_chain(_SUBJECT, [*variants, extra])})

    assert not shorter or longer


@given(axis=_axis_with_extra())
@example(axis=(_VARIANTS, _EXTRA))
@settings(max_examples=250, deadline=None)
def test_membership_dispatch_property_stays_reported_as_variants_grow(
    axis: tuple[list[str], str],
) -> None:
    variants, extra = axis
    shorter = findings_for({"a.py": membership_chain(_SUBJECT, variants)})
    longer = findings_for(
        {"a.py": membership_chain(_SUBJECT, [*variants, extra])}
    )

    assert not shorter or longer


@given(subject=subject_names, variants=variant_sets)
@example(subject=_SUBJECT, variants=_VARIANTS)
@settings(max_examples=250, deadline=None)
def test_string_dispatch_property_ignores_the_side_the_literal_is_on(
    subject: str, variants: list[str]
) -> None:
    forward = findings_for({"a.py": equality_chain(subject, variants)})
    reversed_operands = findings_for({"a.py": _yoda_chain(subject, variants)})

    assert reversed_operands == forward


@given(subject=subject_names, variants=variant_sets)
@example(subject=_SUBJECT, variants=_VARIANTS)
@settings(max_examples=250, deadline=None)
def test_string_dispatch_property_ignores_whether_equality_is_negated(
    subject: str, variants: list[str]
) -> None:
    equal = findings_for({"a.py": equality_chain(subject, variants)})
    negated = findings_for({"a.py": _negated_chain(subject, variants)})

    assert negated == equal
