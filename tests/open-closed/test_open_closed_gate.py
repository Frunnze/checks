import subprocess
from pathlib import Path

import pytest

from check_support import (
    link_real_python,
    link_toolkit_node_modules,
    repository,
    run_check,
    stage_file,
    stderr_lines,
)

_DECLINED = "Payment was declined by the bank"
_PRODUCERS = {
    "python": (
        "user-service/src/server.py",
        f"def register():\n    raise ValueError({_DECLINED!r})\n",
    ),
    "typescript": (
        "ui-service/src/server.ts",
        "export function register(): void {\n"
        f"  throw new Error({_DECLINED!r});\n}}\n",
    ),
}
_CONSUMERS = {
    "python": (
        "user-service/src/client.py",
        f"def retry(text):\n    return text == {_DECLINED!r}\n",
    ),
    "typescript": (
        "ui-service/src/client.ts",
        "export function retry(text: string): boolean {\n"
        f"  return text === {_DECLINED!r};\n}}\n",
    ),
}


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


@pytest.mark.parametrize("scope", ["repository", "changed"])
@pytest.mark.parametrize(
    ("producer", "consumer"),
    [("python", "typescript"), ("typescript", "python")],
)
def test_reports_error_text_coupling_across_languages_once(
    tmp_path: Path, producer: str, consumer: str, scope: str
) -> None:
    producer_path, producer_source = _PRODUCERS[producer]
    consumer_path, consumer_source = _CONSUMERS[consumer]
    repository(tmp_path)
    link_real_python(tmp_path)
    link_toolkit_node_modules(tmp_path)
    stage_file(tmp_path, producer_path, producer_source)
    _ = subprocess.run(
        ["git", "commit", "--quiet", "-m", "producer"],
        cwd=tmp_path,
        check=True,
    )
    stage_file(tmp_path, consumer_path, consumer_source)
    finished = run_check(
        tmp_path, "open-closed", {"open-closed": f'scope = "{scope}"\n'}
    )

    assert finished.returncode == 1
    assert [
        line for line in stderr_lines(finished) if "error text" in line
    ] == [
        (
            f'{consumer_path}:2: branches on human-readable error text '
            f'"{_DECLINED}" produced at {producer_path}:2; use a stable '
            "error code and handler registry"
        )
    ]
