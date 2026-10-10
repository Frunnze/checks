import os
import subprocess
from pathlib import Path

from check_support import COPIED_TOOLKIT, repository, stage_file

CONFIGURATION = 'source_directories = ["plugin/src"]\n'
FUNCTIONS_ONLY_SUMMARY = (
    "Code Coverage Report Summary:\n"
    "  Classes:          (0/0)\n"
    "  Methods:          (0/0)\n"
    "  Lines:    100.00% (12/12)\n"
)


def test_passes_a_fully_covered_package_without_classes(
    tmp_path: Path,
) -> None:
    repository(tmp_path)
    stage_file(
        tmp_path,
        "plugin/src/functions.php",
        "<?php\nfunction one(): int { return 1; }\n",
    )
    phpunit = tmp_path / "plugin" / "vendor" / "bin" / "phpunit"
    phpunit.parent.mkdir(parents=True)
    _ = phpunit.write_text("#!/bin/sh\n", encoding="utf-8")
    phpunit.chmod(0o755)
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    _ = (stubs / "summary.txt").write_text(
        FUNCTIONS_ONLY_SUMMARY, encoding="utf-8"
    )
    php = stubs / "php"
    _ = php.write_text(f'#!/bin/sh\ncat "{stubs}/summary.txt"\n', encoding="utf-8")
    php.chmod(0o755)
    _ = (tmp_path / "checks.toml").write_text(CONFIGURATION, encoding="utf-8")

    finished = subprocess.run(
        ["sh", f"{COPIED_TOOLKIT}/run", "coverage"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PATH": f"{stubs}:{os.environ['PATH']}"},
    )

    assert finished.returncode == 0, finished.stderr
