import subprocess
import sys
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_CHECKS = Path(__file__).resolve().parents[2] / "checks"
_FINDER = (
    _CHECKS / "experimental" / "uneven-twins" / "python" / "uneven_twins.py"
)
_AXES = (("x", "y"), ("width", "height"), ("row", "column"))


def _report_for(tmp_path: Path, source: str) -> list[str]:
    module = tmp_path / "shapes.py"
    _ = module.write_text(source, encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="shapes.py",
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def test_reports_a_distance_without_its_twins_abs(tmp_path: Path) -> None:
    source = (
        "def touching(upper, lower, gap):\n"
        "    above = abs(upper.bottom - lower.top) <= gap\n"
        "    below = upper.top - lower.bottom <= gap\n"
        "    return above or below\n"
    )

    expected = (
        "shapes.py:3: below = upper.top - lower.bottom <= gap lacks the"
        " abs() of its twin on line 2 - add the abs() here or drop it"
        " from the twin"
    )

    assert _report_for(tmp_path, source) == [expected]


def test_reports_a_column_bound_without_the_rows_plus_one(
    tmp_path: Path,
) -> None:
    source = (
        "def bounds(rows, columns):\n"
        "    top, bottom = int(rows.min()), int(rows.max()) + 1\n"
        "    left, right = int(columns.min()), int(columns.max())\n"
        "    return top, bottom, left, right\n"
    )

    expected = (
        "shapes.py:3: left, right = (int(columns.min()), int(columns.max()))"
        " lacks the + 1 of its twin on line 2 - add the + 1 here or drop it"
        " from the twin"
    )

    assert _report_for(tmp_path, source) == [expected]


def test_reports_a_width_without_the_heights_plus_one(
    tmp_path: Path,
) -> None:
    source = (
        "def size(first_row, last_row, first_column, last_column):\n"
        "    width = int(last_column - first_column)\n"
        "    height = int(last_row - first_row) + 1\n"
        "    return width, height\n"
    )

    expected = (
        "shapes.py:2: width = int(last_column - first_column) lacks the + 1"
        " of its twin on line 3 - add the + 1 here or drop it from the twin"
    )

    assert _report_for(tmp_path, source) == [expected]


def test_reports_an_end_without_the_other_axis_minus_one(
    tmp_path: Path,
) -> None:
    source = (
        "def corner(x, y, size_x, size_y):\n"
        "    last_x = x + size_x - 1\n"
        "    last_y = y + size_y\n"
        "    return last_x, last_y\n"
    )

    expected = (
        "shapes.py:3: last_y = y + size_y lacks the - 1 of its twin on"
        " line 2 - add the - 1 here or drop it from the twin"
    )

    assert _report_for(tmp_path, source) == [expected]


def test_reports_an_operand_without_the_other_operands_plus_one(
    tmp_path: Path,
) -> None:
    source = (
        "def inside(x, y, width, height):\n"
        "    return (0 <= x < width + 1\n"
        "            and 0 <= y < height)\n"
    )

    expected = (
        "shapes.py:3: 0 <= y < height lacks the + 1 of its twin on line 2"
        " - add the + 1 here or drop it from the twin"
    )

    assert _report_for(tmp_path, source) == [expected]


@pytest.mark.parametrize(
    "source",
    [
        "width = right - left + 1\nheight = bottom - top + 1\n",
        "width = right - left\nheight = bottom - top\n",
    ],
)
def test_passes_twins_that_agree(tmp_path: Path, source: str) -> None:
    assert _report_for(tmp_path, source) == []


def test_passes_a_step_inside_an_index(tmp_path: Path) -> None:
    source = "row_value = grid[row + 1]\ncolumn_value = grid[column]\n"

    assert _report_for(tmp_path, source) == []


def test_passes_opposite_ends(tmp_path: Path) -> None:
    source = "start_x = origin_x + 1\nend_y = origin_y\n"

    assert _report_for(tmp_path, source) == []


@pytest.mark.parametrize(
    "source",
    [
        "apples = basket.apples + 1\npears = basket.pears\n",
        "fits = 0 <= apples < limit + 1 and 0 <= pears < limit\n",
    ],
)
def test_passes_twins_that_are_not_two_axes(
    tmp_path: Path, source: str
) -> None:
    assert _report_for(tmp_path, source) == []


def test_passes_axis_names_only_in_the_targets(tmp_path: Path) -> None:
    source = "x = ones(2, 2)\ny = ones(2, 2) + 1\n"

    assert _report_for(tmp_path, source) == []


def test_passes_axis_names_only_in_the_values(tmp_path: Path) -> None:
    source = "real = self.x_values(m)\nimag = self.y_values(m + 1)\n"

    assert _report_for(tmp_path, source) == []


@pytest.mark.parametrize(
    "source",
    [
        "near = abs(a.x - b.x) <= limit\nfar = a.y - b.y <= other_limit\n",
        "wide = abs(box.x) <= limit\ntall = box.y <= limit\n",
        "dx = abs(a.x - b.x)\ndy = a.y - b.y\n",
    ],
)
def test_passes_an_abs_without_a_shared_bound_on_a_difference(
    tmp_path: Path, source: str
) -> None:
    assert _report_for(tmp_path, source) == []


@HYPOTHESIS_SETTINGS
@given(axes=st.sampled_from(_AXES), twin_line=st.sampled_from((1, 2)))
def test_twin_property_flags_only_the_line_without_the_step(
    tmp_path: Path, axes: tuple[str, str], twin_line: int
) -> None:
    plain_line = 3 - twin_line
    lines: list[str] = []

    for line_number, axis in enumerate(axes, start=1):
        step = " + 1" if line_number == twin_line else ""
        lines.append(f"{axis}_span = {axis}_last - {axis}_first{step}")

    source = "\n".join(lines) + "\n"
    plain = lines[plain_line - 1]

    expected = (
        f"shapes.py:{plain_line}: {plain} lacks the + 1 of its twin on line"
        f" {twin_line} - add the + 1 here or drop it from the twin"
    )

    report = _report_for(tmp_path, source)

    assert report == [expected]
