import tempfile
from pathlib import Path

from hypothesis import example, given, settings
from hypothesis import strategies as st
from srp_support import analyze, unit_named

IMPORTED_OPERATIONS = {
    "process": ("from subprocess import run", "run"),
    "network": ("from httpx import get", "get"),
    "filesystem": ("from shutil import copy", "copy"),
    "authentication": ("from jwt import encode", "encode"),
}
NEUTRAL_METHOD_NAMES = [
    "execute",
    "fetch",
    "duplicate",
    "sign",
    "perform",
    "handle",
]
COLLIDING_NAMES = [operation for _, operation in IMPORTED_OPERATIONS.values()]
IMPORTED_MODULES = {
    "process": ("import subprocess", "subprocess.run(['ls'])"),
    "network": ("import httpx", "httpx.get(target)"),
    "filesystem": ("import shutil", "shutil.copy(target, target)"),
}
DOMAIN_LISTS = st.lists(
    st.sampled_from(sorted(IMPORTED_OPERATIONS)),
    min_size=2,
    max_size=4,
    unique=True,
)


def unit_entities(source: str, unit: str) -> list[str]:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "adapter.py"
        _ = path.write_text(source, encoding="utf-8")
        report = analyze([path], "node", None)

    return unit_named(report, unit)["entities"]


def adapter_class(
    domains: list[str], method_names: list[str], attribute: str | None
) -> str:
    lines = [IMPORTED_OPERATIONS[domain][0] for domain in domains]
    lines.append("class Adapter:")

    if attribute is not None:
        lines.append(f"    {attribute} = 'configured'")

    for domain, method_name in zip(domains, method_names, strict=True):
        operation = IMPORTED_OPERATIONS[domain][1]
        lines.append(f"    def {method_name}(self, value):")
        lines.append(f"        return {operation}(value)")

    return "\n".join(lines) + "\n"


@st.composite
def domains_with_method_names(
    draw: st.DrawFn,
) -> tuple[list[str], list[str]]:
    domains = draw(DOMAIN_LISTS)
    method_names = draw(
        st.lists(
            st.sampled_from(NEUTRAL_METHOD_NAMES + COLLIDING_NAMES),
            min_size=len(domains),
            max_size=len(domains),
            unique=True,
        )
    )

    return domains, method_names


@settings(max_examples=60, deadline=None)
@given(case=domains_with_method_names())
@example(case=(["filesystem", "process"], ["duplicate", "run"]))
def test_class_entities_property_ignore_method_names(
    case: tuple[list[str], list[str]],
) -> None:
    domains, method_names = case
    neutral_names = NEUTRAL_METHOD_NAMES[: len(domains)]
    neutral = unit_entities(
        adapter_class(domains, neutral_names, None), "<module>.Adapter"
    )
    renamed = unit_entities(
        adapter_class(domains, method_names, None), "<module>.Adapter"
    )

    assert neutral == sorted(domains)
    assert renamed == neutral


@settings(max_examples=60, deadline=None)
@given(
    domains=DOMAIN_LISTS,
    attribute=st.sampled_from([*COLLIDING_NAMES, "label"]),
)
@example(domains=["filesystem", "process"], attribute="run")
def test_class_attributes_property_never_shadow_names_in_methods(
    domains: list[str], attribute: str
) -> None:
    neutral_names = NEUTRAL_METHOD_NAMES[: len(domains)]
    source = adapter_class(domains, neutral_names, attribute)

    assert unit_entities(source, "<module>.Adapter") == sorted(domains)


@settings(max_examples=60, deadline=None)
@given(
    domains=st.lists(
        st.sampled_from(sorted(IMPORTED_MODULES)),
        min_size=2,
        max_size=3,
        unique=True,
    ),
    variable=st.sampled_from(["item", "subprocess", "httpx", "shutil"]),
)
@example(domains=["filesystem", "process"], variable="subprocess")
def test_comprehension_variables_property_never_shadow_function_names(
    domains: list[str], variable: str
) -> None:
    lines = [IMPORTED_MODULES[domain][0] for domain in domains]
    lines.append("def work(target, names):")
    lines.extend(f"    {IMPORTED_MODULES[domain][1]}" for domain in domains)
    lines.append(f"    return [len({variable}) for {variable} in names]")
    source = "\n".join(lines) + "\n"

    assert unit_entities(source, "<module>.work") == sorted(domains)
