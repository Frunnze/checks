from pathlib import Path

from check_support import repository, run_configured, stage_file

CONFIGURATION = (
    'source_directories = ["api/src", "api/tests"]\n'
    '[checks.api-contract]\nwhen = "pre-commit"\n'
)
COVERAGE_GATED_PYTHON = (
    "#!/bin/sh\n"
    'case "$*" in\n'
    '    *"import pytest_cov"* | *--no-cov*) exit 0 ;;\n'
    "esac\n"
    'echo "FAIL Required test coverage of 90% not reached" >&2\n'
    "exit 1\n"
)


def test_passes_when_only_the_coverage_gate_of_the_package_fails(
    tmp_path: Path,
) -> None:
    repository(tmp_path)
    project_python = tmp_path / ".venv" / "bin" / "python"
    project_python.parent.mkdir(parents=True)
    _ = project_python.write_text(COVERAGE_GATED_PYTHON, encoding="utf-8")
    project_python.chmod(0o755)
    stage_file(tmp_path, "api/src/app.py", "VALUE = 1\n")
    stage_file(
        tmp_path,
        "api/tests/test_api_contract.py",
        "def test_contract() -> None:\n    pass\n",
    )

    finished = run_configured(tmp_path, CONFIGURATION, "api-contract")

    assert finished.returncode == 0, finished.stderr
