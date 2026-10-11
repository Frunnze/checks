"""
A registry annotated with a string-keyed `Record` must still be grouped by
the keys of its object literal, like the same registry left unannotated or
annotated `{ [key: string]: V }`.
Domain: a LABELS and a HANDLERS registry over 3-5 shared keys, each
annotated with nothing, an index signature, `Record<string, V>`,
`Readonly<Record<string, V>>` or `Partial<Record<string, V>>`; and a
`Record<Kind, V>` registry beside a `Record<string, V>` one in one file.
Oracle: the fragmentation finding of the unannotated registries.

Concrete inputs -> expected outputs:
- input:
      src/labels.ts:   export const LABELS: Record<string, string> =
                         { deck: "Deck", file: "File", note: "Note" };
      src/handlers.ts: export const HANDLERS: Record<string, () => number> =
                         { deck: () => 1, file: () => 1, note: () => 1 };
  output: reported once per file -> ["src/handlers.ts:1: variant behavior
  is split across 2 registries in 2 files: HANDLERS, LABELS",
  "src/labels.ts:1: variant behavior is split across 2 registries in 2
  files: HANDLERS, LABELS"] (was []).
- input:
      src/registries.ts:
        type Kind = "deck" | "file" | "note";
        export const LABELS: Record<Kind, string> = { ... };
        export const HANDLERS: Record<string, () => number> = { ... };
  output: reported -> ["src/registries.ts:2: Kind behavior is split across
  2 registries in 1 file: HANDLERS, LABELS"] (was []).
"""

from hypothesis import example, given, settings
from hypothesis import strategies as st
from open_closed_typescript_shapes import typescript_findings

_KEYS = ["deck", "file", "note", "quiz", "link"]
_ANNOTATIONS = {
    "none": "",
    "index_signature": ": {{ [key: string]: {value} }}",
    "record": ": Record<string, {value}>",
    "readonly_record": ": Readonly<Record<string, {value}>>",
    "partial_record": ": Partial<Record<string, {value}>>",
}
_KIND_ANNOTATIONS = [
    ": Record<Kind, {value}>",
    ": Readonly<Record<Kind, {value}>>",
]
_STRING_ANNOTATIONS = [
    ": Record<string, {value}>",
    ": Readonly<Record<string, {value}>>",
]
_KEY_SETS = st.lists(st.sampled_from(_KEYS), min_size=3, max_size=5,
                     unique=True)


def _registry(name: str, keys: list[str], annotation: str, label: bool) -> str:
    value_type = "string" if label else "() => number"
    entries = ", ".join(
        f'{key}: "{key.title()}"' if label else f"{key}: () => 1"
        for key in keys
    )
    typed = annotation.format(value=value_type)

    return f"export const {name}{typed} = {{ {entries} }};\n"


@given(
    keys=_KEY_SETS,
    labels=st.sampled_from(sorted(_ANNOTATIONS)),
    handlers=st.sampled_from(sorted(_ANNOTATIONS)),
)
@example(keys=["deck", "file", "note"], labels="record", handlers="record")
@example(
    keys=["deck", "file", "note"],
    labels="readonly_record",
    handlers="readonly_record",
)
@settings(max_examples=8, deadline=None)
def test_string_keyed_record_property_keeps_the_registry(
    keys: list[str], labels: str, handlers: str
) -> None:
    findings = typescript_findings(
        {
            "src/labels.ts": _registry(
                "LABELS", keys, _ANNOTATIONS[labels], label=True
            ),
            "src/handlers.ts": _registry(
                "HANDLERS", keys, _ANNOTATIONS[handlers], label=False
            ),
        }
    )
    message = (
        "variant behavior is split across 2 registries in 2 files: "
        "HANDLERS, LABELS"
    )

    assert findings == [
        f"src/handlers.ts:1: {message}",
        f"src/labels.ts:1: {message}",
    ]


@given(
    keys=_KEY_SETS,
    kind_annotation=st.sampled_from(_KIND_ANNOTATIONS),
    string_annotation=st.sampled_from(_STRING_ANNOTATIONS),
)
@example(
    keys=["deck", "file", "note"],
    kind_annotation=": Record<Kind, {value}>",
    string_annotation=": Record<string, {value}>",
)
@settings(max_examples=6, deadline=None)
def test_string_keyed_record_property_joins_the_typed_registry(
    keys: list[str], kind_annotation: str, string_annotation: str
) -> None:
    union = " | ".join(f'"{key}"' for key in keys)
    source = (
        f"type Kind = {union};\n"
        + _registry("LABELS", keys, kind_annotation, label=True)
        + _registry("HANDLERS", keys, string_annotation, label=False)
    )

    assert typescript_findings({"src/registries.ts": source}) == [
        "src/registries.ts:2: Kind behavior is split across 2 registries "
        "in 1 file: HANDLERS, LABELS"
    ]
