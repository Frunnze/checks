"""
A module-level instance of a class declared in the same file must be
followed like the function-local instance that
test_same_file_class_methods_are_followed pins.
Domain: the `Storage` instance created inside `sync`, or at module level
as `const`, typed `const`, `let` or `export const`.
Oracle: the entities of the function-local spelling.

Concrete inputs -> expected outputs:
- input:
      import axios from "axios";
      import * as fs from "node:fs";
      class Storage {
        save(path: string, text: string) { fs.writeFileSync(path, text); }
      }
      const storage = new Storage();
      export async function sync(url: string, path: string) {
        const text = (await axios.get(url)).data;
        storage.save(path, text);
      }
  output: <module>.sync reaches ["filesystem", "network"] and the report
  fails (was ["network"], passing).
"""

from check_support import HYPOTHESIS_SETTINGS
from hypothesis import example, given
from hypothesis import strategies as st
from srp_support import run_report, unit_named

STORAGE = (
    'import axios from "axios";\nimport * as fs from "node:fs";\n\n'
    "class Storage {\n  save(path: string, text: string) {\n"
    "    fs.writeFileSync(path, text);\n  }\n}\n\n"
)
INSTANCES = {
    "function_local": ("", "const storage = new Storage();\n  "),
    "module_const": ("const storage = new Storage();\n", ""),
    "module_typed": ("const storage: Storage = new Storage();\n", ""),
    "module_let": ("let storage = new Storage();\n", ""),
    "module_export": ("export const storage = new Storage();\n", ""),
}


def sync_source(instance):
    module_line, local_line = INSTANCES[instance]
    return (
        STORAGE
        + module_line
        + "export async function sync(url: string, path: string) {\n"
        + "  const text = (await axios.get(url)).data;\n"
        + f"  {local_line}storage.save(path, text);\n}}\n"
    )


@HYPOTHESIS_SETTINGS
@given(instance=st.sampled_from(sorted(INSTANCES)))
@example(instance="module_const")
def test_module_level_instance_property_is_followed(tmp_path, instance):
    report = run_report(tmp_path, sync_source(instance), ".ts")

    assert unit_named(report, "<module>.sync")["entities"] == [
        "filesystem",
        "network",
    ]
    assert report["failed"]
