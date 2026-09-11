"""Independent small reference algorithms. Never imported by the learner."""
from collections import defaultdict
import itertools


def temporal_oracle(events, functional, subject, relation, cutoff, context="default"):
    """Chronological state machine, unlike ledger's assertion/tombstone filtering."""
    buckets = defaultdict(list)
    for event in events:
        if (event.subject == subject and event.relation == relation
                and event.context == context and event.time <= cutoff):
            buckets[event.time].append(event)
    state = {}
    for time in sorted(buckets):
        batch = buckets[time]
        if relation in functional and any(e.operation == "ASSERT" and e.positive for e in batch):
            state = {id: e for id, e in state.items() if not e.positive}
        for e in batch:
            if e.operation == "ASSERT":
                state[e.id] = e
        for r in batch:
            if r.operation == "RETRACT":
                for id, e in list(state.items()):
                    if (e.object == r.object and e.positive == r.positive
                            and (r.target is None or r.target == id)):
                        del state[id]
    return set(state)


def enumerate_walks(edges, start, relations, kind):
    """Explicit path enumeration: intentionally no semantic frontier merging."""
    paths = [(start, 0 if kind == "min_plus" else 1)]
    for relation in relations:
        next_paths = []
        for node, weight in paths:
            for s, r, o, w in edges:
                if s == node and r == relation:
                    new = (min(weight, w) if kind == "max_min" else
                           weight+w if kind == "min_plus" else weight*w)
                    next_paths.append((o, new))
        paths = next_paths
    grouped = defaultdict(list)
    for node, weight in paths:
        grouped[node].append(weight)
    if kind == "min_plus":
        return {node: min(weights) for node, weights in grouped.items()}
    if kind == "max_min":
        return {node: max(weights) for node, weights in grouped.items() if max(weights) > 0}
    if kind == "boolean":
        return {node: True for node, weights in grouped.items() if any(weights)}
    return {node: sum(weights) for node, weights in grouped.items() if sum(weights) != 0}


def relational_oracle(parent, male, child):
    return {(a, b, p) for a, p in parent for b, p2 in parent
            if p == p2 and b in male and (b, child) in parent}
