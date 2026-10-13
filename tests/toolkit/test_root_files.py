import json
import tempfile
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from root_files import package_root_files

WORDPRESS_TYPES = ("wordpress-plugin", "wordpress-theme")
OTHER_TYPES = ("library", "project", "wordpress-core", "symfony-bundle")
file_stems = st.text(alphabet="abcdef-_", min_size=1, max_size=6)
root_file_stems = st.lists(file_stems, max_size=4, unique=True)


def _project(
    project_root: Path, package_type: str | None, stems: list[str]
) -> Path:
    package = project_root / "api"
    package.mkdir()

    if package_type is not None:
        manifest = json.dumps({"type": package_type})
        _ = (package / "composer.json").write_text(manifest, encoding="utf-8")

    for stem in stems:
        root_file = project_root / f"{stem}.php"
        _ = root_file.write_text("<?php\n", encoding="utf-8")

    _ = (project_root / "notes.txt").write_text("", encoding="utf-8")

    return package


@given(st.sampled_from(WORDPRESS_TYPES), root_file_stems)
def test_package_root_files_property_gives_a_wordpress_package_every_root_file(
    package_type: str, stems: list[str]
) -> None:
    with tempfile.TemporaryDirectory() as temporary_directory:
        project_root = Path(temporary_directory).resolve()
        package = _project(project_root, package_type, stems)

        owned_files = package_root_files(package, project_root)

    expected_files: list[str] = []

    for stem in stems:
        expected_files.append(f"{stem}.php")

    assert owned_files == sorted(expected_files)


@given(st.sampled_from((None, *OTHER_TYPES)), root_file_stems)
def test_package_root_files_property_gives_other_packages_no_root_file(
    package_type: str | None, stems: list[str]
) -> None:
    with tempfile.TemporaryDirectory() as temporary_directory:
        project_root = Path(temporary_directory).resolve()
        package = _project(project_root, package_type, stems)

        owned_files = package_root_files(package, project_root)

    assert owned_files == []
