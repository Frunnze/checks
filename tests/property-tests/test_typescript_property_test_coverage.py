import tempfile
from pathlib import Path

from hypothesis import example, given, settings
from hypothesis import strategies as st

from typescript_finder_support import CHECKS, report_from

_FINDER = (
    CHECKS
    / "experimental"
    / "property-tests"
    / "typescript"
    / "property_test_coverage.js"
)
_SOURCE = "src/units.ts"
_TESTS = "tests/units.test.ts"
_SETTINGS = settings(max_examples=8, deadline=None)
_FAST_CHECK_STYLES = ["default", "namespace", "named"]
_ELEMENT_TYPES = ["JSX.Element", "React.JSX.Element"]
_MINIMUM_PROPERTY_TESTS = 4

function_names = st.from_regex(r"unit[a-z]{0,6}", fullmatch=True)
function_name_lists = st.lists(
    function_names, min_size=1, max_size=4, unique=True
)
file_names_with_whitespace = st.text(
    alphabet="abcXYZ019_. \t", min_size=1, max_size=8
)


def _report_for(root: Path, files: dict[str, str]) -> list[str]:
    return report_from(_FINDER, root, files)


def _missing(source: str, name: str, line_number: int) -> str:
    return (
        f"{source}:{line_number}: {name} needs 4 property tests titled "
        f'"{name} property ..."'
    )


def _source_module(names: list[str]) -> str:
    functions: list[str] = []

    for name in names:
        functions.append(
            f"export function {name}(value: number): number {{\n"
            "  return value * 2;\n"
            "}\n"
        )

    return "".join(functions)


def _fast_check_tests(name: str, alias: str, style: str) -> str:
    if style == "named":
        assertion = f"assert(property(integer(), (n) => {name}(n) === n * 2))"
    else:
        assertion = (
            f"{alias}.assert({alias}.property({alias}.integer(), "
            f"(n) => {name}(n) === n * 2))"
        )

    return _repeated_tests(name, f"() => {{\n  {assertion};\n}}")


def _repeated_tests(name: str, body: str) -> str:
    tests: list[str] = []

    for number in range(_MINIMUM_PROPERTY_TESTS):
        tests.append(f'test("{name} property doubles {number}", {body});\n')

    return "".join(tests)


def _fast_check_module(names: list[str], alias: str, style: str) -> str:
    if style == "named":
        header = 'import { assert, property, integer } from "fast-check";\n'
    elif style == "namespace":
        header = f'import * as {alias} from "fast-check";\n'
    else:
        header = f'import {alias} from "fast-check";\n'

    tests: list[str] = []

    for name in names:
        tests.append(_fast_check_tests(name, alias, style))

    return header + "".join(tests)


def _component_module(name: str, element_type: str) -> str:
    return (
        'import React from "react";\n'
        f"export function {name}(props: {{ label: string }}): "
        f"{element_type} {{\n"
        "  return <p>{props.label}</p>;\n"
        "}\n"
    )


@given(name=file_names_with_whitespace)
@example(name="my score")
@_SETTINGS
def test_finder_property_reads_a_path_with_whitespace(name: str) -> None:
    source = f"src/d/{name}.ts"

    with tempfile.TemporaryDirectory() as directory:
        report = _report_for(
            Path(directory), {source: _source_module(["score"])}
        )

    assert report == [_missing(source, "score", 1)]


@given(
    names=function_name_lists,
    ancestor=st.sampled_from(["tests", "src", "ui"]),
)
@example(names=["score"], ancestor="tests")
@_SETTINGS
def test_finder_property_ignores_where_the_project_is_checked_out(
    names: list[str], ancestor: str
) -> None:
    files = {
        _SOURCE: _source_module(names),
        _TESTS: _fast_check_module(names[:-1], "fc", "default"),
    }

    with tempfile.TemporaryDirectory() as directory:
        plain = _report_for(Path(directory) / "plain" / "repo", files)
        moved = _report_for(Path(directory) / ancestor / "repo", files)

    assert len(plain) == 1
    assert moved == plain


@given(
    names=function_name_lists,
    runner=st.sampled_from(["test", "it"]),
)
@example(names=["score"], runner="test")
@_SETTINGS
def test_finder_property_counts_the_test_prop_form_it_asks_for(
    names: list[str], runner: str
) -> None:
    tests = [f'import {{ fc, {runner} }} from "@fast-check/vitest";\n']

    for name in names:
        for number in range(_MINIMUM_PROPERTY_TESTS):
            tests.append(
                f'{runner}.prop([fc.integer()])("{name} property doubles '
                f'{number}", (value) => {name}(value) === value * 2);\n'
            )

    files = {_SOURCE: _source_module(names), _TESTS: "".join(tests)}

    with tempfile.TemporaryDirectory() as directory:
        report = _report_for(Path(directory), files)

    assert report == []


