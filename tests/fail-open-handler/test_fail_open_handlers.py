import subprocess
import sys
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_FINDER = (
    Path(__file__).resolve().parents[2] / "checks" / "experimental"
    / "fail-open-handler" / "python" / "fail_open_handlers.py"
)
_THROUGH = "when it fails, so an error lets the request through"


def _report_for(tmp_path: Path, source: str) -> list[str]:
    _ = (tmp_path / "gate.py").write_text(source, encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="gate.py",
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def _open(line: int, function: str, answer: bool) -> str:
    return (
        f"gate.py:{line}: {function}() answers {answer} {_THROUGH} -"
        f" return {not answer}"
    )


def test_reports_a_grant_on_error(tmp_path: Path) -> None:
    source = (
        "def has_permission(user, action) -> bool:\n"
        "    try:\n"
        "        return user.policy.allows(action)\n"
        "    except TimeoutError:\n"
        "        return True\n"
    )

    assert _report_for(tmp_path, source) == [
        _open(5, "has_permission", answer=True)
    ]


def test_reports_a_limit_lifted_on_error(tmp_path: Path) -> None:
    source = (
        "class Limits:\n"
        "    def isRateLimited(self, client):\n"
        "        try:\n"
        "            return self.counter.over(client)\n"
        "        except ConnectionError:\n"
        "            return False\n"
    )

    assert _report_for(tmp_path, source) == [
        _open(6, "isRateLimited", answer=False)
    ]


def test_passes_checks_that_fail_closed(tmp_path: Path) -> None:
    source = (
        "def is_valid(token) -> bool:\n"
        "    try:\n        decode(token)\n"
        "    except ValueError:\n        return False\n"
        "    return True\n"
        "def is_expired(token):\n"
        "    try:\n        return past(token)\n"
        "    except ValueError:\n        return True\n"
        "def load(path):\n"
        "    try:\n        return read(path)\n"
        "    except OSError:\n        return True\n"
    )

    assert _report_for(tmp_path, source) == []


@HYPOTHESIS_SETTINGS
@given(
    word=st.sampled_from(
        ["allowed", "authorized", "permitted", "trusted", "valid"]
    ),
    error=st.sampled_from(["Exception", "OSError", "KeyError"]),
)
def test_grant_property_flags_only_the_permissive_answer(
    tmp_path: Path, word: str, error: str
) -> None:
    source = (
        f"def is_{word}(item) -> bool:\n"
        "    try:\n        return check(item)\n"
        f"    except {error}:\n        return True\n"
        f"def was_{word}(item) -> bool:\n"
        "    try:\n        return check(item)\n"
        f"    except {error}:\n        return False\n"
    )

    assert _report_for(tmp_path, source) == [
        _open(5, f"is_{word}", answer=True)
    ]
