import subprocess
import sys
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_CHECKS = Path(__file__).resolve().parents[2] / "checks"
_FINDER = (
    _CHECKS / "experimental" / "unreachable-branch" / "python"
    / "unreachable_branches.py"
)
_NEVER = "this branch never runs - line {} already takes all its cases"


def _report_for(tmp_path: Path, files: dict[str, str]) -> list[str]:
    for relative, source in files.items():
        _ = (tmp_path / relative).write_text(source, encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="\n".join(files),
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def _never(path: str, line: int, covering_line: int) -> str:
    return f"{path}:{line}: {_NEVER.format(covering_line)}"


def test_reports_a_threshold_shadowed_by_a_lower_one(tmp_path: Path) -> None:
    source = (
        "WARN_RATIO = 0.8\nBLOCK_RATIO = 1.0\n"
        "def level(usage):\n"
        "    if usage >= WARN_RATIO:\n        return 'warn'\n"
        "    elif usage >= BLOCK_RATIO:\n        return 'block'\n"
        "    return 'ok'\n"
    )

    report = _report_for(tmp_path, {"quota.py": source})

    assert report == [_never("quota.py", 6, 4)]


def test_reads_a_limit_defined_in_another_module(tmp_path: Path) -> None:
    limits = "MAX_ITEMS = 100\n"
    source = (
        "def size(items):\n"
        "    if len(items) > 10:\n        return 'large'\n"
        "    elif len(items) > MAX_ITEMS:\n        return 'huge'\n"
        "    return 'small'\n"
    )

    report = _report_for(tmp_path, {"limits.py": limits, "size.py": source})

    assert report == [_never("size.py", 4, 2)]


def test_reports_a_subclass_tested_after_its_base(tmp_path: Path) -> None:
    errors = "class PaymentError(Exception):\n    pass\n"
    source = (
        "class CardDeclined(PaymentError):\n    pass\n"
        "def kind(value):\n"
        "    if isinstance(value, int):\n        return 'number'\n"
        "    elif isinstance(value, bool):\n        return 'flag'\n"
        "    return 'other'\n"
        "def pay(charge):\n"
        "    try:\n        charge()\n"
        "    except PaymentError:\n        return 'retry'\n"
        "    except CardDeclined:\n        return 'stop'\n"
        "    return 'done'\n"
    )

    report = _report_for(tmp_path, {"errors.py": errors, "pay.py": source})

    assert report == [_never("pay.py", 6, 4), _never("pay.py", 14, 12)]


def test_skips_a_class_name_defined_twice(tmp_path: Path) -> None:
    first = "class TimeoutError(Exception):\n    pass\n"
    second = "class TimeoutError(OSError):\n    pass\n"
    source = (
        "def call(run):\n"
        "    try:\n        run()\n"
        "    except OSError:\n        return 'network'\n"
        "    except TimeoutError:\n        return 'slow'\n"
        "    return 'done'\n"
    )
    files = {"first.py": first, "second.py": second, "call.py": source}

    assert _report_for(tmp_path, files) == []


def test_reports_a_repeated_condition(tmp_path: Path) -> None:
    source = (
        "def route(method, user):\n"
        "    if method == 'GET' and user:\n        return 1\n"
        "    elif method == 'POST':\n        return 2\n"
        "    elif method == 'GET':\n        return 3\n"
        "    elif method == 'POST' and user.admin:\n        return 4\n"
        "    return 0\n"
    )

    assert _report_for(tmp_path, {"route.py": source}) == [
        _never("route.py", 8, 4)
    ]


def test_reports_equality_tested_after_containment(tmp_path: Path) -> None:
    source = (
        "def match(word, line):\n"
        "    if word in line:\n        return 'partial'\n"
        "    elif line == word:\n        return 'exact'\n"
        "    return 'none'\n"
    )

    assert _report_for(tmp_path, {"match.py": source}) == [
        _never("match.py", 4, 2)
    ]


def test_passes_conditions_in_narrowing_order(tmp_path: Path) -> None:
    source = (
        "def grade(score, value):\n"
        "    if score >= 90:\n        return 'a'\n"
        "    elif score >= 80:\n        return 'b'\n"
        "    if isinstance(value, bool):\n        return 'flag'\n"
        "    if value == score:\n        return 'same'\n"
        "    elif value in score:\n        return 'part'\n"
        "    elif isinstance(value, int):\n        return 'number'\n"
        "    if read() == 'a':\n        return 'first'\n"
        "    elif read() == 'a':\n        return 'second'\n"
        "    if isinstance(value, numpy.dtype):\n        return 'numpy'\n"
        "    elif isinstance(value, torch.dtype):\n        return 'torch'\n"
        "    if False:\n        return 'off'\n"
        "    elif False:\n        return 'also off'\n"
        "    return 'f'\n"
    )

    assert _report_for(tmp_path, {"grade.py": source}) == []


@HYPOTHESIS_SETTINGS
@given(
    low=st.integers(min_value=-1000, max_value=1000),
    gap=st.integers(min_value=1, max_value=1000),
)
def test_threshold_property_flags_only_the_wrong_order(
    tmp_path: Path, low: int, gap: int
) -> None:
    high = low + gap
    wrong = (
        "def wrong(value):\n"
        f"    if value > {low}:\n        return 1\n"
        f"    elif value > {high}:\n        return 2\n"
        "    return 0\n"
    )
    right = (
        "def right(value):\n"
        f"    if value > {high}:\n        return 2\n"
        f"    elif value > {low}:\n        return 1\n"
        "    return 0\n"
    )

    report = _report_for(tmp_path, {"wrong.py": wrong, "right.py": right})

    assert report == [_never("wrong.py", 4, 2)]
