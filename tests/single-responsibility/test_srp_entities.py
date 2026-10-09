import pytest
from hypothesis import given
from hypothesis import strategies as st
from srp_support import (
    THRESHOLD,
    CallableFacts,
    callable_score,
    effect_domains,
    entity_members,
    entity_reasons,
    external_entities,
    members_of,
    owner_score,
    reason_coefficient,
    run_project,
    run_report,
    unit_named,
)

KNOWN_CALLS = [
    "httpx.get",
    "pathlib.Path.write_text",
    "sqlalchemy.orm.Session.execute",
    "celery.Celery.send_task",
    "subprocess.run",
    "jwt.encode",
    "smtplib.SMTP.send_message",
    "openai.OpenAI.chat.completions.create",
]


@given(st.lists(st.sampled_from(KNOWN_CALLS), max_size=8))
def test_external_entities_property_are_unique_and_sorted(calls):
    entities = external_entities(calls)

    assert entities == sorted(set(entities))


@given(st.lists(st.text(max_size=12), max_size=8))
def test_external_entities_property_unresolved_names_are_never_entities(names):
    assert external_entities([name for name in names if "." not in name]) == []


@given(st.lists(st.sampled_from(KNOWN_CALLS), min_size=1, max_size=8))
def test_reason_coefficient_property_grows_with_every_added_entity(calls):
    entities = external_entities(calls)
    larger = external_entities(calls + ["subprocess.check_output"])

    assert reason_coefficient(larger) >= reason_coefficient(entities)
    assert 0.0 <= reason_coefficient(entities) <= 1.0


@given(st.lists(st.sampled_from(KNOWN_CALLS), max_size=8))
def test_reason_coefficient_property_blocks_exactly_above_one_entity(calls):
    entities = external_entities(calls)

    assert (reason_coefficient(entities) >= THRESHOLD) == (len(entities) >= 2)


def test_one_external_entity_is_a_single_reason_to_change():
    facts = CallableFacts("save", 1, "<module>", calls=["sqlalchemy.Session.execute"])
    unit = callable_score(facts)

    assert unit["entities"] == ["persistence"]
    assert unit["coefficient"] < THRESHOLD


def test_two_external_entities_are_two_reasons_to_change():
    facts = CallableFacts(
        "publish",
        1,
        "<module>",
        calls=["httpx.post", "pathlib.Path.write_text"],
    )
    unit = callable_score(facts)

    assert unit["entities"] == ["filesystem", "network"]
    assert unit["coefficient"] >= THRESHOLD


def test_repeating_one_entity_never_becomes_a_second_reason():
    facts = CallableFacts(
        "fetch_all",
        1,
        "<module>",
        calls=["httpx.get", "httpx.post", "httpx.put", "httpx.delete"],
    )

    assert callable_score(facts)["coefficient"] < THRESHOLD


def test_entities_reached_through_a_resolved_helper_still_count(tmp_path):
    source = (
        "import httpx\n"
        "from pathlib import Path\n"
        "def _download(address):\n"
        "    return httpx.get(address).text\n"
        "def _store(name, body):\n"
        "    Path(name).write_text(body)\n"
        "def archive(address, name):\n"
        "    _store(name, _download(address))\n"
    )
    unit = unit_named(run_report(tmp_path, source), "<module>.archive")

    assert unit["entities"] == ["filesystem", "network"]
    assert unit["coefficient"] >= THRESHOLD


def test_a_module_carries_every_entity_its_members_reach(tmp_path):
    source = (
        "import httpx\n"
        "import subprocess\n"
        "def fetch(address):\n"
        "    return httpx.get(address)\n"
        "def convert(name):\n"
        "    subprocess.run([name])\n"
    )
    owner = unit_named(run_report(tmp_path, source), "<module>")

    assert owner["entities"] == ["network", "process"]
    assert owner["coefficient"] >= THRESHOLD


def test_wiring_without_operations_of_its_own_has_no_entity(tmp_path):
    root = tmp_path / "src"
    root.mkdir()
    (root / "routes.py").write_text(
        "class Router:\n    def register(self):\n        return 1\n"
    )
    (root / "app.py").write_text(
        "from routes import Router\n"
        "def create_app():\n"
        "    app = Router()\n"
        "    app.register()\n"
        "    return app\n"
    )
    report = run_project(root)

    assert unit_named(report, "<module>.create_app")["entities"] == []
    assert not report["failed"]


def test_an_unrecognized_library_is_never_guessed_to_be_an_entity(tmp_path):
    source = (
        "import untracked_toolkit\n"
        "def work(value):\n"
        "    untracked_toolkit.write(value)\n"
        "    untracked_toolkit.send(value)\n"
    )
    report = run_report(tmp_path, source)

    assert unit_named(report, "<module>.work")["entities"] == []
    assert not report["failed"]


@pytest.mark.parametrize(
    ("call", "entity"),
    [
        ("pathlib.Path.read_text", "filesystem"),
        ("httpx.get", "network"),
        ("sqlalchemy.Session.execute", "persistence"),
        ("celery.Celery.send_task", "queue"),
        ("subprocess.run", "process"),
        ("jwt.encode", "authentication"),
        ("smtplib.SMTP.send_message", "email"),
        ("openai.OpenAI.chat.completions.create", "ai"),
        ("react-dom.createElement", "presentation"),
    ],
)
def test_each_supported_outside_world_is_one_named_entity(call, entity):
    assert external_entities([call]) == [entity]


def test_an_owner_reports_which_members_reach_each_entity():
    members = [
        CallableFacts("<module>.fetch", 1, "<module>", calls=["httpx.get"]),
        CallableFacts(
            "<module>.store", 2, "<module>", calls=["pathlib.Path.write_text"]
        ),
    ]
    owner = owner_score({"name": "<module>", "line": 1, "kind": "module"}, members)

    assert owner["entity_members"] == {
        "filesystem": ["<module>.store"],
        "network": ["<module>.fetch"],
    }


def test_an_owner_without_members_reports_no_reason_to_change():
    owner = owner_score({"name": "<module>", "line": 1, "kind": "module"}, [])

    assert owner["entities"] == []
    assert owner["coefficient"] == 0


def facts_from(names_and_calls):
    return [
        CallableFacts(name, index + 1, "<module>", calls=list(calls))
        for index, (name, calls) in enumerate(names_and_calls)
    ]


MEMBERS = st.lists(
    st.tuples(
        st.text(min_size=1, max_size=6),
        st.lists(st.sampled_from(KNOWN_CALLS), max_size=4),
    ),
    max_size=6,
    unique_by=lambda member: member[0],
)


@given(MEMBERS)
def test_members_of_property_selects_exactly_the_owned_callables(members):
    owned = facts_from(members)
    foreign = CallableFacts("outsider", 99, "<other>")

    assert members_of({"name": "<module>"}, owned + [foreign]) == owned


@given(MEMBERS)
def test_entity_members_property_names_only_members_that_reach_the_entity(members):
    owned = facts_from(members)
    reached = entity_members(owned)

    for entity, names in reached.items():
        assert names == sorted(names)
        for name in names:
            member = next(item for item in owned if item.name == name)
            assert entity in external_entities(member.calls)


@given(MEMBERS)
def test_entity_reasons_property_explains_every_entity_exactly_once(members):
    calls = [call for _, member_calls in members for call in member_calls]
    direct = effect_domains(calls)
    reasons = entity_reasons(direct, {})

    assert len(reasons) == len(external_entities(calls))
    assert [reason.split(":")[0] for reason in reasons] == external_entities(calls)
