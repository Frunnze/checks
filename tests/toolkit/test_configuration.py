import json
import tempfile
import tomllib
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from configuration_support import (
    TOOLKIT,
    read_setting,
    toml_list,
    written_configuration,
)
from settings import (
    DEFAULT_SETTINGS,
    check_settings,
    read_configuration,
    setting_lines,
    with_defaults,
)
from settings_validation import CHECK_ORDER, validate_configuration

CHECKS = TOOLKIT / "checks"
MINIMAL = 'source_directories = ["src"]\n'

directory_names = st.from_regex(r"[a-z][a-z-]{0,11}", fullmatch=True)
whitelist_entries = st.lists(
    st.text(alphabet="abcdefghijklmnopqrstuvwxyz/._:-", min_size=1),
    max_size=5,
)


def test_defaults_fill_every_check_setting(tmp_path: Path) -> None:
    configuration = read_configuration(written_configuration(tmp_path, MINIMAL))

    file_length = check_settings(configuration, "file-length")

    assert file_length["max-lines"] == 300
    assert file_length["when"] == "pre-commit"
    assert file_length["scope"] == "repository"
    assert file_length["whitelist"] == []
    assert check_settings(configuration, "coverage")["fail-under"] == 100


def test_a_check_section_overrides_the_global_folders(tmp_path: Path) -> None:
    configuration = read_configuration(
        written_configuration(
            tmp_path,
            'source_directories = ["api/src", "ui/src"]\n'
            '[checks.coverage]\nsource_directories = ["api/src"]\n',
        )
    )

    assert check_settings(configuration, "coverage")["source_directories"] == [
        "api/src"
    ]
    assert check_settings(configuration, "linters")["source_directories"] == [
        "api/src",
        "ui/src",
    ]


@pytest.mark.parametrize(
    ("text", "complaint"),
    [
        ("[checks.linters]\nwhen = \"pre-commit\"\n", "source_directories"),
        (MINIMAL + "colour = 3\n", "colour"),
        (MINIMAL + "[checks.linter]\n", "linter"),
        (MINIMAL + "[checks.coverage]\nwhitelist = [\"x\"]\n", "coverage"),
        (MINIMAL + "[checks.linters]\nwhen = \"post-merge\"\n", "when"),
        (MINIMAL + "[checks.linters]\nscope = \"staged\"\n", "scope"),
        (MINIMAL + "[checks.file-length]\nmax_lines = 3\n", "max_lines"),
        (MINIMAL + "[checks.file-length]\nmax-lines = 0\n", "max-lines"),
        (MINIMAL + "[checks.coverage]\nfail-under = 101\n", "fail-under"),
        (MINIMAL + 'stable = "always"\n', "stable"),
        ('source_directories = [""]\n', "empty folder name"),
        ('source_directories = ["svc/src/"]\n', "write svc/src/ as svc/src"),
        ('source_directories = ["./svc/src"]\n', "write ./svc/src as"),
        ('source_directories = ["my svc/src"]\n', "not supported"),
        ('source_directories = ["src[1]"]\n', "not supported"),
        ('source_directories = ["-svc/src"]\n', "not supported"),
        ('source_directories = ["../svc/src"]\n', "inside the repository"),
        ('source_directories = ["/svc/src"]\n', "inside the repository"),
        (MINIMAL + "stable = []\n", "stable"),
        (MINIMAL + "[checks.linters]\nwhen = []\n", "when"),
        (MINIMAL + "[checks.linters]\nscope = {}\n", "scope"),
        (MINIMAL + "[checks.linters.ruff]\nx = 1979-05-27\n", "dates"),
        (MINIMAL + "[checks.linters.ruff]\nx = inf\n", "inf and nan"),
        (
            MINIMAL
            + "[checks.single-responsibility]\n"
            + "whitelist = [{ reviewed = 07:32:00 }]\n",
            "dates",
        ),
        (MINIMAL + "python_environment = 5\n", "python_environment"),
        (MINIMAL + 'python_environment = ""\n', "python_environment"),
    ],
)
def test_rejects_an_invalid_configuration(
    tmp_path: Path, text: str, complaint: str
) -> None:
    configuration_path = written_configuration(tmp_path, text)

    with pytest.raises(ValueError, match=complaint):
        _ = read_configuration(configuration_path)


def test_rejects_a_setting_of_an_unknown_check(tmp_path: Path) -> None:
    configuration_path = written_configuration(tmp_path, MINIMAL)

    finished = read_setting(configuration_path, "checks.file-lenght.scope")

    assert finished.returncode == 1
    assert "file-lenght is not one of" in finished.stderr


def test_prints_whitelist_tables_as_json_lines(tmp_path: Path) -> None:
    configuration_path = written_configuration(
        tmp_path,
        MINIMAL
        + "[checks.single-responsibility]\n"
        + 'whitelist = [{ path = "src/a.py", kind = "module" }]\n',
    )

    finished = read_setting(
        configuration_path, "checks.single-responsibility.whitelist"
    )

    assert json.loads(finished.stdout)["path"] == "src/a.py"


