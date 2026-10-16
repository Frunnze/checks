"""
TypeScript registries keyed by enum members are one axis whatever values
the members hold: TypeScript's default enum is numeric. Domain: an enum
Kind with members Deck, File and Note holding their default numbers or
strings, and a HANDLERS and a LABELS registry keyed by computed member
keys, unannotated or annotated `Record<Kind, V>`. Oracle: metamorphic - the
numeric enum gets the report of the string enum.

Concrete inputs -> expected outputs:
- input (src/registries.ts):
      export enum Kind { Deck = "deck", File = "file", Note = "note" }
      export const HANDLERS = { [Kind.Deck]: () => 0,
                                [Kind.File]: () => 1,
                                [Kind.Note]: () => 2 };
      export const LABELS = { [Kind.Deck]: "Deck", [Kind.File]: "File",
                              [Kind.Note]: "Note" };
  output: one split-registry report naming HANDLERS and LABELS.
- input (falsifying example, pinned as @example): the same with
  `export enum Kind { Deck, File, Note }`
  output: expected the same report, got [] - only string literal keys
  formed a domain.
"""

from hypothesis import example, given, settings
from hypothesis import strategies as st
from open_closed_typescript_shapes import typescript_findings

MEMBERS = ("Deck", "File", "Note")
ANNOTATIONS = {
    "none": ("", ""),
    "record": (": Record<Kind, () => number>", ": Record<Kind, string>"),
}


def _registries(numeric: bool, annotation: str) -> str:
    if numeric:
        members = ", ".join(MEMBERS)
    else:
        members = ", ".join(f'{name} = "{name.lower()}"' for name in MEMBERS)

    handlers_type, labels_type = ANNOTATIONS[annotation]
    handlers = ", ".join(
        f"[Kind.{name}]: () => {index}" for index, name in enumerate(MEMBERS)
    )
    labels = ", ".join(f'[Kind.{name}]: "{name}"' for name in MEMBERS)

    return (
        f"export enum Kind {{ {members} }}\n"
        f"export const HANDLERS{handlers_type} = {{ {handlers} }};\n"
        f"export const LABELS{labels_type} = {{ {labels} }};\n"
    )


@given(annotation=st.sampled_from(sorted(ANNOTATIONS)))
@example(annotation="none")
@example(annotation="record")
@settings(max_examples=4, deadline=None)
def test_registries_property_numeric_enum_keys_form_the_same_axis(
    annotation: str,
) -> None:
    string_report = typescript_findings(
        {"src/registries.ts": _registries(False, annotation)}
    )
    numeric_report = typescript_findings(
        {"src/registries.ts": _registries(True, annotation)}
    )

    assert string_report != []
    assert numeric_report == string_report
