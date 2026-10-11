from pathlib import Path

import pytest
from srp_support import run_project, unit_named

NETWORK_HELPER = (
    "import httpx\n\n\n"
    "def fetch(address):\n"
    "    return httpx.get(address).text\n"
)


def sync_source(import_line: str) -> str:
    return (
        "from pathlib import Path\n\n" + import_line + "\n\n\n"
        "def sync(address):\n"
        "    Path(address).write_text(fetch(address))\n"
    )


def write_files(root: Path, files: dict[str, str]) -> None:
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


MIXED_LAYOUTS = {
    "namespace folder inside a package root": (
        "src",
        {
            "__init__.py": "",
            "core/net.py": NETWORK_HELPER,
            "main.py": sync_source("from src.core.net import fetch"),
        },
    ),
    "caller in a namespace folder of a package root": (
        "src",
        {
            "__init__.py": "",
            "net.py": NETWORK_HELPER,
            "core/main.py": sync_source("from src.net import fetch"),
        },
    ),
    "package inside a namespace folder": (
        "app",
        {
            "core/core/__init__.py": "",
            "core/core/net.py": NETWORK_HELPER,
            "main.py": sync_source("from core.core.net import fetch"),
        },
    ),
}


@pytest.mark.parametrize(
    "scanned_folder, files", MIXED_LAYOUTS.values(), ids=list(MIXED_LAYOUTS)
)
def test_files_of_one_importable_project_resolve_each_other(
    tmp_path, scanned_folder, files
):
    scanned = tmp_path / "user-service" / scanned_folder
    write_files(scanned, files)

    unit = unit_named(run_project(scanned), "<module>.sync")

    assert unit["entities"] == ["filesystem", "network"]
