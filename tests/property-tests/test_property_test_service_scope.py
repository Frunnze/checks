from pathlib import Path

from property_coverage_support import (
    given_test,
    missing_in,
    report_for_files,
)

_ALPHA_SOURCE = "alpha-service/src/features/study_units/scheduler.py"
_BETA_SOURCE = "beta-service/src/features/study_units/scheduler.py"
_ALPHA_TESTS = "alpha-service/tests/test_scheduler.py"
_BETA_TESTS = "beta-service/tests/test_scheduler.py"
_NEXT_REVIEW = "def next_review(card):\n    return card.due\n"
_COVERING_TEST = given_test("test_next_review_property_never_regresses")


def test_a_property_test_in_another_service_covers_nothing(
    tmp_path: Path,
) -> None:
    files = {
        _ALPHA_SOURCE: _NEXT_REVIEW,
        _ALPHA_TESTS: _COVERING_TEST,
        _BETA_SOURCE: _NEXT_REVIEW,
    }

    assert report_for_files(tmp_path, files) == [
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

    assert report_for_files(tmp_path, files) == []


def test_a_service_without_a_test_suite_reports_its_definitions(
    tmp_path: Path,
) -> None:
    files = {
        _ALPHA_SOURCE: _NEXT_REVIEW,
        _ALPHA_TESTS: _COVERING_TEST,
        _BETA_SOURCE: "def archive(card):\n    return card\n",
    }

    assert report_for_files(tmp_path, files) == [
        missing_in(_BETA_SOURCE, "archive", 1)
    ]


def test_every_service_reports_its_own_uncovered_definitions(
    tmp_path: Path,
) -> None:
    files = {
        _ALPHA_SOURCE: _NEXT_REVIEW,
        _BETA_SOURCE: _NEXT_REVIEW,
    }

    assert report_for_files(tmp_path, files) == [
        missing_in(_ALPHA_SOURCE, "next_review", 1),
        missing_in(_BETA_SOURCE, "next_review", 1),
    ]
