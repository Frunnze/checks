import tempfile
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st
from phpstan_settings import dead_code_paths

PROJECT_ROOT = Path("/project")
SCANNED_ROOT_FILES = {"scan-root-files": True}
folder_names = st.text(alphabet="abcdef", min_size=1, max_size=4)
listed_folders = st.lists(
    st.tuples(folder_names, folder_names), max_size=6, unique=True
)
root_file_stems = st.lists(folder_names, max_size=4, unique=True)


@given(listed_folders, folder_names)
def test_dead_code_paths_property_lists_every_folder_of_the_package(
    folders: list[tuple[str, str]], package_name: str
) -> None:
    source_directories: list[object] = []
    expected_paths: set[str] = set()

    for folder_package, folder_name in folders:
        source_directories.append(f"{folder_package}/{folder_name}")

        if folder_package == package_name:
            folder = PROJECT_ROOT / folder_package / folder_name
            expected_paths.add(str(folder))

    package = PROJECT_ROOT / package_name

    analysed = dead_code_paths(
        {}, source_directories, (package, PROJECT_ROOT)
    )

    assert set(analysed) == expected_paths


@given(root_file_stems)
def test_dead_code_paths_property_analyses_every_root_php_file(
    stems: list[str],
) -> None:
    with tempfile.TemporaryDirectory() as temporary_directory:
        project_root = Path(temporary_directory).resolve()
        expected_paths: set[str] = set()

        for stem in stems:
            root_file = project_root / f"{stem}.php"
            _ = root_file.write_text("<?php\n", encoding="utf-8")
            expected_paths.add(str(root_file))

        analysed = dead_code_paths(
            SCANNED_ROOT_FILES, [], (project_root / "api", project_root)
        )

    assert set(analysed) == expected_paths


@given(root_file_stems)
def test_dead_code_paths_property_skips_root_files_unless_scanned(
    stems: list[str],
) -> None:
    with tempfile.TemporaryDirectory() as temporary_directory:
        project_root = Path(temporary_directory).resolve()

        for stem in stems:
            root_file = project_root / f"{stem}.php"
            _ = root_file.write_text("<?php\n", encoding="utf-8")

        analysed = dead_code_paths(
            {}, [], (project_root / "api", project_root)
        )

    assert analysed == []
