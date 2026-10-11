"""
A service object exported with `export default { ... }` must delegate its
methods like the named and default-exported service values that
test_exported_service_values_delegate_their_methods pins.
Domain: an `api` and a `storage` service, each an object literal exported
as `export const`, as a default-exported constant, as `export { x as
default }`, or directly as `export default { ... }` (optionally `as const`
or `satisfies object`, with methods or arrow members), called by `work`.
Oracle: the entities of the `export const` spelling.

Concrete inputs -> expected outputs:
- input:
      api.ts:     import axios from "axios";
                  export default {
                    getUser(key: string) { return axios.get(key); },
                  };
      storage.ts: export default {
                    save(key: string) { return localStorage.setItem(key, key); },
                  };
      work.ts:    import api from "./api";
                  import storage from "./storage";
                  export async function work(id: string) {
                    const user = await api.getUser(id);
                    storage.save(String(user));
                  }
  output: <module>.work reaches ["network", "persistence"] and the report
  fails (was [], passing).
"""

from check_support import HYPOTHESIS_SETTINGS
from hypothesis import example, given
from hypothesis import strategies as st
from srp_support import run_project, unit_named

SERVICES = {
    "api": ('import axios from "axios";\n', "getUser", "axios.get(key)"),
    "storage": ("", "save", "localStorage.setItem(key, key)"),
}
EXPORTS = {
    "export_const": "export const {name} = {{\n{members}}};\n",
    "default_constant": (
        "const {name} = {{\n{members}}};\nexport default {name};\n"
    ),
    "default_alias": (
        "const {name} = {{\n{members}}};\nexport {{ {name} as default }};\n"
    ),
    "default_object": "export default {{\n{members}}};\n",
    "default_object_as_const": "export default {{\n{members}}} as const;\n",
    "default_object_satisfies": (
        "export default {{\n{members}}} satisfies object;\n"
    ),
}
MEMBERS = {
    "method": "  {method}(key: string) {{ return {body}; }},\n",
    "arrow": "  {method}: (key: string) => {body},\n",
}
WORK = (
    "export async function work(id: string) {\n"
    "  const user = await api.getUser(id);\n"
    "  storage.save(String(user));\n}\n"
)


def write_services(root, shape, member):
    imports = ""
    for name, (header, method, body) in SERVICES.items():
        members = MEMBERS[member].format(method=method, body=body)
        service = EXPORTS[shape].format(name=name, members=members)
        (root / f"{name}.ts").write_text(header + service)
        if shape == "export_const":
            imports += f'import {{ {name} }} from "./{name}";\n'
        else:
            imports += f'import {name} from "./{name}";\n'
    (root / "work.ts").write_text(imports + WORK)


@HYPOTHESIS_SETTINGS
@given(
    shape=st.sampled_from(sorted(EXPORTS)),
    member=st.sampled_from(sorted(MEMBERS)),
)
@example(shape="default_object", member="method")
def test_default_exported_service_object_property_delegates(
    tmp_path, shape, member
):
    write_services(tmp_path, shape, member)

    report = run_project(tmp_path)

    assert unit_named(report, "<module>.work")["entities"] == [
        "network",
        "persistence",
    ]
    assert report["failed"]
