import subprocess
import tempfile
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import (
    DART_CONFIGURATION,
    DART_PUBSPEC,
    HYPOTHESIS_SETTINGS,
    TOOLKIT,
    dart_package,
    run_configured,
    stage_file,
)

TESTED_PUBSPEC = DART_PUBSPEC + "dev_dependencies:\n  test: ^1.27.0\n"
SIGN_LIBRARY = (
    "String sign(int number) {\n"
    "  if (number < 0) {\n"
    "    return 'negative';\n"
    "  }\n"
    "  return 'positive';\n"
    "}\n"
)
POSITIVE_EXPECTATION = "    expect(sign(1), 'positive');\n"
NEGATIVE_EXPECTATION = "    expect(sign(-1), 'negative');\n"
HALF_TESTED_BRANCH_PERCENT = 50
COVERAGE_CHECK = TOOLKIT / "checks" / "stable" / "coverage" / "dart"
SHORTFALL_FINDER = COVERAGE_CHECK / "coverage_shortfalls.dart"
file_suffixes = st.from_regex(r"[a-z]{3,10}", fullmatch=True)
wrong_results = st.from_regex(r"wrong[a-z]{0,6}", fullmatch=True)


def _sign_test(expectations: str) -> str:
    return (
        "import 'package:app/sign.dart';\n"
        "import 'package:test/test.dart';\n\n"
        "void main() {\n"
        "  test('sign', () {\n"
        f"{expectations}"
        "  });\n"
        "}\n"
    )


def _verdict(
    files: dict[str, str], configuration: str = DART_CONFIGURATION
) -> tuple[int, str]:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        dart_package(root, TESTED_PUBSPEC)
        stage_file(root, "app/lib/sign.dart", SIGN_LIBRARY)

        for relative, source in files.items():
            stage_file(root, relative, source)

        finished = run_configured(root, configuration, "coverage")

    return finished.returncode, finished.stdout + finished.stderr


@HYPOTHESIS_SETTINGS
@given(st.booleans())
def test_coverage_property_fails_only_on_an_untested_dart_branch(
    is_negative_tested: bool,
) -> None:
    expectations = POSITIVE_EXPECTATION

    if is_negative_tested:
        expectations += NEGATIVE_EXPECTATION

    returncode, output = _verdict(
        {"app/tests/sign_test.dart": _sign_test(expectations)}
    )

    assert returncode == int(not is_negative_tested), output


@HYPOTHESIS_SETTINGS
@given(file_suffixes)
def test_coverage_property_fails_on_a_dart_file_no_test_loads(
    file_suffix: str,
) -> None:
    lonely_file = f"app/lib/lonely_{file_suffix}.dart"
    expectations = POSITIVE_EXPECTATION + NEGATIVE_EXPECTATION

    returncode, output = _verdict(
        {
            "app/tests/sign_test.dart": _sign_test(expectations),
            lonely_file: "int lonely() => 1;\n",
        }
    )

    assert returncode == 1, output
    assert lonely_file in output


@HYPOTHESIS_SETTINGS
@given(st.integers(min_value=0, max_value=100))
def test_coverage_property_obeys_the_configured_dart_minimum(
    minimum_percent: int,
) -> None:
    configuration = (
        DART_CONFIGURATION
        + f"[checks.coverage]\nfail-under = {minimum_percent}\n"
    )

    returncode, output = _verdict(
        {"app/tests/sign_test.dart": _sign_test(POSITIVE_EXPECTATION)},
        configuration,
    )

    is_below_minimum = HALF_TESTED_BRANCH_PERCENT < minimum_percent
    assert returncode == int(is_below_minimum), output


@HYPOTHESIS_SETTINGS
@given(wrong_results)
def test_coverage_property_fails_on_a_failing_dart_test(
    wrong_result: str,
) -> None:
    expectation = f"    expect(sign(1), '{wrong_result}');\n"

    returncode, output = _verdict(
        {"app/tests/sign_test.dart": _sign_test(expectation)}
    )

    assert returncode == 1, output
    assert "the tests of app fail" in output


@HYPOTHESIS_SETTINGS
@given(file_suffixes, st.sampled_from(["bin", "tool"]))
def test_coverage_property_measures_only_the_listed_dart_folder(
    file_suffix: str, unlisted_folder: str
) -> None:
    expectations = POSITIVE_EXPECTATION + NEGATIVE_EXPECTATION

    returncode, output = _verdict(
        {
            "app/tests/sign_test.dart": _sign_test(expectations),
            f"app/{unlisted_folder}/{file_suffix}.dart": "int x() => 1;\n",
        }
    )

    assert returncode == 0, output



def _relative_lcov_shortfalls(line_hits: list[int]) -> list[str]:
    with tempfile.TemporaryDirectory() as directory:
        package = Path(directory) / "app"
        source = package / "lib" / "sign.dart"
        source.parent.mkdir(parents=True)
        _ = source.write_text(SIGN_LIBRARY, encoding="utf-8")
        line_records = "".join(
            f"DA:{line_number},{hits}\n"
            for line_number, hits in enumerate(line_hits, start=1)
        )
        lcov_report = package / "lcov.info"
        _ = lcov_report.write_text(
            f"SF:lib/sign.dart\n{line_records}end_of_record\n",
            encoding="utf-8",
        )
        finished = subprocess.run(
            [
                "dart",
                str(SHORTFALL_FINDER),
                str(lcov_report),
                "100",
                str(package),
            ],
            input=f"{source}\n",
            capture_output=True,
            text=True,
            check=True,
        )

    return finished.stdout.splitlines()


@HYPOTHESIS_SETTINGS
@given(st.lists(st.integers(min_value=0, max_value=3), min_size=1, max_size=6))
def test_shortfalls_property_read_package_relative_lcov_paths(
    line_hits: list[int],
) -> None:
    shortfalls = _relative_lcov_shortfalls(line_hits)

    unrun_lines = [
        line_number
        for line_number, hits in enumerate(line_hits, start=1)
        if hits == 0
    ]
    reported_lines = [
        int(shortfall.split(":")[1])
        for shortfall in shortfalls
        if shortfall.endswith("no test runs this line")
    ]
    assert reported_lines == unrun_lines
    assert (shortfalls == []) == (unrun_lines == [])
