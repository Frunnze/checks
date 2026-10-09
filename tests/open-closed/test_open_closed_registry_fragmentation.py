"""
Splitting one variant axis across several registries is an open/closed
defect because adding a variant forces an edit in every registry. Domain:
3-5 distinct variant names shared by a behaviour registry and a label
registry in separate modules, plus one extra variant added to only one of
them. Oracle: monotonicity - a pair of registries that already drifted
apart is strictly more fragmented than an identical pair, so a finder
that reports the identical pair must also report the drifted one.

Concrete inputs -> expected outputs:
- input (identical domains):
      labels.py:   LABELS = {'deck': 'Deck', 'file': 'File',
                             'note': 'Note'}
      handlers.py: HANDLERS = {'deck': deck, 'file': file, 'note': note}
  output: reported -> ["handlers.py:5: variant behavior is split across 2
  registries in 2 files: HANDLERS, LABELS"].
- input (shrunk falsifying example, now pinned as @example - handlers
  gained 'wide', labels did not):
      labels.py:   LABELS = {'deck': 'Deck', 'file': 'File',
                             'note': 'Note'}
      handlers.py: HANDLERS = {'deck': deck, 'file': file, 'note': note,
                               'wide': wide}
  output: expected a report, got [].
"""

from hypothesis import example, given, settings
from hypothesis import strategies as st

from open_closed_finder_support import (
    IDENTIFIERS,
    findings_for,
    handler_registry,
    label_registry,
    variant_sets,
)

_VARIANTS = ["deck", "file", "note"]
_EXTRA = "wide"


@st.composite
def _axis_with_extra(draw: st.DrawFn) -> tuple[list[str], str]:
    variants = draw(variant_sets)
    extra = draw(IDENTIFIERS.filter(lambda name: name not in variants))

    return variants, extra


@given(axis=_axis_with_extra())
@example(axis=(_VARIANTS, _EXTRA))
@settings(max_examples=150, deadline=None)
def test_fragmented_registry_property_survives_one_sided_growth(
    axis: tuple[list[str], str],
) -> None:
    variants, extra = axis
    aligned = findings_for(
        {
            "labels.py": label_registry("LABELS", variants),
            "handlers.py": handler_registry("HANDLERS", variants),
        }
    )
    drifted = findings_for(
        {
            "labels.py": label_registry("LABELS", variants),
            "handlers.py": handler_registry(
                "HANDLERS", [*variants, extra]
            ),
        }
    )

    assert not aligned or drifted


@given(axis=_axis_with_extra())
@example(axis=(_VARIANTS, _EXTRA))
@settings(max_examples=150, deadline=None)
def test_fragmented_registry_property_survives_extra_variant_everywhere(
    axis: tuple[list[str], str],
) -> None:
    variants, extra = axis
    aligned = findings_for(
        {
            "labels.py": label_registry("LABELS", variants),
            "handlers.py": handler_registry("HANDLERS", variants),
        }
    )
    grown = findings_for(
        {
            "labels.py": label_registry("LABELS", [*variants, extra]),
            "handlers.py": handler_registry(
                "HANDLERS", [*variants, extra]
            ),
        }
    )

    assert not aligned or grown
