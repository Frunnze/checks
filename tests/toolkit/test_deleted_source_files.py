import subprocess
from pathlib import Path

from check_support import (
    link_real_python,
    repository,
    run_check,
    stage_file,
    stub_binary,
)

FEATURE_SOURCE = "user-service/src/features/notes/router.py"
SIBLING_SOURCE = "user-service/src/features/tests/api.py"
TEST_SOURCE = "user-service/tests/test_router.py"


def _committed_repository(tmp_path: Path) -> None:
    repository(tmp_path)
    link_real_python(tmp_path)
    stage_file(tmp_path, SIBLING_SOURCE, "value = 1\n")
    stage_file(
        tmp_path, FEATURE_SOURCE, "def route(value):\n    return value\n"
    )
    stage_file(tmp_path, TEST_SOURCE, "def helper():\n    return 1\n")
    _ = subprocess.run(
        ["git", "commit", "--quiet", "-m", "seed"],
        cwd=tmp_path,
        check=True,
    )
    (tmp_path / FEATURE_SOURCE).unlink()


def test_feature_isolation_survives_a_deleted_source_file(
    tmp_path: Path,
) -> None:
    _committed_repository(tmp_path)
    finished = run_check(tmp_path, "feature-isolation")

    assert finished.returncode == 0
    assert "Traceback" not in finished.stderr


def test_nested_definitions_survives_a_deleted_source_file(
    tmp_path: Path,
) -> None:
    _committed_repository(tmp_path)
    finished = run_check(tmp_path, "nested-definitions")

    assert finished.returncode == 0
    assert "Traceback" not in finished.stderr


def test_property_tests_survives_a_deleted_source_file(
    tmp_path: Path,
) -> None:
    _committed_repository(tmp_path)
    finished = run_check(tmp_path, "property-tests")

    assert "Traceback" not in finished.stderr


def test_linters_pylint_survives_a_deleted_source_file(
    tmp_path: Path,
) -> None:
    _committed_repository(tmp_path)
    stub_binary(tmp_path, "pylint", 'exit 0\n')
    finished = run_check(tmp_path, "linters/pylint")

    assert finished.returncode == 0
    assert "fatal" not in finished.stdout
