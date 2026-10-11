from pathlib import Path

import pytest
from test_python_structure_open_closed import report_from

_KINDS = "DECK = 'deck'\nFILE = 'file'\nNOTE = 'note'\n"
_REEXPORT = "from .kinds import DECK, FILE, NOTE\n"
_STAR_REEXPORT = "from .kinds import *\n"
_PACKAGE_IMPORT = "from app.constants import DECK, FILE, NOTE"
_CONSTANT_BRANCHES = (
    "    if kind == DECK:\n        return 0\n"
    "    if kind == FILE:\n        return 1\n"
    "    if kind == NOTE:\n        return 2\n"
    "    return -1\n"
)
_STRING_BRANCHES = (
    "    if kind == 'deck':\n        return 0\n"
    "    if kind == 'file':\n        return 1\n"
    "    if kind == 'note':\n        return 2\n"
    "    return -1\n"
)
_ROUTE_REPORT = "route compares kind to 3 strings: deck, file, note"


@pytest.mark.parametrize(
    ("application_import", "constants_import", "route_import"),
    [
        ("", _REEXPORT, _PACKAGE_IMPORT),
        ("", _STAR_REEXPORT, _PACKAGE_IMPORT),
        ("", "from app.constants.kinds import *\n", "from .constants import *"),
        ("", "", "from app.constants.kinds import *"),
        ("", "", "from .constants.kinds import *"),
        (
            "from .constants import *\n",
            _REEXPORT,
            "from app import DECK, FILE, NOTE",
        ),
    ],
)
def test_resolves_constants_through_reexports_and_star_imports(
    tmp_path: Path,
    application_import: str,
    constants_import: str,
    route_import: str,
) -> None:
    files = {
        "src/app/__init__.py": application_import,
        "src/app/constants/__init__.py": constants_import,
        "src/app/constants/kinds.py": _KINDS,
        "src/app/route.py": (
            f"{route_import}\ndef route(kind):\n{_CONSTANT_BRANCHES}"
        ),
    }

    assert report_from(tmp_path, files) == [
        f"src/app/route.py:2: {_ROUTE_REPORT}"
    ]


@pytest.mark.parametrize(
    "binding",
    [
        "def route(kind):\n",
        "def route(*, kind):\n",
        "def route(unit):\n    kind = unit.kind\n",
    ],
)
def test_local_names_shadow_a_module_string_of_the_same_name(
    tmp_path: Path, binding: str
) -> None:
    files = {
        "src/route.py": f"kind = 'default'\n{binding}{_STRING_BRANCHES}",
    }

    assert report_from(tmp_path, files) == [f"src/route.py:2: {_ROUTE_REPORT}"]
