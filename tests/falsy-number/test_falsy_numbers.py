import subprocess
import sys
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_FINDER = (
    Path(__file__).resolve().parents[2] / "checks" / "experimental"
    / "falsy-number" / "python" / "falsy_numbers.py"
)


def _report_for(tmp_path: Path, source: str) -> list[str]:
    _ = (tmp_path / "nearest.py").write_text(source, encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="nearest.py",
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def _falsy(line: int, test: str, subject: str) -> str:
    return (
        f"nearest.py:{line}: `{test}` treats 0 like None but {subject} is"
        " compared as a number beside it"
    )


def test_reports_a_best_so_far_that_can_be_zero(tmp_path: Path) -> None:
    source = (
        "def nearest(points, target):\n"
        "    best: float | None = None\n"
        "    for point in points:\n"
        "        gap = abs(point - target)\n"
        "        if not best or gap < best:\n"
        "            best = gap\n"
        "    return best\n"
    )

    assert _report_for(tmp_path, source) == [_falsy(5, "not best", "best")]


def test_reports_parameters_and_attributes(tmp_path: Path) -> None:
    source = (
        "from typing import Optional\n"
        "class Quota:\n"
        "    remaining: int | None = None\n"
        "    def low(self, limit: Optional[int]):\n"
        "        low = not self.remaining or self.remaining < 5\n"
        "        return low, not limit or limit > 100\n"
    )

    assert _report_for(tmp_path, source) == [
        _falsy(5, "not self.remaining", "self.remaining"),
        _falsy(6, "not limit", "limit"),
    ]


def test_passes_none_checks_and_plain_fallbacks(tmp_path: Path) -> None:
    source = (
        "import datetime\n"
        "def pick(best: float | None, ttl: int | None, count: int,\n"
        "         last: datetime.datetime | None, now, limit: int | None):\n"
        "    if best is None or best > 1:\n        best = 1\n"
        "    timeout = ttl or 30\n"
        "    many = not count or count > 10\n"
        "    stale = not last or last < now\n"
        "    full = limit and count >= limit\n"
        "    return best, timeout, many, stale, full\n"
    )

    assert _report_for(tmp_path, source) == []


@HYPOTHESIS_SETTINGS
@given(
    operator=st.sampled_from(["<", "<=", ">", ">="]),
    annotation=st.sampled_from(
        ["int | None", "float | None", "None | int", "Optional[float]"]
    ),
)
def test_none_property_flags_every_ordering(
    tmp_path: Path, operator: str, annotation: str
) -> None:
    source = (
        "from typing import Optional\n"
        f"def better(best: {annotation}, value: int):\n"
        f"    return not best or value {operator} best\n"
    )

    assert _report_for(tmp_path, source) == [_falsy(3, "not best", "best")]
