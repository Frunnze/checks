import pytest
from srp_support import run_project, unit_named
from test_srp_mixed_package_roots import (
    NETWORK_HELPER,
    sync_source,
    write_files,
)

STAR_LAYOUTS = {
    "re-exported by the package": {
        "app/__init__.py": "from .net import *\n",
        "app/net.py": NETWORK_HELPER,
        "app/main.py": sync_source("from app import fetch"),
    },
    "re-exported through two packages": {
        "app/__init__.py": "from .inner import *\n",
        "app/inner/__init__.py": "from .net import *\n",
        "app/inner/net.py": NETWORK_HELPER,
        "app/main.py": sync_source("from app import fetch"),
    },
    "imported by the caller": {
        "app/__init__.py": "",
        "app/net.py": NETWORK_HELPER,
        "app/main.py": sync_source("from app.net import *"),
    },
}


@pytest.mark.parametrize(
    "files", STAR_LAYOUTS.values(), ids=list(STAR_LAYOUTS)
)
def test_star_imported_helpers_keep_their_entity(tmp_path, files):
    write_files(tmp_path, files)

    unit = unit_named(run_project(tmp_path), "<module>.sync")

    assert unit["entities"] == ["filesystem", "network"]
