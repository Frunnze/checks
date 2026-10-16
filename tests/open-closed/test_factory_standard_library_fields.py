"""
A factory's standard-library fields - a cache, a lock, a path - are not
leaked concrete dependencies, like the language built-ins the TypeScript
twin skips (test_injected_factory_property_guards_and_caches_are_not_
dependencies). Domain: a TransportFactory creating an abstract Transport
from an injected client, holding one extra field built by a
standard-library constructor in any import spelling, or by a project
class. Oracle: twin - only the project class is reported.

Concrete inputs -> expected outputs:
- input:
      class TransportFactory:
          def __init__(self, client):
              self._client = client
              self._made = OrderedDict()
          def create(self) -> Transport:
              return self._client.transport()
  with `from collections import OrderedDict`
  output: expected [], got ["m.py:15: TransportFactory leaks concrete
  dependencies while creating Transport: OrderedDict"].
- input: the same field built as `HttpClient()`, a project class
  output: ["m.py:15: TransportFactory leaks concrete dependencies while
  creating Transport: HttpClient"].
"""

from hypothesis import example, given, settings
from hypothesis import strategies as st

from open_closed_finder_support import findings_for

STANDARD_FIELDS = {
    "ordered_dict": ("from collections import OrderedDict", "OrderedDict()"),
    "module_lock": ("import threading", "threading.Lock()"),
    "imported_lock": ("from threading import RLock", "RLock()"),
    "aliased_path": ("from pathlib import Path as FilePath", "FilePath('.')"),
    "asyncio_lock": ("import asyncio", "asyncio.Lock()"),
}
FACTORY = (
    "{imports}\nfrom abc import ABC, abstractmethod\n\n\n"
    "class Transport(ABC):\n    @abstractmethod\n"
    "    def send(self) -> None: ...\n\n\n"
    "class HttpClient:\n    pass\n\n\n"
    "class TransportFactory:\n"
    "    def __init__(self, client):\n"
    "        self._client = client\n"
    "        self._made = {field}\n\n"
    "    def create(self) -> Transport:\n"
    "        return self._client.transport()\n"
)


@given(field=st.sampled_from(sorted(STANDARD_FIELDS)))
@example(field="ordered_dict")
@example(field="module_lock")
@settings(max_examples=5, deadline=None)
def test_factory_property_standard_library_fields_are_not_leaks(
    field: str,
) -> None:
    imports, constructor = STANDARD_FIELDS[field]
    source = FACTORY.format(imports=imports, field=constructor)

    assert findings_for({"m.py": source}) == []


def test_factory_still_reports_a_project_class_field() -> None:
    source = FACTORY.format(imports="", field="HttpClient()")

    assert findings_for({"m.py": source}) == [
        (
            "m.py:15: TransportFactory leaks concrete dependencies while "
            "creating Transport: HttpClient"
        )
    ]
