import subprocess
import sys
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_FINDER = (
    Path(__file__).resolve().parents[2] / "checks" / "experimental"
    / "float-drift" / "python" / "float_drift.py"
)


def _report_for(tmp_path: Path, source: str) -> list[str]:
    _ = (tmp_path / "wallet.py").write_text(source, encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="wallet.py",
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def _drift(line: int, total: str, step: str, compared: int) -> str:
    return (
        f"wallet.py:{line}: {total} steps by {step}, which a binary float"
        f" cannot hold exactly, and is compared on line {compared}"
    )


def test_reports_credits_spent_in_tenths(tmp_path: Path) -> None:
    source = (
        "PRICE = 0.1\n"
        "class Wallet:\n"
        "    def __init__(self, credits):\n"
        "        self.credits = credits * PRICE\n"
        "    def spend(self):\n"
        "        if self.credits <= 0:\n            return False\n"
        "        self.credits -= PRICE\n"
        "        return True\n"
    )

    assert _report_for(tmp_path, source) == [
        _drift(8, "self.credits", "PRICE", 6)
    ]


def test_reports_a_local_total_compared_for_equality(tmp_path: Path) -> None:
    source = (
        "def fill(level):\n"
        "    while level != 1.0:\n"
        "        level += 0.2\n"
        "    return level\n"
    )

    assert _report_for(tmp_path, source) == [_drift(3, "level", "0.2", 2)]


def test_passes_exact_steps_and_uncompared_totals(tmp_path: Path) -> None:
    source = (
        "def fill(level, cents, ratio):\n"
        "    while level < 1.0:\n"
        "        level += 0.25\n"
        "    while cents < 100:\n"
        "        cents += 10\n"
        "    ratio += 0.1\n"
        "    return level, cents, ratio\n"
    )

    assert _report_for(tmp_path, source) == []


@HYPOTHESIS_SETTINGS
@given(
    step=st.sampled_from(["0.1", "0.2", "0.3", "0.7", "1.1", "2.05"]),
    exact=st.sampled_from(["0.5", "0.25", "0.125", "1.5", "2.0"]),
)
def test_step_property_flags_only_inexact_steps(
    tmp_path: Path, step: str, exact: str
) -> None:
    source = (
        "def walk(drifting, steady):\n"
        f"    drifting -= {step}\n"
        f"    steady -= {exact}\n"
        "    return drifting <= 0 or steady <= 0\n"
    )

    assert _report_for(tmp_path, source) == [_drift(2, "drifting", step, 4)]
