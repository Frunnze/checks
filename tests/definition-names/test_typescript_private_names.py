"""
The TypeScript definition-names finder must judge a class member by its
name, whether it is spelled public or with a #private name. Domain: a
class with one method, function-valued field or getter whose name joins
two words with And/Or, spelled with or without the # prefix. Oracle:
metamorphic - the privacy spelling must not change the verdict (the
Python twin flags _load_and_save and __load_and_save alike).

Concrete inputs -> expected outputs:
- input:
      export class Store {
        loadAndSave(): void {}
      }
  output: ["src/store.ts:2:  loadAndSave(): void {}"].
- input (falsifying example, pinned as @example):
      export class Store {
        #loadAndSave(): void {}
      }
  output: expected ["src/store.ts:2:  #loadAndSave(): void {}"], got [].
"""

import tempfile
from pathlib import Path

from hypothesis import example, given, settings
from hypothesis import strategies as st

from typescript_finder_support import CHECKS, report_from

_FINDER = (
    CHECKS / "experimental" / "definition-names" / "typescript"
    / "joined_names.js"
)
_SOURCE = "src/store.ts"
_SETTINGS = settings(max_examples=8, deadline=None)
_MEMBER_FORMS = {
    "method": "  {name}(): void {{}}",
    "arrow_field": "  {name} = (): void => {{}};",
    "getter": "  get {name}(): number {{\n    return 1;\n  }}",
}

joined_names = st.sampled_from(
    ["loadAndSave", "cacheOrFetch", "readAndParse", "validateOrThrow"]
)
member_forms = st.sampled_from(sorted(_MEMBER_FORMS))


@given(name=joined_names, form=member_forms, private=st.booleans())
@example(name="loadAndSave", form="method", private=True)
@_SETTINGS
def test_joined_names_property_privacy_never_hides_a_joined_member(
    name: str, form: str, private: bool
) -> None:
    spelled = "#" + name if private else name
    member = _MEMBER_FORMS[form].format(name=spelled)
    files = {_SOURCE: "export class Store {\n" + member + "\n}\n"}

    with tempfile.TemporaryDirectory() as directory:
        report = report_from(_FINDER, Path(directory), files)

    assert report == [f"{_SOURCE}:2:" + member.split("\n")[0]]
