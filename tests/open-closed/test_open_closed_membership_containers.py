"""
`x in (a, b, c)`, `x in [a, b, c]` and `x in {a, b, c}` select between the
same variants, so the finder must judge all three the same way, and a
registry whose keys are a subset of two equally wide registries must be
grouped the same way whichever order the files arrive in. Domain: 3-5
distinct lowercase variant names over the three container literals, and
three registries whose domains overlap ambiguously. Oracle: differential
across container spellings, plus permutation invariance over input paths.

Concrete inputs -> expected outputs:
- input (variants ['deck', 'file', 'note'], tuple then list then set):
      def route(a_kind):
          if a_kind in ('deck', 'file', 'note'):
              return 1
          return -1
  output: reported -> ["a.py:1: route compares a_kind to 3 strings:
  deck, file, note"], identical for `[...]` and `{...}`.
- input (ambiguous overlap - HANDLERS over {aaa, bbb, ccc} is a subset of
  both WIDE_ONE over {aaa, bbb, ccc, ddd} and WIDE_TWO over
  {aaa, bbb, ccc, eee}):
      wide_one.py, wide_two.py, narrow.py
  output: the same report set whichever order the three paths are given.
"""

import random

from hypothesis import example, given, settings
from hypothesis import strategies as st

from open_closed_finder_support import (
    findings_for,
    handler_registry,
    membership_chain,
    subject_names,
    variant_sets,
)

_VARIANTS = ["deck", "file", "note"]
_SUBJECT = "a_kind"
_SHARED = ["aaa", "bbb", "ccc"]


@given(subject=subject_names, variants=variant_sets)
@example(subject=_SUBJECT, variants=_VARIANTS)
@settings(max_examples=200, deadline=None)
def test_membership_dispatch_property_ignores_the_container_literal(
    subject: str, variants: list[str]
) -> None:
    reports = [
        findings_for({"a.py": membership_chain(subject, variants, container)})
        for container in range(3)
    ]

    assert reports[1] == reports[0]
    assert reports[2] == reports[0]


@given(seed=st.integers(min_value=0, max_value=9999))
@example(seed=0)
@settings(max_examples=100, deadline=None)
def test_fragmented_registry_property_groups_ambiguous_overlap_stably(
    seed: int,
) -> None:
    modules = {
        "wide_one.py": handler_registry("WIDE_ONE", [*_SHARED, "ddd"]),
        "wide_two.py": handler_registry("WIDE_TWO", [*_SHARED, "eee"]),
        "narrow.py": handler_registry("NARROW", _SHARED),
    }
    shuffled = list(modules)
    random.Random(seed).shuffle(shuffled)

    assert sorted(findings_for(modules, order=shuffled)) == sorted(
        findings_for(modules)
    )
