from srp_effects import effect_domains

REASON_COEFFICIENT_STEP = 0.25


def external_entities(calls: list[str]) -> list[str]:
    return sorted(effect_domains(calls))


def reason_coefficient(entities: list[str]) -> float:
    return min(1.0, REASON_COEFFICIENT_STEP * len(entities))
