from pathlib import Path

from test_open_closed import _report_for
from test_python_structure_open_closed import report_from


def test_resolves_named_string_constants(tmp_path: Path) -> None:
    source = (
        "_CSV = 'csv'\n"
        "_PDF = 'pdf'\n"
        "_DOCX = 'docx'\n"
        "def convert(kind):\n"
        "    if kind == _CSV:\n        return 'csv'\n"
        "    if kind == _PDF:\n        return 'pdf'\n"
        "    if kind == _DOCX:\n        return 'docx'\n"
    )

    assert _report_for(tmp_path, source) == [
        (
            "service/src/features/units/presentation.py:4: convert compares "
            "kind to 3 strings: csv, docx, pdf"
        )
    ]


def test_resolves_string_constants_imported_from_another_module(
    tmp_path: Path,
) -> None:
    files = {
        "src/kinds.py": "DECK = 'deck'\nFILE = 'file'\nNOTE = 'note'\n",
        "src/route.py": (
            "from kinds import DECK, FILE as DOCUMENT\n"
            "from .kinds import NOTE\n"
            "def route(kind):\n"
            "    if kind == DECK:\n        return 0\n"
            "    if kind == DOCUMENT:\n        return 1\n"
            "    if kind == NOTE:\n        return 2\n"
        ),
    }

    assert report_from(tmp_path, files) == [
        "src/route.py:3: route compares kind to 3 strings: deck, file, note"
    ]


def test_flags_dispatch_over_any_member_spelling_of_a_scanned_enum(
    tmp_path: Path,
) -> None:
    files = {
        "src/kinds.py": (
            "from enum import Enum\n"
            "class Kind(str, Enum):\n"
            "    deck = 'deck'\n    file = 'file'\n    note = 'note'\n"
        ),
        "src/route.py": (
            "import kinds\n"
            "from kinds import Kind\n"
            "def route(kind, user):\n"
            "    if kind is Kind.deck:\n        return 0\n"
            "    if kind == kinds.Kind.file:\n        return 1\n"
            "    if kind == Kind.note.value:\n        return 2\n"
            "    if user.role in (roles.admin, roles.editor):\n"
            "        return 3\n"
            "    if user.role == roles.viewer:\n        return 4\n"
        ),
    }

    assert report_from(tmp_path, files) == [
        (
            "src/route.py:3: route compares kind to 3 enum members: "
            "Kind.deck, Kind.file, Kind.note"
        )
    ]


def test_flags_named_constant_dispatch_scattered_across_functions(
    tmp_path: Path,
) -> None:
    source = (
        "_TRUE_FALSE = 'true_or_false'\n"
        "_SHORT = 'short_answer'\n"
        "def prepare(item_type):\n"
        "    if item_type == _TRUE_FALSE:\n        return 'boolean'\n"
        "    if item_type == _SHORT:\n        return 'text'\n"
        "    return 'options'\n"
        "def grade(item_type):\n"
        "    if item_type == _SHORT:\n        return 'typed'\n"
        "    return 'selected'\n"
    )

    assert _report_for(tmp_path, source) == [
        (
            "service/src/features/units/presentation.py:3: item_type dispatch "
            "is scattered across 2 functions, starting at prepare: "
            "short_answer, true_or_false"
        )
    ]


def test_keeps_instance_attribute_dispatch_within_its_class(
    tmp_path: Path,
) -> None:
    source = (
        "class Order:\n"
        "    def is_paid(self):\n        return self.status == 'paid'\n"
        "    def is_open(self):\n        return self.status == 'open'\n"
        "class Invoice:\n"
        "    def is_void(self):\n        return self.status == 'void'\n"
    )

    assert _report_for(tmp_path, source) == [
        (
            "service/src/features/units/presentation.py:2: self.status "
            "dispatch is scattered across 2 functions, starting at is_paid: "
            "open, paid"
        )
    ]


def test_flags_factory_closed_over_a_concrete_implementation(
    tmp_path: Path,
) -> None:
    source = (
        "class Manager:\n    pass\n"
        "class OpenManager(Manager):\n    pass\n"
        "class ManagerFactory:\n"
        "    def get(self) -> Manager:\n"
        "        return OpenManager()\n"
    )

    assert _report_for(tmp_path, source) == [
        (
            "service/src/features/units/presentation.py:6: get closes Manager "
            "over concrete implementations: OpenManager"
        )
    ]


def test_allows_a_factory_with_an_injected_builder(tmp_path: Path) -> None:
    source = (
        "class Manager:\n    pass\n"
        "class ManagerFactory:\n"
        "    def __init__(self, builder):\n        self.builder = builder\n"
        "    def get(self) -> Manager:\n        return self.builder()\n"
    )

    assert _report_for(tmp_path, source) == []


def test_flags_concrete_dependency_stored_by_abstract_factory(
    tmp_path: Path,
) -> None:
    source = (
        "from abc import ABC, abstractmethod\n"
        "class Manager(ABC):\n"
        "    @abstractmethod\n    def run(self): ...\n"
        "class OpenClient:\n    pass\n"
        "class ManagerFactory:\n"
        "    def __init__(self):\n"
        "        self.client: OpenClient = OpenClient()\n"
        "    def get(self) -> Manager:\n        raise NotImplementedError\n"
    )

    assert _report_for(tmp_path, source) == [
        (
            "service/src/features/units/presentation.py:8: ManagerFactory "
            "leaks concrete dependencies while creating Manager: OpenClient"
        )
    ]


def test_flags_factory_of_a_protocol_named_through_its_module(
    tmp_path: Path,
) -> None:
    files = {
        "src/exporters.py": (
            "from typing import Protocol\n"
            "class Exporter(Protocol):\n"
            "    def export(self) -> bytes: ...\n"
            "class CsvExporter(Exporter):\n"
            "    def export(self) -> bytes:\n        return b''\n"
        ),
        "src/factory.py": (
            "import exporters\n"
            "class ExporterFactory:\n"
            "    def __init__(self):\n        self.client = HttpClient()\n"
            "    def create(self) -> exporters.Exporter:\n"
            "        return exporters.CsvExporter()\n"
        ),
    }

    assert report_from(tmp_path, files) == [
        (
            "src/factory.py:3: ExporterFactory leaks concrete dependencies "
            "while creating Exporter: HttpClient"
        ),
        (
            "src/factory.py:5: create closes Exporter over concrete "
            "implementations: CsvExporter"
        ),
    ]


def test_allows_injected_dependency_in_abstract_factory(
    tmp_path: Path,
) -> None:
    source = (
        "from abc import ABC, abstractmethod\n"
        "class Manager(ABC):\n"
        "    @abstractmethod\n    def run(self): ...\n"
        "class ManagerFactory:\n"
        "    def __init__(self, client):\n        self.client = client\n"
        "    def get(self) -> Manager:\n        raise NotImplementedError\n"
    )

    assert _report_for(tmp_path, source) == []
