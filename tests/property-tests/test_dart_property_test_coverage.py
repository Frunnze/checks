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

FINDER = TOOLKIT / ".pub-cache" / "bin" / "property_test_coverage"
SOURCE_DIRECTORY = "app/lib"
TESTS_DIRECTORY = "app/tests"
SOURCE = "app/lib/scheduler.dart"
TESTS = "app/tests/scheduler_test.dart"
KIRI_IMPORT = "import 'package:kiri_check/kiri_check.dart';\n"
GATE_CONFIGURATION = (
    DART_CONFIGURATION + '[checks.property-tests]\nwhen = "pre-commit"\n'
)
EXEMPT_DEFINITIONS = (
    "abstract class Shape {\n  int area();\n}\n",
    "external int nativeClock();\n",
    "void nothing() {}\n",
    "class Money {\n  bool operator ==(Object other) => true;\n}\n",
    "class Money {\n  @override\n  String toString() => 'money';\n}\n",
    "class Money {\n  @override\n  int get hashCode => 1;\n}\n",
    "class Card {\n  Widget build(BuildContext context) => Text('a');\n}\n",
)
MEMBERS = (
    "  int get {name} => _value;\n",
    "  set {name}(int value) => _value = value;\n",
    "  int {name}(int value) => value + _value;\n",
)
names = st.from_regex(r"compute[A-Z0-9][a-zA-Z0-9]{0,8}", fullmatch=True)
prefixes = st.from_regex(r"[a-z]{2,8}Checks", fullmatch=True)
name_sets = st.sets(names, min_size=1, max_size=5)


def _report(root: Path, files: dict[str, str]) -> list[str]:
    for relative, source in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(source, encoding="utf-8")

    finished = subprocess.run(
        [str(FINDER), SOURCE_DIRECTORY, TESTS_DIRECTORY],
        input="\n".join(files),
        capture_output=True,
        text=True,
        check=True,
        cwd=root,
    )

    return finished.stdout.splitlines()


def _report_in_new_folder(files: dict[str, str]) -> list[str]:
    with tempfile.TemporaryDirectory() as directory:
        return _report(Path(directory), files)


def _property(title: str, prefix: str = "") -> str:
    return (
        f"  {prefix}property('{title}', () {{\n"
        f"    {prefix}forAll({prefix}integer(), (number) {{}});\n"
        "  });\n"
    )


def _properties(name: str, prefix: str = "", count: int = 4) -> str:
    properties = ""

    for index in range(count):
        properties += _property(f"{name} property holds {index}", prefix)

    return properties


def _tests(properties: str, imports: str = KIRI_IMPORT) -> str:
    return f"{imports}\nvoid main() {{\n{properties}}}\n"


def _missing(name: str, line_number: int) -> str:
    return (
        f"{SOURCE}:{line_number}: {name} needs 4 property tests titled "
        f'"{name} property ..."'
    )


@HYPOTHESIS_SETTINGS
@given(name_sets, st.data())
def test_finder_property_reports_exactly_the_untested_functions(
    defined: set[str], data: st.DataObject
) -> None:
    ordered = sorted(defined)
    tested = data.draw(st.sets(st.sampled_from(ordered)))
    source_lines: list[str] = []
    properties = ""

    for name in ordered:
        source_lines.append(f"int {name}(int value) => value;")

    for name in sorted(tested):
        properties += _properties(name)

    report = _report_in_new_folder(
        {SOURCE: "\n".join(source_lines) + "\n", TESTS: _tests(properties)}
    )

    expected: list[str] = []

    for line_index, name in enumerate(ordered):
        if name not in tested:
            expected.append(_missing(name, line_index + 1))

    assert report == expected


@HYPOTHESIS_SETTINGS
@given(names, st.sampled_from(MEMBERS))
def test_finder_property_covers_class_members_by_their_name(
    name: str, member_template: str
) -> None:
    member = member_template.format(name=name)
    source = f"class Clock {{\n  int _value = 0;\n{member}}}\n"

    untested = _report_in_new_folder({SOURCE: source, TESTS: _tests("")})
    tested = _report_in_new_folder(
        {SOURCE: source, TESTS: _tests(_properties(name))}
    )

    assert untested == [_missing(name, 3)]
    assert tested == []


