import subprocess
import sys
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_FINDER = (
    Path(__file__).resolve().parents[2] / "checks" / "experimental"
    / "constant-condition" / "python" / "constant_conditions.py"
)
_ADVICE = "- swap and/or, or use in / not in"


def _report_for(tmp_path: Path, source: str) -> list[str]:
    _ = (tmp_path / "guards.py").write_text(source, encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="guards.py",
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def test_reports_a_guard_that_always_passes(tmp_path: Path) -> None:
    source = (
        "def guard(user):\n"
        "    if user.role != 'admin' or user.role != 'owner':\n"
        "        raise PermissionError(user)\n"
    )

    assert _report_for(tmp_path, source) == [
        "guards.py:2: user.role != 'admin' or user.role != 'owner' is always"
        f" true {_ADVICE}"
    ]


def test_reports_a_test_that_never_matches(tmp_path: Path) -> None:
    source = (
        "def finished(status, code):\n"
        "    return (status == 'done' and status == 'failed') or code\n"
    )

    assert _report_for(tmp_path, source) == [
        "guards.py:2: status == 'done' and status == 'failed' is always"
        f" false {_ADVICE}"
    ]


def test_passes_membership_shapes_and_mixed_subjects(tmp_path: Path) -> None:
    source = (
        "def check(role, status, other, read):\n"
        "    allowed = role == 'admin' or role == 'owner'\n"
        "    blocked = role != 'admin' and role != 'owner'\n"
        "    pair = role == 'admin' and other == 'owner'\n"
        "    same = status != 'done' or status != 'done'\n"
        "    calls = read() == 1 and read() == 2\n"
        "    return allowed, blocked, pair, same, calls\n"
    )

    assert _report_for(tmp_path, source) == []


@HYPOTHESIS_SETTINGS
@given(
    values=st.lists(
        st.integers(min_value=-50, max_value=50),
        min_size=2,
        max_size=2,
        unique=True,
    )
)
def test_value_property_flags_any_two_values(
    tmp_path: Path, values: list[int]
) -> None:
    first, second = values
    source = (
        "def pick(level):\n"
        f"    return level != {first} or level != {second}\n"
    )

    assert _report_for(tmp_path, source) == [
        f"guards.py:2: level != {first} or level != {second} is always true"
        f" {_ADVICE}"
    ]
