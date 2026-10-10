import posixpath
import tempfile
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from configuration_support import toml_list, written_configuration
from shell_support import SOURCE_CONFIGURATION, printed_lines, shell_function

FILTER_SETTINGS = settings(max_examples=40, deadline=None)
finding_paths = st.builds(
    lambda folder, name: f"{folder}/src/{name}",
    st.sampled_from(["svc", "other-svc"]),
    st.sampled_from(["a.ts", "a.tsx", "util.py"]),
)
finding_formats = st.sampled_from(["{} (400 lines)", "{}:3: helper"])
nested_findings = finding_paths.map(lambda path: f"{path}:3: helper")
whitelist_entries = st.one_of(
    nested_findings, finding_paths, st.just(""), st.just(" ")
)
changed_paths = st.one_of(
    finding_paths, st.sampled_from(["a.ts", "util.py", "src/a.ts"])
)
source_folders = st.sampled_from(["svc/src", "src", "svc/src2", "a/src"])
changed_in_folders = st.builds(
    lambda folder, name: f"{folder}/{name}",
    st.sampled_from(
        ["svc/src", "svc/tests", "src", "tests", "src2", "a/src", "a/tests"]
    ),
    st.sampled_from(["a.py", "b.ts"]),
)


def _tests_folder_of(source_folder: str) -> str:
    package = posixpath.dirname(source_folder)

    return posixpath.join(package, "tests")


def _has_changes(source_folder: str, changed: list[str]) -> bool:
    prefixes = (f"{source_folder}/", f"{_tests_folder_of(source_folder)}/")

    for path in changed:
        if path.startswith(prefixes):
            return True

    return False


@FILTER_SETTINGS
@given(
    st.lists(nested_findings, min_size=1, max_size=6, unique=True),
    st.lists(whitelist_entries, max_size=4),
)
def test_whitelist_property_removes_exactly_the_listed_findings(
    findings: list[str], entries: list[str]
) -> None:
    with tempfile.TemporaryDirectory() as directory_name:
        project_root = Path(directory_name)
        whitelist = f"whitelist = {toml_list(entries)}\n"
        _ = written_configuration(
            project_root,
            SOURCE_CONFIGURATION + "[checks.nested-definitions]\n" + whitelist,
        )
        finished = shell_function(
            project_root,
            "reportable_findings",
            {"check_name": "nested-definitions"},
            "".join(f"{finding}\n" for finding in findings),
        )

    assert printed_lines(finished) == [
        finding for finding in findings if finding not in entries
    ]


@FILTER_SETTINGS
@given(
    st.lists(finding_paths, min_size=1, max_size=6, unique=True),
    st.lists(changed_paths, min_size=1, max_size=4, unique=True),
    finding_formats,
)
def test_changed_scope_property_keeps_exactly_the_changed_files(
    paths: list[str], changed: list[str], finding_format: str
) -> None:
    findings = [finding_format.format(path) for path in paths]

    with tempfile.TemporaryDirectory() as directory_name:
        finished = shell_function(
            Path(directory_name),
            "within_scope",
            {"check_scope": "changed", "changed_files": "\n".join(changed)},
            "".join(f"{finding}\n" for finding in findings),
        )

    assert printed_lines(finished) == [
        finding_format.format(path) for path in paths if path in changed
    ]


@FILTER_SETTINGS
@given(
    st.lists(source_folders, min_size=1, max_size=3, unique=True),
    st.lists(changed_in_folders, min_size=1, max_size=4, unique=True),
)
def test_directories_with_changes_property_matches_the_changed_files(
    folders: list[str], changed: list[str]
) -> None:
    with tempfile.TemporaryDirectory() as directory_name:
        finished = shell_function(
            Path(directory_name),
            f"directories_with_changes {' '.join(folders)}",
            {"changed_files": "\n".join(changed)},
        )

    assert printed_lines(finished) == [
        folder for folder in folders if _has_changes(folder, changed)
    ]
