"""
The TypeScript finder must reach the same verdict as its Python twin on
dispatch spellings that select between the same variants, and must keep
reporting a fragmented registry pair after one side gains a variant.
Domain: 3-4 distinct lowercase variant names rendered into if-chains,
or-chains, `Array.includes`, `switch` and `enum` member comparisons, plus
a behaviour registry and a label registry over the same axis. Oracle:
differential across spellings, and monotonicity for the registry pair.

Concrete inputs -> expected outputs:
- input (or-chain, variants ['deck', 'file', 'note']):
      export function route(kind: string): number {
        if (kind === 'deck' || kind === 'file' || kind === 'note') return 1;
        return -1;
      }
  output: reported -> ["a.ts:1: route compares kind to 3 strings:
  deck, file, note"], and the same verdict for
  `if (['deck', 'file', 'note'].includes(kind)) return 1;`.
- input (enum spelling of the same dispatch):
      export enum Kind { Deck = 'deck', File = 'file', Note = 'note' }
      export function route(kind: Kind): number {
        if (kind === Kind.Deck) return 0;
        if (kind === Kind.File) return 1;
        if (kind === Kind.Note) return 2;
        return -1;
      }
  output: reported -> ["a.ts:2: route compares kind to 3 enum members:
  Kind.Deck, Kind.File, Kind.Note"].
- input (untyped registry pair where HANDLERS gained 'quiz' and LABELS
  did not - a typed `Record<Kind, V>` cannot drift, the compiler enforces
  exhaustiveness, so drift only exists for object literals):
      labels.ts:   export const LABELS = { deck: 'Deck', file: 'File',
                                           note: 'Note' };
      handlers.ts: export const HANDLERS = { deck: () => 1, file: () => 1,
                                             note: () => 1, quiz: () => 1 };
  output: reported -> ["handlers.ts:1: variant behavior is split across 2
  registries in 2 files: HANDLERS, LABELS"].
"""

from hypothesis import example, given, settings
from hypothesis import strategies as st

from open_closed_finder_support import IDENTIFIERS
from open_closed_typescript_shapes import (
    enum_chain,
    equality_chain,
    handler_registry,
    includes_chain,
    label_registry,
    or_chain,
    switch_chain,
    typescript_findings,
)

_VARIANTS = ["deck", "file", "note"]
_EXTRA = "quiz"
variant_sets = st.lists(
    IDENTIFIERS, min_size=3, max_size=4, unique=True
).map(sorted)


def _reported(source: str) -> bool:
    return bool(typescript_findings({"a.ts": source}))


@given(variants=variant_sets)
@example(variants=_VARIANTS)
@settings(max_examples=15, deadline=None)
def test_includes_dispatch_property_matches_expanded_or_chain(
    variants: list[str]
) -> None:
    expanded = _reported(or_chain(variants))
    membership = _reported(includes_chain(variants))

    assert membership == expanded


@given(variants=variant_sets)
@example(variants=_VARIANTS)
@settings(max_examples=15, deadline=None)
def test_enum_dispatch_property_matches_string_dispatch(
    variants: list[str]
) -> None:
    strings = _reported(equality_chain(variants))
    members = _reported(enum_chain(variants))

    assert members == strings


@given(variants=variant_sets)
@example(variants=_VARIANTS)
@settings(max_examples=15, deadline=None)
def test_switch_dispatch_property_matches_if_chain_dispatch(
    variants: list[str]
) -> None:
    chained = _reported(equality_chain(variants))
    switched = _reported(switch_chain(variants))

    assert switched == chained


@given(variants=variant_sets)
@example(variants=_VARIANTS)
@settings(max_examples=15, deadline=None)
def test_fragmented_registry_property_survives_one_sided_growth(
    variants: list[str]
) -> None:
    aligned = typescript_findings(
        {
            "labels.ts": label_registry("LABELS", variants),
            "handlers.ts": handler_registry("HANDLERS", variants),
        }
    )
    drifted = typescript_findings(
        {
            "labels.ts": label_registry("LABELS", variants),
            "handlers.ts": handler_registry("HANDLERS", [*variants, _EXTRA]),
        }
    )

    assert not aligned or drifted
