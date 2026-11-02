import subprocess
import sys
from pathlib import Path

from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_FINDER = (
    Path(__file__).resolve().parents[2] / "checks" / "experimental"
    / "uncapped-stream" / "python" / "uncapped_streams.py"
)


def _report_for(tmp_path: Path, source: str) -> list[str]:
    _ = (tmp_path / "download.py").write_text(source, encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="download.py",
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def _uncapped(line: int, collector: str) -> str:
    return (
        f"download.py:{line}: every chunk goes into {collector} with no"
        " size check inside the loop"
    )


def test_reports_a_cap_checked_after_the_loop(tmp_path: Path) -> None:
    source = (
        "def download(response, limit):\n"
        "    body = bytearray()\n"
        "    for chunk in response.iter_bytes():\n"
        "        body.extend(chunk)\n"
        "    if len(body) > limit:\n        raise ValueError(limit)\n"
        "    return bytes(body)\n"
    )

    assert _report_for(tmp_path, source) == [_uncapped(3, "body")]


def test_reports_async_text_and_kept_parts(tmp_path: Path) -> None:
    source = (
        "async def save(response):\n"
        "    text = ''\n"
        "    async for part in response.aiter_text():\n"
        "        text += part\n"
        "    blocks = []\n"
        "    for block in response.iter_content(8192):\n"
        "        blocks.append(block)\n"
        "    return text, blocks\n"
    )

    assert _report_for(tmp_path, source) == [
        _uncapped(3, "text"),
        _uncapped(6, "blocks"),
    ]


def test_passes_a_download_streamed_to_a_file(tmp_path: Path) -> None:
    source = (
        "def save(response, target):\n"
        "    for block in response.iter_bytes():\n"
        "        target.write(block)\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_a_cap_inside_the_loop(tmp_path: Path) -> None:
    source = (
        "def download(response, limit, log):\n"
        "    body = bytearray()\n"
        "    for chunk in response.iter_bytes():\n"
        "        body.extend(chunk)\n"
        "        if len(body) >= limit:\n            break\n"
        "    for line in response.iter_lines():\n"
        "        log(line)\n"
        "    for item in [b'a', b'b']:\n"
        "        body.extend(item)\n"
        "    return bytes(body)\n"
    )

    assert _report_for(tmp_path, source) == []


@HYPOTHESIS_SETTINGS
@given(
    iterator=st.sampled_from(
        ["iter_bytes", "iter_raw", "iter_chunked", "iter_any", "iter_text"]
    ),
    collect=st.sampled_from(
        ["kept.append(piece)", "kept.extend(piece)", "kept += piece"]
    ),
)
def test_stream_property_flags_every_collecting_shape(
    tmp_path: Path, iterator: str, collect: str
) -> None:
    source = (
        "def read(stream, kept):\n"
        f"    for piece in stream.{iterator}():\n"
        f"        {collect}\n"
        "    return kept\n"
    )

    assert _report_for(tmp_path, source) == [_uncapped(2, "kept")]
