import os
import subprocess
from pathlib import Path

from check_support import COPIED_TOOLKIT, repository, stage_file

LEAKED_KEY = 'AWS_KEY = "AKIAIOSFODNN7EXAMPLE"\n'
GITLEAKS_STUB = """#!/bin/sh
case "$2" in
    --staged) scanned=$(git diff --staged) ;;
    --log-opts=*) scanned=$(git log -p ${2#--log-opts=}) ;;
esac
if printf '%s' "$scanned" | grep -q AKIA; then
    exit 1
fi
"""
CONFIGURATION = 'source_directories = ["service/src"]\nstable = "pre-push"\n'


def test_fails_at_pre_push_on_a_secret_in_a_pushed_commit(
    tmp_path: Path,
) -> None:
    repository(tmp_path)
    stage_file(tmp_path, "service/src/settings.py", LEAKED_KEY)
    _ = subprocess.run(
        ["git", "commit", "--quiet", "-m", "settings"],
        cwd=tmp_path,
        check=True,
    )
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    gitleaks = stubs / "gitleaks"
    _ = gitleaks.write_text(GITLEAKS_STUB, encoding="utf-8")
    gitleaks.chmod(0o755)
    _ = (tmp_path / "checks.toml").write_text(CONFIGURATION, encoding="utf-8")

    finished = subprocess.run(
        ["sh", f"{COPIED_TOOLKIT}/run", "--stage", "pre-push", "secrets"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PATH": f"{stubs}:{os.environ['PATH']}"},
    )

    assert finished.returncode == 1
