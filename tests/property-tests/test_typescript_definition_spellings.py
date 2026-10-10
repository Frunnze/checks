from pathlib import Path

import pytest

from typescript_finder_support import CHECKS, report_from

FINDER = (
    CHECKS
    / "experimental"
    / "property-tests"
    / "typescript"
    / "property_test_coverage.js"
)
SOURCE = "src/units.ts"


@pytest.mark.parametrize(
    ("source", "line_number"),
    [
        (
            "export const score = ((value: number): number => value * 2)\n"
            "  satisfies (value: number) => number;\n",
            1,
        ),
        (
            "export const score = ((value: number) => value * 2) as (\n"
            "  value: number,\n"
            ") => number;\n",
            1,
        ),
        (
            "export const units = {\n"
            "  score: (value: number) => value * 2,\n"
            "} as const;\n",
            2,
        ),
    ],
)
def test_reports_a_function_behind_a_type_only_wrapper(
    tmp_path: Path, source: str, line_number: int
) -> None:
    report = report_from(FINDER, tmp_path, {SOURCE: source})

    assert report == [
        f'{SOURCE}:{line_number}: score needs a test.prop named '
        '"score property ..."'
    ]
