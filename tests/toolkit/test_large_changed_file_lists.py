"""
A hook must judge the code, not trip over how many files changed. Domain:
a repository whose only source folder holds one clean module, plus a
generated number of tracked assets outside it, on a branch with no
upstream yet - so pre-push counts every tracked file as changed. Oracle:
postcondition - nothing breaks a rule, so the pre-push run passes whatever
the size of the changed-file list.

Concrete inputs -> expected outputs:
- input: svc/src/main.py = "VALUE = 1", 10 tracked assets,
  run --stage pre-push file-length
  output: exit 0.
- input (falsifying example, pinned as @example): the same repository with
  1,120 tracked assets/00000-xxx...x.png (118 bytes a line, 132,187 bytes
  of tracked paths, just over the 131,072 bytes Linux allows one
  environment variable)
  output: expected exit 0, got 126 with "paste: Argument list too long"
  before any check ran - every push of a new branch, and every commit of
  that many staged files, was blocked.
"""

import subprocess
import tempfile
from pathlib import Path

from hypothesis import example, given, settings
from hypothesis import strategies as st

from check_support import COPIED_TOOLKIT, repository, stage_file

CONFIGURATION = 'source_directories = ["svc/src"]\n'
ASSET_STEM = "x" * 100
ASSETS_OVER_THE_LIMIT = 1_120


def _add_assets(project: Path, count: int) -> None:
    assets = project / "assets"
    assets.mkdir()

    for index in range(count):
        asset = assets / f"{index:05d}-{ASSET_STEM}.png"
        _ = asset.write_text("x", encoding="utf-8")


def _commit_everything(project: Path) -> None:
    for command in (
        ["git", "add", "-A"],
        ["git", "commit", "--quiet", "-m", "seed"],
    ):
        _ = subprocess.run(command, cwd=project, check=True)


def _run_pre_push(project: Path) -> subprocess.CompletedProcess[str]:
    _ = (project / "checks.toml").write_text(CONFIGURATION, encoding="utf-8")

    return subprocess.run(
        ["sh", f"{COPIED_TOOLKIT}/run", "--stage", "pre-push", "file-length"],
        cwd=project,
        capture_output=True,
        text=True,
        check=False,
    )


@given(count=st.integers(min_value=0, max_value=ASSETS_OVER_THE_LIMIT))
@example(count=ASSETS_OVER_THE_LIMIT)
@settings(max_examples=3, deadline=None)
def test_pre_push_property_passes_a_clean_branch_of_any_size(
    count: int,
) -> None:
    with tempfile.TemporaryDirectory() as directory:
        project = Path(directory)
        repository(project)
        stage_file(project, "svc/src/main.py", "VALUE = 1\n")
        _add_assets(project, count)
        _commit_everything(project)
        finished = _run_pre_push(project)

    assert finished.returncode == 0, finished.stderr
