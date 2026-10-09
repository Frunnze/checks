from pathlib import Path

from test_open_closed import _report_for


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
