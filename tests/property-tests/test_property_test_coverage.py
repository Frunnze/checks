import codecs
import keyword
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS
from property_coverage_support import (
    SOURCE,
    given_test,
    missing,
    missing_in,
    report_for,
    report_for_bytes,
    report_for_files,
)

_NEXT_REVIEW = "def next_review(card):\n    return card.due\n"
_IDENTIFIERS = st.from_regex(r"[a-z]{3,8}", fullmatch=True).filter(
    lambda name: not keyword.iskeyword(name)
)
_LATIN1_COOKIE = "# -*- coding: latin-1 -*-\n"


def _encoded(source: str, encoding: str) -> bytes:
    if encoding == "bom":
        return codecs.BOM_UTF8 + source.encode("utf-8")

    return (_LATIN1_COOKIE + source + "LABEL = 'café'\n").encode("latin-1")


def _findings(report: list[str]) -> list[str]:
    return [line.split(": ", 1)[1] for line in report]


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


def test_reads_a_path_with_a_space(tmp_path: Path) -> None:
    source = "service/src/my scheduler.py"
    report = report_for_files(tmp_path, {source: _NEXT_REVIEW})

    assert report == [missing_in(source, "next_review", 1)]


@pytest.mark.parametrize("encoding", ("bom", "latin1_cookie"))
@HYPOTHESIS_SETTINGS
@given(name=_IDENTIFIERS)
def test_coverage_property_reads_every_encoding_python_reads(
    tmp_path: Path, encoding: str, name: str
) -> None:
    source = f"def {name}(value):\n    return value + 1\n"
    plain = report_for_bytes(tmp_path, {str(SOURCE): source.encode("utf-8")})
    encoded = report_for_bytes(
        tmp_path, {str(SOURCE): _encoded(source, encoding)}
    )

    assert _findings(encoded) == _findings(plain) == _findings(
        [missing(name, 1)]
    )
