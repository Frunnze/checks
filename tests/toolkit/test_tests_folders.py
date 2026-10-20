from pathlib import Path

import pytest

from check_support import (
    link_real_python,
    repository,
    run_configured,
    stage_file,
)

SOURCE = "def score(value: int) -> int:\n    return value\n"
PROPERTY_TEST = (
    "from hypothesis import given, strategies as st\n\n"
    "from score import score\n\n\n"
    "@given(st.integers())\n"
    "def test_score_property_returns_its_input(value: int) -> None:\n"
    "    assert score(value) == value\n\n\n"
    "@given(st.integers())\n"
    "def test_score_property_keeps_the_sign(value: int) -> None:\n"
    "    assert (score(value) < 0) == (value < 0)\n\n\n"
    "@given(st.integers())\n"
    "def test_score_property_is_idempotent(value: int) -> None:\n"
    "    assert score(score(value)) == score(value)\n\n\n"
    "@given(st.integers(), st.integers())\n"
    "def test_score_property_keeps_the_order(left: int, right: int) -> None:\n"
    "    assert (score(left) <= score(right)) == (left <= right)\n\n\n"
    "def helper() -> int:\n"
    "    return 1\n"
)
TESTED_CHECKS = ["coverage", "api-contract", "property-tests"]


def _configuration(source_directories: str, check_name: str) -> str:
    return (
        f"source_directories = {source_directories}\n"
        f'[checks.{check_name}]\nwhen = "pre-commit"\n'
    )


@pytest.mark.parametrize("check_name", TESTED_CHECKS)
def test_a_check_that_needs_tests_fails_when_they_are_not_listed(
    tmp_path: Path, check_name: str
) -> None:
    repository(tmp_path)
    link_real_python(tmp_path)
    stage_file(tmp_path, "svc/src/score.py", SOURCE)
    stage_file(tmp_path, "svc/tests/test_score.py", PROPERTY_TEST)

    finished = run_configured(
        tmp_path, _configuration('["svc/src"]', check_name), check_name
    )

    assert finished.returncode == 1
    assert f"{check_name} needs svc/tests" in finished.stderr


def test_a_listed_tests_folder_is_read_as_tests_not_as_sources(
    tmp_path: Path,
) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "svc/src/score.py", SOURCE)
    stage_file(tmp_path, "svc/tests/test_score.py", PROPERTY_TEST)

    finished = run_configured(
        tmp_path,
        _configuration('["svc/src", "svc/tests"]', "property-tests"),
        "property-tests",
    )

    assert finished.returncode == 0, finished.stderr
