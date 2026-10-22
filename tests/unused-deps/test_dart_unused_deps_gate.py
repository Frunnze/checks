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
LIBRARY = "app/lib/feature.dart"
TESTS = "app/tests/feature_test.dart"
UNRELATED_LIBRARY = "int one() => 1;\n"
LIBRARIES = {
    "path": (
        "import 'package:path/path.dart';\n\n"
        "String joined() => join('a', 'b');\n"
    ),
    "collection": (
        "import 'package:collection/collection.dart';\n\n"
        "int? first() => <int>[].firstOrNull;\n"
    ),
    "meta": (
        "import 'package:meta/meta.dart';\n\n"
        "@immutable\nclass Point {\n  const Point();\n}\n"
    ),
}
dependencies = st.sampled_from(sorted(LIBRARIES))
sections = st.sampled_from(["dependencies", "dev_dependencies"])


def _verdict(
    declarations: str, files: dict[str, str]
) -> tuple[int, str]:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        dart_package(root, DART_PUBSPEC + declarations)

        for relative, source in files.items():
            stage_file(root, relative, source)

        finished = run_configured(root, CONFIGURATION, "unused-deps")

    return finished.returncode, finished.stdout + finished.stderr


def _declared(section: str, dependency: str) -> str:
    return f"{section}:\n  {dependency}: any\n"


@HYPOTHESIS_SETTINGS
@given(dependencies, st.booleans())
def test_unused_deps_property_fails_only_on_a_declared_unimported_package(
    dependency: str, is_imported: bool
) -> None:
    library = LIBRARIES[dependency] if is_imported else UNRELATED_LIBRARY

    returncode, output = _verdict(
        _declared("dependencies", dependency), {LIBRARY: library}
    )

    assert returncode == int(not is_imported), output
    assert (f"* {dependency}" in output) == (not is_imported)


@HYPOTHESIS_SETTINGS
@given(dependencies, dependencies)
def test_unused_deps_property_fails_on_an_undeclared_import(
    declared: str, imported: str
) -> None:
    returncode, output = _verdict(
        _declared("dependencies", declared), {LIBRARY: LIBRARIES[imported]}
    )

    assert returncode == int(declared != imported), output


@HYPOTHESIS_SETTINGS
@given(dependencies, sections)
def test_unused_deps_property_wants_a_test_only_package_in_dev(
    dependency: str, section: str
) -> None:
    files = {
        LIBRARY: UNRELATED_LIBRARY,
        TESTS: LIBRARIES[dependency] + "void main() {}\n",
    }

    returncode, output = _verdict(_declared(section, dependency), files)

    assert returncode == int(section != "dev_dependencies"), output


@HYPOTHESIS_SETTINGS
@given(dependencies)
def test_unused_deps_property_fails_on_a_dev_package_used_in_lib(
    dependency: str,
) -> None:
    returncode, output = _verdict(
        _declared("dev_dependencies", dependency),
        {LIBRARY: LIBRARIES[dependency]},
    )

    assert returncode == 1, output
    assert f"* {dependency}" in output


@HYPOTHESIS_SETTINGS
@given(dependencies)
def test_unused_deps_property_honours_the_validator_ignore_list(
    dependency: str,
) -> None:
    files = {
        LIBRARY: UNRELATED_LIBRARY,
        "app/dart_dependency_validator.yaml": f"ignore:\n  - {dependency}\n",
    }

    returncode, output = _verdict(_declared("dependencies", dependency), files)

    assert returncode == 0, output
