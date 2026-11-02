import subprocess
import sys
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_FINDER = (
    Path(__file__).resolve().parents[2] / "checks" / "experimental"
    / "lost-fraction" / "python" / "lost_fractions.py"
)


def _report_for(tmp_path: Path, source: str) -> list[str]:
    _ = (tmp_path / "ratios.py").write_text(source, encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="ratios.py",
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def _lost(line: int, whole: str, fraction: str) -> str:
    return (
        f"ratios.py:{line}: {whole} has lost its fraction but is compared"
        f" with {fraction}"
    )


def test_reports_a_floor_ratio_against_a_fraction(tmp_path: Path) -> None:
    source = (
        "WIDE = 1.5\n"
        "def shape(width, height):\n"
        "    ratio = width // height\n"
        "    if ratio > WIDE:\n        return 'wide'\n"
        "    return 'tall' if ratio < 0.7 else 'square'\n"
    )

    assert _report_for(tmp_path, source) == [
        _lost(4, "ratio", "WIDE"),
        _lost(6, "ratio", "0.7"),
    ]


def test_reports_int_of_a_division(tmp_path: Path) -> None:
    source = (
        "import math\n"
        "def busy(used, total):\n"
        "    return int(used / total) >= 0.9 or math.floor(used / 2) > 2.5\n"
    )

    assert _report_for(tmp_path, source) == [
        _lost(3, "int(used / total)", "0.9"),
        _lost(3, "math.floor(used / 2)", "2.5"),
    ]


def test_passes_true_division_and_whole_thresholds(tmp_path: Path) -> None:
    source = (
        "def shape(width, height, items):\n"
        "    ratio = width / height\n"
        "    pages = len(items) // 10\n"
        "    return ratio > 1.5, pages > 2, pages >= 3.0, int(ratio) > 1\n"
    )

    assert _report_for(tmp_path, source) == []


@HYPOTHESIS_SETTINGS
@given(
    whole=st.integers(min_value=0, max_value=100),
    tenths=st.integers(min_value=1, max_value=9),
)
def test_fraction_property_flags_only_fractional_thresholds(
    tmp_path: Path, whole: int, tenths: int
) -> None:
    source = (
        "def compare(total, count):\n"
        "    share = total // count\n"
        f"    return share > {whole}.{tenths}, share > {whole}\n"
    )

    assert _report_for(tmp_path, source) == [
        _lost(3, "share", f"{whole}.{tenths}")
    ]
