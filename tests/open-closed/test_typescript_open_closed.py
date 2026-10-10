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
