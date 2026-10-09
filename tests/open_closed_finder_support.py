import keyword
import sys
import tempfile
from pathlib import Path

from hypothesis import strategies as st

from typescript_finder_support import CHECKS

FINDER_DIRECTORY = CHECKS / "experimental" / "open-closed" / "python"

if str(FINDER_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(FINDER_DIRECTORY))

from variant_dispatches import VariantDispatches, message_for


def findings_for(
    modules: dict[str, str], order: list[str] | None = None
) -> list[str]:
    with tempfile.TemporaryDirectory() as directory:
        written = written_paths(Path(directory), modules)
        chosen = (
            written
            if order is None
            else [str(Path(directory) / name) for name in order]
        )

        return reports_for(chosen)


def written_paths(root: Path, modules: dict[str, str]) -> list[str]:
    paths: list[str] = []

    for name, source in modules.items():
        module = root / name
        module.parent.mkdir(parents=True, exist_ok=True)
        _ = module.write_text(source, encoding="utf-8")
        paths.append(str(module))

    return paths


def reports_for(paths: list[str]) -> list[str]:
    return [
        f"{Path(finding.path).name}:{finding.line_number}: "
        f"{message_for(finding)}"
        for finding in VariantDispatches().find_in(paths)
    ]


IDENTIFIERS = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz", min_size=3, max_size=7
).filter(lambda name: not keyword.iskeyword(name))
variant_sets = st.lists(
    IDENTIFIERS, min_size=3, max_size=5, unique=True
).map(sorted)
subject_names = IDENTIFIERS.map(lambda name: f"{name}_kind")


def equality_chain(subject: str, variants: list[str]) -> str:
    branches = "".join(
        f"    if {subject} == {variant!r}:\n        return {index}\n"
        for index, variant in enumerate(variants)
    )

    return f"def route({subject}):\n{branches}    return -1\n"


def or_chain(subject: str, variants: list[str]) -> str:
    condition = " or ".join(
        f"{subject} == {variant!r}" for variant in variants
    )

    return (
        f"def route({subject}):\n"
        f"    if {condition}:\n        return 1\n"
        "    return -1\n"
    )


_CONTAINERS = ("({values})", "[{values}]", "{{{values}}}")


def membership_chain(
    subject: str, variants: list[str], container: int = 0
) -> str:
    values = ", ".join(repr(variant) for variant in variants)
    written = _CONTAINERS[container % len(_CONTAINERS)].format(values=values)

    return (
        f"def route({subject}):\n"
        f"    if {subject} in {written}:\n        return 1\n"
        "    return -1\n"
    )


def match_chain(subject: str, variants: list[str]) -> str:
    cases = "".join(
        f"        case {variant!r}:\n            return {index}\n"
        for index, variant in enumerate(variants)
    )

    return (
        f"def route({subject}):\n"
        f"    match {subject}:\n{cases}"
        "        case _:\n            return -1\n"
    )


def constant_chain(subject: str, variants: list[str]) -> str:
    names = [f"{variant.upper()}_KIND" for variant in variants]
    header = "".join(
        f"{name} = {variant!r}\n"
        for name, variant in zip(names, variants, strict=True)
    )
    branches = "".join(
        f"    if {subject} == {name}:\n        return {index}\n"
        for index, name in enumerate(names)
    )

    return f"{header}\n\ndef route({subject}):\n{branches}    return -1\n"


def enum_chain(subject: str, variants: list[str]) -> str:
    members = "".join(
        f"    {variant.upper()} = {variant!r}\n" for variant in variants
    )
    branches = "".join(
        f"    if {subject} == Kind.{variant.upper()}:\n"
        f"        return {index}\n"
        for index, variant in enumerate(variants)
    )

    return (
        "from enum import Enum\n\n\n"
        f"class Kind(Enum):\n{members}\n\n"
        f"def route({subject}):\n{branches}    return -1\n"
    )


def handler_registry(name: str, variants: list[str]) -> str:
    definitions = "".join(
        f"def {variant}(unit):\n    return {index}\n\n\n"
        for index, variant in enumerate(variants)
    )
    entries = ", ".join(f"{variant!r}: {variant}" for variant in variants)

    return f"{definitions}{name} = {{{entries}}}\n"


def label_registry(name: str, variants: list[str]) -> str:
    entries = ", ".join(
        f"{variant!r}: {variant.title()!r}" for variant in variants
    )

    return f"{name} = {{{entries}}}\n"


def abstraction_module(implementations: list[str]) -> str:
    subclasses = "".join(
        f"class {name.title()}Exporter(Exporter):\n"
        "    def export(self, deck):\n        return b''\n\n\n"
        for name in implementations
    )

    return (
        "from abc import ABC, abstractmethod\n\n\n"
        "class Exporter(ABC):\n"
        "    @abstractmethod\n"
        "    def export(self, deck):\n        ...\n\n\n"
        f"{subclasses}"
    )


def factory_body(implementations: list[str]) -> str:
    branches = "".join(
        f"        if fmt == {name!r}:\n"
        f"            return {name.title()}Exporter()\n"
        for name in implementations[:-1]
    )
    last = implementations[-1].title()

    return (
        "class ExporterFactory:\n"
        "    def create(self, fmt: str) -> Exporter:\n"
        f"{branches}        return {last}Exporter()\n"
    )
