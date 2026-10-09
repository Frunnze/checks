"""Summarize possible I/O through uniquely resolved calls in the scanned source."""

from collections import Counter, deque

from srp_effects import effect_domains
from srp_imports import ImportResolver


def effect_call_graph(parsed: list[dict]) -> dict:
    """Capture actual call sites before import aliases are canonicalized."""
    resolver = ImportResolver(parsed)
    counts = Counter(
        (item["path"], fact.name) for item in parsed for fact in item["facts"]
    )
    unstable = {
        (item["path"], fact.name)
        for item in parsed
        for fact in item["facts"]
        if not fact.binding_stable
    }
    graph = {}
    for item in parsed:
        path = item["path"]
        for fact in item["facts"]:
            caller = (path, fact.name)
            if counts[caller] != 1:
                continue
            graph[caller] = set()
            for block in fact.flow:
                targets = {(path, name) for name in block.get("links", [])}
                for call in block["calls"]:
                    targets.update(resolver.resolve(path, call))
                targets = {
                    target
                    for target in targets
                    if counts[target] == 1 and target not in unstable
                }
                block["callees"] = [
                    {"path": target, "name": name} for target, name in sorted(targets)
                ]
                graph[caller].update(targets)
    return graph


def summarize_effects(parsed: list[dict], graph: dict) -> None:
    """A finite worklist handles recursion without counting helper body size."""
    summaries = {
        (item["path"], fact.name): {
            call for calls in effect_domains(fact.calls).values() for call in calls
        }
        for item in parsed
        for fact in item["facts"]
        if (item["path"], fact.name) in graph
    }
    callers = {key: set() for key in graph}
    for caller, targets in graph.items():
        for target in targets:
            callers[target].add(caller)
    pending, queued = deque(graph), set(graph)
    while pending:
        target = pending.popleft()
        queued.remove(target)
        for caller in callers[target]:
            added = summaries[target] - summaries[caller]
            if added:
                summaries[caller].update(added)
                if caller not in queued:
                    pending.append(caller)
                    queued.add(caller)
    for item in parsed:
        for fact in item["facts"]:
            effects = set()
            for block in fact.flow:
                delegated = {
                    call
                    for target in block.get("callees", [])
                    for call in summaries[(target["path"], target["name"])]
                }
                block["delegated_effects"] = sorted(delegated)
                effects.update(delegated)
            fact.delegated_effects = sorted(effects)
