"""
A variant axis dispatched across files must keep its axis when the kind is
destructured, from the parameter or from the value inside the function.
Domain: one `ImportRequest` model and two consumer files that split its
three kinds; each consumer reads the kind as `request.kind`, through a
destructured parameter `{ kind }: ImportRequest`, or through
`const { kind } = request`.
Oracle: the scattered-dispatch finding of the `request.kind` spelling.

Concrete inputs -> expected outputs:
- input:
      src/models.ts:
        export type ImportRequest = {
          readonly kind: "file" | "link" | "text";
        };
      src/label.ts:
        import type { ImportRequest } from "./models";
        export function label({ kind }: ImportRequest): boolean {
          return kind === "file" || kind === "link";
        }
      src/origin.ts:
        import type { ImportRequest } from "./models";
        export function origin({ kind }: ImportRequest): boolean {
          return kind === "text";
        }
  output: reported once per file -> ["src/label.ts:2: ImportRequest.kind
  dispatch is scattered across 2 functions in 2 files: file, link, text",
  "src/origin.ts:2: ..."] (was []).
"""

from hypothesis import example, given, settings
from hypothesis import strategies as st
from open_closed_typescript_shapes import typescript_findings

_MODEL = (
    "export type ImportRequest = {\n"
    '  readonly kind: "file" | "link" | "text";\n'
    "};\n"
)
_SPELLINGS = ["member", "parameter", "local"]
_SPLITS = [
    (["file", "link"], ["text"]),
    (["file"], ["link", "text"]),
    (["text", "file"], ["link"]),
]


def _consumer(name: str, variants: list[str], spelling: str) -> str:
    parameter = "request: ImportRequest"
    subject = "kind"
    destructuring = ""

    if spelling == "member":
        subject = "request.kind"
    elif spelling == "parameter":
        parameter = "{ kind }: ImportRequest"
    else:
        destructuring = "  const { kind } = request;\n"

    condition = " || ".join(f'{subject} === "{variant}"'
                            for variant in variants)

    return (
        'import type { ImportRequest } from "./models";\n'
        f"export function {name}({parameter}): boolean {{\n"
        f"{destructuring}  return {condition};\n}}\n"
    )


@given(
    split=st.sampled_from(_SPLITS),
    label=st.sampled_from(_SPELLINGS),
    origin=st.sampled_from(_SPELLINGS),
)
@example(split=_SPLITS[0], label="parameter", origin="parameter")
@example(split=_SPLITS[0], label="local", origin="member")
@settings(max_examples=8, deadline=None)
def test_destructured_kind_property_keeps_the_scattered_axis(
    split: tuple[list[str], list[str]], label: str, origin: str
) -> None:
    findings = typescript_findings(
        {
            "src/models.ts": _MODEL,
            "src/label.ts": _consumer("label", split[0], label),
            "src/origin.ts": _consumer("origin", split[1], origin),
        }
    )
    message = (
        "ImportRequest.kind dispatch is scattered across 2 functions in "
        "2 files: file, link, text"
    )

    assert findings == [
        f"src/label.ts:2: {message}",
        f"src/origin.ts:2: {message}",
    ]
