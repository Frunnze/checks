"""
The Python coverage gate measures every module under a source folder,
including folders without an __init__.py - coverage.py only reports a
never-imported module in an importable folder. Domain: svc/src/calc.py
covered by svc/tests, plus a never-imported 4-statement module in a
subfolder without __init__.py at depth one or two. Oracle: postcondition -
the README promises "every line and branch tested", so the gate fails and
names the untested module; with no untested module it passes.

Concrete inputs -> expected outputs:
- input: svc/src/calc.py (tested), svc/src/helpers/untested.py:
      def never_tested(flag):
          if flag:
              return 1
          return 2
  output: expected exit 1 naming src/helpers/untested.py, got exit 0 and
  "Required test coverage of 100% reached".
- input: svc/src/calc.py (tested) alone
  output: exit 0.
"""

from pathlib import Path

import pytest

from check_support import TOOLKIT, repository, run_configured, stage_file

CONFIGURATION = 'source_directories = ["svc/src", "svc/tests"]\n'
PYTEST_SETTINGS = '[tool.pytest.ini_options]\npythonpath = ["."]\n'
UNTESTED = (
    "def never_tested(flag):\n    if flag:\n        return 1\n    return 2\n"
)


def _covered_package(tmp_path: Path) -> None:
    repository(tmp_path)
    (tmp_path / ".venv").symlink_to(TOOLKIT / ".venv")
    stage_file(tmp_path, "svc/pyproject.toml", PYTEST_SETTINGS)
    stage_file(
        tmp_path, "svc/src/calc.py", "def add(a, b):\n    return a + b\n"
    )
    stage_file(
        tmp_path,
        "svc/tests/test_calc.py",
        "from src.calc import add\n\n\ndef test_add():\n"
        "    assert add(1, 2) == 3\n",
    )


@pytest.mark.parametrize("folder", ["helpers", "helpers/deep"])
def test_fails_on_an_untested_module_in_a_folder_without_init(
    tmp_path: Path, folder: str
) -> None:
    _covered_package(tmp_path)
    stage_file(tmp_path, f"svc/src/{folder}/untested.py", UNTESTED)

    finished = run_configured(tmp_path, CONFIGURATION, "coverage")

    assert finished.returncode == 1, finished.stdout + finished.stderr
    assert f"src/{folder}/untested.py" in finished.stdout


def test_passes_a_fully_tested_package(tmp_path: Path) -> None:
    _covered_package(tmp_path)

    finished = run_configured(tmp_path, CONFIGURATION, "coverage")

    assert finished.returncode == 0, finished.stdout + finished.stderr
