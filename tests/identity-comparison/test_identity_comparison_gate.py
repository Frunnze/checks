from pathlib import Path

from check_support import repository, run_configured, stage_file

_CONFIGURATION = (
    'source_directories = ["user-service/src"]\n'
    '[checks.identity-comparison]\nwhen = "pre-commit"\n'
)


def _gate_run(tmp_path: Path, operator: str) -> tuple[int, str]:
    repository(tmp_path)
    stage_file(
        tmp_path,
        "user-service/src/orders.py",
        "SHIPPED = 'shipped'\n"
        "def is_done(order_state):\n"
        "    if order_state == 'cancelled':\n        return False\n"
        f"    return order_state {operator} SHIPPED\n",
    )
    finished = run_configured(tmp_path, _CONFIGURATION, "identity-comparison")

    return finished.returncode, finished.stderr


def test_failure_names_the_constant(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "is")

    assert returncode == 1
    assert (
        "user-service/src/orders.py:5: order_state is SHIPPED compares"
        " object identity, but SHIPPED is a constant str" in stderr
    )
    assert "use ==" in stderr


def test_passes_an_equality_comparison(tmp_path: Path) -> None:
    returncode, stderr = _gate_run(tmp_path, "==")

    assert returncode == 0, stderr


def test_a_file_that_does_not_parse_fails_the_check(tmp_path: Path) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "user-service/src/broken.py", "def broken(:\n")

    finished = run_configured(tmp_path, _CONFIGURATION, "identity-comparison")

    assert finished.returncode != 0
