"""
Top-level script code, plain or under `if __name__ == "__main__":`, reaches
the methods of a class defined in the same file exactly as it reaches the
same class imported from a sibling module. Domain: static, inline-instance
and local-instance calls, plain or guarded, times six effect kinds.
Oracle: model (the script writes a file and reaches effect X, so <module>
reaches [filesystem, X]) and placement (same file == sibling module).

Concrete inputs -> expected outputs:
- input (pkg/main.py):
      import pathlib
      import requests
      class Tools:
          def helper(self, target):
              return requests.Session().get(target)
      if __name__ == "__main__":
          pathlib.Path('out.txt').write_text('x')
          Tools().helper('x')
  output: <module> -> ["filesystem", "network"] (before the fix
  ["filesystem"], so the gate passed).
- input: the same script with `Tools.helper('x')` on a @staticmethod
  output: <module> -> ["filesystem", "network"].
"""

from hypothesis import example, given, settings
from hypothesis import strategies as st
from srp_program_support import CLIENTS, unit_entities

CALLS = {
    "static": ("    @staticmethod\n    def helper(target):\n", "Tools.helper('x')"),
    "inline_instance": (
        "    def helper(self, target):\n",
        "Tools().helper('x')",
    ),
    "local_instance": (
        "    def helper(self, target):\n",
        "tools = Tools()\n{pad}tools.helper('x')",
    ),
}


def program(
    call: str, guarded: bool, kind: str, same_file: bool
) -> dict[str, str]:
    import_line, factory, _, operation = CLIENTS[kind]
    method, use = CALLS[call]
    tools = (
        f"{import_line}\n\n\nclass Tools:\n"
        + method
        + f"        return {factory}{operation}\n"
    )
    pad = "    " if guarded else ""
    script = (
        f"{pad}pathlib.Path('out.txt').write_text('x')\n"
        + pad
        + use.replace("{pad}", pad)
        + "\n"
    )
    if guarded:
        script = 'if __name__ == "__main__":\n' + script
    if same_file:
        main = "import pathlib\n" + tools + "\n\n" + script
        return {"pkg/__init__.py": "", "pkg/main.py": main}
    main = "import pathlib\n\nfrom pkg.tools import Tools\n\n\n" + script
    return {"pkg/__init__.py": "", "pkg/tools.py": tools, "pkg/main.py": main}


@settings(max_examples=40, deadline=None)
@given(
    st.sampled_from(sorted(CALLS)),
    st.booleans(),
    st.sampled_from(sorted(CLIENTS)),
)
@example("inline_instance", True, "network")
def test_script_code_reaches_same_file_class_methods(call, guarded, kind):
    expected = sorted({"filesystem", kind})
    imported = unit_entities(
        program(call, guarded, kind, same_file=False),
        "pkg/main.py",
        "module",
        "<module>",
    )
    same_file = unit_entities(
        program(call, guarded, kind, same_file=True),
        "pkg/main.py",
        "module",
        "<module>",
    )

    assert imported == expected
    assert same_file == expected
