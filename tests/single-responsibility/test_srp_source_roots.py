from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from srp_support import run_project, unit_named

from srp_imports import deepest_root, is_marked_source_root, source_root

HELPERS = (
    "import requests\n\n\ndef fetch(url):\n    return requests.get(url)\n"
)
IMPORT_FORMS = (
    "from {package}.helpers import fetch",
    "from .helpers import fetch",
)
PYTHON_MARKERS = ("pyproject.toml", "setup.cfg", "setup.py")
FOLDER_NAMES = st.sampled_from(["src", "app", "code", "lib", "proj"])
SHARED_TEMPORARY_DIRECTORY = [
    HealthCheck.function_scoped_fixture,
    HealthCheck.too_slow,
]


def write_syncing_package(
    project: Path, package: str, import_line: str
) -> None:
    package_directory = project / package
    package_directory.mkdir(parents=True)
    (package_directory / "__init__.py").write_text("")
    (package_directory / "helpers.py").write_text(HELPERS)
    main_source = (
        import_line.format(package=package)
        + "\n\n\ndef sync(url, path):\n"
        + "    with open(path, 'w') as handle:\n"
        + "        handle.write(fetch(url).text)\n"
    )
    (package_directory / "main.py").write_text(main_source)


def sync_coefficient(project: Path) -> float:
    report = run_project(project)
    return unit_named(report, "<module>.sync")["coefficient"]


@pytest.mark.parametrize("import_form", IMPORT_FORMS)
def test_package_named_src_resolves_like_any_package(tmp_path, import_form):
    control = tmp_path / "control"
    source_package = tmp_path / "source_package"
    write_syncing_package(control, "app", import_form)
    write_syncing_package(source_package, "src", import_form)

    assert sync_coefficient(control) == 0.5
    assert sync_coefficient(source_package) == sync_coefficient(control)


@pytest.mark.parametrize("import_form", IMPORT_FORMS)
def test_scanned_package_resolves_imports_like_its_parent(tmp_path, import_form):
    write_syncing_package(tmp_path, "app", import_form)
    (tmp_path / "app" / "requests.py").write_text("def get(url):\n    return url\n")

    assert sync_coefficient(tmp_path) == 0.5
    assert sync_coefficient(tmp_path / "app") == sync_coefficient(tmp_path)


def test_ancestor_named_src_above_the_scan_does_not_change_verdict(tmp_path):
    outside = tmp_path / "code" / "proj"
    inside_source = tmp_path / "src" / "proj"
    write_syncing_package(outside, "app", IMPORT_FORMS[0])
    write_syncing_package(inside_source, "app", IMPORT_FORMS[0])

    assert sync_coefficient(outside) == 0.5
    assert sync_coefficient(inside_source) == sync_coefficient(outside)


def test_marker_above_the_scan_root_is_ignored(tmp_path):
    (tmp_path / "pyproject.toml").write_text("")
    project = tmp_path / "proj"
    write_syncing_package(project, "app", IMPORT_FORMS[0])

    assert sync_coefficient(project) == 0.5


@settings(suppress_health_check=SHARED_TEMPORARY_DIRECTORY, deadline=None)
@given(
    st.lists(FOLDER_NAMES, min_size=1, max_size=4),
    st.integers(min_value=0, max_value=4),
    st.sets(st.integers(min_value=0, max_value=4)),
)
def test_source_root_property_never_leaves_the_scan_root(
    tmp_path_factory, folders, scan_depth, marked_depths
):
    base = tmp_path_factory.mktemp("tree").resolve()
    directories = [base]
    for folder in folders:
        directories.append(directories[-1] / folder)
    directories[-1].mkdir(parents=True)
    for depth in marked_depths:
        if depth < len(directories):
            (directories[depth] / "pyproject.toml").write_text("")
    file = directories[-1] / "module.py"
    file.write_text("")
    scan_root = directories[min(scan_depth, len(directories) - 1)]

    chosen = source_root(file, [scan_root], [])

    assert chosen.is_relative_to(scan_root)
    assert file.is_relative_to(chosen)


@settings(suppress_health_check=SHARED_TEMPORARY_DIRECTORY, deadline=None)
@given(FOLDER_NAMES, st.booleans(), st.sampled_from(PYTHON_MARKERS + ("",)))
def test_is_marked_source_root_property_packages_named_src_need_a_marker(
    tmp_path_factory, name, is_package, marker
):
    directory = tmp_path_factory.mktemp("marker") / name
    directory.mkdir()
    if is_package:
        (directory / "__init__.py").write_text("")
    if marker:
        (directory / marker).write_text("")

    expected = bool(marker) or (name == "src" and not is_package)

    assert is_marked_source_root(directory, PYTHON_MARKERS) == expected


@given(st.lists(st.lists(FOLDER_NAMES, max_size=4), max_size=5))
def test_deepest_root_property_returns_the_longest_containing_root(
    root_folder_lists,
):
    path = Path("/", "base", "src", "app", "lib", "module.py")
    roots = [Path("/", "base", *folders) for folders in root_folder_lists]
    containing = [root for root in roots if path.is_relative_to(root)]

    chosen = deepest_root(path, roots)

    if not containing:
        assert chosen is None
        return
    assert chosen in containing
    assert len(chosen.parts) == max(len(root.parts) for root in containing)
