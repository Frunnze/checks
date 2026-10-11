import subprocess
from pathlib import Path

import pytest

from check_support import (
    link_toolkit_node_modules,
    repository,
    run_check,
    stage_file,
)

CHANGED_SCOPE = {"single-responsibility": 'scope = "changed"\n'}
TWO_REASONS = [
    (
        "user-service/src/sync.py",
        "user-service/src/total.py",
        "import httpx\nfrom pathlib import Path\n\n\n"
        "def sync(url: str, path: str) -> None:\n"
        "    Path(path).write_text(httpx.get(url).text)\n",
        "def total(numbers: list[int]) -> int:\n    return sum(numbers)\n",
    ),
    (
        "ui-service/src/sync.ts",
        "ui-service/src/total.ts",
        'import axios from "axios";\nimport * as fs from "node:fs";\n\n'
        "export async function sync(url: string, path: string) {\n"
        "  const response = await axios.get(url);\n"
        "  fs.writeFileSync(path, response.data);\n"
        "}\n",
        "export const total = (numbers: number[]) =>\n"
        "  numbers.reduce((sum, number) => sum + number, 0);\n",
    ),
]


def _commit(tmp_path: Path) -> None:
    _ = subprocess.run(
        ["git", "commit", "--quiet", "-m", "seed"], cwd=tmp_path, check=True
    )


@pytest.mark.parametrize(
    "problem, clean, problem_source, clean_source", TWO_REASONS
)
def test_changed_scope_ignores_an_unchanged_old_problem(
    tmp_path: Path,
    problem: str,
    clean: str,
    problem_source: str,
    clean_source: str,
) -> None:
    repository(tmp_path)
    link_toolkit_node_modules(tmp_path)
    stage_file(tmp_path, problem, problem_source)
    _commit(tmp_path)
    stage_file(tmp_path, clean, clean_source)

    finished = run_check(tmp_path, "single-responsibility", CHANGED_SCOPE)

    assert finished.returncode == 0, finished.stderr


@pytest.mark.parametrize(
    "problem, clean, problem_source, clean_source", TWO_REASONS
)
def test_changed_scope_reports_a_staged_problem(
    tmp_path: Path,
    problem: str,
    clean: str,
    problem_source: str,
    clean_source: str,
) -> None:
    repository(tmp_path)
    link_toolkit_node_modules(tmp_path)
    stage_file(tmp_path, clean, clean_source)
    _commit(tmp_path)
    stage_file(tmp_path, problem, problem_source)

    finished = run_check(tmp_path, "single-responsibility", CHANGED_SCOPE)

    assert finished.returncode == 1
    assert f"{problem}:" in finished.stderr
