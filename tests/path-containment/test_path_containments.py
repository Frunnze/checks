import subprocess
import sys
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_FINDER = (
    Path(__file__).resolve().parents[2] / "checks" / "experimental"
    / "path-containment" / "python" / "path_containments.py"
)
_ESCAPE = (
    "onto a folder and opens the result without checking it stays inside -"
    " resolve it and test is_relative_to()"
)


def _report_for(tmp_path: Path, source: str) -> list[str]:
    _ = (tmp_path / "files.py").write_text(source, encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="files.py",
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def _escaping(line: int, handler: str, parameter: str) -> str:
    return (
        f"files.py:{line}: {handler}() joins the request value {parameter}"
        f" {_ESCAPE}"
    )


def test_reports_handlers_that_open_a_joined_name(tmp_path: Path) -> None:
    source = (
        "import os\n"
        "from pathlib import Path\n"
        "UPLOADS = Path('/srv/uploads')\n"
        "@api.get('/files/{name}')\n"
        "def download(name):\n"
        "    return FileResponse(os.path.join('/srv/files', name))\n"
        "@web.route('/raw/<filename>')\n"
        "def raw(filename):\n"
        "    return (UPLOADS / filename).read_bytes()\n"
    )

    assert _report_for(tmp_path, source) == [
        _escaping(6, "download", "name"),
        _escaping(9, "raw", "filename"),
    ]


def test_passes_contained_paths_and_plain_functions(tmp_path: Path) -> None:
    source = (
        "import os\n"
        "from pathlib import Path\n"
        "UPLOADS = Path('/srv/uploads')\n"
        "@api.get('/safe/{name}')\n"
        "def safe(name):\n"
        "    safe_name = os.path.basename(name)\n"
        "    return FileResponse(os.path.join('/srv', safe_name))\n"
        "@api.delete('/files/{name}')\n"
        "def remove(name):\n"
        "    target = (UPLOADS / name).resolve()\n"
        "    if not target.is_relative_to(UPLOADS):\n"
        "        raise ValueError(name)\n"
        "    target.unlink()\n"
        "def load(root, name):\n"
        "    return open(os.path.join(root, name)).read()\n"
    )

    assert _report_for(tmp_path, source) == []


@HYPOTHESIS_SETTINGS
@given(
    method=st.sampled_from(["get", "post", "put", "delete", "route"]),
    opener=st.sampled_from(["open", "send_file", "FileResponse"]),
)
def test_route_property_flags_every_route_and_opener(
    tmp_path: Path, method: str, opener: str
) -> None:
    source = (
        "import os\n"
        f"@app.{method}('/files/<path>')\n"
        "def serve(path):\n"
        f"    return {opener}(os.path.join('/srv', path))\n"
    )

    assert _report_for(tmp_path, source) == [_escaping(4, "serve", "path")]
