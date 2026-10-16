"""
With scope = "changed", a source folder counts as changed when a file its
checks read changed: a file under it or its tests folder, a manifest,
lockfile or Dockerfile directly in its package, the root PHP files its
WordPress package owns - and any file at all for the root folder ".".
Domain: one source folder and one changed path. Oracle: a model of the
files a package owns - directories_with_changes lists the folder exactly
when the changed path is one of them.

Concrete inputs -> expected outputs:
- input: svc/src, changed svc/pyproject.toml (a new unused dependency)
  output: expected ["svc/src"], got [] - unused-deps never ran.
- input: ".", changed long.py
  output: expected ["."], got [] - the prefix "./" matched no git path.
- input: api/src of a wordpress-plugin package, changed root plugin.php
  output: expected ["api/src"], got [] - the root file it owns was
  ignored.
- input: svc/src, changed svc/docs/guide.md or svc2/pyproject.toml
  output: [].
"""

from pathlib import Path

import pytest

from shell_support import printed_lines, shell_function

PACKAGE_CHANGES = {
    "manifest": ("svc/src", "svc/pyproject.toml", ["svc/src"]),
    "lockfile": ("svc/src", "svc/package-lock.json", ["svc/src"]),
    "dockerfile": ("svc/src", "svc/Dockerfile", ["svc/src"]),
    "source_file": ("svc/src", "svc/src/a.py", ["svc/src"]),
    "root_folder_file": (".", "long.py", ["."]),
    "root_folder_nested_file": (".", "pkg/long.py", ["."]),
    "nested_package_file": ("svc/src", "svc/docs/guide.md", []),
    "other_package_manifest": ("svc/src", "svc2/pyproject.toml", []),
}
WORDPRESS_MANIFEST = '{"type": "wordpress-plugin"}\n'
LIBRARY_MANIFEST = '{"type": "library"}\n'


def _directories_with_changes(
    project_root: Path, source_directory: str, changed_file: str
) -> list[str]:
    finished = shell_function(
        project_root,
        f"directories_with_changes {source_directory}",
        {},
        changed_files=[changed_file],
    )

    assert finished.returncode == 0, finished.stderr

    return printed_lines(finished)


@pytest.mark.parametrize("case", sorted(PACKAGE_CHANGES))
def test_a_change_counts_for_the_folders_that_read_it(
    tmp_path: Path, case: str
) -> None:
    source_directory, changed_file, expected = PACKAGE_CHANGES[case]

    changed = _directories_with_changes(
        tmp_path, source_directory, changed_file
    )

    assert changed == expected


@pytest.mark.parametrize(
    "manifest, expected",
    [(WORDPRESS_MANIFEST, ["api/src"]), (LIBRARY_MANIFEST, [])],
)
def test_a_root_php_file_counts_only_for_its_wordpress_package(
    tmp_path: Path, manifest: str, expected: list[str]
) -> None:
    (tmp_path / "api").mkdir()
    _ = (tmp_path / "api" / "composer.json").write_text(
        manifest, encoding="utf-8"
    )
    _ = (tmp_path / "plugin.php").write_text("<?php\n", encoding="utf-8")

    changed = _directories_with_changes(tmp_path, "api/src", "plugin.php")

    assert changed == expected
