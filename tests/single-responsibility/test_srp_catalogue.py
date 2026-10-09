import pytest
from hypothesis import given
from hypothesis import strategies as st
from srp_support import effect_domains, external_entities

from srp_effect_rules import EFFECT_RULES
from srp_effects import is_catalogued_client, is_within_prefixes

CATALOGUED_OPERATIONS = sorted(
    {
        operation
        for _, _, operations in EFFECT_RULES
        for operation in operations
    }
)
NON_ENTITY_CALLS = [
    "hashlib.sha256.hexdigest",
    "hashlib.md5.digest",
    "hashlib.new",
    "os.environ.copy",
    "os.environ.get",
    "os.path.join",
    "os.path.exists",
    "os.getcwd",
    "pandas.DataFrame.copy",
    "pandas.DataFrame.rename",
]
ENTITY_CALLS = [
    ("hmac.new.hexdigest", "authentication"),
    ("os.remove", "filesystem"),
    ("os.makedirs", "filesystem"),
    ("os.listdir", "filesystem"),
    ("pandas.read_csv", "filesystem"),
    ("pandas.DataFrame.to_csv", "filesystem"),
    ("pandas.read_parquet", "filesystem"),
    ("pymongo.MongoClient.shop.orders.insert_one", "persistence"),
    ("pymongo.MongoClient.find", "persistence"),
    ("pymongo.MongoClient.shop.orders.update_one", "persistence"),
    ("redis.Redis.setex", "persistence"),
    ("redis.Redis.set", "persistence"),
    ("os.system", "process"),
    ("os.popen", "process"),
    ("asyncio.create_subprocess_exec", "process"),
    ("asyncio.create_subprocess_shell", "process"),
    ("ftplib.FTP.storbinary", "network"),
    ("paramiko.SSHClient.exec_command", "network"),
    ("paramiko.SSHClient.connect", "network"),
    ("socket.create_connection", "network"),
    ("openai.OpenAI.chat.completions.create", "ai"),
    ("anthropic.Anthropic.messages.create", "ai"),
]
TYPE_NAME_SEGMENT = st.from_regex(
    r"[A-Za-z][A-Za-z0-9_]{0,10}", fullmatch=True
)


@pytest.mark.parametrize("call", NON_ENTITY_CALLS)
def test_value_helpers_are_not_external_entities(call):
    assert external_entities([call]) == []


@pytest.mark.parametrize("call, entity", ENTITY_CALLS)
def test_catalogued_operations_are_external_entities(call, entity):
    assert external_entities([call]) == [entity]


@given(st.sampled_from(CATALOGUED_OPERATIONS))
def test_effect_domains_property_environment_and_path_math_are_not_entities(
    operation,
):
    environment_call = "os.environ." + operation
    path_call = "os.path." + operation

    assert effect_domains([environment_call, path_call]) == {}


@given(TYPE_NAME_SEGMENT, st.sampled_from(CATALOGUED_OPERATIONS))
def test_effect_domains_property_content_hashing_is_never_authentication(
    algorithm, operation
):
    hashing_call = f"hashlib.{algorithm}.{operation}"

    assert "authentication" not in effect_domains([hashing_call])


@given(st.sampled_from(ENTITY_CALLS))
def test_effect_domains_property_every_domain_lists_its_own_call(entry):
    call, entity = entry

    assert effect_domains([call]) == {entity: [call]}


@given(TYPE_NAME_SEGMENT)
def test_is_catalogued_client_property_library_types_are_catalogued(type_name):
    assert is_catalogued_client("sqlite3." + type_name)
    assert is_catalogued_client("openai." + type_name)


@given(TYPE_NAME_SEGMENT)
def test_is_catalogued_client_property_unknown_modules_are_not(type_name):
    assert not is_catalogued_client("local:" + type_name)
    assert not is_catalogued_client("typing." + type_name)
    assert not is_catalogued_client("sqlite3x." + type_name)


@given(st.lists(TYPE_NAME_SEGMENT, min_size=1, max_size=4), TYPE_NAME_SEGMENT)
def test_is_within_prefixes_property_accepts_only_whole_segments(
    segments, suffix
):
    prefix = ".".join(segments)

    assert is_within_prefixes(prefix, (prefix,))
    assert is_within_prefixes(f"{prefix}.{suffix}", (prefix,))
    assert not is_within_prefixes(prefix + suffix, (prefix,))
