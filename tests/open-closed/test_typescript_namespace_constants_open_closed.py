"""
A dispatch over string constants must be reported whether the constants
are imported by name or through a namespace import.
Domain: 3-5 action-type constants exported from one module and dispatched
on through `import * as types`, in a `switch` or an `includes` list.
Oracle: the finding the named-import spelling yields.

Concrete inputs -> expected outputs:
- input:
      src/action-types.ts:
        export const ADD_TODO = "ADD_TODO";
        export const DELETE_TODO = "DELETE_TODO";
        export const EDIT_TODO = "EDIT_TODO";
      src/reducer.ts:
        import * as types from "./action-types";
        export function todos(state: string[], action: { type: string }) {
          switch (action.type) {
            case types.ADD_TODO: return state;
            case types.DELETE_TODO: return state;
            case types.EDIT_TODO: return state;
            default: return state;
          }
        }
  output: reported -> ["src/reducer.ts:2: todos compares action.type to 3
  strings: ADD_TODO, DELETE_TODO, EDIT_TODO"] (was []).
- input: the same reducer returning
  `[types.ADD_TODO, types.DELETE_TODO, types.EDIT_TODO].includes(action.type)`
  output: the same finding (was []).
"""

from hypothesis import example, given, settings
from hypothesis import strategies as st
from open_closed_typescript_shapes import typescript_findings

_ACTIONS = [
    "ADD_TODO", "DELETE_TODO", "EDIT_TODO", "COMPLETE_TODO", "CLEAR_TODOS",
]


def _action_types(actions: list[str]) -> str:
    return "".join(f'export const {action} = "{action}";\n'
                   for action in actions)


def _reducer(actions: list[str], structure: str) -> str:
    if structure == "switch":
        cases = "".join(f"    case types.{action}: return state;\n"
                        for action in actions)
        body = (f"  switch (action.type) {{\n{cases}"
                "    default: return state;\n  }\n")
    else:
        members = ", ".join(f"types.{action}" for action in actions)
        body = (f"  return [{members}].includes(action.type) "
                "? state : [];\n")

    return (
        'import * as types from "./action-types";\n'
        "export function todos(state: string[], action: { type: string }"
        f"): string[] {{\n{body}}}\n"
    )


@given(
    actions=st.lists(st.sampled_from(_ACTIONS), min_size=3, max_size=5,
                     unique=True),
    structure=st.sampled_from(["switch", "includes"]),
)
@example(actions=["ADD_TODO", "DELETE_TODO", "EDIT_TODO"],
         structure="switch")
@example(actions=["ADD_TODO", "DELETE_TODO", "EDIT_TODO"],
         structure="includes")
@settings(max_examples=6, deadline=None)
def test_namespace_imported_constants_property_are_dispatch_variants(
    actions: list[str], structure: str
) -> None:
    findings = typescript_findings(
        {
            "src/action-types.ts": _action_types(actions),
            "src/reducer.ts": _reducer(actions, structure),
        }
    )
    variants = ", ".join(sorted(actions))

    assert findings == [
        f"src/reducer.ts:2: todos compares action.type to {len(actions)} "
        f"strings: {variants}"
    ]
