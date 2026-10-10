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

import random

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
_KEYS = ["aaa", "bbb", "ccc", "ddd", "eee"]
_KEY_DOMAINS = st.lists(
    st.sampled_from(_KEYS), min_size=2, max_size=5, unique=True
).map(sorted)
_LITERAL_IMPORT = "from typing import Literal\n"
_SWAPPING_SEED = 6


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


def _literal(domain: list[str]) -> str:
    return f"Literal[{', '.join(repr(key) for key in domain)}]"


def _registry(name: str, domain: list[str], annotation: str) -> str:
    entries = ", ".join(f"{key!r}: len" for key in domain)

    return f"{name}{annotation} = {{{entries}}}\n"


@st.composite
def _module_lines(draw: st.DrawFn) -> tuple[list[str], list[str]]:
    aliases = draw(st.lists(_KEY_DOMAINS, max_size=2))
    alias_lines = [
        f"Axis{index} = {_literal(domain)}\n"
        for index, domain in enumerate(aliases)
    ]
    styles = ["plain", "inline", "alias"] if aliases else ["plain", "inline"]
    registries: list[str] = []

    for index in range(draw(st.integers(2, 5))):
        domain = draw(_KEY_DOMAINS)
        style = draw(st.sampled_from(styles))
        annotation = ""

        if style == "inline":
            annotation = f": dict[{_literal(domain)}, object]"
        if style == "alias":
            alias_index = draw(st.integers(0, len(aliases) - 1))
            annotation = f": dict[Axis{alias_index}, object]"
            domain = aliases[alias_index]

        registries.append(_registry(f"REGISTRY_{index}", domain, annotation))

    return alias_lines, registries


_WIDE_KEYS = ["aaa", "bbb", "ccc", "ddd"]
_NARROW_KEYS = ["aaa", "bbb", "ccc"]
_WIDE_ANNOTATION = f": dict[{_literal(_WIDE_KEYS)}, object]"
_ORDER_DEPENDENT_MODULE = (
    [f"Axis0 = {_literal(_NARROW_KEYS)}\n"],
    [
        _registry("REGISTRY_0", _WIDE_KEYS, _WIDE_ANNOTATION),
        _registry("REGISTRY_1", _WIDE_KEYS, ""),
        _registry("REGISTRY_2", _NARROW_KEYS, ""),
    ],
)


@given(lines=_module_lines(), seed=st.integers(min_value=0, max_value=9999))
@example(lines=_ORDER_DEPENDENT_MODULE, seed=_SWAPPING_SEED)
@settings(max_examples=200, deadline=None)
def test_fragmented_registry_property_ignores_statement_order(
    lines: tuple[list[str], list[str]], seed: int
) -> None:
    aliases, registries = lines
    shuffled = list(registries)
    random.Random(seed).shuffle(shuffled)
    header = _LITERAL_IMPORT + "".join(aliases)
    in_order = findings_for({"m.py": header + "".join(registries)})
    reordered = findings_for({"m.py": header + "".join(shuffled)})

    assert sorted(line.split(": ", 1)[1] for line in reordered) == sorted(
        line.split(": ", 1)[1] for line in in_order
    )
