"""
The finder is a pre-commit gate, so on any valid Python it must terminate
with well-formed, reproducible reports rather than a traceback, and its
verdict must not depend on the order the files reach it. Domain: 1-4
generated modules, each assembled from 1-3 open/closed shapes (dispatch
chains, Literal and Enum axes, Protocol visitors, annotated and plain
registries, isinstance dispatch, abstract factories, odd annotations)
over 3-5 variant names. Oracle: implicit (no unexpected exception,
line numbers inside the reported file) plus the metamorphic relation
"permuting the input paths leaves the finding set unchanged".

Concrete inputs -> expected outputs:
- input:
      module_0.py:
          from typing import Literal

          Kind = Literal['deck', 'file', 'note']
      module_1.py:
          def route(a_kind):
              if a_kind == 'deck':
                  return 0
              if a_kind == 'file':
                  return 1
              if a_kind == 'note':
                  return 2
              return -1
  output: reported -> ["module_1.py:1: route compares a_kind to 3
  strings: deck, file, note"], and the same single report when the two
  paths are passed as ["module_1.py", "module_0.py"].
- input: the same two modules, reports parsed for line numbers ->
  every report's line number is between 1 and the line count of the file
  it names.
"""

import random
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

from open_closed_finder_support import findings_for
from open_closed_module_shapes import module_sets


def _line_numbers(reports: list[str]) -> list[tuple[str, int]]:
    parsed: list[tuple[str, int]] = []

    for report in reports:
        name, line_number, _ = report.split(":", 2)
        parsed.append((name, int(line_number)))

    return parsed


@given(modules=module_sets())
@settings(max_examples=300, deadline=None)
def test_finder_property_reports_lines_inside_the_file_it_names(
    modules: dict[str, str],
) -> None:
    reports = findings_for(modules)

    for name, line_number in _line_numbers(reports):
        assert 1 <= line_number <= len(modules[name].splitlines())


@given(modules=module_sets(), seed=st.integers(min_value=0, max_value=999))
@settings(max_examples=300, deadline=None)
def test_finder_property_ignores_the_order_of_its_input_paths(
    modules: dict[str, str], seed: int
) -> None:
    shuffled = list(modules)
    random.Random(seed).shuffle(shuffled)
    reordered = findings_for(modules, order=shuffled)

    assert sorted(reordered) == sorted(findings_for(modules))


@given(modules=module_sets())
@settings(max_examples=200, deadline=None)
def test_finder_property_returns_the_same_reports_on_a_repeated_run(
    modules: dict[str, str],
) -> None:
    assert findings_for(modules) == findings_for(modules)


@given(modules=module_sets())
@settings(max_examples=200, deadline=None)
def test_finder_property_names_only_the_paths_it_was_given(
    modules: dict[str, str],
) -> None:
    reports = findings_for(modules)

    for name, _ in _line_numbers(reports):
        assert Path(name).name in modules
