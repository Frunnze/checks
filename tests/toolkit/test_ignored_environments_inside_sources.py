"""
A git-ignored virtual environment inside a source folder holds installed
packages, not project code, so no check reads it - like the ignored
vendor, dist and build folders. A tracked folder is still checked, however
it is named. Domain: svc/src with a clean main.py and a 301-line module in
svc/src/<folder>/lib/big.py, the folder .venv, venv, .tox or .hidden,
git-ignored or tracked. Oracle: postcondition - file-length passes the
ignored environment and fails the tracked folder naming the module.

Concrete inputs -> expected outputs:
- input: svc/src/.venv/lib/big.py, 301 lines, `.venv/` in .gitignore
  output: expected exit 0, got exit 1 "svc/src/.venv/lib/big.py (301
  lines)" - the file listing walked every ignored folder except the
  vendor, dist and build ones.
- input: svc/src/.hidden/lib/big.py, 301 lines, tracked
  output: exit 1 naming svc/src/.hidden/lib/big.py (301 lines).
"""

from pathlib import Path

import pytest

from check_support import repository, run_configured, stage_file

CONFIGURATION = 'source_directories = ["svc/src"]\n'
OVERLONG = "VALUE = 1\n" * 301
IGNORED_FOLDERS = (".venv", "venv", ".tox")


@pytest.mark.parametrize("folder", IGNORED_FOLDERS)
def test_file_length_skips_an_ignored_environment(
    tmp_path: Path, folder: str
) -> None:
    repository(tmp_path)
    ignore_file = tmp_path / ".gitignore"
    ignored = ignore_file.read_text(encoding="utf-8") + f"{folder}/\n"
    _ = ignore_file.write_text(ignored, encoding="utf-8")
    stage_file(tmp_path, "svc/src/main.py", "VALUE = 1\n")
    module = tmp_path / "svc" / "src" / folder / "lib" / "big.py"
    module.parent.mkdir(parents=True)
    _ = module.write_text(OVERLONG, encoding="utf-8")

    finished = run_configured(tmp_path, CONFIGURATION, "file-length")

    assert finished.returncode == 0, finished.stderr


def test_file_length_checks_a_tracked_hidden_folder(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "svc/src/main.py", "VALUE = 1\n")
    stage_file(tmp_path, "svc/src/.hidden/lib/big.py", OVERLONG)

    finished = run_configured(tmp_path, CONFIGURATION, "file-length")

    assert finished.returncode == 1
    assert "svc/src/.hidden/lib/big.py (301 lines)" in finished.stderr
