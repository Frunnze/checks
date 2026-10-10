import subprocess
import sys
from pathlib import Path

import pytest
from typescript_finder_support import CHECKS

_FINDERS = CHECKS / "experimental" / "open-closed" / "python"
_PYTHON_FINDERS = ["protocol_strings.py", "variant_dispatches.py"]
_DECLINED = "Payment was declined by the bank"
_ADVICE = "use a stable error code and handler registry"
_ROUTE = (
    "def route(kind):\n"
    "    if kind == 'deck':\n        return 0\n"
    "    if kind == 'file':\n        return 1\n"
    "    if kind == 'note':\n        return 2\n"
    "    return -1\n"
)
_PRODUCER = f"def register():\n    raise ValueError({_DECLINED!r})\n"
_CONSUMER = f"def retry(text):\n    return text == {_DECLINED!r}\n"
_SERVER = (
    "def register(kind):\n"
    "    if kind == 'deck':\n"
    "        raise ValueError('Le paiement a été refusé')\n"
    "    if kind == 'file':\n        return 1\n"
    "    if kind == 'note':\n        return 2\n"
    "    return -1\n"
)
_CLIENT = "def retry(text):\n    return text == 'Le paiement a été refusé'\n"
_ENCODED_SERVERS = {
    "utf8_bom": (
        b"\xef\xbb\xbf" + _SERVER.encode(),
        _SERVER.encode(),
    ),
    "latin1_cookie": (
        f"# coding: latin-1\n{_SERVER}".encode("latin-1"),
        f"# coding: utf-8\n{_SERVER}".encode(),
    ),
}


def _finder_output(
    root: Path, finder: str, files: dict[str, bytes]
) -> list[str]:
    for relative, content in files.items():
        module = root / relative
        module.parent.mkdir(parents=True, exist_ok=True)
        _ = module.write_bytes(content)

    finished = subprocess.run(
        [sys.executable, str(_FINDERS / finder)],
        input="".join(f"{relative}\n" for relative in files),
        capture_output=True,
        text=True,
        check=True,
        cwd=root,
    )

    return finished.stdout.splitlines()


@pytest.mark.parametrize("folder", ["my folder", "tab\tfolder"])
def test_finders_read_one_path_per_input_line(
    tmp_path: Path, folder: str
) -> None:
    route = f"{folder}/route.py"
    producer = f"{folder}/server.py"
    consumer = f"{folder}/client.py"
    dispatches = _finder_output(
        tmp_path, "variant_dispatches.py", {route: _ROUTE.encode()}
    )
    protocol = _finder_output(
        tmp_path,
        "protocol_strings.py",
        {producer: _PRODUCER.encode(), consumer: _CONSUMER.encode()},
    )

    assert dispatches == [
        f"{route}:1: route compares kind to 3 strings: deck, file, note"
    ]
    assert protocol == [
        (
            f'{consumer}:2: branches on human-readable error text '
            f'"{_DECLINED}" produced at {producer}:2; {_ADVICE}'
        )
    ]


@pytest.mark.parametrize("encoding", sorted(_ENCODED_SERVERS))
@pytest.mark.parametrize("finder", _PYTHON_FINDERS)
def test_finders_parse_modules_the_way_cpython_does(
    tmp_path: Path, finder: str, encoding: str
) -> None:
    encoded, utf8_twin = _ENCODED_SERVERS[encoding]
    client = _CLIENT.encode()
    expected = _finder_output(
        tmp_path / "twin",
        finder,
        {"server.py": utf8_twin, "client.py": client},
    )
    found = _finder_output(
        tmp_path / "encoded",
        finder,
        {"server.py": encoded, "client.py": client},
    )

    assert expected
    assert found == expected


def test_protocol_finder_scans_typescript_with_latin1_bytes(
    tmp_path: Path,
) -> None:
    files = {
        "server.py": _PRODUCER.encode(),
        "client.ts": (
            b"// caf\xe9\n"
            b"export function retry(message: string): boolean {\n"
            b'  return message === "Payment was declined by the bank";\n'
            b"}\n"
        ),
    }

    assert _finder_output(tmp_path, "protocol_strings.py", files) == [
        (
            'client.ts:3: branches on human-readable error text '
            f'"{_DECLINED}" produced at server.py:2; {_ADVICE}'
        )
    ]
