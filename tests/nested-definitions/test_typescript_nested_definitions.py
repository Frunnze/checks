from pathlib import Path

from typescript_finder_support import CHECKS, report_from

_FINDER = CHECKS / "experimental" / "nested-definitions" / "typescript" / "nested_definitions.js"
_MODULE = "src/features/folder/units.ts"


def _report_for(tmp_path: Path, source: str) -> list[str]:
    return report_from(_FINDER, tmp_path, {_MODULE: source})


def test_flags_a_function_declared_inside_a_function(
    tmp_path: Path,
) -> None:
    source = (
        "export function outer(value: number): number {\n"
        "  function inner(other: number): number {\n"
        "    return other;\n"
        "  }\n"
        "\n"
        "  return inner(value);\n"
        "}\n"
    )

    assert _report_for(tmp_path, source) == [f"{_MODULE}:2: inner"]


def test_flags_a_function_declared_inside_an_arrow_function(
    tmp_path: Path,
) -> None:
    source = (
        "export const outer = (): number => {\n"
        "  function inner(): number {\n"
        "    return 1;\n"
        "  }\n"
        "\n"
        "  return inner();\n"
        "}\n"
    )

    assert _report_for(tmp_path, source) == [f"{_MODULE}:2: inner"]


def test_flags_a_function_declared_inside_a_method(tmp_path: Path) -> None:
    source = (
        "export class Units {\n"
        "  count(): number {\n"
        "    function inner(): number {\n"
        "      return 1;\n"
        "    }\n"
        "\n"
        "    return inner();\n"
        "  }\n"
        "}\n"
    )

    assert _report_for(tmp_path, source) == [f"{_MODULE}:3: inner"]


def test_allows_an_arrow_function_inside_a_function(tmp_path: Path) -> None:
    source = (
        "export function outer(): number {\n"
        "  const inner = (): number => 1;\n"
        "\n"
        "  return inner();\n"
        "}\n"
    )

    assert _report_for(tmp_path, source) == []


def test_allows_a_method_inside_a_class_inside_a_function(
    tmp_path: Path,
) -> None:
    source = (
        "export function outer(): number {\n"
        "  class Inner {\n"
        "    count(): number {\n"
        "      return 1;\n"
        "    }\n"
        "  }\n"
        "\n"
        "  return new Inner().count();\n"
        "}\n"
    )

    assert _report_for(tmp_path, source) == []


def test_allows_functions_declared_side_by_side(tmp_path: Path) -> None:
    source = (
        "function first(): number {\n"
        "  return 1;\n"
        "}\n"
        "\n"
        "export function second(): number {\n"
        "  return first();\n"
        "}\n"
    )

    assert _report_for(tmp_path, source) == []
