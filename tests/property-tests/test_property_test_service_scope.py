import keyword
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS
from property_coverage_support import (
    given_test,
    missing_in,
    report_for_files,
)

_SERVICES = ("alpha-service/src", "beta-service/src")
_ALPHA_SOURCE = "alpha-service/src/features/study_units/scheduler.py"
_BETA_SOURCE = "beta-service/src/features/study_units/scheduler.py"
_ALPHA_TESTS = "alpha-service/tests/test_scheduler.py"
_BETA_TESTS = "beta-service/tests/test_scheduler.py"
_NEXT_REVIEW = "def next_review(card):\n    return card.due\n"
_COVERING_TEST = given_test("test_next_review_property_never_regresses")
_IDENTIFIERS = st.from_regex(r"[a-z]{3,8}", fullmatch=True).filter(
    lambda name: not keyword.iskeyword(name)
)


def test_a_property_test_in_another_service_covers_nothing(
    tmp_path: Path,
) -> None:
    files = {
        _ALPHA_SOURCE: _NEXT_REVIEW,
        _ALPHA_TESTS: _COVERING_TEST,
        _BETA_SOURCE: _NEXT_REVIEW,
    }

    assert report_for_files(tmp_path, files, _SERVICES) == [
        missing_in(_BETA_SOURCE, "next_review", 1)
    ]


def test_each_service_is_covered_by_its_own_property_test(
    tmp_path: Path,
) -> None:
    files = {
        _ALPHA_SOURCE: _NEXT_REVIEW,
        _ALPHA_TESTS: _COVERING_TEST,
        _BETA_SOURCE: _NEXT_REVIEW,
        _BETA_TESTS: _COVERING_TEST,
    }

    assert report_for_files(tmp_path, files, _SERVICES) == []


def test_a_service_without_a_test_suite_reports_its_definitions(
    tmp_path: Path,
) -> None:
    files = {
        _ALPHA_SOURCE: _NEXT_REVIEW,
        _ALPHA_TESTS: _COVERING_TEST,
        _BETA_SOURCE: "def archive(card):\n    return card\n",
    }

    assert report_for_files(tmp_path, files, _SERVICES) == [
        missing_in(_BETA_SOURCE, "archive", 1)
    ]


def test_every_service_reports_its_own_uncovered_definitions(
    tmp_path: Path,
) -> None:
    files = {
        _ALPHA_SOURCE: _NEXT_REVIEW,
        _BETA_SOURCE: _NEXT_REVIEW,
    }

    assert report_for_files(tmp_path, files, _SERVICES) == [
        missing_in(_ALPHA_SOURCE, "next_review", 1),
        missing_in(_BETA_SOURCE, "next_review", 1),
    ]


def test_a_source_folder_named_like_its_service_finds_its_tests(
    tmp_path: Path,
) -> None:
    source = "app/app/scheduler.py"
    files = {
        source: (
            "def schedule(cards):\n    return cards\n"
            "def plan(cards):\n    return cards\n"
        ),
        "app/tests/test_scheduler.py": given_test(
            "test_schedule_property_sorted"
        ),
    }

    assert report_for_files(tmp_path, files, ("app/app",)) == [
        missing_in(source, "plan", 3)
    ]


@pytest.mark.parametrize("feature", ("notes", "tests", "fixtures"))
@HYPOTHESIS_SETTINGS
@given(name=_IDENTIFIERS)
def test_scope_property_ignores_the_feature_name(
    tmp_path: Path, feature: str, name: str
) -> None:
    source = f"service/src/features/{feature}/api.py"
    files = {source: f"def {name}(value):\n    return value + 1\n"}

    assert report_for_files(tmp_path, files) == [missing_in(source, name, 1)]
