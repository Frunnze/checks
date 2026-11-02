import subprocess
import sys
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_FINDER = (
    Path(__file__).resolve().parents[2] / "checks" / "experimental"
    / "mass-assignment" / "python" / "mass_assignments.py"
)
_ADVICE = "so the caller picks which fields change - allow a fixed set"


def _report_for(tmp_path: Path, source: str) -> list[str]:
    _ = (tmp_path / "accounts.py").write_text(source, encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="accounts.py",
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def test_reports_every_key_copied_onto_a_record(tmp_path: Path) -> None:
    source = (
        "def update_account(account, changes):\n"
        "    for field, value in changes.items():\n"
        "        setattr(account, field, value)\n"
        "    return account\n"
    )

    assert _report_for(tmp_path, source) == [
        f"accounts.py:2: every key of changes is set on account, {_ADVICE}"
    ]


def test_passes_allowlists_and_own_options(tmp_path: Path) -> None:
    source = (
        "EDITABLE = {'name', 'email'}\n"
        "class Options:\n"
        "    def __init__(self, settings):\n"
        "        for name, value in settings.items():\n"
        "            setattr(self, name, value)\n"
        "def update_account(account, changes, model):\n"
        "    for field, value in changes.items():\n"
        "        if field not in EDITABLE:\n            continue\n"
        "        setattr(account, field, value)\n"
        "    for field, value in model.model_dump().items():\n"
        "        setattr(account, field, value)\n"
        "    return account\n"
    )

    assert _report_for(tmp_path, source) == []


@HYPOTHESIS_SETTINGS
@given(
    names=st.lists(
        st.from_regex(r"[a-z]{3,8}", fullmatch=True),
        min_size=4,
        max_size=4,
        unique=True,
    )
)
def test_copy_property_flags_any_spelling(
    tmp_path: Path, names: list[str]
) -> None:
    target, source_name, key, value = names
    source = (
        f"def apply({target}, {source_name}):\n"
        f"    for {key}, {value} in {source_name}.items():\n"
        f"        setattr({target}, {key}, {value})\n"
    )

    assert _report_for(tmp_path, source) == [
        f"accounts.py:2: every key of {source_name} is set on {target},"
        f" {_ADVICE}"
    ]
