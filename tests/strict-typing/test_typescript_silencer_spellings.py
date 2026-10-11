"""
The TypeScript strict-typing check must catch every silencer spelling tsc
or ESLint honours. Domain: a module in web/src behind a generated
directive - @ts-nocheck, @ts-ignore or @ts-expect-error in any letter
case, or an ESLint rule comment laid out on one or several lines. Oracle:
postcondition - tsc or ESLint obeys each of these, so the silencer scan
must fail the gate and name the file.

Concrete inputs -> expected outputs:
- input:
      // @ts-nocheck
      export const label: number = "text";
  output: exit 1, "the type checker is silenced here",
  "web/src/value.ts:1:// @ts-nocheck".
- input (falsifying example, pinned as @example):
      // @TS-NOCHECK
      export const label: number = "text";
  output: expected exit 1, got exit 0 - tsc reads the pragma in any case
  and skipped the file; the linters gate passed it too.
- input (falsifying example, pinned as @example):
      /* eslint
        no-debugger: off
      */
  output: expected exit 1, got exit 0 - ESLint applied the rule comment
  split over lines; the one-line form was already caught.
"""

import tempfile
from pathlib import Path

from hypothesis import example, given, settings
from hypothesis import strategies as st

from check_support import (
    link_toolkit_node_modules,
    repository,
    run_configured,
    stage_file,
)

CONFIGURATION = 'source_directories = ["web/src"]\n'
MODULE = "web/src/value.ts"
TSCONFIG = (
    '{"compilerOptions": {"strict": true, "noEmit": true}, '
    '"include": ["src"]}\n'
)
TYPE_ERROR = 'export const label: number = "text";\n'
DIRECTIVES = ("ts-nocheck", "ts-ignore", "ts-expect-error")
RULE_LAYOUTS = (
    "/* eslint {rule} */\n",
    "/* eslint\n  {rule}\n*/\n",
    "/*\n  eslint {rule}\n*/\n",
)


def _recased(text: str, upper: list[bool]) -> str:
    letters: list[str] = []

    for position, letter in enumerate(text):
        if upper[position % len(upper)]:
            letters.append(letter.upper())
        else:
            letters.append(letter)

    return "".join(letters)


@st.composite
def _silenced_modules(draw: st.DrawFn) -> str:
    if draw(st.booleans()):
        directive = draw(st.sampled_from(DIRECTIVES))
        upper = draw(st.lists(st.booleans(), min_size=1, max_size=4))

        return f"// @{_recased(directive, upper)}\n{TYPE_ERROR}"

    layout = draw(st.sampled_from(RULE_LAYOUTS))
    rule = draw(st.sampled_from(("no-debugger: off", "no-console: 0")))

    return layout.format(rule=rule) + "export const value = 1;\n"


@given(source=_silenced_modules())
@example(source=f"// @TS-NOCHECK\n{TYPE_ERROR}")
@example(source="/* eslint\n  no-debugger: off\n*/\nexport const value = 1;\n")
@settings(max_examples=6, deadline=None)
def test_silencer_property_catches_every_honoured_spelling(
    source: str,
) -> None:
    with tempfile.TemporaryDirectory() as directory:
        project = Path(directory)
        repository(project)
        link_toolkit_node_modules(project)
        stage_file(project, MODULE, source)
        stage_file(project, "web/tsconfig.json", TSCONFIG)
        stage_file(project, "web/package.json", '{"name": "web"}\n')
        (project / "web" / "node_modules").mkdir()
        finished = run_configured(project, CONFIGURATION, "strict-typing")

    assert finished.returncode == 1, finished.stdout
    assert "the type checker is silenced here" in finished.stderr
    assert MODULE in finished.stderr
