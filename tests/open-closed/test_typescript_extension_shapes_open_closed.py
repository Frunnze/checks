from pathlib import Path

from hypothesis import example, given, settings
from hypothesis import strategies as st
from open_closed_typescript_shapes import typescript_findings
from typescript_finder_support import CHECKS, report_from

_FINDER = CHECKS / "experimental" / "open-closed" / "typescript" / "variant_dispatches.js"
_CONSTRUCTOR_BODIES = {
    "guard": '    if (!client) throw new Error("client is required");\n',
    "type_error_guard": (
        '    if (!client) throw new TypeError("client is required");\n'
    ),
    "empty": "",
}
_CACHE_FIELDS = {
    "map": "  private readonly made = new Map<string, Transport>();\n",
    "set": "  private readonly seen = new Set<string>();\n",
    "none": "",
}


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


def test_flags_concrete_dependency_owned_by_async_factory(
    tmp_path: Path,
) -> None:
    files = {
        "src/factory.ts": (
            "interface Transport { send(): void }\n"
            "class SocketClient {}\n"
            "class TransportFactory {\n"
            "  private readonly client = new SocketClient();\n"
            "  async create(): Promise<Transport> { throw new Error(); }\n"
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


@given(
    constructor_body=st.sampled_from(sorted(_CONSTRUCTOR_BODIES)),
    cache_field=st.sampled_from(sorted(_CACHE_FIELDS)),
)
@example(constructor_body="guard", cache_field="none")
@example(constructor_body="empty", cache_field="map")
@settings(max_examples=15, deadline=None)
def test_injected_factory_property_guards_and_caches_are_not_dependencies(
    constructor_body: str, cache_field: str
) -> None:
    factory = (
        "interface Transport { send(): void }\n"
        "interface Client { request(): void }\n"
        "class TransportFactory {\n"
        f"{_CACHE_FIELDS[cache_field]}"
        "  constructor(private readonly client: Client) {\n"
        f"{_CONSTRUCTOR_BODIES[constructor_body]}"
        "  }\n"
        "  create(): Transport { throw new Error(); }\n"
        "}\n"
    )

    assert typescript_findings({"src/factory.ts": factory}) == []


def test_a_factory_that_builds_its_own_web_socket_is_reported() -> None:
    factory = (
        "interface Transport { send(): void }\n"
        "class TransportFactory {\n"
        "  private readonly socket = new WebSocket(\"wss://example.com\");\n"
        "  create(): Transport { throw new Error(); }\n"
        "}\n"
    )

    findings = typescript_findings({"src/factory.ts": factory})

    assert len(findings) == 1
    assert "WebSocket" in findings[0]
