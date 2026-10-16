"""
A client returned by a catalogued library call keeps its entity when it is
held in a local variable, like the same call chained inline. Domain: a
RabbitMQ channel and a pymongo database, each taken from a catalogued
client inline or through a variable, used next to an HTTP post. Oracle:
metamorphic (extract variable) - the variable spelling reaches the entities
of the inline spelling.

Concrete inputs -> expected outputs:
- input:
      import httpx, pika
      def publish(url):
          httpx.post(url)
          connection = pika.BlockingConnection()
          connection.channel().basic_publish(exchange='', routing_key='q',
                                             body=url)
  output: <module>.publish -> ["network", "queue"].
- input (falsifying example, pinned as @example): the same with
      channel = connection.channel()
      channel.basic_publish(exchange='', routing_key='q', body=url)
  output: expected ["network", "queue"], got ["network"] - the variable
  was bound to nothing, so its calls reached no entity.
"""

import tempfile
from pathlib import Path

from check_support import HYPOTHESIS_SETTINGS
from hypothesis import example, given
from hypothesis import strategies as st
from srp_support import run_project, unit_named

CLIENTS = {
    "queue": (
        "import pika\n",
        "connection = pika.BlockingConnection()\n",
        "connection.channel()",
        ".basic_publish(exchange='', routing_key='q', body=url)",
    ),
    "persistence": (
        "import pymongo\n",
        "connection = pymongo.MongoClient()\n",
        "connection.get_database('shop')",
        ".orders.insert_one({'url': url})",
    ),
}


def _publish(entity: str, in_variable: bool) -> str:
    imports, setup, client, use = CLIENTS[entity]
    body = f"    {setup}"

    if in_variable:
        body += f"    client = {client}\n    client{use}\n"
    else:
        body += f"    {client}{use}\n"

    return (
        f"import httpx\n{imports}\n\n"
        f"def publish(url):\n    httpx.post(url)\n{body}"
    )


@given(entity=st.sampled_from(sorted(CLIENTS)), in_variable=st.booleans())
@example(entity="queue", in_variable=True)
@example(entity="persistence", in_variable=True)
@HYPOTHESIS_SETTINGS
def test_client_property_keeps_its_entity_in_a_variable(
    entity: str, in_variable: bool
) -> None:
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        source = _publish(entity, in_variable)
        _ = (root / "publish.py").write_text(source, encoding="utf-8")
        report = run_project(root)

    entities = unit_named(report, "<module>.publish")["entities"]

    assert entities == sorted({"network", entity})
