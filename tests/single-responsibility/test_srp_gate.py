import subprocess
import sys

import pytest
from check_support import (
    link_real_python,
    link_toolkit_node_modules,
    remove_toolkit_python,
    repository,
    run_check,
    stage_file,
)
from settings_validation import CHECK_ORDER
from srp_support import CHECK, mixed_function, split_class


def test_check_is_executable_and_registered_early():
    order = list(CHECK_ORDER)

    assert (CHECK / "check").stat().st_mode & 0o111
    assert order.count("single-responsibility") == 1
    assert order.index("file-length") < order.index("single-responsibility")
    assert order.index("single-responsibility") < order.index("linters")


@pytest.mark.parametrize(
    "relative, suffix",
    [
        ("user-service/src/worker.py", ".py"),
        ("content-management-service/src/worker.py", ".py"),
        ("ui-service/src/worker.tsx", ".tsx"),
        ("api-gateway/src/worker.ts", ".ts"),
    ],
)
@pytest.mark.parametrize("at_threshold", [False, True])
def test_hook_enforces_two_entities_in_every_declared_package(
    tmp_path, relative, suffix, at_threshold
):
    repository(tmp_path)
    link_real_python(tmp_path)
    link_toolkit_node_modules(tmp_path)
    stage_file(tmp_path, relative, split_class(suffix, cohesive=not at_threshold))
    result = run_check(tmp_path, "single-responsibility")

    assert result.returncode == int(at_threshold)
    assert f"coefficient={'0.5000' if at_threshold else '0.2500'}" in result.stdout
    assert "threshold=0.5" in result.stdout
    if at_threshold:
        assert f"{relative}:" in result.stderr
        assert "2 reasons to change (filesystem, network)" in result.stderr
        assert "follow SRP" in result.stderr
    else:
        assert result.stderr == ""


def test_untracked_working_tree_sources_are_checked(tmp_path):
    repository(tmp_path)
    link_real_python(tmp_path)
    source = tmp_path / "user-service/src/new with spaces.py"
    source.parent.mkdir(parents=True)
    source.write_text(mixed_function())

    assert run_check(tmp_path, "single-responsibility").returncode == 1


def test_deleted_sources_and_non_source_directories_do_not_block(tmp_path):
    repository(tmp_path)
    link_real_python(tmp_path)
    stage_file(tmp_path, "user-service/src/deleted.py", mixed_function())
    (tmp_path / "user-service/src/deleted.py").unlink()
    stage_file(tmp_path, "user-service/tests/worker.py", mixed_function())
    stage_file(tmp_path, "user-service/src/__pycache__/cached.py", mixed_function())
    stage_file(tmp_path, "user-service/src/plain.py", "VALUE = 1\n")
    result = run_check(tmp_path, "single-responsibility")

    assert result.returncode == 0
    assert "coefficient=0.0000" in result.stdout


def test_missing_runtime_fails_with_install_instructions(tmp_path):
    repository(tmp_path)
    remove_toolkit_python(tmp_path)
    stage_file(tmp_path, "user-service/src/worker.py", split_class())
    result = run_check(tmp_path, "single-responsibility")

    assert result.returncode == 1
    assert "run ./install.sh" in result.stderr


def test_missing_typescript_does_not_silently_skip_typescript(tmp_path):
    repository(tmp_path)
    link_real_python(tmp_path)
    stage_file(tmp_path, "ui-service/src/worker.ts", split_class(".ts"))
    result = run_check(tmp_path, "single-responsibility")

    assert result.returncode == 1
    assert "typescript is not installed" in result.stderr


def test_standalone_missing_source_is_an_analysis_error(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(CHECK / "srp_check.py"),
            "--json",
            str(tmp_path / "missing.py"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "does not exist" in result.stderr
    assert result.stdout == ""


def test_missing_directories_allow_an_empty_repository(tmp_path):
    repository(tmp_path)

    assert run_check(tmp_path, "single-responsibility").returncode == 0
