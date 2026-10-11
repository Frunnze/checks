import os
import subprocess
import tempfile
from collections.abc import Sequence
from pathlib import Path

TOOLKIT = Path(__file__).resolve().parents[2]
SOURCE_CONFIGURATION = 'source_directories = ["svc/src"]\n'


def shell_function(
    project_root: Path,
    script: str,
    environment: dict[str, str],
    standard_input: str = "",
    changed_files: Sequence[str] = (),
) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory() as directory_name:
        changed_files_list = Path(directory_name) / "changed-files"
        _ = changed_files_list.write_text(
            "".join(f"{path}\n" for path in changed_files), encoding="utf-8"
        )
        function_environment = {
            **os.environ,
            "toolkit": str(TOOLKIT),
            "project_root": str(project_root),
            "configuration_file": str(project_root / "checks.toml"),
            "check_name": "file-length",
            "check_scope": "repository",
            "changed_files_list": str(changed_files_list),
            **environment,
        }

        return subprocess.run(
            ["sh", "-c", f'. "$toolkit/tools.sh"\n{script}'],
            input=standard_input,
            capture_output=True,
            text=True,
            check=False,
            env=function_environment,
        )


def printed_lines(finished: subprocess.CompletedProcess[str]) -> list[str]:
    return [line for line in finished.stdout.split("\n") if line]
