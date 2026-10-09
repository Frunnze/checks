from srp_effects import effect_domains
from srp_entities import external_entities, reason_coefficient
from srp_metrics import CallableFacts, entity_reasons


def members_of(owner: dict, callables: list[CallableFacts]) -> list[CallableFacts]:
    return [member for member in callables if member.owner == owner["name"]]


def entity_members(members: list[CallableFacts]) -> dict[str, list[str]]:
    reached: dict[str, list[str]] = {}
    for member in members:
        for name in external_entities(member.calls + member.delegated_effects):
            reached.setdefault(name, []).append(member.name)
    return {name: sorted(names) for name, names in sorted(reached.items())}


def owner_score(owner: dict, callables: list[CallableFacts]) -> dict:
    members = members_of(owner, callables)
    direct_calls = [call for member in members for call in member.calls]
    delegated_calls = [call for member in members for call in member.delegated_effects]
    direct = effect_domains(direct_calls)
    delegated = effect_domains(delegated_calls)
    domains = effect_domains(direct_calls + delegated_calls)
    entities = external_entities(direct_calls + delegated_calls)
    reached = entity_members(members)
    return {
        **owner,
        "coefficient": round(reason_coefficient(entities), 12),
        "entities": entities,
        "entity_members": reached,
        "metrics": {"members": len(members)},
        "effect_domains": domains,
        "direct_effect_domains": direct,
        "delegated_effect_domains": delegated,
        "reasons": entity_reasons(direct, delegated)
        + [
            f"{name} is reached by: " + ", ".join(names)
            for name, names in reached.items()
        ],
    }
