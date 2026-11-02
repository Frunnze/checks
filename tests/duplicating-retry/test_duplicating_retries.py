import subprocess
import sys
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_FINDER = (
    Path(__file__).resolve().parents[2] / "checks" / "experimental"
    / "duplicating-retry" / "python" / "duplicating_retries.py"
)
_REPEAT = (
    "it may already have run, so the retry repeats it - send an idempotency"
    " key or do not retry timeouts"
)


def _report_for(tmp_path: Path, source: str) -> list[str]:
    _ = (tmp_path / "payments.py").write_text(source, encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="payments.py",
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def _retried(line: int, call: str) -> str:
    return (
        f"payments.py:{line}: {call}() is retried after a timeout, but"
        f" {_REPEAT}"
    )


def test_reports_a_charge_retried_after_a_timeout(tmp_path: Path) -> None:
    source = (
        "import time\n"
        "def charge(client, card):\n"
        "    for attempt in range(3):\n"
        "        try:\n"
        "            return client.charges.create(card=card)\n"
        "        except TimeoutError:\n"
        "            time.sleep(attempt)\n"
        "    raise RuntimeError(card)\n"
    )

    assert _report_for(tmp_path, source) == [
        _retried(5, "client.charges.create")
    ]


def test_reports_a_catch_all_around_a_send(tmp_path: Path) -> None:
    source = (
        "def notify(mailer, message):\n"
        "    while True:\n"
        "        try:\n"
        "            mailer.send(message)\n"
        "            break\n"
        "        except Exception:\n"
        "            continue\n"
    )

    assert _report_for(tmp_path, source) == [_retried(4, "mailer.send")]


def test_passes_safe_retries_and_processing_loops(tmp_path: Path) -> None:
    source = (
        "def charge(client, card, key, url, http, queue):\n"
        "    for attempt in range(3):\n"
        "        try:\n"
        "            return client.charges.create(card=card,"
        " idempotency_key=key)\n"
        "        except TimeoutError:\n"
        "            continue\n"
        "    for attempt in range(3):\n"
        "        try:\n"
        "            return http.get(url)\n"
        "        except TimeoutError:\n"
        "            continue\n"
        "    for job in queue:\n"
        "        try:\n"
        "            client.send(job)\n"
        "        except Exception:\n"
        "            continue\n"
        "    for attempt in range(3):\n"
        "        try:\n"
        "            return client.send(card)\n"
        "        except TimeoutError:\n"
        "            raise\n"
    )

    assert _report_for(tmp_path, source) == []


@HYPOTHESIS_SETTINGS
@given(
    method=st.sampled_from(["post", "create", "publish", "apply_async"]),
    error=st.sampled_from(
        ["TimeoutError", "ReadTimeout", "Exception", "httpx.TimeoutException"]
    ),
)
def test_retry_property_flags_every_write_and_timeout(
    tmp_path: Path, method: str, error: str
) -> None:
    source = (
        "def write(target, record):\n"
        "    for _ in range(5):\n"
        "        try:\n"
        f"            return target.{method}(record)\n"
        f"        except {error}:\n"
        "            pass\n"
    )

    assert _report_for(tmp_path, source) == [_retried(4, f"target.{method}")]
