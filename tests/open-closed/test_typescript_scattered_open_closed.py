from pathlib import Path

from hypothesis import example, given, settings
from hypothesis import strategies as st
from open_closed_typescript_shapes import typescript_findings
from typescript_finder_support import CHECKS, report_from

_FINDER = CHECKS / "experimental" / "open-closed" / "typescript" / "variant_dispatches.js"
_WRAPPERS = [
    "{type}",
    "Readonly<{type}>",
    "Partial<{type}>",
    "Required<{type}>",
]
_DISJOINT_KINDS = st.lists(
    st.sampled_from(["file", "link", "text", "topic", "image", "audio"]),
    min_size=4,
    max_size=4,
    unique=True,
)


def _kind_check(type_name: str, wrapper: str, kinds: list[str]) -> str:
    union = " | ".join(f'"{kind}"' for kind in kinds)
    condition = " || ".join(f'value.kind === "{kind}"' for kind in kinds)
    annotation = wrapper.format(type=type_name)
    function = type_name.lower()

    return (
        f"type {type_name} = {{ kind: {union} }};\n"
        f"export function {function}(value: {annotation}): boolean {{\n"
        f"  return {condition};\n}}\n"
    )


def test_flags_one_variant_axis_dispatched_across_files(
    tmp_path: Path,
) -> None:
    files = {
        "src/features/import/models.ts": (
            "export type ImportRequest = {\n"
            '  readonly kind: "file" | "link" | "text";\n'
            "};\n"
        ),
        "src/features/import/label.ts": (
            'import type { ImportRequest } from "./models";\n'
            "export function label(request: ImportRequest): string {\n"
            '  if (request.kind === "file") return "File";\n'
            '  return request.kind === "link" ? "Link" : "Text";\n'
            "}\n"
        ),
        "src/features/import/origin.ts": (
            'import type { ImportRequest } from "./models";\n'
            "export function origin(request: ImportRequest): string {\n"
            '  return request.kind === "text" ? "typed" : "external";\n'
            "}\n"
        ),
    }

    assert report_from(_FINDER, tmp_path, files) == [
        (
            "src/features/import/label.ts:2: ImportRequest.kind dispatch "
            "is scattered across 2 functions in 2 files: file, link, text"
        )
    ]


def test_does_not_combine_properties_from_different_types(
    tmp_path: Path,
) -> None:
    files = {
        "src/first.ts": (
            'type First = { kind: "file" | "link" };\n'
            "export function first(value: First): boolean {\n"
            '  return value.kind === "file" || value.kind === "link";\n'
            "}\n"
        ),
        "src/second.ts": (
            'type Second = { kind: "text" | "topic" };\n'
            "export function second(value: Second): boolean {\n"
            '  return value.kind === "text" || value.kind === "topic";\n'
            "}\n"
        ),
    }

    assert report_from(_FINDER, tmp_path, files) == []


def test_flags_five_variants_in_scattered_dispatch(
    tmp_path: Path,
) -> None:
    files = {
        "ui-service/src/features/flashcards/flashcard-models.ts": (
            "export type FlashcardFace = {\n"
            '  kind: "basic" | "cloze" | "list" | "feynman" | "image";\n'
            "};\n"
        ),
        "ui-service/src/features/flashcards/a.ts": (
            'import type { FlashcardFace } from "./flashcard-models";\n'
            "export function a(face: FlashcardFace): boolean {\n"
            '  return face.kind === "basic" || face.kind === "cloze";\n'
            "}\n"
        ),
        "ui-service/src/features/flashcards/b.ts": (
            'import type { FlashcardFace } from "./flashcard-models";\n'
            "export function b(face: FlashcardFace): boolean {\n"
            '  return face.kind === "list" || face.kind === "feynman";\n'
            "}\n"
        ),
        "ui-service/src/features/flashcards/c.ts": (
            'import type { FlashcardFace } from "./flashcard-models";\n'
            "export function c(face: FlashcardFace): boolean {\n"
            '  return face.kind === "image";\n'
            "}\n"
        ),
    }

    assert report_from(_FINDER, tmp_path, files) == [
        (
            "ui-service/src/features/flashcards/a.ts:2: "
            "FlashcardFace.kind dispatch is scattered across 3 functions "
            "in 3 files: basic, cloze, feynman, image, list"
        )
    ]


@given(kinds=_DISJOINT_KINDS, wrapper=st.sampled_from(_WRAPPERS))
@example(kinds=["file", "link", "text", "topic"], wrapper="Readonly<{type}>")
@settings(max_examples=15, deadline=None)
def test_wrapped_types_property_never_combine_different_types(
    kinds: list[str], wrapper: str
) -> None:
    files = {
        "src/first.ts": _kind_check("First", wrapper, kinds[:2]),
        "src/second.ts": _kind_check("Second", wrapper, kinds[2:]),
    }

    assert typescript_findings(files) == []
