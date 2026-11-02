import subprocess
import sys
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from check_support import HYPOTHESIS_SETTINGS

_CHECKS = Path(__file__).resolve().parents[2] / "checks"
_FINDER = (
    _CHECKS / "experimental" / "crossed-names" / "python" / "crossed_names.py"
)
_SIDES = ("north", "south", "east", "west", "inner", "outer")


def _report_for(tmp_path: Path, source: str) -> list[str]:
    module = tmp_path / "layout.py"
    _ = module.write_text(source, encoding="utf-8")

    finished = subprocess.run(
        [sys.executable, str(_FINDER)],
        input="layout.py",
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )

    return finished.stdout.splitlines()


def test_reports_a_keyword_reading_another_keywords_value(
    tmp_path: Path,
) -> None:
    source = (
        "def spacing(desktop, styles):\n"
        "    return Spacing(\n"
        "        desktop=desktop.gap,\n"
        "        tablet=styles.tablet.gap,\n"
        "        mobile=styles.tablet.gap,\n"
        "    )\n"
    )

    expected = (
        "layout.py:5: mobile takes the value written for tablet"
        " (styles.tablet.gap) - give mobile its own value"
    )

    assert _report_for(tmp_path, source) == [expected]


def test_reports_a_dictionary_entry_copied_from_a_neighbour(
    tmp_path: Path,
) -> None:
    source = (
        "def borders_of(borders):\n"
        "    return {\n"
        "        'north': borders.north_width,\n"
        "        'south': borders.south_width,\n"
        "        'east': borders.south_width,\n"
        "        'west': borders.west_width,\n"
        "    }\n"
    )

    expected = (
        "layout.py:5: east takes the value written for south"
        " (borders.south_width) - give east its own value"
    )

    assert _report_for(tmp_path, source) == [expected]


def test_reports_an_attribute_wired_to_a_neighbours_class(
    tmp_path: Path,
) -> None:
    source = (
        "from steps import CheckerStep, ReaderStep, WriterStep\n"
        "class Pipeline:\n"
        "    def __init__(self, context):\n"
        "        self.context = context\n"
        "        self.reader = ReaderStep(context).run\n"
        "        self.writer = WriterStep(context).run\n"
        "        self.checker = WriterStep(context).run\n"
    )

    expected = (
        "layout.py:7: checker takes the value written for writer"
        " (WriterStep(context).run) - give checker its own value"
    )

    assert _report_for(tmp_path, source) == [expected]


def test_reports_a_name_copied_when_the_right_name_exists(
    tmp_path: Path,
) -> None:
    source = (
        "def box(frame_width, frame_height, frame_depth):\n"
        "    width = frame_width\n"
        "    height = frame_height\n"
        "    depth = frame_height\n"
        "    return width, height, depth\n"
    )

    expected = (
        "layout.py:4: depth takes the value written for height"
        " (frame_height) - give depth its own value"
    )

    assert _report_for(tmp_path, source) == [expected]


def test_passes_every_item_reading_its_own_value(tmp_path: Path) -> None:
    source = (
        "def spacing(desktop, styles):\n"
        "    return Spacing(\n"
        "        desktop=desktop.gap,\n"
        "        tablet=styles.tablet.gap,\n"
        "        mobile=styles.mobile.gap,\n"
        "    )\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_a_group_of_two(tmp_path: Path) -> None:
    source = "size = Size(width=box.width_px, height=box.width_px)\n"

    assert _report_for(tmp_path, source) == []


@pytest.mark.parametrize(
    "computed",
    [
        "{side} * 2",
        "{side} or 0",
        "{side} > 0",
        "{side} if wide else 0",
        "-{side}",
        "lambda: {side}",
    ],
)
def test_passes_computed_values(tmp_path: Path, computed: str) -> None:
    desktop = computed.format(side="styles.desktop.gap")
    tablet = computed.format(side="styles.tablet.gap")
    source = (
        f"spacing = Spacing(desktop={desktop}, tablet={tablet},"
        f" mobile={tablet})\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_a_value_shared_by_three_items(tmp_path: Path) -> None:
    source = (
        "theme = Theme(\n"
        "    header=palette.header_color,\n"
        "    body=palette.header_color,\n"
        "    footer=palette.header_color,\n"
        "    sidebar=palette.sidebar_color,\n"
        ")\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_a_group_whose_items_rarely_name_their_key(
    tmp_path: Path,
) -> None:
    source = (
        "layout = Layout(\n"
        "    left=margins.left_width,\n"
        "    right=defaults.gap,\n"
        "    top=defaults.padding,\n"
        "    bottom=margins.left_width,\n"
        ")\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_an_alias_table(tmp_path: Path) -> None:
    source = (
        "LEVELS = {\n"
        "    'warning': levels.WARNING,\n"
        "    'caution': levels.WARNING,\n"
        "    'error': levels.ERROR,\n"
        "}\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_an_alias_table_of_constructor_calls(tmp_path: Path) -> None:
    source = (
        "CODECS = {\n"
        "    'json_codec': codecs.JsonCodec(),\n"
        "    'fallback': codecs.JsonCodec(),\n"
        "    'xml_codec': codecs.XmlCodec(),\n"
        "}\n"
    )

    assert _report_for(tmp_path, source) == []


@pytest.mark.parametrize(
    ("short", "long"), [("hist", "histogram"), ("graph", "subgraph")]
)
def test_passes_a_key_spelled_as_a_variant_of_another(
    tmp_path: Path, short: str, long: str
) -> None:
    source = (
        "def plots(self):\n"
        "    return {\n"
        f"        '{short}': self._{short}_plot,\n"
        f"        '{long}': self._{short}_plot,\n"
        "        'scatter': self._scatter_plot,\n"
        "    }\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_a_name_whose_renamed_twin_does_not_exist(
    tmp_path: Path,
) -> None:
    source = (
        "def box(frame_width, frame_height):\n"
        "    width = frame_width\n"
        "    height = frame_height\n"
        "    depth = frame_height\n"
        "    return width, height, depth\n"
    )

    assert _report_for(tmp_path, source) == []


def test_passes_a_pipeline_rebinding_one_name(tmp_path: Path) -> None:
    source = (
        "def forward(x):\n"
        "    x = x.squeeze(2)\n"
        "    x = layer(x)\n"
        "    x = x.unsqueeze(2)\n"
        "    y = x.unsqueeze(2)\n"
        "    x = head(x)\n"
        "    return x, y\n"
    )

    assert _report_for(tmp_path, source) == []


@HYPOTHESIS_SETTINGS
@given(
    sides=st.lists(
        st.sampled_from(_SIDES), min_size=3, max_size=5, unique=True
    )
)
def test_crossed_property_flags_only_the_copied_keyword(
    tmp_path: Path, sides: list[str]
) -> None:
    first, copied = sides[0], sides[-1]
    lines = [f"    {side}=settings.{side}.size,\n" for side in sides[:-1]]
    lines.append(f"    {copied}=settings.{first}.size,\n")
    source = "frame = Frame(\n" + "".join(lines) + ")\n"

    expected = (
        f"layout.py:{len(sides) + 1}: {copied} takes the value written for"
        f" {first} (settings.{first}.size) - give {copied} its own value"
    )

    report = _report_for(tmp_path, source)

    assert report == [expected]
