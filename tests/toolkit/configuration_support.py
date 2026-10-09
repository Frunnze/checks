import json
import subprocess
import sys
from pathlib import Path

TOOLKIT = Path(__file__).resolve().parents[2]
READER = TOOLKIT / "configuration" / "settings.py"


def written_configuration(tmp_path: Path, text: str) -> Path:
    configuration_path = tmp_path / "checks.toml"
    configuration_path.write_text(text, encoding="utf-8")

    return configuration_path


def toml_list(values: list[str]) -> str:
    return json.dumps(values)


def read_setting(
    configuration_path: Path, setting_name: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(READER), str(configuration_path), setting_name],
        capture_output=True,
        text=True,
        check=False,
    )
