from pathlib import Path

from check_support import (
    LIBRARY_MANIFEST,
    WORDPRESS_MANIFEST,
    php_package,
    run_configured,
    stage_file,
)

PACKAGE_CONFIGURATION = 'source_directories = ["api/src"]\n'
CLEAN_FILE = "<?php\n\ndeclare(strict_types=1);\n"
WRONG_RETURN = (
    CLEAN_FILE + "\nfunction link_checkup_count(): int\n{\n"
    "    return 'many';\n}\n"
)
SILENCED_FILE = (
    CLEAN_FILE + "\n// @phpstan-ignore-next-line\n"
    "function link_checkup_size(): int\n{\n    return 1;\n}\n"
)


def test_type_checks_the_root_plugin_file_of_a_wordpress_package(
    tmp_path: Path,
) -> None:
    php_package(tmp_path, "api", WORDPRESS_MANIFEST)
    stage_file(tmp_path, "api/src/Clean.php", CLEAN_FILE)
    stage_file(tmp_path, "plugin.php", WRONG_RETURN)

    finished = run_configured(
        tmp_path, PACKAGE_CONFIGURATION, "strict-typing"
    )

    assert finished.returncode == 1
    assert "plugin.php" in finished.stdout


def test_refuses_a_silenced_root_plugin_file_of_a_wordpress_package(
    tmp_path: Path,
) -> None:
    php_package(tmp_path, "api", WORDPRESS_MANIFEST)
    stage_file(tmp_path, "api/src/Clean.php", CLEAN_FILE)
    stage_file(tmp_path, "plugin.php", SILENCED_FILE)

    finished = run_configured(
        tmp_path, PACKAGE_CONFIGURATION, "strict-typing"
    )

    assert finished.returncode == 1
    assert "plugin.php" in finished.stderr


def test_still_type_checks_the_folders_of_a_wordpress_package(
    tmp_path: Path,
) -> None:
    php_package(tmp_path, "api", WORDPRESS_MANIFEST)
    stage_file(tmp_path, "api/src/Count.php", WRONG_RETURN)
    stage_file(tmp_path, "plugin.php", CLEAN_FILE)

    finished = run_configured(
        tmp_path, PACKAGE_CONFIGURATION, "strict-typing"
    )

    assert finished.returncode == 1
    assert "Count.php" in finished.stdout


def test_leaves_root_files_alone_for_a_package_that_is_not_wordpress(
    tmp_path: Path,
) -> None:
    php_package(tmp_path, "api", LIBRARY_MANIFEST)
    stage_file(tmp_path, "api/src/Clean.php", CLEAN_FILE)
    stage_file(tmp_path, "plugin.php", WRONG_RETURN)

    finished = run_configured(
        tmp_path, PACKAGE_CONFIGURATION, "strict-typing"
    )

    assert finished.returncode == 0, finished.stdout + finished.stderr
