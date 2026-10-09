from pathlib import Path

from property_coverage_support import given_test, missing, report_for

_NEXT_REVIEW = "def next_review(card):\n    return card.due\n"
_LIST_DUE = "async def list_due(db):\n    return db.query()\n"


def test_accepts_an_async_function_with_a_property_test(
    tmp_path: Path,
) -> None:
    tests = given_test("test_list_due_property_returns_only_due_cards")

    assert report_for(tmp_path, _LIST_DUE, tests) == []


def test_flags_an_async_function_with_no_property_test(
    tmp_path: Path,
) -> None:
    assert report_for(tmp_path, _LIST_DUE, "") == [missing("list_due", 1)]


def test_rejects_a_test_without_the_given_decorator(tmp_path: Path) -> None:
    tests = "def test_next_review_property_is_stable():\n    return 1\n"

    assert report_for(tmp_path, _NEXT_REVIEW, tests) == [
        missing("next_review", 1)
    ]


def test_accepts_given_beneath_a_settings_decorator(tmp_path: Path) -> None:
    tests = given_test(
        "test_next_review_property_is_stable",
        "@settings(max_examples=10)\n@given()",
    )

    assert report_for(tmp_path, _NEXT_REVIEW, tests) == []


def test_accepts_a_qualified_hypothesis_given(tmp_path: Path) -> None:
    tests = (
        "import hypothesis\n"
        "@hypothesis.given()\n"
        "def test_next_review_property_is_stable():\n"
        "    return 1\n"
    )

    assert report_for(tmp_path, _NEXT_REVIEW, tests) == []
