from pathlib import Path

import pytest

from check_support import (
    COPIED_TOOLKIT,
    TOOLKIT,
    link_real_python,
    link_toolkit_tool,
    repository,
    run_check,
    run_configured,
    stage_file,
)


@pytest.mark.parametrize(
    "silenced_source",
    [
        'VALUE: int = "a"  # pyright: ignore[reportAssignmentType]\n',
        '# pyright: reportAssignmentType=false\nVALUE: int = "a"\n',
        '# pyright: strict, reportAssignmentType=false\nVALUE: int = "a"\n',
        "from typing import no_type_check\n\n\n@no_type_check\n"
        'def broken() -> int:\n    return "a"\n',
    ],
)
def test_fails_on_a_silenced_type_error(
    tmp_path: Path, silenced_source: str
) -> None:
    repository(tmp_path)
    link_real_python(tmp_path)
    basedpyright = tmp_path / COPIED_TOOLKIT / ".venv" / "bin" / "basedpyright"
    basedpyright.symlink_to(TOOLKIT / ".venv" / "bin" / "basedpyright")
    stage_file(tmp_path, "user-service/src/settings.py", silenced_source)

    finished = run_check(tmp_path, "strict-typing")

    assert finished.returncode == 1
    assert "user-service/src/settings.py" in finished.stderr


@pytest.mark.parametrize(
    "source_directories, expected_exit",
    [('["svc/src"]', 0), ('["svc/src", "svc/tests"]', 1)],
)
def test_type_checks_a_tests_folder_only_when_it_is_a_source_folder(
    tmp_path: Path, source_directories: str, expected_exit: int
) -> None:
    repository(tmp_path)
    link_real_python(tmp_path)
    link_toolkit_tool(tmp_path, "basedpyright")
    stage_file(tmp_path, "svc/src/value.py", "VALUE: int = 1\n")
    stage_file(tmp_path, "svc/tests/test_value.py", 'BROKEN: int = "a"\n')

    finished = run_configured(
        tmp_path,
        f"source_directories = {source_directories}\n",
        "strict-typing",
    )

    assert finished.returncode == expected_exit, finished.stdout
