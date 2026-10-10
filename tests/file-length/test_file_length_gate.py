import subprocess
from pathlib import Path

import pytest

from check_support import (
    COPIED_TOOLKIT,
    repository,
    run_check,
    stage_file,
)

MAXIMUM = 300
OVERLONG = "user-service/src/wide.py"


def _numbered_lines(count: int) -> str:
    lines: list[str] = []

    for number in range(count):
        lines.append(f"value_{number} = {number}")

    return "\n".join(lines)


def test_flags_an_overlong_file_without_a_trailing_newline(
    tmp_path: Path,
) -> None:
    repository(tmp_path)
    stage_file(tmp_path, OVERLONG, _numbered_lines(MAXIMUM + 1))
    finished = run_check(tmp_path, "file-length")

    assert finished.returncode == 1
    assert OVERLONG in finished.stderr
    assert "301 lines" in finished.stderr


def test_flags_an_overlong_file_with_a_trailing_newline(
    tmp_path: Path,
) -> None:
    repository(tmp_path)
    stage_file(tmp_path, OVERLONG, _numbered_lines(MAXIMUM + 1) + "\n")
    finished = run_check(tmp_path, "file-length")

    assert finished.returncode == 1
    assert "301 lines" in finished.stderr


def test_accepts_a_file_exactly_at_the_limit(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, OVERLONG, _numbered_lines(MAXIMUM) + "\n")

    assert run_check(tmp_path, "file-length").returncode == 0


def test_reports_the_whole_name_of_a_file_containing_a_space(
    tmp_path: Path,
) -> None:
    spaced = "user-service/src/wide module.py"
    repository(tmp_path)
    stage_file(tmp_path, spaced, _numbered_lines(MAXIMUM + 1) + "\n")
    finished = run_check(tmp_path, "file-length")

    assert finished.returncode == 1
    assert spaced in finished.stderr


def _run_file_length(
    tmp_path: Path, configuration: str
) -> subprocess.CompletedProcess[str]:
    _ = (tmp_path / "checks.toml").write_text(configuration, encoding="utf-8")

    return subprocess.run(
        ["sh", f"{COPIED_TOOLKIT}/run", "file-length"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.mark.parametrize("folder", ["tools/build", "web/dist", "app/vendor"])
def test_checks_a_source_folder_named_like_a_pruned_folder(
    tmp_path: Path, folder: str
) -> None:
    repository(tmp_path)
    stage_file(tmp_path, f"{folder}/wide.py", _numbered_lines(MAXIMUM + 1))

    finished = _run_file_length(
        tmp_path, f'source_directories = ["{folder}"]\n'
    )

    assert finished.returncode == 1
    assert f"{folder}/wide.py (301 lines)" in finished.stderr


@pytest.mark.parametrize("extension", ["mts", "cts"])
def test_flags_an_overlong_typescript_module_file(
    tmp_path: Path, extension: str
) -> None:
    overlong = f"web/src/helpers.{extension}"
    repository(tmp_path)
    stage_file(tmp_path, "web/src/main.ts", "export const a = 1;\n")
    stage_file(tmp_path, overlong, _numbered_lines(MAXIMUM + 1))

    finished = _run_file_length(tmp_path, 'source_directories = ["web/src"]\n')

    assert finished.returncode == 1
    assert f"{overlong} (301 lines)" in finished.stderr


def test_reads_a_file_in_a_folder_named_like_an_assignment(
    tmp_path: Path,
) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "k=v/wide.py", _numbered_lines(MAXIMUM + 1))

    finished = _run_file_length(tmp_path, 'source_directories = ["k=v"]\n')

    assert finished.returncode == 1
    assert "k=v/wide.py (301 lines)" in finished.stderr


def test_whitelist_hides_only_the_named_file(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "web/src/view.tsx", _numbered_lines(MAXIMUM + 1))

    finished = _run_file_length(
        tmp_path,
        'source_directories = ["web/src"]\n'
        '[checks.file-length]\nwhitelist = ["web/src/view.ts"]\n',
    )

    assert finished.returncode == 1
    assert "web/src/view.tsx (301 lines)" in finished.stderr


def test_reports_a_file_once_when_source_folders_overlap(
    tmp_path: Path,
) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "svc/src/sub/wide.py", _numbered_lines(MAXIMUM + 1))

    finished = _run_file_length(
        tmp_path, 'source_directories = ["svc/src", "svc/src/sub"]\n'
    )

    assert finished.returncode == 1
    assert finished.stderr.count("svc/src/sub/wide.py (301 lines)") == 1


def test_checks_a_source_folder_that_is_a_symbolic_link(
    tmp_path: Path,
) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "real/src/wide.py", _numbered_lines(MAXIMUM + 1))
    (tmp_path / "svc").mkdir()
    (tmp_path / "svc" / "src").symlink_to(tmp_path / "real" / "src")

    finished = _run_file_length(tmp_path, 'source_directories = ["svc/src"]\n')

    assert finished.returncode == 1
    assert "svc/src/wide.py (301 lines)" in finished.stderr