@given(
    names=function_name_lists,
    alias=function_names,
    style=st.sampled_from(_FAST_CHECK_STYLES),
)
@example(names=["score"], alias="fastCheck", style="namespace")
@_SETTINGS
def test_finder_property_follows_the_local_name_of_fast_check(
    names: list[str], alias: str, style: str
) -> None:
    source = _source_module(names)
    canonical_tests = _fast_check_module(names, "fc", "default")
    renamed_tests = _fast_check_module(names, alias, style)

    with tempfile.TemporaryDirectory() as directory:
        canonical = _report_for(
            Path(directory) / "canonical",
            {_SOURCE: source, _TESTS: canonical_tests},
        )
        renamed = _report_for(
            Path(directory) / "renamed",
            {_SOURCE: source, _TESTS: renamed_tests},
        )

    assert canonical == []
    assert renamed == canonical


def test_counts_an_assertion_with_a_space_before_its_arguments(
    tmp_path: Path,
) -> None:
    tests = 'import fc from "fast-check";\n' + _repeated_tests(
        "score",
        "() => {\n"
        "  fc.assert (fc.property(fc.integer(), (n) => score(n) === n * 2));\n"
        "}",
    )
    files = {_SOURCE: _source_module(["score"]), _TESTS: tests}

    assert _report_for(tmp_path, files) == []


def test_rejects_an_assert_that_is_not_from_fast_check(
    tmp_path: Path,
) -> None:
    tests = 'import assert from "node:assert";\n' + _repeated_tests(
        "score", "() => {\n  assert(score(1) === 2);\n}"
    )
    files = {_SOURCE: _source_module(["score"]), _TESTS: tests}

    assert _report_for(tmp_path, files) == [_missing(_SOURCE, "score", 1)]


@given(
    name=function_names,
    spelling=st.sampled_from(["arrow_property", "function_property"]),
)
@example(name="scale", spelling="arrow_property")
@_SETTINGS
def test_finder_property_treats_a_function_valued_field_like_a_method(
    name: str, spelling: str
) -> None:
    method = (
        "export class Box {\n"
        f"  {name}(value: number): number {{\n"
        "    return value * 2;\n"
        "  }\n"
        "}\n"
    )

    if spelling == "arrow_property":
        field = (
            "export class Box {\n"
            f"  {name} = (value: number): number => value * 2;\n"
            "}\n"
        )
    else:
        field = (
            "export class Box {\n"
            f"  {name} = function (value: number): number {{\n"
            "    return value * 2;\n"
            "  };\n"
            "}\n"
        )

    with tempfile.TemporaryDirectory() as directory:
        as_method = _report_for(
            Path(directory) / "method", {"src/box.ts": method}
        )
        as_field = _report_for(
            Path(directory) / "field", {"src/box.ts": field}
        )

    assert as_method == [_missing("src/box.ts", name, 2)]
    assert as_field == as_method


@given(
    name=function_names,
    element_type=st.sampled_from(_ELEMENT_TYPES),
)
@example(name="unit", element_type="React.JSX.Element")
@_SETTINGS
def test_finder_property_exempts_a_component_whatever_its_element_spelling(
    name: str, element_type: str
) -> None:
    component = name.title()

    with tempfile.TemporaryDirectory() as directory:
        canonical = _report_for(
            Path(directory) / "canonical",
            {"src/view.tsx": _component_module(component, "JSX.Element")},
        )
        other = _report_for(
            Path(directory) / "other",
            {"src/view.tsx": _component_module(component, element_type)},
        )

    assert canonical == []
    assert other == canonical


_DOUBLING_ASSERTION = (
    "() => {\n"
    "  fc.assert(fc.property(fc.integer(), (n) => score(n) === n * 2));\n"
    "}"
)


@given(test_count=st.integers(min_value=0, max_value=8))
@example(test_count=3)
@_SETTINGS
def test_finder_property_flags_exactly_the_functions_under_four_tests(
    test_count: int,
) -> None:
    tests = ['import fc from "fast-check";\n']

    for number in range(test_count):
        tests.append(
            f'test("score property doubles {number}", '
            f"{_DOUBLING_ASSERTION});\n"
        )

    files = {_SOURCE: _source_module(["score"]), _TESTS: "".join(tests)}

    with tempfile.TemporaryDirectory() as directory:
        report = _report_for(Path(directory), files)

    if test_count < _MINIMUM_PROPERTY_TESTS:
        assert report == [_missing(_SOURCE, "score", 1)]
    else:
        assert report == []


def test_one_title_in_four_test_files_counts_once(tmp_path: Path) -> None:
    repeated = (
        'import fc from "fast-check";\n'
        f'test("score property doubles", {_DOUBLING_ASSERTION});\n'
    )
    files = {
        _SOURCE: _source_module(["score"]),
        "tests/a.test.ts": repeated,
        "tests/b.test.ts": repeated,
        "tests/c.test.ts": repeated,
        "tests/d.test.ts": repeated,
    }

    assert _report_for(tmp_path, files) == [_missing(_SOURCE, "score", 1)]
