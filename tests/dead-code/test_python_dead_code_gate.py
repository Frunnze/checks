import subprocess
from pathlib import Path

from check_support import (
    link_toolkit_tool,
    repository,
    run_configured,
    stage_file,
)

UNUSED_FORMATTER = (
    "def format_price(amount: int) -> str:\n    return str(amount)\n"
)
USED_FORMATTER = UNUSED_FORMATTER + "\n\nprint(format_price(3))\n"


def test_fails_on_dead_code_named_like_live_code_in_another_service(
    tmp_path: Path,
) -> None:
    repository(tmp_path)
    link_toolkit_tool(tmp_path, "vulture")
    stage_file(tmp_path, "user-service/src/prices.py", UNUSED_FORMATTER)
    stage_file(tmp_path, "billing-service/src/prices.py", USED_FORMATTER)

    finished = run_configured(
        tmp_path,
        'source_directories = ["user-service/src", "billing-service/src"]\n',
        "dead-code",
    )

    assert finished.returncode == 1
    assert "user-service/src/prices.py" in finished.stdout


def test_changed_scope_checks_a_folder_whose_only_change_is_a_deletion(
    tmp_path: Path,
) -> None:
    repository(tmp_path)
    link_toolkit_tool(tmp_path, "vulture")
    stage_file(tmp_path, "svc/src/prices.py", UNUSED_FORMATTER)
    stage_file(
        tmp_path,
        "svc/src/main.py",
        "from prices import format_price\n\nprint(format_price(3))\n",
    )
    _ = subprocess.run(
        ["git", "commit", "--quiet", "-m", "seed"], cwd=tmp_path, check=True
    )
    _ = subprocess.run(
        ["git", "rm", "--quiet", "svc/src/main.py"], cwd=tmp_path, check=True
    )

    finished = run_configured(
        tmp_path,
        'source_directories = ["svc/src"]\n'
        '[checks.dead-code]\nscope = "changed"\n',
        "dead-code",
    )

    assert finished.returncode == 1
    assert "svc/src/prices.py" in finished.stdout
