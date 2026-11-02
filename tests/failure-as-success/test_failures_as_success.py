import subprocess
import sys
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_FINDER = (
    Path(__file__).resolve().parents[2] / "checks" / "experimental"
    / "failure-as-success" / "python" / "failures_as_success.py"
)
_EFFECT = "so callers believe the failed action worked - return False"


def _report_for(tmp_path: Path, source: str) -> list[str]:
    _ = (tmp_path / "mailer.py").write_text(source, encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="mailer.py",
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def _masked(line: int, function: str) -> str:
    return (
        f"mailer.py:{line}: {function}() answers True from an except,"
        f" {_EFFECT}"
    )


def test_reports_a_send_that_hides_its_failure(tmp_path: Path) -> None:
    source = (
        "import logging\n"
        "def send_receipt(smtp, order) -> bool:\n"
        "    try:\n"
        "        smtp.send(order.email, order.receipt())\n"
        "    except ConnectionError:\n"
        "        logging.warning('mail server down')\n"
        "        return True\n"
        "    return True\n"
    )

    assert _report_for(tmp_path, source) == [_masked(7, "send_receipt")]


def test_passes_honest_failures_and_recoveries(tmp_path: Path) -> None:
    source = (
        "def cancel_job(queue, job) -> bool:\n"
        "    try:\n        queue.revoke(job)\n"
        "    except TimeoutError:\n        return False\n"
        "    return True\n"
        "def remove_if_stale(lock):\n"
        "    try:\n        lock.read()\n"
        "    except ValueError:\n"
        "        lock.remove()\n"
        "        return True\n"
        "    return False\n"
        "def is_sent(log, order) -> bool:\n"
        "    try:\n        return log.has(order)\n"
        "    except KeyError:\n        return True\n"
    )

    assert _report_for(tmp_path, source) == []


@HYPOTHESIS_SETTINGS
@given(
    verb=st.sampled_from(["save", "publish", "upload", "charge", "commit"]),
    error=st.sampled_from(["OSError", "Exception", "ValueError"]),
)
def test_action_property_flags_every_action_verb(
    tmp_path: Path, verb: str, error: str
) -> None:
    source = (
        f"def {verb}_record(target, record) -> bool:\n"
        "    try:\n        target.put(record)\n"
        f"    except {error}:\n        return True\n"
        "    return True\n"
    )

    assert _report_for(tmp_path, source) == [_masked(5, f"{verb}_record")]
