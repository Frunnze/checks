"""Follow explicit library/type re-exports without treating wrapper bodies as calls."""

from python_qualified_names import RETURNED_TYPE_SUFFIX
from srp_imports import ImportResolver


def canonical_reference(resolver, path, reference, seen, memo):
    key = (path, reference)
    if key in memo:
        return memo[key]
    if key in seen or len(seen) >= 64:
        return "local:" + reference
    seen = seen | {key}
    targets = resolver.module_targets(path, reference)
    if not targets:
        return reference
    values = set()
    for target, symbol in targets:
        head, separator, tail = symbol.partition(".")
        item = resolver.files[target]
        export = item.get("exports", {}).get(head)
        returned = item.get("exports", {}).get(head + RETURNED_TYPE_SUFFIX)
        stars = resolver.star_modules(target)
        if isinstance(export, dict):
            exported = export["reference"] + separator + tail
            values.add(canonical_reference(resolver, target, exported, seen, memo))
        elif returned and tail:
            values.add(returned["reference"] + separator + tail)
        elif export is None and stars and head != "default":
            for module in stars:
                values.add(
                    canonical_reference(
                        resolver, target, module + "." + symbol, seen, memo
                    )
                )
        elif export is not None:
            values.add("local:" + reference)
    memo[key] = next(iter(values)) if len(values) == 1 else "local:" + reference
    return memo[key]


def resolve_call_aliases(parsed: list[dict]) -> None:
    resolver = ImportResolver(parsed)
    for item in parsed:
        cache = {}
        for fact in item["facts"]:
            for call in fact.calls:
                if call not in cache:
                    cache[call] = canonical_reference(
                        resolver, item["path"], call, frozenset(), {}
                    )
            fact.call_aliases = {
                call: cache[call] for call in fact.calls if call != cache[call]
            }
            fact.calls = sorted({cache[call] for call in fact.calls})
            for block in fact.flow:
                block["calls"] = sorted(
                    {cache.get(call, call) for call in block["calls"]}
                )
