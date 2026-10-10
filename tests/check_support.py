import shutil
import subprocess
import sys
from pathlib import Path

from hypothesis import HealthCheck, settings

TOOLKIT = Path(__file__).resolve().parent.parent
COPIED_TOOLKIT = ".checks-toolkit"
TOOLKIT_FILES = ("run", "tools.sh")
TOOLKIT_FOLDERS = ("checks", "configuration")
IGNORED = f"{COPIED_TOOLKIT}/\n.venv/\n"
SOURCE_DIRECTORIES = (
    "user-service/src",
    "content-management-service/src",
    "ui-service/src",
    "api-gateway/src",
)
EXPERIMENTAL_CHECKS = (
    "single-responsibility",
    "feature-isolation",
    "open-closed",
    "dependency-inversion",
    "definition-names",
    "nested-definitions",
    "property-tests",
)
HYPOTHESIS_SETTINGS = settings(
    max_examples=8,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
CheckRun = subprocess.CompletedProcess[str]


def _link_python(python_link: Path) -> None:
    python_link.parent.mkdir(parents=True, exist_ok=True)
    python_link.symlink_to(Path(sys.executable))


def repository(tmp_path: Path) -> None:
    copied_toolkit = tmp_path / COPIED_TOOLKIT
    copied_toolkit.mkdir()

    for file_name in TOOLKIT_FILES:
        _ = shutil.copy2(TOOLKIT / file_name, copied_toolkit / file_name)

    for folder_name in TOOLKIT_FOLDERS:
        _ = shutil.copytree(
            TOOLKIT / folder_name,
            copied_toolkit / folder_name,
            ignore=shutil.ignore_patterns("__pycache__"),
        )
    _link_python(copied_toolkit / ".venv" / "bin" / "python")
    _ = (tmp_path / ".gitignore").write_text(IGNORED, encoding="utf-8")

    for command in (
        ["git", "init", "--quiet"],
        ["git", "config", "user.email", "hooks@example.com"],
        ["git", "config", "user.name", "hooks"],
    ):
        _ = subprocess.run(command, cwd=tmp_path, check=True)


def link_real_python(tmp_path: Path) -> None:
    _link_python(tmp_path / ".venv" / "bin" / "python")


def link_toolkit_node_modules(tmp_path: Path) -> None:
    copied_modules = tmp_path / COPIED_TOOLKIT / "node_modules"
    copied_modules.symlink_to(TOOLKIT / "node_modules")


def remove_toolkit_python(tmp_path: Path) -> None:
    (tmp_path / COPIED_TOOLKIT / ".venv" / "bin" / "python").unlink()


def stub_binary(tmp_path: Path, name: str, body: str) -> None:
    binary = tmp_path / COPIED_TOOLKIT / ".venv" / "bin" / name
    binary.parent.mkdir(parents=True, exist_ok=True)
    _ = binary.write_text(f"#!/bin/sh\n{body}", encoding="utf-8")
    binary.chmod(0o755)


def here_document(label: str, text: str) -> str:
    return f"cat <<'{label}'\n{text}{label}\n"


def stage_file(tmp_path: Path, relative: str, content: str) -> None:
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(content, encoding="utf-8")
    _ = subprocess.run(
        ["git", "add", relative], cwd=tmp_path, check=True
    )


def _write_configuration(
    tmp_path: Path, check_settings: dict[str, str]
) -> None:
    present_directories: list[str] = []

    for source_directory in SOURCE_DIRECTORIES:
        if (tmp_path / source_directory).is_dir():
            present_directories.append(source_directory)

    if not present_directories:
        placeholder = tmp_path / SOURCE_DIRECTORIES[0] / "__init__.py"
        placeholder.parent.mkdir(parents=True)
        placeholder.touch()
        present_directories.append(SOURCE_DIRECTORIES[0])

    listed_directories = ", ".join(
        f'"{directory}"' for directory in present_directories
    )
    configuration = f"source_directories = [{listed_directories}]\n"

    for check_name in EXPERIMENTAL_CHECKS:
        extra_settings = check_settings.get(check_name, "")
        configuration += (
            f'[checks.{check_name}]\nwhen = "pre-commit"\n{extra_settings}'
        )

    _ = (tmp_path / "checks.toml").write_text(configuration, encoding="utf-8")


def run_check(
    tmp_path: Path, name: str, check_settings: dict[str, str] | None = None
) -> CheckRun:
    _write_configuration(tmp_path, check_settings or {})

    return subprocess.run(
        ["sh", f"{COPIED_TOOLKIT}/run", name],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )


def stderr_lines(finished: CheckRun) -> list[str]:
    return [line for line in finished.stderr.splitlines() if line.strip()]
