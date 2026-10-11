"""
Branching on human-readable error text couples the file that produces the
text to the file that compares it, so the finding must name a line in
each participating file; a changed-scope run keeps only lines that start
with a changed path, so a producer added after its consumer must still get
its own line. Domain: generated messages of 3-6 words, produced in Python
or TypeScript and branched on in Python or TypeScript. Oracle: invariant -
every participating file is the path of exactly one report line.

Concrete inputs -> expected outputs:
- input:
      server.py: raise ValueError('Payment was declined by the bank')
      client.py: return text == 'Payment was declined by the bank'
  output: ["client.py:2: branches on human-readable error text \"Payment
  was declined by the bank\" produced at server.py:2; use a stable error
  code and handler registry", "server.py:2: produces human-readable error
  text \"Payment was declined by the bank\" branched on at client.py:2;
  use a stable error code and handler registry"].
- input (falsifying example, now pinned as @example): the same pair.
  output: expected a line at server.py, got only the client.py line.
"""

import tempfile
from pathlib import Path

from hypothesis import example, given, settings
from hypothesis import strategies as st
from open_closed_finder_support import written_paths
from protocol_strings import reports_for

_WORDS = st.sampled_from(
    ["payment", "was", "declined", "by", "the", "bank", "account", "name"]
)
_PRODUCERS = {
    "server.py": "def register():\n    raise ValueError({message!r})\n",
    "server.ts": (
        "export function register(): void {{\n"
        "  throw new Error({message!r});\n}}\n"
    ),
}
_CONSUMERS = {
    "client.py": "def retry(text):\n    return text == {message!r}\n",
    "client.ts": (
        "export function retry(text: string): boolean {{\n"
        "  return text === {message!r};\n}}\n"
    ),
}


@st.composite
def _messages(draw: st.DrawFn) -> str:
    words = draw(st.lists(_WORDS, min_size=3, max_size=6))
    text = " ".join(words) + " for this request"

    return text[0].upper() + text[1:]


def _report_paths(files: dict[str, str]) -> list[str]:
    with tempfile.TemporaryDirectory() as directory:
        paths = written_paths(Path(directory), files)
        reports = reports_for(paths)

    return sorted(
        Path(report.split(":", 1)[0]).name for report in reports
    )


@given(
    message=_messages(),
    producer=st.sampled_from(sorted(_PRODUCERS)),
    consumer=st.sampled_from(sorted(_CONSUMERS)),
)
@example(
    message="Payment was declined by the bank",
    producer="server.py",
    consumer="client.py",
)
@settings(max_examples=60, deadline=None)
def test_protocol_property_reports_at_every_participating_file(
    message: str, producer: str, consumer: str
) -> None:
    files = {
        producer: _PRODUCERS[producer].format(message=message),
        consumer: _CONSUMERS[consumer].format(message=message),
    }

    assert _report_paths(files) == sorted([consumer, producer])
