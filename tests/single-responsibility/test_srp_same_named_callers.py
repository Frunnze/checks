import pytest
from srp_support import run_project

HELPERS = (
    "import httpx\n\n\n"
    "def reach_network(address):\n"
    "    return httpx.get(address).text\n"
)
PROPERTY_PAIR = (
    "from pathlib import Path\n\nfrom helpers import reach_network\n\n\n"
    "class Holder:\n"
    "    def __init__(self, address):\n"
    "        self.address = address\n\n"
    "    @property\n"
    "    def value(self):\n"
    "        return reach_network(self.address)\n\n"
    "    @value.setter\n"
    "    def value(self, path):\n"
    "        Path(path).read_text()\n"
)
UNDERSCORE_REGISTRATIONS = (
    "from functools import singledispatch\nfrom pathlib import Path\n\n"
    "from helpers import reach_network\n\n\n"
    "@singledispatch\n"
    "def handle(argument):\n"
    "    return argument\n\n\n"
    "@handle.register(int)\n"
    "def _(argument):\n"
    "    return reach_network(argument)\n\n\n"
    "@handle.register(str)\n"
    "def _(argument):\n"
    "    return Path(argument).read_text()\n"
)


def owner_entities(report: dict, path: str, owner: str) -> list[str]:
    file = next(file for file in report["files"] if file["path"] == path)
    return next(
        unit["entities"] for unit in file["units"] if unit["name"] == owner
    )


SAME_NAMED_CALLERS = {
    "property getter and setter": (PROPERTY_PAIR, "<module>.Holder"),
    "underscore registrations": (UNDERSCORE_REGISTRATIONS, "<module>"),
}


@pytest.mark.parametrize(
    "source, owner",
    SAME_NAMED_CALLERS.values(),
    ids=list(SAME_NAMED_CALLERS),
)
def test_callers_sharing_a_name_keep_their_helper_effects(
    tmp_path, source, owner
):
    (tmp_path / "helpers.py").write_text(HELPERS)
    worker = tmp_path / "worker.py"
    worker.write_text(source)

    report = run_project(tmp_path)

    assert owner_entities(report, str(worker), owner) == [
        "filesystem",
        "network",
    ]
    assert report["failed"]
