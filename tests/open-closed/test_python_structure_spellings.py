from pathlib import Path

import pytest
from test_python_structure_open_closed import report_from

_EXPORTERS = (
    "from abc import ABC, abstractmethod\n"
    "class Exporter(ABC):\n"
    "    @abstractmethod\n    def export(self) -> bytes: ...\n"
    "class CsvExporter(Exporter):\n"
    "    def export(self) -> bytes:\n        return b''\n"
    "class PdfExporter(Exporter):\n"
    "    def export(self) -> bytes:\n        return b''\n"
)
_TWO_KEY_MODULES = {
    "data": (
        "AGE = {'min': 0, 'max': 120}\n"
        "SCORE = {'min': 0, 'max': 100}\n"
        "PRICE = {'min': 1, 'max': 999}\n"
    ),
    "behavior": (
        "def enable(): ...\n"
        "def disable(): ...\n"
        "LIGHT = {'on': enable, 'off': disable}\n"
        "FAN = {'on': enable, 'off': disable}\n"
        "HEATER = {'on': enable, 'off': disable}\n"
    ),
}


@pytest.mark.parametrize(
    "annotation", ["'Exporter'", '"exporters.Exporter"']
)
def test_flags_factory_with_a_quoted_return_annotation(
    tmp_path: Path, annotation: str
) -> None:
    files = {
        "src/exporters.py": _EXPORTERS,
        "src/factory.py": (
            "class ExporterFactory:\n"
            f"    def create(self, kind: str) -> {annotation}:\n"
            "        if kind == 'csv':\n            return CsvExporter()\n"
            "        return PdfExporter()\n"
        ),
    }

    assert report_from(tmp_path, files) == [
        (
            "src/factory.py:2: create closes Exporter over concrete "
            "implementations: CsvExporter, PdfExporter"
        )
    ]


@pytest.mark.parametrize("shape", sorted(_TWO_KEY_MODULES))
def test_allows_repeated_two_key_mappings_without_a_declared_axis(
    tmp_path: Path, shape: str
) -> None:
    files = {"src/limits.py": _TWO_KEY_MODULES[shape]}

    assert report_from(tmp_path, files) == []