@HYPOTHESIS_SETTINGS
@given(st.sampled_from(EXEMPT_DEFINITIONS))
def test_finder_property_exempts_what_describes_no_behaviour(
    definition: str,
) -> None:
    report = _report_in_new_folder({SOURCE: definition, TESTS: _tests("")})

    assert report == []


@HYPOTHESIS_SETTINGS
@given(names, prefixes, st.booleans())
def test_finder_property_counts_only_kiri_check_property_calls(
    name: str, prefix: str, is_kiri_prefix: bool
) -> None:
    kiri_prefix = prefix if is_kiri_prefix else f"{prefix}other"
    imports = (
        f"import 'package:kiri_check/kiri_check.dart' as {kiri_prefix};\n"
        f"import 'package:test/test.dart' as {prefix};\n"
    )
    properties = _properties(name, f"{prefix}.")
    source = f"int {name}(int value) => value;\n"

    report = _report_in_new_folder(
        {SOURCE: source, TESTS: _tests(properties, imports)}
    )

    assert (report == []) == is_kiri_prefix


@HYPOTHESIS_SETTINGS
@given(names, st.booleans())
def test_property_tests_property_fails_only_on_an_untested_dart_function(
    name: str, is_tested: bool
) -> None:
    properties = _properties(name) if is_tested else _properties("other")

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        dart_package(root, DART_PUBSPEC)
        stage_file(root, SOURCE, f"int {name}(int value) => value;\n")
        stage_file(root, TESTS, _tests(properties))

        finished = run_configured(root, GATE_CONFIGURATION, "property-tests")

    assert finished.returncode == int(not is_tested), finished.stderr
    assert (_missing(name, 1) in finished.stderr) == (not is_tested)


@HYPOTHESIS_SETTINGS
@given(names, st.from_regex(r"[A-Z0-9][a-zA-Z0-9]{0,4}", fullmatch=True))
def test_finder_property_never_covers_a_name_by_its_prefix(
    name: str, extension: str
) -> None:
    longer_name = f"{name}{extension}"
    source = (
        f"int {name}(int value) => value;\n"
        f"int {longer_name}(int value) => value;\n"
    )
    properties = _properties(longer_name)

    report = _report_in_new_folder({SOURCE: source, TESTS: _tests(properties)})

    assert report == [_missing(name, 1)]


@HYPOTHESIS_SETTINGS
@given(
    names,
    st.integers(min_value=0, max_value=6),
    st.integers(min_value=1, max_value=3),
)
def test_finder_property_needs_four_distinct_property_titles(
    name: str, distinct_count: int, repeats: int
) -> None:
    properties = _properties(name, count=distinct_count) * repeats
    source = f"int {name}(int value) => value;\n"

    report = _report_in_new_folder({SOURCE: source, TESTS: _tests(properties)})

    is_covered = distinct_count >= 4
    assert (report == []) == is_covered


@HYPOTHESIS_SETTINGS
@given(names, st.booleans())
def test_finder_property_skips_only_overrides_of_library_members(
    name: str, is_own_member: bool
) -> None:
    own_interface = (
        f"abstract class Ticker {{\n  int {name}(int value);\n}}\n"
        if is_own_member
        else ""
    )
    source = (
        own_interface
        + "class Clock extends Base {\n"
        + "  @override\n"
        + f"  int {name}(int value) => value + 1;\n"
        + "}\n"
    )
    override_line = 6 if is_own_member else 3

    report = _report_in_new_folder({SOURCE: source, TESTS: _tests("")})

    expected = [_missing(name, override_line)] if is_own_member else []
    assert report == expected


@HYPOTHESIS_SETTINGS
@given(names, st.sampled_from(("test", "tests")))
def test_property_tests_property_reads_the_dart_test_folder_in_use(
    name: str, tests_folder: str
) -> None:
    tests_file = f"app/{tests_folder}/scheduler_test.dart"
    configuration = (
        f'source_directories = ["app/lib", "app/{tests_folder}"]\n'
        '[checks.property-tests]\nwhen = "pre-commit"\n'
    )

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        dart_package(root, DART_PUBSPEC)
        stage_file(root, SOURCE, f"int {name}(int value) => value;\n")
        stage_file(root, tests_file, _tests(_properties(name)))

        finished = run_configured(root, configuration, "property-tests")

    assert finished.returncode == 0, finished.stderr
