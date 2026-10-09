from pathlib import Path

from property_coverage_support import given_test, missing, report_for

_NEXT_REVIEW = "def next_review(card):\n    return card.due\n"


def test_flags_a_function_with_no_property_test(tmp_path: Path) -> None:
    report = report_for(tmp_path, _NEXT_REVIEW, "")

    assert report == [missing("next_review", 1)]


def test_accepts_a_function_with_a_matching_property_test(
    tmp_path: Path,
) -> None:
    tests = given_test("test_next_review_property_never_moves_backwards")

    assert report_for(tmp_path, _NEXT_REVIEW, tests) == []


def test_accepts_a_property_test_with_no_description(
    tmp_path: Path,
) -> None:
    tests = given_test("test_next_review_property")

    assert report_for(tmp_path, _NEXT_REVIEW, tests) == []


def test_rejects_a_test_named_without_the_property_marker(
    tmp_path: Path,
) -> None:
    tests = given_test("test_next_review_never_moves_backwards")

    assert report_for(tmp_path, _NEXT_REVIEW, tests) == [
        missing("next_review", 1)
    ]


def test_a_longer_definitions_test_does_not_cover_a_shorter_one(
    tmp_path: Path,
) -> None:
    tests = given_test("test_next_review_interval_property_is_positive")

    assert report_for(tmp_path, _NEXT_REVIEW, tests) == [
        missing("next_review", 1)
    ]


def test_flags_a_method_inside_a_class(tmp_path: Path) -> None:
    source = (
        "class Scheduler:\n"
        "    def due_today(self):\n"
        "        return self.cards\n"
    )

    assert report_for(tmp_path, source, "") == [missing("due_today", 2)]


def test_reports_every_uncovered_definition_in_order(
    tmp_path: Path,
) -> None:
    source = (
        "def first(value):\n    return value\n"
        "class Scheduler:\n"
        "    def second(self):\n        return self.cards\n"
    )
    report = report_for(tmp_path, source, "")

    assert report == [missing("first", 1), missing("second", 4)]


def test_says_nothing_about_definitions_in_the_test_file(
    tmp_path: Path,
) -> None:
    tests = "def helper_for_the_suite():\n    return 1\n"

    assert report_for(tmp_path, "", tests) == []
