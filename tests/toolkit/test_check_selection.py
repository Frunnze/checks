from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from configuration_support import written_configuration
from settings import enabled_check_directories, read_configuration, with_defaults

MINIMAL = 'source_directories = ["src"]\n'


def _enabled_names(tmp_path: Path, text: str, stage: str) -> list[str]:
    configuration = read_configuration(written_configuration(tmp_path, text))
    directories = enabled_check_directories(configuration, stage)

    return [directory.name for directory in directories]


def test_every_stable_check_runs_on_pre_commit_by_default(
    tmp_path: Path,
) -> None:
    names = _enabled_names(tmp_path, MINIMAL, "pre-commit")

    assert "linters" in names
    assert "coverage" in names
    assert "open-closed" not in names


def test_stable_moves_every_stable_check_at_once(tmp_path: Path) -> None:
    text = MINIMAL + 'stable = "pre-push"\n'

    assert _enabled_names(tmp_path, text, "pre-commit") == []
    assert "linters" in _enabled_names(tmp_path, text, "pre-push")


def test_a_check_section_overrides_the_stable_default(tmp_path: Path) -> None:
    text = MINIMAL + '[checks.coverage]\nwhen = "pre-push"\n'

    assert "coverage" not in _enabled_names(tmp_path, text, "pre-commit")
    assert _enabled_names(tmp_path, text, "pre-push") == ["coverage"]


def test_off_turns_a_stable_check_off(tmp_path: Path) -> None:
    text = MINIMAL + '[checks.coverage]\nwhen = "off"\n'

    assert "coverage" not in _enabled_names(tmp_path, text, "all")


def test_an_experimental_check_runs_only_when_named(tmp_path: Path) -> None:
    text = MINIMAL + '[checks.open-closed]\nwhen = "both"\n'

    assert "open-closed" in _enabled_names(tmp_path, text, "pre-commit")
    assert "open-closed" in _enabled_names(tmp_path, text, "pre-push")
    assert "single-responsibility" not in _enabled_names(
        tmp_path, text, "all"
    )


@given(
    st.sampled_from(["pre-commit", "pre-push", "both", "off"]),
    st.sampled_from(["pre-commit", "pre-push"]),
)
def test_enabled_check_directories_property_runs_a_check_only_at_its_hook(
    when: str, stage: str
) -> None:
    configuration = with_defaults(
        {
            "source_directories": ["src"],
            "checks": {"linters": {"when": when}},
        }
    )

    names = {
        directory.name
        for directory in enabled_check_directories(configuration, stage)
    }

    assert ("linters" in names) == (when in {stage, "both"})
