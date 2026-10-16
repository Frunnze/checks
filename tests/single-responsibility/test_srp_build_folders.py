"""
single-responsibility reads every file under a listed source folder,
whatever its subfolder is called, like the other checks
(test_build_folders_inside_sources); only a git-ignored build or dist
folder is generated output and skipped. Domain: a unit reaching network
and filesystem in user-service/src/<subfolder>/worker.py, the subfolder
tools, build, dist or app/build, tracked or git-ignored. Oracle:
postcondition - a tracked worker fails the gate and is named, an ignored
one is not read.

Concrete inputs -> expected outputs:
- input: user-service/src/tools/worker.py:
      import httpx
      from pathlib import Path
      def sync(url, path):
          Path(path).write_text(httpx.get(url).text)
  output: exit 1 naming worker.py.
- input (falsifying example, pinned as @example): the same file in
  user-service/src/build/
  output: expected exit 1, got exit 0 - the walker skipped every folder
  named build or dist.
- input: the same file in a build/ folder that .gitignore lists
  output: exit 0.
"""

from pathlib import Path

from check_support import HYPOTHESIS_SETTINGS, repository, run_check, stage_file
from hypothesis import example, given
from hypothesis import strategies as st

WORKER = (
    "import httpx\nfrom pathlib import Path\n\n\n"
    "def sync(url, path):\n    Path(path).write_text(httpx.get(url).text)\n"
)
SUBFOLDERS = ("tools", "build", "dist", "app/build")


@given(subfolder=st.sampled_from(SUBFOLDERS))
@example(subfolder="build")
@HYPOTHESIS_SETTINGS
def test_gate_property_reads_a_tracked_build_folder(
    tmp_path_factory, subfolder: str
) -> None:
    project = tmp_path_factory.mktemp("project")
    repository(project)
    stage_file(project, "user-service/src/main.py", "VALUE = 1\n")
    stage_file(project, f"user-service/src/{subfolder}/worker.py", WORKER)

    finished = run_check(project, "single-responsibility")

    assert finished.returncode == 1, finished.stdout + finished.stderr
    assert "worker.py" in finished.stdout + finished.stderr


def test_gate_skips_a_git_ignored_build_folder(tmp_path: Path) -> None:
    repository(tmp_path)
    ignore_file = tmp_path / ".gitignore"
    ignored = ignore_file.read_text(encoding="utf-8") + "build/\n"
    _ = ignore_file.write_text(ignored, encoding="utf-8")
    stage_file(tmp_path, "user-service/src/main.py", "VALUE = 1\n")
    worker = tmp_path / "user-service" / "src" / "build" / "worker.py"
    worker.parent.mkdir(parents=True)
    _ = worker.write_text(WORKER, encoding="utf-8")

    finished = run_check(tmp_path, "single-responsibility")

    assert finished.returncode == 0, finished.stdout + finished.stderr
