import re
import tempfile
import warnings
from pathlib import Path

from hypothesis import example, given, settings
from hypothesis import strategies as st
from open_closed_finder_support import protocol_reports_from, written_paths
from protocol_strings import reports_for

_WORDS = st.sampled_from(
    [
        "payment", "was", "declined", "by", "the", "bank", "account",
        "name", "already", "exists", "remote", "service", "did", "not",
    ]
)
_ACCENTED_WORDS = st.sampled_from(
    ["été", "refusé", "Müller", "año", "naïve", "façade"]
)
_COMMENTS = st.lists(
    st.sampled_from(
        [
            "// We don't retry here.",
            "// It's the bank's call.",
            "/* the user's input */",
            "// plain note",
            "/** Doesn't throw. */",
        ]
    ),
    max_size=3,
)
_TEMPLATE_BODIES = st.sampled_from(
    [
        "\\u{1F44D} done",
        "\\u{41}BC",
        "C:\\Users\\me",
        "line\\x41",
        "tab\\there",
    ]
)
_LINE_NUMBER = re.compile(r":[0-9]+")
_DECLINED = "Payment was declined by the bank"
_REFUSED = "Le paiement a été refusé"


def test_flags_behavior_selected_by_python_response_text_in_typescript(
    tmp_path: Path,
) -> None:
    files = {
        "server/account.py": (
            "def register():\n"
            "    return JsonResponse(content='Account name already exists')\n"
        ),
        "web/account.ts": (
            "export function fieldFor(detail: string): string {\n"
            '  return detail === "Account name already exists" ? "name" : "form";\n'
            "}\n"
        ),
    }

    assert protocol_reports_from(tmp_path, files) == [
        (
            'web/account.ts:2: branches on human-readable error text "Account '
            'name already exists" produced at server/account.py:2; use a '
            "stable error code and handler registry"
        )
    ]


def test_allows_stable_machine_error_codes(tmp_path: Path) -> None:
    files = {
        "server/account.py": (
            "def register():\n"
            "    return JsonResponse(content='account_name_exists')\n"
        ),
        "web/account.ts": (
            "export function fieldFor(code: string): string {\n"
            '  return code === "account_name_exists" ? "name" : "form";\n'
            "}\n"
        ),
    }

    assert protocol_reports_from(tmp_path, files) == []


def test_allows_human_message_used_only_for_display(tmp_path: Path) -> None:
    files = {
        "server/account.py": (
            "def register():\n"
            "    return JsonResponse(content='Account name already exists')\n"
        ),
        "web/account.ts": (
            'export const shown = { message: "Account name already exists" };\n'
        ),
    }

    assert protocol_reports_from(tmp_path, files) == []


def test_flags_typescript_error_text_compared_in_python(
    tmp_path: Path,
) -> None:
    files = {
        "web/error.ts": (
            'export const failure = { error: "Remote service did not answer" };\n'
        ),
        "worker/retry.py": (
            "def should_retry(reason):\n"
            "    return reason == 'Remote service did not answer'\n"
        ),
    }

    assert protocol_reports_from(tmp_path, files) == [
        (
            'worker/retry.py:2: branches on human-readable error text "Remote '
            'service did not answer" produced at web/error.ts:1; use a stable '
            "error code and handler registry"
        )
    ]


def _protocol_reports(files: dict[str, str]) -> list[str]:
    with tempfile.TemporaryDirectory() as directory:
        paths = written_paths(Path(directory), files)

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            reports = reports_for(paths)

        return [report.replace(f"{directory}/", "") for report in reports]


@st.composite
def _messages(draw: st.DrawFn, accented: bool = False) -> str:
    words = draw(st.lists(_WORDS, min_size=3, max_size=6))

    if accented:
        position = draw(st.integers(0, len(words)))
        words.insert(position, draw(_ACCENTED_WORDS))

    text = " ".join(words) + " for this request"

    return text[0].upper() + text[1:]


def _producer(message: str, constructor: str = "PaymentError") -> str:
    return (
        "export function fail(): never {\n"
        f'  throw new {constructor}("{message}");\n'
        "}\n"
    )


def _consumer(
    message: str,
    quote: str = '"',
    above: list[str] | None = None,
    below: list[str] | None = None,
) -> str:
    comments_above = "".join(f"{line}\n" for line in above or [])
    comments_below = "".join(f"{line}\n" for line in below or [])

    return (
        f"{comments_above}"
        "export function retry(message: string): boolean {\n"
        f"  return message === {quote}{message}{quote};\n"
        "}\n"
        f"{comments_below}"
    )


@given(message=_messages(), above=_COMMENTS, below=_COMMENTS)
@example(
    message=_DECLINED,
    above=["// We don't retry here."],
    below=["// It's the bank's call."],
)
@settings(max_examples=60, deadline=None)
def test_protocol_property_comments_never_change_the_verdict(
    message: str, above: list[str], below: list[str]
) -> None:
    plain = _protocol_reports(
        {"producer.ts": _producer(message), "consumer.ts": _consumer(message)}
    )
    commented = _protocol_reports(
        {
            "producer.ts": _producer(message),
            "consumer.ts": _consumer(message, above=above, below=below),
        }
    )

    assert plain
    assert [_LINE_NUMBER.sub(":N", line) for line in commented] == [
        _LINE_NUMBER.sub(":N", line) for line in plain
    ]


@given(
    message=_messages(accented=True), quote=st.sampled_from(['"', "'", "`"])
)
@example(message=_REFUSED, quote="`")
@settings(max_examples=60, deadline=None)
def test_protocol_property_quote_style_never_changes_the_verdict(
    message: str, quote: str
) -> None:
    double_quoted = _protocol_reports(
        {"producer.ts": _producer(message), "consumer.ts": _consumer(message)}
    )
    other_quoted = _protocol_reports(
        {
            "producer.ts": _producer(message),
            "consumer.ts": _consumer(message, quote),
        }
    )

    assert double_quoted
    assert other_quoted == double_quoted


@given(
    message=_messages(),
    constructor=st.sampled_from(["Error", "TypeError", "PaymentError"]),
)
@example(message=_DECLINED, constructor="Error")
@settings(max_examples=60, deadline=None)
def test_protocol_property_error_constructor_matches_the_python_twin(
    message: str, constructor: str
) -> None:
    typescript = _protocol_reports(
        {
            "producer.ts": _producer(message, constructor),
            "consumer.ts": _consumer(message),
        }
    )
    python = _protocol_reports(
        {
            "producer.py": (
                f"def fail():\n    raise {constructor}({message!r})\n"
            ),
            "consumer.ts": _consumer(message),
        }
    )

    assert bool(typescript) == bool(python)


@given(body=_TEMPLATE_BODIES, tagged=st.booleans())
@example(body="\\u{1F44D} done", tagged=False)
@settings(max_examples=30, deadline=None)
def test_protocol_property_valid_template_literals_never_crash(
    body: str, tagged: bool
) -> None:
    tag = "String.raw" if tagged else ""
    source = (
        f"export const shown = {tag}`{body}`;\n"
        "// write `\\u` then four hex digits\n"
    )

    assert _protocol_reports({"unit.ts": source}) == []
