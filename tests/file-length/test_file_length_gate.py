from pathlib import Path

from check_support import repository, run_check, stage_file

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
