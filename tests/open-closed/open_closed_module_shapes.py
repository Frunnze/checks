from hypothesis import strategies as st

from open_closed_finder_support import (
    IDENTIFIERS,
    abstraction_module,
    constant_chain,
    enum_chain,
    equality_chain,
    factory_body,
    handler_registry,
    label_registry,
    match_chain,
    membership_chain,
    or_chain,
    variant_sets,
)


def literal_alias(variants: list[str]) -> str:
    values = ", ".join(repr(variant) for variant in variants)

    return (
        "from typing import Literal\n\n"
        f"Kind = Literal[{values}]\n"
    )


def protocol_visitor(variants: list[str]) -> str:
    methods = "".join(
        f"    def visit_{variant}(self, node) -> int:\n        ...\n\n"
        for variant in variants
    )

    return (
        "from typing import Protocol\n\n\n"
        f"class Visitor(Protocol):\n{methods}"
    )


def annotated_registry(variants: list[str]) -> str:
    values = ", ".join(repr(variant) for variant in variants)
    entries = ", ".join(f"{variant!r}: len" for variant in variants)

    return (
        "from typing import Callable, Literal\n\n"
        f"Kind = Literal[{values}]\n"
        f"TABLE: dict[Kind, Callable[[str], int]] = {{{entries}}}\n"
    )


def nested_scopes(subject: str, variants: list[str]) -> str:
    inner = "".join(
        f"        if {subject} == {variant!r}:\n            return {index}\n"
        for index, variant in enumerate(variants)
    )

    return (
        f"def outer({subject}):\n"
        f"    def inner():\n{inner}        return -1\n"
        "    return inner\n\n\n"
        f"picker = lambda {subject}: {subject} == {variants[0]!r}\n"
    )


def isinstance_dispatch(variants: list[str]) -> str:
    classes = "".join(
        f"class {variant.title()}Node:\n    pass\n\n\n" for variant in variants
    )
    branches = "".join(
        f"    if isinstance(node, {variant.title()}Node):\n"
        f"        return {index}\n"
        for index, variant in enumerate(variants)
    )

    return f"{classes}def render(node):\n{branches}    return -1\n"


def odd_annotations(variants: list[str]) -> str:
    return (
        "from typing import Literal, Mapping\n\n"
        f"Empty = Literal[{variants[0]!r}]\n"
        "PAIRS: dict[()] = {}\n"
        "LOOKUP: Mapping[Empty, str] = {}\n"
        "BLANK: dict[str, str] = {}\n"
    )


def enum_axis(variants: list[str]) -> str:
    members = "".join(
        f"    {variant.upper()} = {variant!r}\n" for variant in variants
    )
    branches = "".join(
        f"    if unit.kind == Kind.{variant.upper()}:\n"
        f"        return {index}\n"
        for index, variant in enumerate(variants)
    )

    return (
        "from enum import Enum\n\n\n"
        f"class Kind(Enum):\n{members}\n\n"
        f"def render(unit):\n{branches}    return -1\n"
    )


def split_factory(implementations: list[str]) -> str:
    branches = "".join(
        f"        if fmt == {name!r}:\n"
        f"            return {name.title()}Exporter()\n"
        for name in implementations
    )

    return (
        "class ExporterFactory:\n"
        "    def create(self, fmt: str) -> Exporter:\n"
        f"{branches}        return None\n"
    )


def dataclass_field(variants: list[str]) -> str:
    values = ", ".join(repr(variant) for variant in variants)

    return (
        "from dataclasses import dataclass\n"
        "from typing import Literal\n\n"
        f"Kind = Literal[{values}]\n\n\n"
        "@dataclass(frozen=True)\n"
        "class Unit:\n    kind: Kind\n    name: str\n"
    )


_SHAPES = (
    equality_chain,
    or_chain,
    membership_chain,
    match_chain,
    constant_chain,
    enum_chain,
    nested_scopes,
)
_AXIS_SHAPES = (
    enum_axis,
    split_factory,
    literal_alias,
    protocol_visitor,
    annotated_registry,
    isinstance_dispatch,
    odd_annotations,
    dataclass_field,
)


@st.composite
def module_sources(draw: st.DrawFn) -> str:
    variants = draw(variant_sets)
    subject = draw(IDENTIFIERS.map(lambda name: f"{name}_kind"))
    choices = draw(
        st.lists(
            st.sampled_from(range(len(_SHAPES) + len(_AXIS_SHAPES) + 3)),
            min_size=1,
            max_size=3,
            unique=True,
        )
    )

    return "\n\n".join(_render(index, subject, variants) for index in choices)


def _render(index: int, subject: str, variants: list[str]) -> str:
    if index < len(_SHAPES):
        return _SHAPES[index](subject, variants)

    shifted = index - len(_SHAPES)

    if shifted < len(_AXIS_SHAPES):
        return _AXIS_SHAPES[shifted](variants)
    if shifted == len(_AXIS_SHAPES):
        return handler_registry("HANDLERS", variants)
    if shifted == len(_AXIS_SHAPES) + 1:
        return label_registry("LABELS", variants)

    return abstraction_module(variants[:2]) + factory_body(variants[:2])


@st.composite
def module_sets(draw: st.DrawFn) -> dict[str, str]:
    sources = draw(st.lists(module_sources(), min_size=1, max_size=4))

    return {
        f"module_{index}.py": source for index, source in enumerate(sources)
    }
