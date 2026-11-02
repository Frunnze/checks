from pathlib import Path

from check_support import repository, run_configured, stage_file

_CONFIGURATION = (
    'source_directories = ["user-service/src"]\n'
    '[checks.shared-class-state]\nwhen = "pre-commit"\n'
)
_OWN_COPY = "        self._picked = set()\n"


def _gate_run(tmp_path: Path, initializer: str) -> tuple[int, str]:
    repository(tmp_path)
    stage_file(
        tmp_path,
        "user-service/src/basket.py",
        "class Basket:\n"
        "    _picked = set()\n"
        "    def __init__(self, store):\n"
        "        self.store = store\n"
        f"{initializer}"
        "    def pick(self, item_id):\n"
        "        self._picked.add(item_id)\n",
    )
    finished = run_configured(tmp_path, _CONFIGURATION, "shared-class-state")

    return finished.returncode, finished.stderr


def test_failure_names_the_shared_container(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "")

    assert returncode == 1
    assert (
        "user-service/src/basket.py:2: Basket._picked is one set shared by"
        " every instance, yet line 6 changes it through self" in stderr
    )
    assert "them per instance in __init__" in stderr


def test_passes_a_container_each_instance_owns(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, _OWN_COPY)

    assert returncode == 0, stderr


def test_a_file_that_does_not_parse_fails_the_check(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "user-service/src/broken.py", "def broken(:\n")

    finished = run_configured(tmp_path, _CONFIGURATION, "shared-class-state")

    assert finished.returncode != 0
