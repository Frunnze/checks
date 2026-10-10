import os
import shutil
import subprocess
import sys
from pathlib import Path

TOOLKIT = Path(__file__).resolve().parents[2]
TOOLKIT_FOLDER = ".checks"
TOOLKIT_FILES = ("install.sh", "run", "tools.sh")
TOOLKIT_FOLDERS = ("checks", "configuration", "hooks")
CONFIGURATION = (
    'source_directories = ["svc/src"]\n'
    'stable = "off"\n'
    "[checks.file-length]\n"
    'when = "pre-commit"\n'
    "max-lines = 3\n"
)
SUCCEEDING_STUB = "#!/bin/sh\nexit 0\n"


def _stub(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(SUCCEEDING_STUB, encoding="utf-8")
    path.chmod(0o755)


def _git(project: Path, *arguments: str) -> None:
    _ = subprocess.run(
        ["git", *arguments], cwd=project, check=True, capture_output=True
    )


def _project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    toolkit = project / TOOLKIT_FOLDER
    toolkit.mkdir(parents=True)

    for file_name in TOOLKIT_FILES:
        _ = shutil.copy2(TOOLKIT / file_name, toolkit / file_name)

    for folder_name in TOOLKIT_FOLDERS:
        _ = shutil.copytree(
            TOOLKIT / folder_name,
            toolkit / folder_name,
            ignore=shutil.ignore_patterns("__pycache__"),
        )

    python_link = toolkit / ".venv" / "bin" / "python"
    python_link.parent.mkdir(parents=True)
    python_link.symlink_to(Path(sys.executable))
    _stub(toolkit / ".venv" / "bin" / "pip")
    _git(project, "init", "--quiet")
    _git(project, "config", "user.email", "hooks@example.com")
    _git(project, "config", "user.name", "hooks")

    return project


def _install(tmp_path: Path, project: Path) -> None:
    shims = tmp_path / "shims"
    _stub(shims / "npm")
    environment = {**os.environ, "PATH": f"{shims}:{os.environ['PATH']}"}

    _ = subprocess.run(
        ["sh", f"{TOOLKIT_FOLDER}/install.sh"],
        cwd=project,
        check=True,
        capture_output=True,
        env=environment,
    )


def test_install_keeps_a_last_ignore_line_without_a_newline(
    tmp_path: Path,
) -> None:
    project = _project(tmp_path)
    _ = (project / ".gitignore").write_text("node_modules", encoding="utf-8")

    _install(tmp_path, project)

    ignored = (project / ".gitignore").read_text(encoding="utf-8")
    assert ignored.splitlines() == ["node_modules", f"{TOOLKIT_FOLDER}/"]


def test_hooks_run_in_a_linked_worktree(tmp_path: Path) -> None:
    project = _project(tmp_path)
    _install(tmp_path, project)
    _ = (project / "checks.toml").write_text(CONFIGURATION, encoding="utf-8")
    (project / "svc" / "src").mkdir(parents=True)
    _ = (project / "svc" / "src" / "short.py").write_text(
        "VALUE = 1\n", encoding="utf-8"
    )
    _git(project, "add", ".")
    _git(project, "commit", "--quiet", "--message", "seed")
    worktree = tmp_path / "worktree"
    _git(project, "worktree", "add", "--quiet", str(worktree))
    _ = (worktree / "svc" / "src" / "long.py").write_text(
        "VALUE = 1\n" * 5, encoding="utf-8"
    )
    _git(worktree, "add", ".")

    committed = subprocess.run(
        ["git", "commit", "--quiet", "--message", "long"],
        cwd=worktree,
        capture_output=True,
        text=True,
        check=False,
    )

    assert committed.returncode != 0
    assert "svc/src/long.py" in committed.stdout + committed.stderr
