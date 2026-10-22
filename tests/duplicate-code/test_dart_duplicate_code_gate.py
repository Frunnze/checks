import tempfile
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import (
    HYPOTHESIS_SETTINGS,
    link_toolkit_node_modules,
    repository,
    run_configured,
    stage_file,
)

CONFIGURATION = 'source_directories = ["app/lib"]\n'
FIRST = "app/lib/first.dart"
SECOND = "app/lib/second.dart"
COPIED_FUNCTION = (
    "int total(List<int> values) {\n"
    "  var sum = 0;\n"
    "  for (final value in values) {\n"
    "    if (value > 100) {\n"
    "      sum += value * 2;\n"
    "    } else if (value > 10) {\n"
    "      sum += value + 3;\n"
    "    } else {\n"
    "      sum -= value;\n"
    "    }\n"
    "  }\n"
    "  final rounded = (sum * 100).round() ~/ 100;\n"
    "  return rounded > 0 ? rounded : 0;\n"
    "}\n"
)
identifiers = st.from_regex(r"[a-z][a-zA-Z]{2,12}", fullmatch=True)
folder_names = st.lists(
    st.from_regex(r"[a-z]{2,8}", fullmatch=True), min_size=1, max_size=3
)
directive_kinds = st.sampled_from(["import", "export", "part"])


def _directives(kind: str, count: int) -> str:
    lines: list[str] = []

    for index in range(count):
        lines.append(f"{kind} 'helpers/helper{index}.dart';")

    return "\n".join(lines) + "\n"


def _distinct_module(name: str) -> str:
    return (
        f"int {name}(int count) {{\n"
        f"  var {name}Total = 0;\n"
        f"  for (var step = 0; step < count; step += 1) {name}Total += step;\n"
        f"  return {name}Total;\n"
        "}\n"
    )


def _verdict(
    files: dict[str, str], configuration: str = CONFIGURATION
) -> tuple[int, str]:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        repository(root)
        link_toolkit_node_modules(root)

        for relative, source in files.items():
            stage_file(root, relative, source)

        finished = run_configured(root, configuration, "duplicate-code")

    return finished.returncode, finished.stdout + finished.stderr


def _copied_pair(name: str) -> dict[str, str]:
    return {
        FIRST: COPIED_FUNCTION + _distinct_module(f"{name}One"),
        SECOND: COPIED_FUNCTION + _distinct_module(f"{name}Two"),
    }


@HYPOTHESIS_SETTINGS
@given(identifiers, st.booleans())
def test_duplicate_code_property_fails_only_on_a_copied_dart_block(
    name: str, is_copied: bool
) -> None:
    second_body = COPIED_FUNCTION if is_copied else ""

    returncode, output = _verdict(
        {
            FIRST: COPIED_FUNCTION + _distinct_module(f"{name}One"),
            SECOND: second_body + _distinct_module(f"{name}Two"),
        }
    )

    assert returncode == int(is_copied), output


@HYPOTHESIS_SETTINGS
@given(st.integers(min_value=20, max_value=60), identifiers, directive_kinds)
def test_duplicate_code_property_ignores_shared_dart_directives(
    directive_count: int, name: str, kind: str
) -> None:
    shared_directives = _directives(kind, directive_count)

    returncode, output = _verdict(
        {
            FIRST: shared_directives + _distinct_module(f"{name}One"),
            SECOND: shared_directives + _distinct_module(f"{name}Two"),
        }
    )

    assert returncode == 0, output


@HYPOTHESIS_SETTINGS
@given(identifiers, folder_names)
def test_duplicate_code_property_finds_a_copy_in_nested_dart_folders(
    name: str, folders: list[str]
) -> None:
    nested_folder = "/".join(folders)
    copied_pair = _copied_pair(name)

    returncode, output = _verdict(
        {
            FIRST: copied_pair[FIRST],
            f"app/lib/{nested_folder}/second.dart": copied_pair[SECOND],
        }
    )

    assert returncode == 1, output


@HYPOTHESIS_SETTINGS
@given(identifiers)
def test_duplicate_code_property_never_flags_a_whitelisted_dart_copy(
    name: str,
) -> None:
    configuration = (
        CONFIGURATION
        + '[checks.duplicate-code]\nwhitelist = ["**/second.dart"]\n'
    )

    returncode, output = _verdict(_copied_pair(name), configuration)

    assert returncode == 0, output


@HYPOTHESIS_SETTINGS
@given(identifiers)
def test_duplicate_code_property_finds_a_copy_inside_one_dart_file(
    name: str,
) -> None:
    renamed_copy = COPIED_FUNCTION.replace("total(", f"{name}Total(")

    returncode, output = _verdict({FIRST: COPIED_FUNCTION + renamed_copy})

    assert returncode == 1, output
