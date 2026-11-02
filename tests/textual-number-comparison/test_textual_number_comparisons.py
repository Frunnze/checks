import subprocess
import sys
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_FINDER = (
    Path(__file__).resolve().parents[2] / "checks" / "experimental"
    / "textual-number-comparison" / "python"
    / "textual_number_comparisons.py"
)
_ORDER = (
    "is text, so < and > order it character by character ('10' < '9') -"
    " compare numbers or parsed versions"
)


def _report_for(tmp_path: Path, source: str) -> list[str]:
    _ = (tmp_path / "versions.py").write_text(source, encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="versions.py",
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def test_reports_a_raw_version_compared_as_text(tmp_path: Path) -> None:
    source = (
        "import sys\n"
        "import requests\n"
        "OLD = requests.__version__ < '2.10'\n"
        "NEW = sys.version >= '3.10'\n"
    )

    assert _report_for(tmp_path, source) == [
        f"versions.py:3: '2.10' {_ORDER}",
        f"versions.py:4: '3.10' {_ORDER}",
    ]


def test_reports_numbers_turned_into_text(tmp_path: Path) -> None:
    source = (
        "MAX_ID = 2**63 - 1\n"
        "def too_big(user_id, items, page):\n"
        "    if user_id > str(MAX_ID):\n        return True\n"
        "    return str(len(items)) < page or page >= str(10)\n"
    )

    assert _report_for(tmp_path, source) == [
        f"versions.py:3: str(MAX_ID) {_ORDER}",
        f"versions.py:5: str(10) {_ORDER}",
        f"versions.py:5: str(len(items)) {_ORDER}",
    ]


def test_passes_characters_versions_and_padded_text(tmp_path: Path) -> None:
    source = (
        "from packaging.version import Version\n"
        "import numpy\n"
        "def check(character, version, clock, left, right):\n"
        "    digit = '0' <= character <= '9'\n"
        "    modern = Version(numpy.__version__) >= Version('1.20')\n"
        "    morning = '0500' <= clock < '1200'\n"
        "    same = version == '1.10'\n"
        "    ordered = str(left) < str(right)\n"
        "    return digit, modern, morning, same, ordered\n"
    )

    assert _report_for(tmp_path, source) == []


@HYPOTHESIS_SETTINGS
@given(
    parts=st.lists(
        st.integers(min_value=0, max_value=99), min_size=2, max_size=4
    ),
    operator=st.sampled_from(["<", "<=", ">", ">="]),
)
def test_version_property_flags_only_the_raw_text(
    tmp_path: Path, parts: list[int], operator: str
) -> None:
    version = ".".join(str(part) for part in parts)
    source = (
        "import library\n"
        f"RAW = library.__version__ {operator} '{version}'\n"
        f"PARSED = parse(library.__version__) {operator} '{version}'\n"
    )

    assert _report_for(tmp_path, source) == [
        f"versions.py:2: '{version}' {_ORDER}"
    ]
