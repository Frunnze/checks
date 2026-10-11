import pytest
from srp_support import run_report, unit_named

MODULE_FACTORY = (
    "import httpx\nfrom pathlib import Path\n\n\n"
    "def make_client() -> httpx.Client:\n"
    "    return httpx.Client()\n\n\n"
    "def sync(url, path):\n"
    "    Path(path).write_text(make_client().get(url).text)\n"
)
METHOD_FACTORY = (
    "import httpx\nfrom pathlib import Path\n\n\n"
    "class Syncer:\n"
    "    def _client(self) -> httpx.Client:\n"
    "        return httpx.Client()\n\n"
    "    def sync(self, url, path):\n"
    "        Path(path).write_text(self._client().get(url).text)\n"
)
INLINE_FACTORY_SOURCES = {
    "module factory": (MODULE_FACTORY, "<module>.sync"),
    "method factory": (METHOD_FACTORY, "<module>.Syncer.sync"),
}


@pytest.mark.parametrize(
    "source, name",
    INLINE_FACTORY_SOURCES.values(),
    ids=list(INLINE_FACTORY_SOURCES),
)
def test_factory_results_used_inline_keep_their_client(tmp_path, source, name):
    report = run_report(tmp_path, source)

    unit = unit_named(report, name)

    assert unit["entities"] == ["filesystem", "network"]
    assert report["failed"]
