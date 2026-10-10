from pathlib import Path

from hypothesis import example, given, settings
from hypothesis import strategies as st
from open_closed_typescript_shapes import equality_chain, typescript_findings
from typescript_finder_support import CHECKS, report_from

_FINDER = CHECKS / "experimental" / "open-closed" / "typescript" / "variant_dispatches.js"
_MODULE = "src/features/folder/ImportSource.tsx"


def _report_for(tmp_path: Path, source: str) -> list[str]:
    return report_from(_FINDER, tmp_path, {_MODULE: source})


def _face_view_with(variants: list[str]) -> str:
    matches = ""

    for variant in variants:
        matches += (
            f'    <Match when={{props.face.kind === "{variant}"}}>'
            f"{variant}</Match>\n"
        )

    return (
        "export function FaceView(props: Props): JSX.Element {\n"
        f"  return <Switch>\n{matches}  </Switch>;\n"
        "}\n"
    )


def test_flags_three_strings_compared_to_one_subject(
    tmp_path: Path,
) -> None:
    source = (
        "export function href(unit: Unit): string {\n"
        '  if (unit.kind === "folder") return "/folder";\n'
        '  if (unit.kind === "file") return "/file";\n'
        '  return unit.kind !== "note" ? "/other" : "/note";\n'
        "}\n"
    )

    assert _report_for(tmp_path, source) == [
        (
            f"{_MODULE}:1: href compares unit.kind to 3 strings: "
            "file, folder, note"
        )
    ]

def test_flags_three_string_switch_cases(tmp_path: Path) -> None:
    source = (
        "export function label(unit: Unit): string {\n"
        "  switch (unit.kind) {\n"
        '    case "folder": return "Folder";\n'
        '    case "file": return "File";\n'
        '    case "note": return "Note";\n'
        "  }\n"
        "}\n"
    )

    assert _report_for(tmp_path, source) == [
        (
            f"{_MODULE}:1: label compares unit.kind to 3 strings: "
            "file, folder, note"
        )
    ]


def test_flags_solid_match_comparisons(tmp_path: Path) -> None:
    source = (
        "export function View(props: Props): JSX.Element {\n"
        "  return <Switch>\n"
        '    <Match when={props.kind === "folder"}>Folder</Match>\n'
        '    <Match when={props.kind === "file"}>File</Match>\n'
        '    <Match when={props.kind === "note"}>Note</Match>\n'
        "  </Switch>;\n"
        "}\n"
    )

    assert _report_for(tmp_path, source) == [
        (
            f"{_MODULE}:1: View compares props.kind to 3 strings: "
            "file, folder, note"
        )
    ]


def test_allows_two_strings_for_one_subject(tmp_path: Path) -> None:
    source = (
        "export function href(unit: Unit): string {\n"
        '  if (unit.kind === "folder") return "/folder";\n'
        '  return unit.kind === "file" ? "/file" : "/other";\n'
        "}\n"
    )

    assert _report_for(tmp_path, source) == []


def test_does_not_combine_different_subjects(tmp_path: Path) -> None:
    source = (
        "export function href(unit: Unit, source: Source): string {\n"
        '  if (unit.kind === "folder") return "/folder";\n'
        '  if (unit.kind === "file") return "/file";\n'
        '  return source.kind === "note" ? "/note" : "/other";\n'
        "}\n"
    )

    assert _report_for(tmp_path, source) == []


def test_treats_nested_functions_as_separate_scopes(
    tmp_path: Path,
) -> None:
    source = (
        "export function outer(unit: Unit): string {\n"
        '  if (unit.kind === "folder") return "/folder";\n'
        "  const inner = (): string => {\n"
        '    if (unit.kind === "file") return "/file";\n'
        '    return unit.kind === "note" ? "/note" : "/other";\n'
        "  };\n"
        "  return inner();\n"
        "}\n"
    )

    assert _report_for(tmp_path, source) == []


def test_ignores_runtime_type_checks(tmp_path: Path) -> None:
    source = (
        "export function decode(value: unknown): unknown {\n"
        '  if (typeof value === "string") return value;\n'
        '  if (typeof value === "number") return value;\n'
        '  return typeof value === "boolean" ? value : null;\n'
        "}\n"
    )

    assert _report_for(tmp_path, source) == []


def test_flags_four_strings_compared_to_one_subject(tmp_path: Path) -> None:
    module = "ui-service/src/features/flashcards/FaceView.tsx"
    source = _face_view_with(["basic", "cloze", "list", "feynman"])

    assert report_from(_FINDER, tmp_path, {module: source}) == [
        (
            f"{module}:1: FaceView compares props.face.kind to 4 strings: "
            "basic, cloze, feynman, list"
        )
    ]


