"""Summarize possible I/O through uniquely resolved calls in the scanned source."""

from collections import Counter, deque

from srp_effects import effect_domains
from srp_imports import ImportResolver

TASK_DISPATCH_METHODS = frozenset({"delay", "apply_async"})
TASK_QUEUE_CLIENT = "celery.Task"
MODULE_UNIT_PREFIX = "<module>."


def mark_enqueued_tasks(parsed: list[dict]) -> None:
    """A .delay or .apply_async call on a project function enqueues a task."""
    resolver = ImportResolver(parsed)
    for item in parsed:
        units = {fact.name for fact in item["facts"]}
        for fact in item["facts"]:
            fact.calls = sorted(
                set(fact.calls)
                | enqueued_tasks(resolver, item["path"], units, fact.calls)
            )
            for block in fact.flow:
                block["calls"] = sorted(
                    set(block["calls"])
                    | enqueued_tasks(
                        resolver, item["path"], units, block["calls"]
                    )
                )


def enqueued_tasks(
    resolver: ImportResolver, path: str, units: set[str], calls: list[str]
) -> set[str]:
    enqueued = set()
    for call in calls:
        receiver, _, method = call.rpartition(".")
        if method not in TASK_DISPATCH_METHODS:
            continue
        if receiver.startswith("local:"):
            name = MODULE_UNIT_PREFIX + receiver.removeprefix("local:")
            is_project_function = name in units
        else:
            is_project_function = bool(resolver.resolve(path, receiver))
        if is_project_function:
            enqueued.add(f"{TASK_QUEUE_CLIENT}.{method}")
    return enqueued


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
            graph.setdefault(caller, set())
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