def test_prints_ruff_settings_as_override_pairs(tmp_path: Path) -> None:
    configuration_path = written_configuration(
        tmp_path,
        MINIMAL
        + "[checks.linters.ruff]\nline-length = 100\n"
        + '[checks.linters.ruff.lint.per-file-ignores]\n"t/**" = ["S101"]\n',
    )

    finished = read_setting(configuration_path, "checks.linters.ruff")

    assert finished.stdout.splitlines() == [
        "line-length = 100",
        'lint.per-file-ignores."t/**" = ["S101"]',
    ]


def test_reader_fails_fast_on_a_broken_file(tmp_path: Path) -> None:
    configuration_path = written_configuration(tmp_path, "source = [\n")

    finished = read_setting(configuration_path, "source_directories")

    assert finished.returncode == 1
    assert "checks.toml" in finished.stderr


def test_reader_fails_fast_on_an_unknown_setting(tmp_path: Path) -> None:
    configuration_path = written_configuration(tmp_path, MINIMAL)

    finished = read_setting(configuration_path, "checks.linters.colour")

    assert finished.returncode == 1
    assert "colour" in finished.stderr


def test_every_check_directory_has_a_place_in_the_run_order() -> None:
    check_names: list[str] = []

    for stability in ("stable", "experimental"):
        for check_directory in (CHECKS / stability).iterdir():
            check_names.append(check_directory.name)

    assert sorted(check_names) == sorted(CHECK_ORDER)


@given(st.lists(directory_names, min_size=1, max_size=4))
def test_read_configuration_property_round_trips_source_directories(
    package_names: list[str],
) -> None:
    source_directories = [f"{name}/src" for name in package_names]
    text = f"source_directories = {toml_list(source_directories)}\n"

    with tempfile.TemporaryDirectory() as directory_name:
        configuration_path = written_configuration(Path(directory_name), text)
        configuration = read_configuration(configuration_path)

    assert configuration["source_directories"] == source_directories


@given(st.integers(max_value=0))
def test_validate_configuration_property_rejects_non_positive_line_limits(
    maximum_lines: int,
) -> None:
    configuration = with_defaults(
        {
            "source_directories": ["src"],
            "checks": {"file-length": {"max-lines": maximum_lines}},
        }
    )
    known_settings = {*DEFAULT_SETTINGS, "source_directories"}

    with pytest.raises(ValueError, match="max-lines"):
        validate_configuration(configuration, known_settings)


@given(whitelist_entries)
def test_setting_lines_property_prints_one_line_per_whitelist_entry(
    entries: list[str],
) -> None:
    configuration = with_defaults(
        {
            "source_directories": ["src"],
            "checks": {"file-length": {"whitelist": entries}},
        }
    )

    lines = setting_lines(configuration, "checks.file-length.whitelist")

    assert lines == entries


@given(
    st.dictionaries(
        st.text(alphabet="abcdefghijklmnopqrstuvwxyz-", min_size=1),
        st.integers(),
        max_size=5,
    )
)
def test_setting_lines_property_round_trips_a_tool_table_through_toml(
    tool_settings: dict[str, int],
) -> None:
    configuration = with_defaults(
        {
            "source_directories": ["src"],
            "checks": {"linters": {"ruff": {"lint": tool_settings}}},
        }
    )

    lines = setting_lines(configuration, "checks.linters.ruff")
    parsed_back = tomllib.loads("\n".join(lines))

    assert parsed_back.get("lint", {}) == tool_settings


@given(
    st.dictionaries(
        st.text(min_size=1),
        st.one_of(st.text(), st.booleans(), st.lists(st.text(), max_size=3)),
        max_size=5,
    )
)
def test_setting_lines_property_round_trips_tool_text_through_toml(
    tool_settings: dict[str, object],
) -> None:
    configuration = with_defaults(
        {
            "source_directories": ["src"],
            "checks": {"linters": {"ruff": tool_settings}},
        }
    )

    lines = setting_lines(configuration, "checks.linters.ruff")
    parsed_back = tomllib.loads("\n".join(lines))

    assert parsed_back == tool_settings


@given(st.integers(min_value=1, max_value=10_000))
def test_check_settings_property_keeps_the_written_line_limit(
    maximum_lines: int,
) -> None:
    configuration = with_defaults(
        {
            "source_directories": ["src"],
            "checks": {"file-length": {"max-lines": maximum_lines}},
        }
    )

    settings = check_settings(configuration, "file-length")

    assert settings["max-lines"] == maximum_lines


def test_accepts_a_source_folder_with_any_name(tmp_path: Path) -> None:
    configuration_path = written_configuration(
        tmp_path, 'source_directories = ["api/lib", "web/app"]\n'
    )

    configuration = read_configuration(configuration_path)

    assert configuration["source_directories"] == ["api/lib", "web/app"]
