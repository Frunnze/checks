import posixpath
import tempfile
from pathlib import Path

from hypothesis import example, given, settings
from hypothesis import strategies as st

from typescript_finder_support import CHECKS, report_from

ImportGraph = dict[str, list[str]]

_FINDERS = CHECKS / "experimental" / "feature-isolation" / "typescript"
_FEATURE_IMPORTS = _FINDERS / "feature_imports.js"
_SHARED_USAGE = _FINDERS / "shared_usage.js"
_SETTINGS = settings(max_examples=8, deadline=None)
_METER_THROUGH_RAIL: ImportGraph = {
    "src/shared/meter.ts": [],
    "src/shared/rail.ts": ["src/shared/meter.ts"],
    "src/features/notes/notesPage.ts": ["src/shared/rail.ts"],
    "src/features/folder/folderPage.ts": ["src/shared/rail.ts"],
}
_CHATBOT_CROSSING: ImportGraph = {
    "src/features/chatbot/chatbotPage.ts": [],
    "src/features/flashcards/flashcardsPage.ts": [
        "src/features/chatbot/chatbotPage.ts"
    ],
}

folder_names = st.from_regex(r"[a-z]{3,8}", fullmatch=True)


@st.composite
def import_graphs(draw: st.DrawFn) -> ImportGraph:
    features = draw(
        st.lists(folder_names, min_size=2, max_size=4, unique=True)
    )
    shared = draw(st.lists(folder_names, min_size=1, max_size=3, unique=True))
    paths: list[str] = []

    for feature in features:
        paths.append(f"src/features/{feature}/{feature}Page.ts")

    for name in shared:
        paths.append(f"src/shared/{name}.ts")

    graph: ImportGraph = {}

    for importer in sorted(paths):
        targets = draw(
            st.lists(st.sampled_from(paths), max_size=3, unique=True)
        )
        graph[importer] = []

        for target in targets:
            if target != importer:
                graph[importer].append(target)

    return graph


def _specifier(importer: str, target: str, suffix: str) -> str:
    module = target.removesuffix(".ts")
    relative = posixpath.relpath(module, posixpath.dirname(importer))

    if not relative.startswith(".."):
        relative = "./" + relative

    return relative + suffix


def _rendered(graph: ImportGraph, suffix: str) -> dict[str, str]:
    files: dict[str, str] = {}

    for importer, targets in graph.items():
        lines: list[str] = []

        for index, target in enumerate(targets):
            specifier = _specifier(importer, target, suffix)
            lines.append(f'import * as m{index} from "{specifier}";\n')

        lines.append("export const value = 1;\n")
        files[importer] = "".join(lines)

    return files


def _findings(root: Path, files: dict[str, str]) -> list[list[str]]:
    crossings = report_from(_FEATURE_IMPORTS, root, files)
    lonely = report_from(_SHARED_USAGE, root, files)

    return [crossings, lonely]


@given(
    graph=import_graphs(),
    ancestor=st.sampled_from(["features", "shared", "src", "tests"]),
)
@example(graph=_METER_THROUGH_RAIL, ancestor="features")
@_SETTINGS
def test_finders_property_ignore_where_the_project_is_checked_out(
    graph: ImportGraph, ancestor: str
) -> None:
    files = _rendered(graph, "")

    with tempfile.TemporaryDirectory() as directory:
        plain = _findings(Path(directory) / "plain" / "repo", files)
        moved = _findings(Path(directory) / ancestor / "repo", files)

    assert moved == plain


@given(graph=import_graphs())
@example(graph=_CHATBOT_CROSSING)
@_SETTINGS
def test_finders_property_resolve_a_js_specifier_to_its_typescript_module(
    graph: ImportGraph,
) -> None:
    with tempfile.TemporaryDirectory() as directory:
        extensionless = _findings(
            Path(directory) / "extensionless", _rendered(graph, "")
        )
        emitted = _findings(
            Path(directory) / "emitted", _rendered(graph, ".js")
        )

    assert emitted == extensionless
