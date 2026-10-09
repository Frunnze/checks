from dataclasses import asdict, dataclass, field

from srp_effects import effect_domains
from srp_entities import external_entities, reason_coefficient

THRESHOLD = 0.5


@dataclass
class CallableFacts:
    name: str
    line: int
    owner: str
    lines: int = 0
    statements: int = 0
    complexity: int = 1
    nesting: int = 0
    parameters: int = 0
    locals: int = 0
    calls: list[str] = field(default_factory=list)
    call_aliases: dict[str, str] = field(default_factory=dict)
    delegated_effects: list[str] = field(default_factory=list)
    binding_stable: bool = True
    resources: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    references: list[str] = field(default_factory=list)
    foreign_data: list[str] = field(default_factory=list)
    flow: list[dict] = field(default_factory=list)
    client_only: bool = False


def entity_reasons(
    direct: dict[str, list[str]], delegated: dict[str, list[str]]
) -> list[str]:
    reasons = []
    for name in sorted(set(direct) | set(delegated)):
        reached = set(direct.get(name, [])) | set(delegated.get(name, []))
        operations = sorted(reached)
        via = "" if name in direct else " via resolved helpers"
        reasons.append(f"{name}{via}: " + ", ".join(operations))
    return reasons


def callable_score(facts: CallableFacts) -> dict:
    direct = effect_domains(facts.calls)
    delegated = effect_domains(facts.delegated_effects)
    domains = effect_domains(facts.calls + facts.delegated_effects)
    entities = external_entities(facts.calls + facts.delegated_effects)
    return {
        "name": facts.name,
        "line": facts.line,
        "kind": "callable",
        "coefficient": round(reason_coefficient(entities), 12),
        "entities": entities,
        "metrics": asdict(facts),
        "effect_domains": domains,
        "direct_effect_domains": direct,
        "delegated_effect_domains": delegated,
        "reasons": entity_reasons(direct, delegated),
    }
