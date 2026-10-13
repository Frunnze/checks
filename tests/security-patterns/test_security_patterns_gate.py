from pathlib import Path

import pytest

from check_support import (
    COPIED_TOOLKIT,
    LIBRARY_MANIFEST,
    WORDPRESS_MANIFEST,
    link_toolkit_tool,
    php_package,
    repository,
    run_configured,
    stage_file,
)

EVAL_RULE = (
    "rules:\n"
    "  - id: no-eval\n"
    "    pattern: eval(...)\n"
    "    message: eval runs arbitrary code\n"
    "    languages: [{language}]\n"
    "    severity: ERROR\n"
)
RULESETS = "checks/stable/security-patterns/{language}/rulesets.txt"


def _use_eval_rule(tmp_path: Path, language: str) -> None:
    rule = tmp_path / "eval-rule.yml"
    _ = rule.write_text(EVAL_RULE.format(language=language), encoding="utf-8")
    rulesets = tmp_path / COPIED_TOOLKIT / RULESETS.format(language=language)
    _ = rulesets.write_text(f"{rule}\n", encoding="utf-8")


@pytest.mark.parametrize(
    "source_directory", ["tools/build", "web/dist", "app/vendor"]
)
def test_scans_a_folder_semgrep_ignores_by_default(
    tmp_path: Path, source_directory: str
) -> None:
    repository(tmp_path)
    link_toolkit_tool(tmp_path, "semgrep")
    _use_eval_rule(tmp_path, "python")
    stage_file(tmp_path, f"{source_directory}/run.py", "eval(input())\n")

    finished = run_configured(
        tmp_path,
        f'source_directories = ["{source_directory}"]\n',
        "security-patterns",
    )

    assert finished.returncode == 1


@pytest.mark.parametrize("suffix", [".mts", ".cts"])
def test_scans_module_typescript_files(tmp_path: Path, suffix: str) -> None:
    repository(tmp_path)
    link_toolkit_tool(tmp_path, "semgrep")
    _use_eval_rule(tmp_path, "typescript")
    stage_file(
        tmp_path,
        f"ui/src/run{suffix}",
        "export function run(code: string) {\n  return eval(code);\n}\n",
    )

    finished = run_configured(
        tmp_path, 'source_directories = ["ui/src"]\n', "security-patterns"
    )

    assert finished.returncode == 1


@pytest.mark.parametrize(
    ("manifest", "expected_exit"),
    [(WORDPRESS_MANIFEST, 1), (LIBRARY_MANIFEST, 0)],
)
def test_scans_the_root_plugin_file_only_of_a_wordpress_package(
    tmp_path: Path, manifest: str, expected_exit: int
) -> None:
    php_package(tmp_path, "api", manifest)
    link_toolkit_tool(tmp_path, "semgrep")
    _use_eval_rule(tmp_path, "php")
    stage_file(tmp_path, "api/src/Clean.php", "<?php\n")
    stage_file(tmp_path, "plugin.php", "<?php\neval($_GET['code']);\n")

    finished = run_configured(
        tmp_path, 'source_directories = ["api/src"]\n', "security-patterns"
    )

    assert finished.returncode == expected_exit
