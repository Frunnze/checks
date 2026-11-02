import subprocess
import sys
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_DEEP_TERMS = 1000
_FINDER = (
    Path(__file__).resolve().parents[2] / "checks" / "experimental"
    / "copied-operand" / "python" / "copied_operands.py"
)
_SERIES = "its siblings step through indexes but it repeats one"


def _report_for(tmp_path: Path, source: str) -> list[str]:
    _ = (tmp_path / "shapes.py").write_text(source, encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="shapes.py",
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def test_reports_a_repeated_index_in_a_series(tmp_path: Path) -> None:
    source = (
        "def expand(digits, pixel):\n"
        "    full = digits[0] * 2 + digits[1] * 2 + digits[1] * 2\n"
        "    return full, pixel[0] + pixel[1] + pixel[1] + pixel[3]\n"
    )

    assert _report_for(tmp_path, source) == [
        f"shapes.py:2: digits[1] * 2 - {_SERIES}",
        f"shapes.py:3: pixel[1] - {_SERIES}",
    ]


def test_reports_operands_that_cancel_out(tmp_path: Path) -> None:
    source = (
        "def size(box, other, ready):\n"
        "    width = box.right - box.right\n"
        "    ok = ready and other.valid and ready\n"
        "    return width, max(box.top, box.top), ok\n"
    )

    assert _report_for(tmp_path, source) == [
        "shapes.py:2: box.right - box.right - both operands are the same",
        "shapes.py:3: ready and other.valid and ready - it tests the same"
        " condition twice",
        "shapes.py:4: max(box.top, box.top) - both arguments are the same",
    ]


def test_passes_deliberate_shapes(tmp_path: Path) -> None:
    source = (
        "import random\n"
        "def build(value, offset, digits, size, vector):\n"
        "    doubled = value + value\n"
        "    squared = value * value\n"
        "    not_a_number = value - value\n"
        "    spread = random.random() - random.random()\n"
        "    fill = (offset[0], offset[0], offset[0])\n"
        "    pair = digits[0] + digits[0]\n"
        "    ordered = digits[0] + digits[1] + digits[2]\n"
        "    pad = (size[0], size[1], size[1])\n"
        "    dot = vector & vector\n"
        "    return (doubled, squared, not_a_number, spread, fill, pair,\n"
        "            ordered, pad, dot)\n"
    )

    assert _report_for(tmp_path, source) == []


def test_skips_cancelling_operands_in_tests(tmp_path: Path) -> None:
    folder = tmp_path / "tests"
    folder.mkdir()
    _ = (folder / "test_numbers.py").write_text(
        "def test_zero(box):\n    assert box.top - box.top == 0\n",
        encoding="utf-8",
    )

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="tests/test_numbers.py",
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    assert finished.stdout == ""


@HYPOTHESIS_SETTINGS
@given(
    length=st.integers(min_value=3, max_value=6),
    data=st.data(),
)
def test_series_property_flags_a_repeat_after_a_step(
    tmp_path: Path, length: int, data: st.DataObject
) -> None:
    repeat_at = data.draw(st.integers(min_value=2, max_value=length - 1))
    indexes = list(range(length))
    indexes[repeat_at] = indexes[repeat_at - 1]
    items = " + ".join(f"row[{index}]" for index in indexes)
    clean = " + ".join(f"row[{index}]" for index in range(length))
    source = f"def pick(row):\n    return ({items}), ({clean})\n"

    assert _report_for(tmp_path, source) == [
        f"shapes.py:2: row[{indexes[repeat_at]}] - {_SERIES}"
    ]


def test_survives_deeply_nested_code(tmp_path: Path) -> None:
    terms = " + ".join(f"term_{index}" for index in range(_DEEP_TERMS))
    source = f"def total():\n    return {terms}\n"

    assert _report_for(tmp_path, source) == []
