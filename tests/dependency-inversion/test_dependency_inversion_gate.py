from pathlib import Path

from check_support import (
    link_real_python,
    repository,
    run_check,
    stage_file,
)

_REPOSITORY = (
    "class SqlUnitRepository:\n"
    "    def fetch(self, unit_id):\n        return unit_id\n"
)
_SERVICE = (
    "class UnitService:\n"
    "    def __init__(self):\n"
    "        self.repository = SqlUnitRepository()\n"
    "    def run(self):\n        return None\n"
)


def test_failure_names_the_construction_and_suggests_injection(
    tmp_path: Path,
) -> None:
    repository(tmp_path)
    link_real_python(tmp_path)
    stage_file(tmp_path, "user-service/src/repository.py", _REPOSITORY)
    stage_file(tmp_path, "user-service/src/service.py", _SERVICE)
    finished = run_check(tmp_path, "dependency-inversion")

    assert finished.returncode == 1
    assert "UnitService constructs its own collaborators" in finished.stderr
    assert "follow DIP" in finished.stderr
    assert "injected" in finished.stderr


def test_passes_when_the_collaborator_is_injected(tmp_path: Path) -> None:
    injected = (
        "class UnitService:\n"
        "    def __init__(self, repository):\n"
        "        self.repository = repository\n"
        "    def run(self):\n        return None\n"
    )
    repository(tmp_path)
    link_real_python(tmp_path)
    stage_file(tmp_path, "user-service/src/repository.py", _REPOSITORY)
    stage_file(tmp_path, "user-service/src/service.py", injected)
    finished = run_check(tmp_path, "dependency-inversion")

    assert finished.returncode == 0


def test_ignores_tests_outside_the_source_directories(
    tmp_path: Path,
) -> None:
    repository(tmp_path)
    link_real_python(tmp_path)
    stage_file(tmp_path, "user-service/src/repository.py", _REPOSITORY)
    stage_file(tmp_path, "user-service/tests/test_service.py", _SERVICE)
    finished = run_check(tmp_path, "dependency-inversion")

    assert finished.returncode == 0
