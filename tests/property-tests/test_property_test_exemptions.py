from pathlib import Path

from property_coverage_support import missing, report_for


def test_says_nothing_about_a_dunder_method(tmp_path: Path) -> None:
    source = "class Scheduler:\n    def __init__(self):\n        self.a = 1\n"

    assert report_for(tmp_path, source, "") == []


def test_says_nothing_about_a_route_handler(tmp_path: Path) -> None:
    source = (
        "@router.get('/due')\n"
        "async def list_due(db):\n"
        "    return db.query()\n"
    )

    assert report_for(tmp_path, source, "") == []


def test_says_nothing_about_a_handler_on_any_verb(tmp_path: Path) -> None:
    verbs = ("post", "put", "patch", "delete", "websocket")
    source = "".join(
        f"@router.{verb}('/x')\ndef handle_{verb}(db):\n    return db\n"
        for verb in verbs
    )

    assert report_for(tmp_path, source, "") == []


def test_says_nothing_about_a_body_that_only_says_ellipsis(
    tmp_path: Path,
) -> None:
    source = "class Reader:\n    def read(self) -> str: ...\n"

    assert report_for(tmp_path, source, "") == []


def test_says_nothing_about_a_body_that_only_passes(
    tmp_path: Path,
) -> None:
    source = "def not_written_yet():\n    pass\n"

    assert report_for(tmp_path, source, "") == []


def test_still_flags_a_plain_function_beside_the_exempt_ones(
    tmp_path: Path,
) -> None:
    source = (
        "class Reader:\n"
        "    def __init__(self):\n        self.a = 1\n"
        "    def read(self) -> str: ...\n"
        "def parse(text):\n    return text.strip()\n"
    )

    assert report_for(tmp_path, source, "") == [missing("parse", 5)]


def test_still_flags_a_decorated_function_that_is_not_a_route(
    tmp_path: Path,
) -> None:
    source = "@cache\ndef parse(text):\n    return text.strip()\n"

    assert report_for(tmp_path, source, "") == [missing("parse", 2)]
