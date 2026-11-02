import subprocess
import sys
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_CHECKS = Path(__file__).resolve().parents[2] / "checks"
_FINDER = (
    _CHECKS / "experimental" / "identity-comparison" / "python"
    / "identity_comparisons.py"
)
_FIX = "equal values can be distinct objects, so use"
_LITERALS = {
    "str": "'shipped'",
    "bytes": "b'\\x00'",
    "int": "1000",
    "float": "0.5",
    "tuple": "('a', 'b')",
}
_OPERATORS = {"is": "==", "is not": "!="}


def _report_for(tmp_path: Path, modules: dict[str, str]) -> list[str]:
    for name, source in modules.items():
        _ = (tmp_path / name).write_text(source, encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="\n".join(modules),
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def _finding(location: str, comparison: str, reason: str, fix: str) -> str:
    return (
        f"{location}: {comparison} compares object identity, but {reason}"
        f" - {_FIX} {fix}"
    )


def test_reports_a_module_constant_of_the_same_file(tmp_path: Path) -> None:
    source = (
        "SHIPPED: str = 'shipped'\n"
        "def is_done(order_state: str) -> bool:\n"
        "    if order_state == 'cancelled':\n        return False\n"
        "    return order_state is SHIPPED\n"
    )

    assert _report_for(tmp_path, {"orders.py": source}) == [
        _finding(
            "orders.py:5",
            "order_state is SHIPPED",
            "SHIPPED is a constant str",
            "==",
        )
    ]


def test_reports_imported_and_module_attribute_constants(
    tmp_path: Path,
) -> None:
    settings = "RETRY_LIMIT = 3\nGREETING = 'hi' + '!'\n"
    jobs = (
        "import settings\n"
        "from settings import RETRY_LIMIT\n"
        "def retry(attempts, text):\n"
        "    if attempts == 0 or text in ('', 'none'):\n        return None\n"
        "    if attempts is not RETRY_LIMIT:\n"
        "        return text is settings.GREETING\n"
    )

    assert _report_for(
        tmp_path, {"settings.py": settings, "jobs.py": jobs}
    ) == [
        _finding(
            "jobs.py:6",
            "attempts is not RETRY_LIMIT",
            "RETRY_LIMIT is a constant int",
            "!=",
        ),
        _finding(
            "jobs.py:7",
            "text is settings.GREETING",
            "settings.GREETING is a constant str",
            "==",
        ),
    ]


def test_reports_constants_of_a_plain_class(tmp_path: Path) -> None:
    source = (
        "class Limits:\n"
        "    MAX_RATIO = 0.75\n"
        "    def over(self, ratio):\n"
        "        if ratio == 0:\n            return False\n"
        "        return ratio is self.MAX_RATIO or Limits.MAX_RATIO is ratio\n"
    )

    assert _report_for(tmp_path, {"limits.py": source}) == [
        _finding(
            "limits.py:6",
            "Limits.MAX_RATIO is ratio",
            "Limits.MAX_RATIO is a constant float",
            "==",
        ),
        _finding(
            "limits.py:6",
            "ratio is self.MAX_RATIO",
            "self.MAX_RATIO is a constant float",
            "==",
        ),
    ]


def test_passes_a_marker_only_compared_by_identity(tmp_path: Path) -> None:
    source = (
        "SUPPRESS = '==SUPPRESS=='\n"
        "def format_help(heading):\n"
        "    if heading is SUPPRESS:\n        return ''\n"
        "    return heading\n"
    )

    assert _report_for(tmp_path, {"help.py": source}) == []


def test_reports_a_constant_compared_with_a_looked_up_value(
    tmp_path: Path,
) -> None:
    source = (
        "CANCELLED = 'cancelled'\n"
        "def is_cancelled(job_row: dict[str, str]) -> bool:\n"
        "    return job_row.get('status') is CANCELLED\n"
    )

    assert _report_for(tmp_path, {"jobs.py": source}) == [
        _finding(
            "jobs.py:3",
            "job_row.get('status') is CANCELLED",
            "CANCELLED is a constant str",
            "==",
        )
    ]


def test_passes_a_lookup_whose_default_is_the_constant(
    tmp_path: Path,
) -> None:
    source = (
        "MISSING = '<missing>'\n"
        "def has_option(options: dict[str, str], name: str) -> bool:\n"
        "    return options.get(name, MISSING) is not MISSING\n"
    )

    assert _report_for(tmp_path, {"options.py": source}) == []


def test_reports_values_made_fresh(tmp_path: Path) -> None:
    source = (
        "def same(label, text, number, code):\n"
        "    first = label is text.lower()\n"
        "    second = code is str(number)\n"
        "    third = f'{number}' is not code\n"
        "    return first, second, third\n"
    )

    assert _report_for(tmp_path, {"labels.py": source}) == [
        _finding(
            "labels.py:2",
            "label is text.lower()",
            "text.lower() makes a new value",
            "==",
        ),
        _finding(
            "labels.py:3",
            "code is str(number)",
            "str(number) makes a new value",
            "==",
        ),
        _finding(
            "labels.py:4",
            "f'{number}' is not code",
            "f'{number}' makes a new value",
            "!=",
        ),
    ]


def test_passes_singletons_sentinels_enums_and_classes(
    tmp_path: Path,
) -> None:
    source = (
        "from enum import Enum\n"
        "MISSING = object()\n"
        "class Color(Enum):\n"
        "    RED = 'red'\n"
        "def check(value, kind):\n"
        "    return (\n"
        "        value is None, value is True, value is MISSING,\n"
        "        value is Color.RED, kind is int, value is NotImplemented,\n"
        "        value is ...\n"
        "    )\n"
    )

    assert _report_for(tmp_path, {"marks.py": source}) == []


def test_passes_locals_ambiguous_names_and_star_imports(
    tmp_path: Path,
) -> None:
    first = "LIMIT = 10\nDEFAULT = 'x'\n"
    second = "LIMIT = object()\nfrom first import *\n"
    third = (
        "from first import LIMIT\n"
        "from second import *\n"
        "def check(value, DEFAULT):\n"
        "    return value is LIMIT, value is DEFAULT\n"
        "def other(value):\n"
        "    return value is DEFAULT\n"
    )

    assert _report_for(
        tmp_path,
        {"first.py": first, "second.py": second, "third.py": third},
    ) == []


def test_passes_the_unpassed_argument_idiom(tmp_path: Path) -> None:
    source = (
        "_ONE = 1\n"
        "_UNKNOWN = '--unknown--'\n"
        "def step_range(start, step=_ONE, *, cache):\n"
        "    entry = cache.get(start, _UNKNOWN)\n"
        "    if entry is not _UNKNOWN:\n"
        "        return entry\n"
        "    return step is not _ONE\n"
    )

    assert _report_for(tmp_path, {"ranges.py": source}) == []


@HYPOTHESIS_SETTINGS
@given(
    kind=st.sampled_from(sorted(_LITERALS)),
    operator=st.sampled_from(sorted(_OPERATORS)),
)
def test_identity_property_flags_value_constants_only(
    tmp_path: Path, kind: str, operator: str
) -> None:
    source = (
        f"MARKER = {_LITERALS[kind]}\n"
        "SENTINEL = object()\n"
        "def check(value):\n"
        "    equal = value == MARKER\n"
        "    same = value is SENTINEL\n"
        f"    return value {operator} MARKER, equal, same\n"
    )

    report = _report_for(tmp_path, {"marks.py": source})

    assert report == [
        _finding(
            "marks.py:6",
            f"value {operator} MARKER",
            f"MARKER is a constant {kind}",
            _OPERATORS[operator],
        )
    ]
