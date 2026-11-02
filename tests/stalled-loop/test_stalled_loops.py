import subprocess
import sys
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_FINDER = (
    Path(__file__).resolve().parents[2] / "checks" / "experimental"
    / "stalled-loop" / "python" / "stalled_loops.py"
)


def _report_for(tmp_path: Path, source: str) -> list[str]:
    _ = (tmp_path / "pages.py").write_text(source, encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="pages.py",
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def _stalled(line: int, loop_line: int) -> str:
    return (
        f"pages.py:{line}: this path returns to the loop test on line"
        f" {loop_line} without changing anything the test reads"
    )


def test_reports_a_continue_before_the_offset_moves(tmp_path: Path) -> None:
    source = (
        "def pages(rows, total):\n"
        "    offset = 0\n"
        "    found = []\n"
        "    while offset < total:\n"
        "        page = rows[offset]\n"
        "        if not page:\n            continue\n"
        "        found.append(page)\n"
        "        offset += 10\n"
        "    return found\n"
    )

    assert _report_for(tmp_path, source) == [_stalled(7, 4)]


def test_reports_a_body_that_never_moves(tmp_path: Path) -> None:
    source = (
        "def names(items):\n"
        "    index = 0\n"
        "    while index < len(items):\n"
        "        name = items[index].lower()\n"
        "    return index\n"
    )

    assert _report_for(tmp_path, source) == [_stalled(4, 3)]


def test_passes_loops_that_always_move(tmp_path: Path) -> None:
    source = (
        "def drain(queue, poll, items):\n"
        "    total = 0\n"
        "    while queue:\n"
        "        total += queue.pop()\n"
        "    attempts = 0\n"
        "    while attempts < 5:\n"
        "        if poll():\n            break\n"
        "        attempts += 1\n"
        "    index = 0\n"
        "    while index < len(items):\n"
        "        index += 1\n"
        "        if not items[index - 1]:\n            continue\n"
        "        total += 1\n"
        "    while True:\n"
        "        if poll():\n            return total\n"
        "    left, right = 0, len(items)\n"
        "    while left < right:\n"
        "        if items[left]:\n            left += 1\n"
        "        if not items[left]:\n            right -= 1\n"
        "    return total\n"
    )

    assert _report_for(tmp_path, source) == []


@HYPOTHESIS_SETTINGS
@given(
    step=st.sampled_from(["cursor += 1", "cursor = cursor + 2", "cursor -= 1"])
)
def test_progress_property_flags_only_the_path_that_skips_it(
    tmp_path: Path, step: str
) -> None:
    source = (
        "def walk(rows, limit):\n"
        "    cursor = 0\n"
        "    while cursor < limit:\n"
        "        if rows[cursor] is None:\n"
        "            continue\n"
        f"        {step}\n"
        "    return cursor\n"
    )

    assert _report_for(tmp_path, source) == [_stalled(5, 3)]
