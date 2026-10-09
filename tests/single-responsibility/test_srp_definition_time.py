import ast

import pytest
from hypothesis import given
from hypothesis import strategies as st
from srp_support import CallableFacts, run_report, unit_named

from python_definition_time import collect_definition_body, definition_defaults
from python_metrics import RuntimeMetrics

SCRIPT = (
    "import requests\n\n"
    "response = requests.get('https://example.com')\n"
    "with open('out.txt', 'w') as handle:\n"
    "    handle.write(response.text)\n"
)
CLASS_BODY = (
    "import requests\n\n\n"
    "class Settings:\n"
    "    remote = requests.get('https://example.com').json()\n"
    "    local = open('settings.txt').read()\n"
)
DEFAULTS = (
    "import requests\n\n\n"
    "def mirror(path, payload=requests.get('https://example.com').text):\n"
    "    with open(path, 'w') as handle:\n"
    "        handle.write(payload)\n"
)
WIRING = (
    "import logging\n"
    "from dataclasses import dataclass, field\n\n"
    "LIMIT = 10\n"
    "logger = logging.getLogger(__name__)\n\n\n"
    "@dataclass(frozen=True)\n"
    "class Options:\n"
    "    names: list[str] = field(default_factory=list)\n\n\n"
    "options = Options()\n"
)
DEFAULT_CALL_NAMES = st.lists(
    st.sampled_from(["first", "second", "third", "fourth"]),
    max_size=4,
    unique=True,
)


@pytest.mark.parametrize(
    ("source", "owner_name"),
    [
        (SCRIPT, "<module>"),
        (CLASS_BODY, "<module>.Settings"),
        (DEFAULTS, "<module>"),
    ],
)
def test_definition_time_effects_count_for_their_owner(
    tmp_path, source, owner_name
):
    report = run_report(tmp_path, source)

    owner = unit_named(report, owner_name)

    assert owner["entities"] == ["filesystem", "network"]
    assert report["failed"]


def test_pure_module_wiring_scores_zero(tmp_path):
    report = run_report(tmp_path, WIRING)

    assert report["coefficient"] == 0.0


def function_with_defaults(names: list[str]) -> str:
    positional = [f"{name}={name}()" for name in names[:2]]
    keyword_only = [f"{name}={name}()" for name in names[2:]]
    parameters = positional + (["*"] + keyword_only if keyword_only else [])
    return f"def target({', '.join(parameters)}):\n    pass\n"


@given(DEFAULT_CALL_NAMES)
def test_definition_defaults_property_returns_every_default(names):
    tree = ast.parse(function_with_defaults(names))

    defaults = definition_defaults(tree)

    called = [default.func.id for default in defaults]
    assert called == names


@given(DEFAULT_CALL_NAMES)
def test_collect_definition_body_property_records_every_default_call(names):
    tree = ast.parse(function_with_defaults(names) + "top_level()\n")
    facts = CallableFacts("<module-body>", 1, "<module>", client_only=True)
    collector = RuntimeMetrics(facts, {}, set(), set(), set())

    collected = collect_definition_body(collector, tree)

    expected = sorted("local:" + name for name in [*names, "top_level"])
    assert collected.calls == expected
