import os
import subprocess
from pathlib import Path

TOOLKIT = Path(__file__).resolve().parents[2]
SOURCE_CONFIGURATION = 'source_directories = ["svc/src"]\n'


def shell_function(
    project_root: Path,
    script: str,
    environment: dict[str, str],
    standard_input: str = "",
) -> subprocess.CompletedProcess[str]:
    function_environment = {
        **os.environ,
        "toolkit": str(TOOLKIT),
        "project_root": str(project_root),
        "configuration_file": str(project_root / "checks.toml"),
        "check_name": "file-length",
        "check_scope": "repository",
        "changed_files": "",
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
