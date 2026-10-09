from pathlib import Path

from typescript_finder_support import CHECKS, report_from

_FINDER = CHECKS / "experimental" / "open-closed" / "typescript" / "variant_dispatches.js"


def test_flags_concrete_dependency_owned_by_abstract_factory(
    tmp_path: Path,
) -> None:
    files = {
        "src/factory.ts": (
            "interface Transport { send(): void }\n"
            "class SocketClient {}\n"
            "class TransportFactory {\n"
            "  private readonly client = new SocketClient();\n"
            "  create(): Transport { throw new Error(); }\n"
            "}\n"
        ),
    }

    assert report_from(_FINDER, tmp_path, files) == [
        (
            "src/factory.ts:3: TransportFactory leaks concrete dependencies "
            "while creating Transport: SocketClient"
        )
    ]


def test_allows_dependency_injected_into_abstract_factory(
    tmp_path: Path,
) -> None:
    files = {
        "src/factory.ts": (
            "interface Transport { send(): void }\n"
            "interface Client { request(): void }\n"
            "class TransportFactory {\n"
            "  constructor(private readonly client: Client) {}\n"
            "  create(): Transport { throw new Error(); }\n"
            "}\n"
        ),
    }

    assert report_from(_FINDER, tmp_path, files) == []
