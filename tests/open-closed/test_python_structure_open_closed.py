import subprocess
import sys
from pathlib import Path

from typescript_finder_support import CHECKS

_FINDER = CHECKS / "experimental" / "open-closed" / "python" / "variant_dispatches.py"


def report_from(tmp_path: Path, files: dict[str, str]) -> list[str]:
    paths: list[str] = []

    for relative, source in files.items():
        module = tmp_path / relative
        module.parent.mkdir(parents=True, exist_ok=True)
        _ = module.write_text(source, encoding="utf-8")
        paths.append(relative)

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="\n".join(paths),
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def test_flags_behavior_split_across_python_registries(
    tmp_path: Path,
) -> None:
    files = {
        "src/policy.py": (
            "from typing import Literal\n"
            "Channel = Literal['email', 'sms', 'push']\n"
            "ENDPOINTS: dict[Channel, str] = {\n"
            "    'email': '/email', 'sms': '/sms', 'push': '/push'\n"
            "}\n"
            "LABELS: dict[Channel, str] = {\n"
            "    'email': 'Email', 'sms': 'SMS', 'push': 'Push'\n"
            "}\n"
        )
    }

    assert report_from(tmp_path, files) == [
        (
            "src/policy.py:3: Channel behavior is split across 2 "
            "registries in 1 file: ENDPOINTS, LABELS"
        )
    ]


def test_does_not_merge_unrelated_python_registry_domains(
    tmp_path: Path,
) -> None:
    files = {
        "src/policy.py": (
            "FIRST = {'email': 1, 'sms': 2, 'push': 3}\n"
            "SECOND = {'small': 1, 'medium': 2, 'large': 3}\n"
        )
    }

    assert report_from(tmp_path, files) == []
