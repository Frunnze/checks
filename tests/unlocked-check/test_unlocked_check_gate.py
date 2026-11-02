from pathlib import Path

from check_support import repository, run_configured, stage_file

_CONFIGURATION = (
    'source_directories = ["user-service/src"]\n'
    '[checks.unlocked-check]\nwhen = "pre-commit"\n'
)
_UNLOCKED = (
    "        if key not in self.entries:\n"
    "            self.entries[key] = build(key)\n"
)
_LOCKED = (
    "        with self._lock:\n"
    "            if key not in self.entries:\n"
    "                self.entries[key] = build(key)\n"
)


def _gate_run(tmp_path: Path, entry_body: str) -> tuple[int, str]:
    repository(tmp_path)
    stage_file(
        tmp_path,
        "user-service/src/registry.py",
        "class Registry:\n"
        "    def reset(self):\n"
        "        with self._lock:\n"
        "            self.entries = {}\n"
        "    def entry(self, key):\n"
        f"{entry_body}",
    )
    finished = run_configured(tmp_path, _CONFIGURATION, "unlocked-check")

    return finished.returncode, finished.stderr


def test_failure_names_the_unlocked_attribute(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, _UNLOCKED)

    assert returncode == 1
    assert (
        "user-service/src/registry.py:6: self.entries is checked then set"
        " outside the lock that guards it elsewhere, so two threads can"
        " both pass the check" in stderr
    )
    assert "locked block" in stderr


def test_passes_a_check_under_the_lock(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, _LOCKED)

    assert returncode == 0, stderr


def test_a_file_that_does_not_parse_fails_the_check(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "user-service/src/broken.py", "def broken(:\n")

    finished = run_configured(tmp_path, _CONFIGURATION, "unlocked-check")

    assert finished.returncode != 0