def test_flags_five_strings_compared_to_one_subject(
    tmp_path: Path,
) -> None:
    module = "ui-service/src/features/flashcards/FaceView.tsx"
    variants = ["basic", "cloze", "list", "feynman", "image"]
    source = _face_view_with(variants)

    assert report_from(_FINDER, tmp_path, {module: source}) == [
        (
            f"{module}:1: FaceView compares props.face.kind to 5 strings: "
            "basic, cloze, feynman, image, list"
        )
    ]


def test_flags_dispatch_over_as_const_values(tmp_path: Path) -> None:
    files = {
        "src/kinds.ts": (
            "export const Kind = {\n"
            "  Deck: 'deck', File: 'file', Note: 'note'\n"
            "} as const;\n"
            "export type Kind = (typeof Kind)[keyof typeof Kind];\n"
            "export function route(kind: Kind): number {\n"
            "  if (kind === Kind.Deck) return 0;\n"
            "  if (kind === Kind.File) return 1;\n"
            "  return kind === Kind.Note ? 2 : -1;\n"
            "}\n"
        ),
        "src/names.ts": (
            "const DECK = 'deck' as const;\n"
            "const FILE = 'file' as const;\n"
            "const NOTE = 'note' as const;\n"
            "export function name(kind: string): number {\n"
            "  if (kind === DECK) return 0;\n"
            "  if (kind === FILE) return 1;\n"
            "  return kind === NOTE ? 2 : -1;\n"
            "}\n"
        ),
    }

    assert report_from(_FINDER, tmp_path, files) == [
        (
            "src/kinds.ts:5: route compares kind to 3 enum members: "
            "Kind.Deck, Kind.File, Kind.Note"
        ),
        "src/names.ts:4: name compares kind to 3 strings: deck, file, note",
    ]


def test_flags_constants_imported_from_another_module(
    tmp_path: Path,
) -> None:
    files = {
        "src/kinds.ts": (
            "export const DECK = 'deck';\n"
            "export const FILE = 'file';\n"
            "export const NOTE = 'note';\n"
        ),
        "src/route.ts": (
            "import { DECK, FILE, NOTE } from './kinds';\n"
            "export function route(kind: string): number {\n"
            "  if (kind === DECK) return 0;\n"
            "  if (kind === FILE) return 1;\n"
            "  return kind === NOTE ? 2 : -1;\n"
            "}\n"
        ),
    }

    assert report_from(_FINDER, tmp_path, files) == [
        "src/route.ts:2: route compares kind to 3 strings: deck, file, note"
    ]


def test_flags_enum_members_listed_in_includes(tmp_path: Path) -> None:
    source = (
        "export enum Kind { Deck = 'deck', File = 'file', Note = 'note' }\n"
        "export function isKnown(kind: Kind): boolean {\n"
        "  return [Kind.Deck, Kind.File, Kind.Note].includes(kind);\n"
        "}\n"
    )

    assert _report_for(tmp_path, source) == [
        (
            f"{_MODULE}:2: isKnown compares kind to 3 enum members: "
            "Kind.Deck, Kind.File, Kind.Note"
        )
    ]


def test_flags_enum_dispatch_imported_through_a_tsconfig_path_alias(
    tmp_path: Path,
) -> None:
    _ = (tmp_path / "tsconfig.json").write_text(
        '{ "compilerOptions": { "paths": { "@/*": ["./src/*"] } } }\n',
        encoding="utf-8",
    )
    files = {
        "src/kinds.ts": (
            "export enum Kind { Deck = 'deck', File = 'file', Note = 'note' }\n"
        ),
        "src/route.ts": (
            "import { Kind } from '@/kinds';\n"
            "export function route(kind: Kind): number {\n"
            "  if (kind === Kind.Deck) return 0;\n"
            "  if (kind === Kind.File) return 1;\n"
            "  return kind === Kind.Note ? 2 : -1;\n"
            "}\n"
        ),
    }

    assert report_from(_FINDER, tmp_path, files) == [
        (
            "src/route.ts:2: route compares kind to 3 enum members: "
            "Kind.Deck, Kind.File, Kind.Note"
        )
    ]


@given(name=st.text(alphabet="ab \t", min_size=1, max_size=8))
@example(name="a b")
@settings(max_examples=15, deadline=None)
def test_file_name_whitespace_property_keeps_the_file_analysed(
    name: str,
) -> None:
    module = f"src/{name}.ts"
    source = equality_chain(["deck", "file", "note"])

    assert typescript_findings({module: source}) == [
        f"{module}:1: route compares kind to 3 strings: deck, file, note"
    ]
