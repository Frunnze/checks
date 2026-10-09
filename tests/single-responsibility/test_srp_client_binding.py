import pytest
from srp_support import run_report, unit_named

FACTORY_CLIENT_SOURCES = [
    (
        "import redis\n"
        "def remember(key):\n"
        "    cache = redis.from_url('redis://cache')\n"
        "    cache.setex(key, 5, 'value')\n",
        "persistence",
    ),
    (
        "import boto3\n"
        "def remember(key):\n"
        "    storage = boto3.client('s3')\n"
        "    storage.upload_file(key, 'bucket', key)\n",
        "network",
    ),
    (
        "import boto3\n"
        "def remember(key):\n"
        "    storage = boto3.resource('s3')\n"
        "    storage.meta.client.download_file('bucket', key, key)\n",
        "network",
    ),
    (
        "import httpx\n"
        "async def remember(key):\n"
        "    client = httpx.AsyncClient()\n"
        "    await client.post(key)\n",
        "network",
    ),
    (
        "import asyncpg\n"
        "async def remember(key):\n"
        "    connection = await asyncpg.connect(key)\n"
        "    await connection.execute('insert', key)\n",
        "persistence",
    ),
    (
        "from sqlalchemy import create_engine, text\n"
        "def remember(key):\n"
        "    engine = create_engine(key)\n"
        "    with engine.connect() as connection:\n"
        "        connection.execute(text('insert'))\n",
        "persistence",
    ),
    (
        "import socket\n"
        "def remember(key):\n"
        "    connection = socket.create_connection((key, 1))\n"
        "    connection.sendall(b'value')\n",
        "network",
    ),
    (
        "import pymongo\n"
        "def remember(key):\n"
        "    client = pymongo.MongoClient(key)\n"
        "    client['shop']['orders'].insert_one({'key': key})\n",
        "persistence",
    ),
    (
        "import asyncio\n"
        "async def remember(key):\n"
        "    await asyncio.create_subprocess_exec('echo', key)\n",
        "process",
    ),
    (
        "from pathlib import Path\n"
        "def remember(directory: Path, key: str):\n"
        "    (directory / key).write_text(key)\n",
        "filesystem",
    ),
    (
        "from pathlib import Path\n"
        "def remember(directory: Path, key: str):\n"
        "    target = directory / 'cache' / key\n"
        "    target.unlink()\n",
        "filesystem",
    ),
    (
        "from pathlib import Path\n"
        "def remember(root, key):\n"
        "    with (Path(root) / key).open('w') as handle:\n"
        "        handle.write(key)\n",
        "filesystem",
    ),
    (
        "import sqlite3\n"
        "def remember(key):\n"
        "    def connect_cache() -> sqlite3.Connection:\n"
        "        return sqlite3.connect(key)\n"
        "    connection = connect_cache()\n"
        "    connection.execute('insert', key)\n",
        "persistence",
    ),
]
AI_WRITER_SOURCES = [
    "from openai import OpenAI\n"
    "class Writer:\n"
    "    def __init__(self):\n"
    "        self._client = OpenAI()\n"
    "    def write(self, prompt):\n"
    "        return self._client.chat.completions.create(messages=prompt)\n",
    "from openai import OpenAI\n"
    "class Writer:\n"
    "    def __init__(self):\n"
    "        self._client = self._build_client()\n"
    "    def _build_client(self) -> OpenAI:\n"
    "        return OpenAI()\n"
    "    def write(self, prompt):\n"
    "        return self._client.chat.completions.create(messages=prompt)\n",
    "import anthropic\n"
    "class Writer:\n"
    "    def _build_client(self) -> anthropic.Anthropic:\n"
    "        return anthropic.Anthropic()\n"
    "    def write(self, prompt):\n"
    "        client = self._build_client()\n"
    "        return client.messages.create(messages=prompt)\n",
]
NON_ENTITY_SOURCES = [
    "import os\nimport subprocess\n"
    "def remember(command):\n"
    "    return subprocess.run(command, env=os.environ.copy(), check=True)\n",
    "import hashlib\nfrom pathlib import Path\n"
    "def remember(path: Path) -> str:\n"
    "    return hashlib.sha256(path.read_bytes()).hexdigest()\n",
    "def remember(count, key):\n"
    "    (count / key).write_text(key)\n",
]


@pytest.mark.parametrize("source, entity", FACTORY_CLIENT_SOURCES)
def test_factory_built_clients_are_bound(tmp_path, source, entity):
    unit = unit_named(run_report(tmp_path, source), "<module>.remember")

    assert list(unit["effect_domains"]) == [entity]


@pytest.mark.parametrize("source", AI_WRITER_SOURCES)
def test_model_clients_held_by_a_writer_are_ai(tmp_path, source):
    unit = unit_named(run_report(tmp_path, source), "<module>.Writer.write")

    assert list(unit["effect_domains"]) == ["ai"]


@pytest.mark.parametrize("source", NON_ENTITY_SOURCES)
def test_value_helpers_add_no_second_entity(tmp_path, source):
    unit = unit_named(run_report(tmp_path, source), "<module>.remember")

    assert len(unit["effect_domains"]) <= 1
    assert unit["coefficient"] < 0.5


MODULE_FACTORY_SOURCE = (
    "import sqlite3\n"
    "def make_connection() -> sqlite3.Connection:\n"
    "    return sqlite3.connect('store.db')\n"
    "def remember(key):\n"
    "    connection = make_connection()\n"
    "    connection.execute('insert', key)\n"
)


def test_module_factories_bind_their_returned_client(tmp_path):
    report = run_report(tmp_path, MODULE_FACTORY_SOURCE)

    unit = unit_named(report, "<module>.remember")

    assert "persistence" in unit["effect_domains"]
