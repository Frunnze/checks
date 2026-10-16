"""
The pre-push hook judges the checked-out branch, so it must refuse to push
commits that branch does not hold - otherwise they leave unchecked. Domain:
a project in sync with its remote on main and a feature branch whose one
commit adds a 301-line module, file-length at pre-push; pushed from main
by name or with --all, or with feature checked out. Oracle: postcondition
- the push fails and the module never reaches the remote.

Concrete inputs -> expected outputs:
- input: on main, `git push origin feature`
  output: expected the push refused, got exit 0 and svc/src/long.py on the
  remote - the checks diffed @{upstream}...HEAD of main and found nothing.
- input: on main, `git push --all origin`
  output: refused, the same way.
- input: on feature, `git push origin feature`
  output: refused by file-length naming svc/src/long.py (301 lines).
"""

import shutil
import subprocess
from pathlib import Path

import pytest

from check_support import COPIED_TOOLKIT, TOOLKIT, repository, stage_file

CONFIGURATION = (
    'source_directories = ["svc/src"]\n'
    'stable = "off"\n'
    "[checks.file-length]\n"
    'when = "pre-push"\n'
)
OVERLONG = "VALUE = 1\n" * 301
GitRun = subprocess.CompletedProcess[str]


def _git(folder: Path, *arguments: str) -> GitRun:
    return subprocess.run(
        ["git", *arguments],
        cwd=folder,
        capture_output=True,
        text=True,
        check=False,
    )


def _project_with_feature(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    project.mkdir()
    repository(project)
    _ = shutil.copytree(
        TOOLKIT / "hooks", project / COPIED_TOOLKIT / "hooks"
    )
    _ = (project / "checks.toml").write_text(CONFIGURATION, encoding="utf-8")
    remote = tmp_path / "remote.git"
    _ = _git(tmp_path, "init", "--quiet", "--bare", str(remote))
    _ = _git(project, "checkout", "-q", "-b", "main")
    stage_file(project, "svc/src/ok.py", "VALUE = 1\n")
    _ = _git(project, "commit", "-q", "-m", "seed")
    _ = _git(project, "remote", "add", "origin", str(remote))
    _ = _git(project, "config", "core.hooksPath", f"{COPIED_TOOLKIT}/hooks")
    assert _git(project, "push", "-q", "-u", "origin", "main").returncode == 0
    _ = _git(project, "checkout", "-q", "-b", "feature")
    stage_file(project, "svc/src/long.py", OVERLONG)
    _ = _git(project, "commit", "-q", "-m", "long module")
    _ = _git(project, "checkout", "-q", "main")

    return project


@pytest.mark.parametrize(
    "push",
    [["push", "origin", "feature"], ["push", "--all", "origin"]],
)
def test_refuses_to_push_a_branch_that_is_not_checked_out(
    tmp_path: Path, push: list[str]
) -> None:
    project = _project_with_feature(tmp_path)

    pushed = _git(project, *push)
    remote_feature = _git(
        tmp_path / "remote.git", "rev-parse", "--verify", "--quiet", "feature"
    )

    assert pushed.returncode != 0, pushed.stderr
    assert "refs/heads/feature is not the checked-out branch" in pushed.stderr
    assert remote_feature.returncode != 0


def test_checks_the_pushed_branch_when_it_is_checked_out(
    tmp_path: Path,
) -> None:
    project = _project_with_feature(tmp_path)
    _ = _git(project, "checkout", "-q", "feature")

    pushed = _git(project, "push", "origin", "feature")

    assert pushed.returncode != 0
    assert "svc/src/long.py (301 lines)" in pushed.stderr
