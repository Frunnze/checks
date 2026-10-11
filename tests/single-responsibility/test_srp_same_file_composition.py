"""
A project class defined in the caller's own file is followed like the same
class imported from a sibling module, whether the caller holds it in a
field set in __init__, a typed __init__ parameter, a class annotation, a
typed parameter or a module-level instance; a module-level alias of a
same-file function is followed like the function. Domain: those six
holding idioms times six effect kinds. Oracle: model (the caller writes a
file and reaches effect X, so it reaches [filesystem, X]) and placement
(same file == sibling module).

Concrete inputs -> expected outputs:
- input (pkg/main.py):
      import pathlib
      import requests
      class Tools:
          def helper(self, target):
              return requests.Session().get(target)
      class Service:
          def __init__(self):
              self.tools = Tools()
          def unit(self, target, path):
              pathlib.Path(path).write_text('x')
              self.tools.helper(target)
  output: <module>.Service.unit -> ["filesystem", "network"]
  (before the fix ["filesystem"], so the gate passed).
- input: the same Tools, then `tools = Tools()` at module level and
  `def unit(target, path)` writing a file and calling
  `tools.helper(target)`
  output: <module>.unit -> ["filesystem", "network"].
"""

from hypothesis import example, given, settings
from hypothesis import strategies as st
from srp_program_support import CLIENTS, unit_entities

HOLDERS = {
    "init_field": (
        (
            "class Service:\n    def __init__(self):\n"
            "        self.tools = Tools()\n"
            "    def unit(self, target, path):\n"
        ),
        "self.tools.helper(target)",
        "<module>.Service.unit",
    ),
    "init_typed_parameter": (
        (
            "class Service:\n    def __init__(self, tools: Tools):\n"
            "        self.tools = tools\n"
            "    def unit(self, target, path):\n"
        ),
        "self.tools.helper(target)",
        "<module>.Service.unit",
    ),
    "class_annotation": (
        "class Service:\n    tools: Tools\n    def unit(self, target, path):\n",
        "self.tools.helper(target)",
        "<module>.Service.unit",
    ),
    "typed_parameter": (
        "def unit(target, path, tools: Tools):\n",
        "tools.helper(target)",
        "<module>.unit",
    ),
    "module_instance": (
        "tools = Tools()\n\n\ndef unit(target, path):\n",
        "tools.helper(target)",
        "<module>.unit",
    ),
    "function_alias": (
        "def unit(target, path):\n",
        "run_helper(target)",
        "<module>.unit",
    ),
}


def definitions(kind: str) -> str:
    import_line, factory, _, operation = CLIENTS[kind]
    return (
        f"{import_line}\n\n\nclass Tools:\n"
        f"    def helper(self, target):\n"
        f"        return {factory}{operation}\n\n\n"
        f"def helper(target):\n    return {factory}{operation}\n\n\n"
        "run_helper = helper\n"
    )


def program(holder: str, kind: str, same_file: bool) -> dict[str, str]:
    header, call, _ = HOLDERS[holder]
    pad = "        " if header.startswith("class") else "    "
    caller = (
        header
        + f"{pad}pathlib.Path(path).write_text('x')\n"
        + f"{pad}{call}\n"
    )
    if same_file:
        main = "import pathlib\n" + definitions(kind) + "\n\n" + caller
        return {"pkg/__init__.py": "", "pkg/main.py": main}
    main = (
        "import pathlib\n\nfrom pkg.tools import Tools, run_helper\n\n\n"
        + caller
    )
    return {
        "pkg/__init__.py": "",
        "pkg/tools.py": definitions(kind),
        "pkg/main.py": main,
    }


@settings(max_examples=40, deadline=None)
@given(st.sampled_from(sorted(HOLDERS)), st.sampled_from(sorted(CLIENTS)))
@example("init_field", "network")
def test_same_file_classes_reach_what_imported_classes_reach(holder, kind):
    name = HOLDERS[holder][2]
    expected = sorted({"filesystem", kind})
    imported = unit_entities(
        program(holder, kind, same_file=False), "pkg/main.py", "callable", name
    )
    same_file = unit_entities(
        program(holder, kind, same_file=True), "pkg/main.py", "callable", name
    )

    assert imported == expected
    assert same_file == expected
