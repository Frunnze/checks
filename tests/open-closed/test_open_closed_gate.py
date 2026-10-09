from pathlib import Path

from check_support import (
    link_real_python,
    repository,
    run_check,
    stage_file,
)


def test_failure_suggests_ocp_extension_patterns(tmp_path: Path) -> None:
    source = (
        "def href(unit):\n"
        "    if unit.kind == 'folder':\n        return '/folder'\n"
        "    if unit.kind == 'file':\n        return '/file'\n"
        "    if unit.kind == 'note':\n        return '/note'\n"
    )
    repository(tmp_path)
    link_real_python(tmp_path)
    stage_file(tmp_path, "user-service/src/presentation.py", source)
    finished = run_check(tmp_path, "open-closed")

    assert finished.returncode == 1
    assert "follow OCP" in finished.stderr
    assert "strategy/handler" in finished.stderr
    assert "polymorphism" in finished.stderr
    assert "registry" in finished.stderr
