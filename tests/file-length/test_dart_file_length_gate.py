import tempfile
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import (
    HYPOTHESIS_SETTINGS,
    repository,
    run_configured,
    stage_file,
)

MAXIMUM_LINES = 300
SOURCE = "app/lib/values.dart"
GENERATED = "app/lib/.dart_tool/build/generated.dart"
CONFIGURATION = 'source_directories = ["app/lib"]\n'
overlong_counts = st.integers(min_value=MAXIMUM_LINES + 1, max_value=400)


def _numbered_constants(count: int) -> str:
    lines: list[str] = []

    for number in range(count):
        lines.append(f"const value{number} = {number};")

    return "\n".join(lines) + "\n"


def _verdict(
    line_count: int,
    configuration: str = CONFIGURATION,
    unstaged: dict[str, str] | None = None,
) -> tuple[int, str]:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        repository(root)
        stage_file(root, SOURCE, _numbered_constants(line_count))

        for relative, source in (unstaged or {}).items():
            unstaged_path = root / relative
            unstaged_path.parent.mkdir(parents=True)
            _ = unstaged_path.write_text(source, encoding="utf-8")

        finished = run_configured(root, configuration, "file-length")

    return finished.returncode, finished.stderr


@HYPOTHESIS_SETTINGS
@given(st.integers(min_value=1, max_value=400))
def test_file_length_property_flags_a_dart_file_only_past_the_limit(
    line_count: int,
) -> None:
    returncode, output = _verdict(line_count)

    is_overlong = line_count > MAXIMUM_LINES
    assert returncode == int(is_overlong), output
    assert (SOURCE in output) == is_overlong


@HYPOTHESIS_SETTINGS
@given(
    st.integers(min_value=1, max_value=60),
    st.integers(min_value=1, max_value=60),
)
def test_file_length_property_obeys_the_configured_dart_limit(
    maximum_lines: int, line_count: int
) -> None:
    configuration = (
        CONFIGURATION + f"[checks.file-length]\nmax-lines = {maximum_lines}\n"
    )

    returncode, output = _verdict(line_count, configuration)

    assert returncode == int(line_count > maximum_lines), output


@HYPOTHESIS_SETTINGS
@given(overlong_counts)
def test_file_length_property_reports_the_exact_dart_line_count(
    line_count: int,
) -> None:
    returncode, output = _verdict(line_count)

    assert returncode == 1
    assert f"{SOURCE} ({line_count} lines)" in output


@HYPOTHESIS_SETTINGS
@given(overlong_counts)
def test_file_length_property_never_flags_a_whitelisted_dart_file(
    line_count: int,
) -> None:
    configuration = (
        CONFIGURATION + f'[checks.file-length]\nwhitelist = ["{SOURCE}"]\n'
    )

    returncode, output = _verdict(line_count, configuration)

    assert returncode == 0, output


@HYPOTHESIS_SETTINGS
@given(overlong_counts)
def test_file_length_property_skips_ignored_dart_tool_output(
    line_count: int,
) -> None:
    generated = {GENERATED: _numbered_constants(line_count)}

    returncode, output = _verdict(1, unstaged=generated)

    assert returncode == 0, output
