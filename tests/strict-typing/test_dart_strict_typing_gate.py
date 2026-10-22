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
SOURCE = "app/lib/reader.dart"
STRICT_PUBSPEC = (
    DART_PUBSPEC + "dev_dependencies:\n  very_good_analysis: ^11.0.0\n"
)
STRICT_OPTIONS = (
    "include: package:very_good_analysis/analysis_options.yaml\n"
    "linter:\n  rules:\n    public_member_api_docs: false\n"
)
STRICT_MODES = ("strict-casts", "strict-inference", "strict-raw-types")
CLEAN_LIBRARY = "int twice(int number) => number * 2;\n"
GENERIC_TYPES = {"List": "<int>", "Map": "<int, int>", "Set": "<int>"}
name_suffixes = st.from_regex(r"[A-Z][a-zA-Z]{2,10}", fullmatch=True)
silencers = st.sampled_from(
    [
        "// ignore: avoid_print",
        "//ignore: avoid_print",
        "// ignore_for_file: avoid_print",
        "//  ignore_for_file:avoid_print",
    ]
)


def _verdict(analysis_options: str, library: str) -> tuple[int, str]:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        dart_package(root, STRICT_PUBSPEC)
        stage_file(root, "app/analysis_options.yaml", analysis_options)
        stage_file(root, SOURCE, library)

        finished = run_configured(root, CONFIGURATION, "strict-typing")

    return finished.returncode, finished.stdout + finished.stderr


@HYPOTHESIS_SETTINGS
@given(name_suffixes, st.booleans())
def test_strict_typing_property_fails_only_on_an_implicit_dynamic_cast(
    name_suffix: str, is_cast_explicitly: bool
) -> None:
    cast = " as int" if is_cast_explicitly else ""
    library = f"int read{name_suffix}(dynamic value) => value{cast};\n"

    returncode, output = _verdict(STRICT_OPTIONS, library)

    assert returncode == int(not is_cast_explicitly), output


@HYPOTHESIS_SETTINGS
@given(silencers)
def test_strict_typing_property_fails_on_every_silencer_spelling(
    silencer: str,
) -> None:
    returncode, output = _verdict(
        STRICT_OPTIONS, f"{silencer}\n{CLEAN_LIBRARY}"
    )

    assert returncode == 1, output
    assert f"{SOURCE}:1:" in output


@HYPOTHESIS_SETTINGS
@given(st.sampled_from(STRICT_MODES))
def test_strict_typing_property_fails_when_a_strict_mode_is_off(
    strict_mode: str,
) -> None:
    analysis_options = (
        STRICT_OPTIONS + f"analyzer:\n  language:\n    {strict_mode}: false\n"
    )

    returncode, output = _verdict(analysis_options, CLEAN_LIBRARY)

    assert returncode == 1, output
    assert strict_mode in output


@HYPOTHESIS_SETTINGS
@given(name_suffixes)
def test_strict_typing_property_fails_without_the_strict_dart_rule_set(
    name_suffix: str,
) -> None:
    library = f"int twice{name_suffix}(int number) => number * 2;\n"

    returncode, output = _verdict("", library)

    assert returncode == 1, output
    assert "package:very_good_analysis/analysis_options.yaml" in output


@HYPOTHESIS_SETTINGS
@given(name_suffixes, st.booleans(), st.sampled_from(sorted(GENERIC_TYPES)))
def test_strict_typing_property_fails_only_on_a_raw_dart_generic(
    name_suffix: str, is_parameterised: bool, collection: str
) -> None:
    full_type = collection + GENERIC_TYPES[collection]
    return_type = full_type if is_parameterised else collection
    signature = f"{return_type} same{name_suffix}({full_type} values)"
    library = f"{signature} => values;\n"

    returncode, output = _verdict(STRICT_OPTIONS, library)

    assert returncode == int(not is_parameterised), output
