from srp_effect_rules import EFFECT_RULES


def is_within_prefixes(qualified_name: str, prefixes: tuple[str, ...]) -> bool:
    for prefix in prefixes:
        if qualified_name == prefix or qualified_name.startswith(prefix + "."):
            return True
    return False


def is_catalogued_client(type_name: str) -> bool:
    for _, prefixes, _ in EFFECT_RULES:
        if is_within_prefixes(type_name, prefixes):
            return True
    return False


def effect_domains(calls: list[str]) -> dict[str, list[str]]:
    domains: dict[str, set[str]] = {}
    for call in calls:
        operation = call.rsplit(".", 1)[-1]
        for domain, prefixes, operations in EFFECT_RULES:
            if operation not in operations:
                continue
            if is_within_prefixes(call, prefixes):
                domains.setdefault(domain, set()).add(call)
    return {name: sorted(found) for name, found in sorted(domains.items())}
