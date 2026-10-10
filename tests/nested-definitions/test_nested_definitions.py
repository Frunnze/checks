import codecs
import keyword
import subprocess
import sys
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_CHECKS = Path(__file__).resolve().parents[2] / "checks"
_FINDER = _CHECKS / "experimental" / "nested-definitions" / "python" / "nested_definitions.py"
_MODULE = "src/features/folder/units.py"
_IDENTIFIERS = st.from_regex(r"[a-z]{3,8}", fullmatch=True).filter(
    lambda name: not keyword.iskeyword(name)
)
_LATIN1_COOKIE = "# -*- coding: latin-1 -*-\n"


def _report_for(tmp_path: Path, files: dict[str, bytes]) -> list[str]:
    for relative, source in files.items():
        module = tmp_path / relative
        module.parent.mkdir(parents=True, exist_ok=True)
        _ = module.write_bytes(source)

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="\n".join(files),
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def _nested(name: str) -> str:
    return (
        "def outer(value):\n"
        f"    def {name}(other):\n"
        "        return other\n"
        f"    return {name}(value)\n"
    )


def _encoded(source: str, encoding: str) -> bytes:
    if encoding == "bom":
        return codecs.BOM_UTF8 + source.encode("utf-8")

    return (_LATIN1_COOKIE + source + "LABEL = 'café'\n").encode("latin-1")


def _findings(report: list[str]) -> list[str]:
    return [line.split(": ", 1)[1] for line in report]


def test_reads_a_path_with_a_space(tmp_path: Path) -> None:
    module = "src/features/folder/my units.py"
    source = _nested("inner").encode("utf-8")

    assert _report_for(tmp_path, {module: source}) == [f"{module}:2: inner"]


@pytest.mark.parametrize("encoding", ("bom", "latin1_cookie"))
@HYPOTHESIS_SETTINGS
@given(name=_IDENTIFIERS)
def test_nested_property_reads_every_encoding_python_reads(
    tmp_path: Path, encoding: str, name: str
) -> None:
    source = _nested(name)
    plain = _report_for(tmp_path, {_MODULE: source.encode("utf-8")})
    encoded = _report_for(tmp_path, {_MODULE: _encoded(source, encoding)})

    assert _findings(encoded) == _findings(plain) == [name]
