import tempfile
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import (
    DART_PUBSPEC,
    HYPOTHESIS_SETTINGS,
    dart_package,
    run_configured,
    stage_file,
)

CONFIGURATION = 'source_directories = ["app/lib"]\n'
STRICT_PUBSPEC = (
    DART_PUBSPEC + "dev_dependencies:\n  very_good_analysis: ^11.0.0\n"
)
STRICT_OPTIONS = (
    "include: package:very_good_analysis/analysis_options.yaml\n"
    "linter:\n  rules:\n    public_member_api_docs: false\n"
)
LOOSE_OPTIONS = "linter:\n  rules:\n    public_member_api_docs: false\n"
name_suffixes = st.from_regex(r"[A-Z][a-zA-Z]{2,10}", fullmatch=True)


def _verdict(analysis_options: str, library: str) -> tuple[int, str]:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        dart_package(root, STRICT_PUBSPEC)
        stage_file(root, "app/analysis_options.yaml", analysis_options)
        stage_file(root, "app/lib/greeting.dart", library)

        finished = run_configured(root, CONFIGURATION, "linters")

    return finished.returncode, finished.stdout + finished.stderr


@HYPOTHESIS_SETTINGS
@given(name_suffixes, st.booleans())
def test_linters_property_fails_only_on_a_dart_lint_violation(
    name_suffix: str, is_printing: bool
) -> None:
    name = f"greeting{name_suffix}"
    body = f"print('{name}');" if is_printing else f"return '{name}';"
    return_type = "void" if is_printing else "String"
    library = f"{return_type} {name}() {{\n  {body}\n}}\n"

    returncode, output = _verdict(STRICT_OPTIONS, library)

    assert returncode == int(is_printing), output
    assert ("avoid_print" in output) == is_printing


@HYPOTHESIS_SETTINGS
@given(name_suffixes)
def test_linters_property_fails_without_the_strict_dart_rule_set(
    name_suffix: str,
) -> None:
    library = f"String greeting{name_suffix}() => 'hello';\n"

    returncode, output = _verdict(LOOSE_OPTIONS, library)

    assert returncode == 1, output
    assert "package:very_good_analysis/analysis_options.yaml" in output


@HYPOTHESIS_SETTINGS
@given(name_suffixes)
def test_linters_property_ignores_a_commented_out_dart_rule_set(
    name_suffix: str,
) -> None:
    commented_options = "# " + STRICT_OPTIONS
    library = f"String greeting{name_suffix}() => 'hello';\n"

    returncode, output = _verdict(commented_options, library)

    assert returncode == 1, output
    assert "package:very_good_analysis/analysis_options.yaml" in output


@HYPOTHESIS_SETTINGS
@given(name_suffixes, st.sampled_from(["10.0.0", "10.1.0", "10.3.0"]))
def test_linters_property_accepts_a_pinned_dart_rule_set_version(
    name_suffix: str, rule_set_version: str
) -> None:
    pinned_options = STRICT_OPTIONS.replace(
        "analysis_options.yaml", f"analysis_options.{rule_set_version}.yaml"
    )
    library = f"String greeting{name_suffix}() => 'hello';\n"

    returncode, output = _verdict(pinned_options, library)

    assert returncode == 0, output


@HYPOTHESIS_SETTINGS
@given(name_suffixes, st.sampled_from(["bin", "tool", "example"]))
def test_linters_property_lints_only_the_listed_dart_folder(
    name_suffix: str, unlisted_folder: str
) -> None:
    printing = f"void greeting{name_suffix}() {{\n  print('hi');\n}}\n"

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        dart_package(root, STRICT_PUBSPEC)
        stage_file(root, "app/analysis_options.yaml", STRICT_OPTIONS)
        stage_file(root, "app/lib/greeting.dart", "const greeting = 1;\n")
        stage_file(root, f"app/{unlisted_folder}/noisy.dart", printing)

        finished = run_configured(root, CONFIGURATION, "linters")

    assert finished.returncode == 0, finished.stdout + finished.stderr


@HYPOTHESIS_SETTINGS
@given(name_suffixes)
def test_linters_property_fails_fast_on_an_unresolved_dart_package(
    name_suffix: str,
) -> None:
    library = f"String greeting{name_suffix}() => 'hello';\n"

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        dart_package(root, STRICT_PUBSPEC)
        stage_file(root, "app/analysis_options.yaml", STRICT_OPTIONS)
        stage_file(root, "app/lib/greeting.dart", library)
        package_config = root / "app" / ".dart_tool" / "package_config.json"
        package_config.unlink()

        finished = run_configured(root, CONFIGURATION, "linters")

    assert finished.returncode == 1
    assert "run dart pub get" in finished.stderr
