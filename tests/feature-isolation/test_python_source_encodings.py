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
_FINDERS = _CHECKS / "experimental" / "feature-isolation" / "python"
_IMPORTER = "src/features/notes/router.py"
_ENCODINGS = ("bom", "latin1_cookie")
_NAMES = st.from_regex(r"[a-z]{3,8}", fullmatch=True).filter(
    lambda name: not keyword.iskeyword(name)
)
_LATIN1_COOKIE = "# -*- coding: latin-1 -*-\n"


def _findings_for(
    tmp_path: Path, finder: str, relative: str, source: bytes
) -> list[str]:
    module = tmp_path / relative
    module.parent.mkdir(parents=True, exist_ok=True)
    _ = module.write_bytes(source)

    finished = subprocess.run(
        [sys.executable, str(_FINDERS / finder), "src"],
        input=relative,
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return [line.split(": ", 1)[1] for line in finished.stdout.splitlines()]


def _encoded(source: str, encoding: str) -> bytes:
    if encoding == "bom":
        return codecs.BOM_UTF8 + source.encode("utf-8")

    return (_LATIN1_COOKIE + source + "LABEL = 'café'\n").encode("latin-1")


@pytest.mark.parametrize("encoding", _ENCODINGS)
@HYPOTHESIS_SETTINGS
@given(name=_NAMES.filter(lambda name: name != "notes"))
def test_feature_imports_property_reads_every_encoding_python_reads(
    tmp_path: Path, encoding: str, name: str
) -> None:
    source = f"from features.{name} import due\n"
    finder = "feature_imports.py"
    plain = _findings_for(
        tmp_path, finder, _IMPORTER, source.encode("utf-8")
    )
    encoded = _findings_for(
        tmp_path, finder, _IMPORTER, _encoded(source, encoding)
    )

    assert encoded == plain == [f"features.{name}"]


@pytest.mark.parametrize("encoding", _ENCODINGS)
@HYPOTHESIS_SETTINGS
@given(name=_NAMES)
def test_shared_usage_property_reads_every_encoding_python_reads(
    tmp_path: Path, encoding: str, name: str
) -> None:
    source = "def now():\n    return 1\n"
    module = f"src/shared/{name}.py"
    finder = "shared_usage.py"
    plain = _findings_for(tmp_path, finder, module, source.encode("utf-8"))
    encoded = _findings_for(
        tmp_path, finder, module, _encoded(source, encoding)
    )

    assert encoded == plain == ["no feature imports it"]
