import json
import subprocess
import sys
from pathlib import Path

import pytest
from srp_support import CHECK, run_project, unit_named, write_split_project

LINK_TARGETS = {
    "loop": "link.py",
    "dangling": "missing.py",
    "directory_named_py": "../elsewhere",
}


@pytest.mark.parametrize("suffix", [".py", ".ts"])
@pytest.mark.parametrize("clients_per_group", [1, 2])
@pytest.mark.parametrize("relative_first", [False, True])
def test_overlapping_input_spellings_do_not_change_the_report(
    tmp_path, suffix, clients_per_group, relative_first
):
    root = tmp_path / "src"
    write_split_project(root, suffix)
    if clients_per_group == 1:
        for group in range(2):
            (root / f"client_{group}_1{suffix}").unlink()
    command = [sys.executable, str(CHECK / "srp_check.py"), "--json"]
    baseline = subprocess.run(
        command + [str(root)], capture_output=True, text=True, check=False
    )
    alias = tmp_path / "linked-source"
    alias.symlink_to(root, target_is_directory=True)
    inputs = [str(root), "src/../src", f"src/worker{suffix}", str(alias)]
    overlapping = subprocess.run(
        command + (list(reversed(inputs)) if relative_first else inputs),
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert baseline.returncode in {0, 1}, baseline.stderr
    assert overlapping.returncode == baseline.returncode, overlapping.stderr
    original, repeated = json.loads(baseline.stdout), json.loads(overlapping.stdout)
    assert len(repeated["files"]) == len(original["files"])
    assert repeated["coefficient"] == original["coefficient"]


@pytest.mark.parametrize("suffix", [".py", ".ts"])
def test_callers_resolve_with_mixed_absolute_and_relative_files(tmp_path, suffix):
    root = tmp_path / "src"
    write_split_project(root, suffix)
    result = subprocess.run(
        [sys.executable, str(CHECK / "srp_check.py"), "--json"]
        + [str(root / f"worker{suffix}")]
        + [str(path.relative_to(tmp_path)) for path in sorted(root.glob("client*"))],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1, result.stderr
    owner = unit_named(json.loads(result.stdout), "<module>.Worker")
    assert owner["coefficient"] == 0.5


@pytest.mark.parametrize("link", sorted(LINK_TARGETS))
def test_directory_scan_skips_symbolic_links_like_find(tmp_path, link):
    root = tmp_path / "src"
    root.mkdir()
    (root / "plain.py").write_text("VALUE = 1\n")
    (tmp_path / "elsewhere").mkdir()
    (tmp_path / "elsewhere" / "outside.py").write_text("VALUE = 2\n")
    (root / "link.py").symlink_to(LINK_TARGETS[link])

    report = run_project(root)

    assert [Path(file["path"]).name for file in report["files"]] == [
        "plain.py"
    ]
