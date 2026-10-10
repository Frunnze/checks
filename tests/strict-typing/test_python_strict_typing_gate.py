from pathlib import Path

import pytest

from check_support import (
    COPIED_TOOLKIT,
    TOOLKIT,
    link_real_python,
    repository,
    run_check,
    stage_file,
)


@pytest.mark.parametrize(
    "silenced_source",
    [
        'VALUE: int = "a"  # pyright: ignore[reportAssignmentType]\n',
        '# pyright: reportAssignmentType=false\nVALUE: int = "a"\n',
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
