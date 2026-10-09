"""Follow explicit library/type re-exports without treating wrapper bodies as calls."""

from srp_imports import ImportResolver


def canonical_reference(resolver, path, reference, seen=frozenset()):
    key = (path, reference)
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
        if isinstance(export, dict):
            values.add(
                canonical_reference(
                    resolver, target, export["reference"] + separator + tail, seen
                )
            )
        elif export is None and item.get("export_stars") and head != "default":
            for module in item["export_stars"]:
                values.add(
                    canonical_reference(resolver, target, module + "." + symbol, seen)
                )
        else:
            values.add("local:" + reference)
    return next(iter(values)) if len(values) == 1 else "local:" + reference


def resolve_call_aliases(parsed: list[dict]) -> None:
    resolver = ImportResolver(parsed)
    for item in parsed:
        cache = {}
        for fact in item["facts"]:
            for call in fact.calls:
                if call not in cache:
                    cache[call] = canonical_reference(resolver, item["path"], call)
            fact.call_aliases = {
                call: cache[call] for call in fact.calls if call != cache[call]
            }
            fact.calls = sorted({cache[call] for call in fact.calls})
            for block in fact.flow:
                block["calls"] = sorted(
                    {cache.get(call, call) for call in block["calls"]}
                )
