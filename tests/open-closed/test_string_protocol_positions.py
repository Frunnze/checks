from pathlib import Path

import pytest
from open_closed_finder_support import protocol_reports_from

_TAKEN = "Email already taken"
_DECLINED = "Payment was declined by the bank"
_EXPIRED = "'Card has expired'"


@pytest.mark.parametrize(
    ("leading_arguments", "producer_line"),
    [
        ("400, ", 2),
        ("'conflict', ", 2),
        ("status, { field: 'email' },\n    ", 3),
    ],
)
def test_typescript_error_constructor_produces_a_later_message_argument(
    tmp_path: Path, leading_arguments: str, producer_line: int
) -> None:
    files = {
        "web/server.ts": (
            "export function register(status: number): void {\n"
            f"  throw new ApiError({leading_arguments}{_TAKEN!r});\n"
            "}\n"
        ),
        "worker/client.py": (
            f"def is_taken(text):\n    return text == {_TAKEN!r}\n"
        ),
    }

    assert protocol_reports_from(tmp_path, files) == [
        (
            "worker/client.py:2: branches on human-readable error text "
            f'"{_TAKEN}" produced at web/server.ts:{producer_line}; use a '
            "stable error code and handler registry"
        ),
        (
            f"web/server.ts:{producer_line}: produces human-readable error "
            f'text "{_TAKEN}" branched on at worker/client.py:2; use a '
            "stable error code and handler registry"
        ),
    ]


@pytest.mark.parametrize(
    ("elements", "consumer_line"),
    [
        (f"{_DECLINED!r}, {_EXPIRED}", 2),
        (f"{_EXPIRED}, {_DECLINED!r}", 2),
        (f"\n    {_EXPIRED},\n    {_DECLINED!r},\n  ", 4),
    ],
)
def test_typescript_array_includes_consumes_each_listed_message(
    tmp_path: Path, elements: str, consumer_line: int
) -> None:
    files = {
        "server/payment.py": (
            f"def pay():\n    raise PaymentError({_DECLINED!r})\n"
        ),
        "web/payment.ts": (
            "export function declined(text: string): boolean {\n"
            f"  return [{elements}].includes(text);\n"
            "}\n"
        ),
    }

    assert protocol_reports_from(tmp_path, files) == [
        (
            f"web/payment.ts:{consumer_line}: branches on human-readable "
            f'error text "{_DECLINED}" produced at server/payment.py:2; use '
            "a stable error code and handler registry"
        ),
        (
            "server/payment.py:2: produces human-readable error text "
            f'"{_DECLINED}" branched on at web/payment.ts:{consumer_line}; '
            "use a stable error code and handler registry"
        ),
    ]
