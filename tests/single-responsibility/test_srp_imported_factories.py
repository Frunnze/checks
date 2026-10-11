"""
A client factory whose return annotation names a catalogued client keeps
its client when it is imported, exactly as it does in the caller's own
file. Domain: the factory imported by name, through a package re-export,
through a star import or as a module attribute, its result used inline,
through a variable or as a `with` target, times five client kinds.
Oracle: model (the caller writes a file and uses the client of entity X,
so it reaches [filesystem, X]) and placement (imported == same file).

Concrete inputs -> expected outputs:
- input:
      pkg/clients.py:
          import sqlite3
          def build(target) -> sqlite3.Connection:
              return sqlite3.connect(target)
      pkg/main.py:
          import pathlib
          from pkg.clients import build
          def unit(target, path):
              pathlib.Path(path).write_text('x')
              build(target).execute('select 1')
  output: <module>.unit -> ["filesystem", "persistence"] (before the fix
  ["filesystem"], so the gate passed).
- input: the same with `client = build(target)` then
  `client.execute('select 1')`
  output: <module>.unit -> ["filesystem", "persistence"].
"""

from hypothesis import example, given, settings
from hypothesis import strategies as st
from srp_program_support import CLIENTS, unit_entities

PLACEMENTS = {
    "sibling": ("from pkg.clients import build\n", "build"),
    "reexport": ("from pkg.public import build\n", "build"),
    "star": ("from pkg.clients import *\n", "build"),
    "module_attribute": ("from pkg import clients\n", "clients.build"),
}
USES = {
    "inline": "    {factory}(target){operation}\n",
    "variable": "    client = {factory}(target)\n    client{operation}\n",
    "with": "    with {factory}(target) as client:\n        client{operation}\n",
}
FACTORY_KINDS = sorted(kind for kind in CLIENTS if kind != "process")


def factory_source(kind: str) -> str:
    import_line, factory, type_name, _ = CLIENTS[kind]
    return (
        f"{import_line}\n\n\ndef build(target) -> {type_name}:\n"
        f"    return {factory}\n"
    )


def caller(header: str, factory: str, use: str, kind: str) -> str:
    operation = CLIENTS[kind][3]
    body = USES[use].format(factory=factory, operation=operation)
    return (
        "import pathlib\n"
        + header
        + "\n\ndef unit(target, path):\n"
        + "    pathlib.Path(path).write_text('x')\n"
        + body
    )


@settings(max_examples=60, deadline=None)
@given(
    st.sampled_from(sorted(PLACEMENTS)),
    st.sampled_from(sorted(USES)),
    st.sampled_from(FACTORY_KINDS),
)
@example("sibling", "inline", "persistence")
def test_imported_factories_keep_their_client(placement, use, kind):
    header, factory = PLACEMENTS[placement]
    imported = {
        "pkg/__init__.py": "",
        "pkg/public/__init__.py": "from pkg.clients import build\n",
        "pkg/clients.py": factory_source(kind),
        "pkg/main.py": caller(header, factory, use, kind),
    }
    same_file = {
        "pkg/__init__.py": "",
        "pkg/main.py": factory_source(kind) + caller("", "build", use, kind),
    }
    expected = sorted({"filesystem", kind})

    assert (
        unit_entities(same_file, "pkg/main.py", "callable", "<module>.unit")
        == expected
    )
    assert (
        unit_entities(imported, "pkg/main.py", "callable", "<module>.unit")
        == expected
    )
