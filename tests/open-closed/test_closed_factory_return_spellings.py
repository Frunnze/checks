"""
A factory that picks a concrete implementation is closed however it spells
the return, so returning from an if/else, from a conditional expression or
through a variable must get the same verdict. Domain: two distinct
lowercase implementation names rendered into an abstract Storage, its two
subclasses and a StorageFactory.create that selects between them. Oracle:
metamorphic - the conditional-expression and assign-then-return spellings
must match the if/return spelling.

Concrete inputs -> expected outputs:
- input (if/return spelling, implementations ['s3', 'local']):
      class StorageFactory:
          def create(self, use_cloud: bool) -> Storage:
              if use_cloud:
                  return S3Storage()
              return LocalStorage()
  output: reported -> ["storage.py:20: create closes Storage over concrete
  implementations: LocalStorage, S3Storage"].
- input (falsifying example, same factory as a conditional expression,
  now pinned as @example):
              return S3Storage() if use_cloud else LocalStorage()
  output: expected the same report, got [].
- input (falsifying example, same factory through a variable, pinned as
  @example):
              storage = LocalStorage()
              if use_cloud:
                  storage = S3Storage()
              return storage
  output: expected the same report, got [].
"""

from hypothesis import example, given, settings
from hypothesis import strategies as st

from open_closed_finder_support import IDENTIFIERS, findings_for

_STORAGE = (
    "from abc import ABC, abstractmethod\n\n\n"
    "class Storage(ABC):\n"
    "    @abstractmethod\n"
    "    def save(self, blob: bytes) -> str: ...\n"
)
_SPELLINGS = {
    "conditional": (
        "        return {first}() if use_cloud else {second}()\n"
    ),
    "assigned": (
        "        storage = {second}()\n"
        "        if use_cloud:\n            storage = {first}()\n"
        "        return storage\n"
    ),
}
_IF_RETURN = (
    "        if use_cloud:\n            return {first}()\n"
    "        return {second}()\n"
)


def _storage_module(names: list[str], body: str) -> str:
    first, second = (f"{name.title()}Storage" for name in names)
    subclasses = "".join(
        f"\n\nclass {name}(Storage):\n"
        "    def save(self, blob: bytes) -> str:\n        return ''\n"
        for name in (first, second)
    )

    return (
        f"{_STORAGE}{subclasses}\n\nclass StorageFactory:\n"
        "    def create(self, use_cloud: bool) -> Storage:\n"
        + body.format(first=first, second=second)
    )


@given(
    names=st.lists(IDENTIFIERS, min_size=2, max_size=2, unique=True),
    spelling=st.sampled_from(sorted(_SPELLINGS)),
)
@example(names=["s3", "local"], spelling="conditional")
@example(names=["s3", "local"], spelling="assigned")
@settings(max_examples=100, deadline=None)
def test_closed_factory_property_ignores_the_return_spelling(
    names: list[str], spelling: str
) -> None:
    expected = findings_for(
        {"storage.py": _storage_module(names, _IF_RETURN)}
    )
    found = findings_for(
        {"storage.py": _storage_module(names, _SPELLINGS[spelling])}
    )

    assert expected
    assert found == expected
