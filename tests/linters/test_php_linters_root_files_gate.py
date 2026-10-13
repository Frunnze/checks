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
OVERLONG_FILE = (
    CLEAN_FILE + "\n$link_checkup_greeting = '" + "a" * 80 + "';\n"
)


def test_lints_the_root_plugin_file_of_a_wordpress_package(
    tmp_path: Path,
) -> None:
    php_package(tmp_path, "api", WORDPRESS_MANIFEST)
    stage_file(tmp_path, "api/src/Clean.php", CLEAN_FILE)
    stage_file(tmp_path, "plugin.php", OVERLONG_FILE)

    finished = run_configured(tmp_path, PACKAGE_CONFIGURATION, "linters")

    assert finished.returncode == 1
    assert "plugin.php" in finished.stdout


def test_still_lints_the_folders_of_a_wordpress_package(
    tmp_path: Path,
) -> None:
    php_package(tmp_path, "api", WORDPRESS_MANIFEST)
    stage_file(tmp_path, "api/src/Overlong.php", OVERLONG_FILE)
    stage_file(tmp_path, "plugin.php", CLEAN_FILE)

    finished = run_configured(tmp_path, PACKAGE_CONFIGURATION, "linters")

    assert finished.returncode == 1
    assert "Overlong.php" in finished.stdout


def test_leaves_root_files_alone_for_a_package_that_is_not_wordpress(
    tmp_path: Path,
) -> None:
    php_package(tmp_path, "api", LIBRARY_MANIFEST)
    stage_file(tmp_path, "api/src/Clean.php", CLEAN_FILE)
    stage_file(tmp_path, "plugin.php", OVERLONG_FILE)

    finished = run_configured(tmp_path, PACKAGE_CONFIGURATION, "linters")

    assert finished.returncode == 0, finished.stdout + finished.stderr
