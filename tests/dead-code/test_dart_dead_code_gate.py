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
ENTRY_POINT = "app/lib/main.dart"
name_suffixes = st.from_regex(r"[A-Z][a-zA-Z]{2,10}", fullmatch=True)


def _verdict(entry_point: str, library: str) -> tuple[int, str]:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        dart_package(root, DART_PUBSPEC)
        stage_file(root, ENTRY_POINT, entry_point)
        stage_file(root, "app/lib/greeter.dart", library)

        finished = run_configured(root, CONFIGURATION, "dead-code")

    return finished.returncode, finished.stdout + finished.stderr


@HYPOTHESIS_SETTINGS
@given(name_suffixes, st.booleans())
def test_dead_code_property_fails_only_on_a_dart_function_nobody_calls(
    name_suffix: str, is_called: bool
) -> None:
    name = f"forgotten{name_suffix}"
    call = f"  print({name}());\n" if is_called else ""
    entry_point = (
        f"import 'greeter.dart';\n\nvoid main() {{\n{call}  print(1);\n}}\n"
    )

    returncode, output = _verdict(entry_point, f"int {name}() => 1;\n")

    assert returncode == int(not is_called), output
    assert (name in output) == (not is_called)


@HYPOTHESIS_SETTINGS
@given(name_suffixes, st.booleans())
def test_dead_code_property_fails_only_on_a_dart_method_nobody_calls(
    name_suffix: str, is_called: bool
) -> None:
    name = f"forgotten{name_suffix}"
    call = f"  print(const Greeter().{name}());\n" if is_called else ""
    entry_point = (
        "import 'greeter.dart';\n\nvoid main() {\n"
        f"  print(const Greeter());\n{call}}}\n"
    )
    library = (
        "class Greeter {\n  const Greeter();\n\n"
        f"  int {name}() => 1;\n}}\n"
    )

    returncode, output = _verdict(entry_point, library)

    assert returncode == int(not is_called), output
    assert (name in output) == (not is_called)


@HYPOTHESIS_SETTINGS
@given(name_suffixes, st.booleans())
def test_dead_code_property_fails_only_on_a_private_dart_function_unused(
    name_suffix: str, is_called: bool
) -> None:
    name = f"_forgotten{name_suffix}"
    greeting_body = f"{name}()" if is_called else "2"
    library = f"int greeting() => {greeting_body};\nint {name}() => 1;\n"
    entry_point = (
        "import 'greeter.dart';\n\nvoid main() {\n"
        "  print(greeting());\n}\n"
    )

    returncode, output = _verdict(entry_point, library)

    assert returncode == int(not is_called), output
    assert (name in output) == (not is_called)


@HYPOTHESIS_SETTINGS
@given(name_suffixes, st.booleans())
def test_dead_code_property_fails_only_on_a_dart_class_nobody_uses(
    name_suffix: str, is_used: bool
) -> None:
    class_name = f"Forgotten{name_suffix}"
    use = f"  print(const {class_name}());\n" if is_used else ""
    entry_point = (
        f"import 'greeter.dart';\n\nvoid main() {{\n{use}  print(1);\n}}\n"
    )
    library = f"class {class_name} {{\n  const {class_name}();\n}}\n"

    returncode, output = _verdict(entry_point, library)

    assert returncode == int(not is_used), output
    assert (class_name in output) == (not is_used)


@HYPOTHESIS_SETTINGS
@given(name_suffixes, st.integers(min_value=1, max_value=5))
def test_dead_code_property_keeps_dart_code_reached_through_a_chain(
    name_suffix: str, chain_length: int
) -> None:
    library_lines: list[str] = []

    for link in range(chain_length):
        is_last = link + 1 == chain_length
        next_call = "1" if is_last else f"link{name_suffix}{link + 1}()"
        library_lines.append(f"int link{name_suffix}{link}() => {next_call};")

    entry_point = (
        "import 'greeter.dart';\n\nvoid main() {\n"
        f"  print(link{name_suffix}0());\n}}\n"
    )
    library = "\n".join(library_lines) + "\n"

    returncode, output = _verdict(entry_point, library)

    assert returncode == 0, output
