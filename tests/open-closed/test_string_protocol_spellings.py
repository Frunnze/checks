from pathlib import Path

import pytest
from open_closed_finder_support import protocol_reports_from

_DECLINED = "Payment was declined by the bank"
_PYTHON_PRODUCER = f"def register():\n    raise ValueError({_DECLINED!r})\n"
_TYPESCRIPT_PRODUCER = (
    "export function register(): void {\n"
    f"  throw new Error({_DECLINED!r});\n}}\n"
)
_TYPESCRIPT_CONSUMER = (
    "export function retry(text: string): boolean {\n"
    f"  return text === {_DECLINED!r};\n}}\n"
)


@pytest.mark.parametrize(
    ("producer", "consumer", "consumer_line"),
    [
        (
            ("server.py", _PYTHON_PRODUCER),
            (
                "client.py",
                "def retry(text):\n    match text:\n"
                f"        case {_DECLINED!r}:\n            return True\n"
                "    return False\n",
            ),
            3,
        ),
        (
            ("server.py", _PYTHON_PRODUCER),
            (
                "client.py",
                "def retry(text):\n"
                f"    return text in ({_DECLINED!r}, 'Account was closed')\n",
            ),
            2,
        ),
        (
            ("server.ts", _TYPESCRIPT_PRODUCER),
            (
                "client.ts",
                "export function retry(text: string): boolean {\n"
                f"  switch (text) {{\n    case {_DECLINED!r}:\n"
                "      return true;\n  }\n  return false;\n}\n",
            ),
            3,
        ),
        (
            ("server.ts", _TYPESCRIPT_PRODUCER),
            (
                "client.ts",
                f"const DECLINED = {_DECLINED!r};\n"
                "// text === DECLINED in a comment is no branch\n"
                "export function retry(text: string): boolean {\n"
                "  return text === DECLINED;\n}\n",
            ),
            4,
        ),
        (
            (
                "server.ts",
                _TYPESCRIPT_PRODUCER.replace("throw new Error", "throw Error"),
            ),
            ("client.ts", _TYPESCRIPT_CONSUMER),
            2,
        ),
        (
            (
                "server.ts",
                f"const DECLINED = {_DECLINED!r};\n"
                "export const fail = () => { throw new Error(DECLINED); };\n",
            ),
            ("client.ts", _TYPESCRIPT_CONSUMER),
            2,
        ),
    ],
)
def test_flags_error_text_in_every_branch_spelling(
    tmp_path: Path,
    producer: tuple[str, str],
    consumer: tuple[str, str],
    consumer_line: int,
) -> None:
    producer_path, producer_source = producer
    consumer_path, consumer_source = consumer
    files = {producer_path: producer_source, consumer_path: consumer_source}

    assert protocol_reports_from(tmp_path, files) == [
        (
            f"{consumer_path}:{consumer_line}: branches on human-readable "
            f'error text "{_DECLINED}" produced at {producer_path}:2; use a '
            "stable error code and handler registry"
        )
    ]
