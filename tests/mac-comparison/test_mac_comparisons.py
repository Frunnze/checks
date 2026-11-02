import subprocess
import sys
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_FINDER = (
    Path(__file__).resolve().parents[2] / "checks" / "experimental"
    / "mac-comparison" / "python" / "mac_comparisons.py"
)
_ADVICE = "which leaks how much matched - use hmac.compare_digest()"


def _report_for(tmp_path: Path, source: str) -> list[str]:
    _ = (tmp_path / "webhook.py").write_text(source, encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="webhook.py",
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def _compared(line: int, mac: str) -> str:
    return f"webhook.py:{line}: {mac} is an HMAC compared with ==, {_ADVICE}"


def test_reports_a_mac_compared_directly(tmp_path: Path) -> None:
    source = (
        "import hashlib\n"
        "import hmac\n"
        "def valid(key, body, received):\n"
        "    return hmac.new(key, body, hashlib.sha256).hexdigest()"
        " == received\n"
    )

    assert _report_for(tmp_path, source) == [
        _compared(4, "hmac.new(key, body, hashlib.sha256).hexdigest()")
    ]


def test_reports_a_mac_kept_in_names(tmp_path: Path) -> None:
    source = (
        "import hmac as macs\n"
        "def valid(key, body, received):\n"
        "    signer = macs.new(key, body, 'sha256')\n"
        "    expected = signer.digest()\n"
        "    quick = macs.digest(key, body, 'sha256')\n"
        "    return received != expected or quick == received\n"
    )

    assert _report_for(tmp_path, source) == [
        _compared(6, "expected"),
        _compared(6, "quick"),
    ]


def test_passes_constant_time_checks_and_plain_hashes(tmp_path: Path) -> None:
    source = (
        "import hashlib\n"
        "import hmac\n"
        "def valid(key, body, received, path):\n"
        "    expected = hmac.new(key, body, 'sha256').hexdigest()\n"
        "    checksum = hashlib.sha256(body).hexdigest()\n"
        "    same_file = checksum == path\n"
        "    return hmac.compare_digest(expected, received), same_file\n"
    )

    assert _report_for(tmp_path, source) == []


@HYPOTHESIS_SETTINGS
@given(
    method=st.sampled_from(["digest", "hexdigest"]),
    operator=st.sampled_from(["==", "!="]),
)
def test_mac_property_flags_every_equality(
    tmp_path: Path, method: str, operator: str
) -> None:
    source = (
        "import hmac\n"
        "def check(key, body, received):\n"
        f"    mac = hmac.new(key, body, 'sha256').{method}()\n"
        f"    return mac {operator} received\n"
    )

    assert _report_for(tmp_path, source) == [_compared(4, "mac")]
