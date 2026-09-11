"""Sparse finite-horizon weighted propagation and exact relational reductions."""
from dataclasses import dataclass
from collections import defaultdict
import math
import operator
from .ledger import Answer


@dataclass(frozen=True)
class Semiring:
    name: str
    merge: object
    extend: object
    zero: object
    one: object


MAX_MIN = Semiring("max_min", max, min, 0.0, 1.0)
COUNT = Semiring("count", operator.add, operator.mul, 0, 1)
MIN_PLUS = Semiring("min_plus", min, operator.add, math.inf, 0)
BOOLEAN = Semiring("boolean", operator.or_, operator.and_, False, True)


class Graph:
    """A sparse multigraph. COUNT counts walks/edge witnesses, not distinct nodes."""
    def __init__(self):
        self._out = {}
        self.edges = 0

    def add(self, subject, relation, object, weight=1):
        self._out.setdefault((subject, relation), []).append((object, weight))
        self.edges += 1

    def neighbors(self, subject, relation):
        return tuple(self._out.get((subject, relation), ()))

    def propagate(self, initial, relations, algebra=MAX_MIN, proof=False):
        frontier = dict(initial)
        max_frontier = len(frontier)
        dag = {} if proof else None
        for depth, relation in enumerate(relations, 1):
            following = {}
            for subject, support in frontier.items():
                for obj, weight in self._out.get((subject, relation), ()):
                    value = algebra.extend(support, weight)
                    if value == algebra.zero:
                        continue
                    previous = following.get(obj, algebra.zero)
                    following[obj] = algebra.merge(previous, value)
                    if proof:
                        dag.setdefault((depth, obj), []).append((depth - 1, subject, weight))
            frontier = following
            max_frontier = max(max_frontier, len(frontier))
            if not frontier:
                break
        return frontier, {"max_frontier": max_frontier,
                          "proof_nodes": len(dag) if proof else 0, "proof": dag}

    def max_min(self, initial, relations):
        """Specialized backend for the same max-min semantics."""
        frontier = dict(initial)
        for relation in relations:
            following = {}
            for subject, support in frontier.items():
                for obj, weight in self._out.get((subject, relation), ()):
                    value = min(support, weight)
                    if value > following.get(obj, 0):
                        following[obj] = value
            frontier = following
            if not frontier:
                break
        return frontier


def join(tables):
    """Natural join of binding dictionaries with deterministic exact join planning.

    Rows have set semantics.  Table order is semantically irrelevant, so choose an
    execution order that closes constraints over already-bound variables before
    introducing more variables.  This avoids large unnecessary Cartesian prefixes
    on CSP-like workloads while preserving the exact same relational result.
    Project explicitly after joining if necessary.
    """
    pending = []
    for table in tables:
        dedup = {}
        for row in table:
            row = dict(row)
            dedup[tuple(sorted(row.items()))] = row
        pending.append(list(dedup.values()))
    if not pending:
        return [{}]
    if any(not table for table in pending):
        return []

    # Start from the smallest relation.  Thereafter prefer constraints sharing the
    # most already-bound variables; ties introduce fewer new variables, then fewer
    # rows.  The heuristic changes only evaluation order, never logical semantics.
    first = min(range(len(pending)), key=lambda i: len(pending[i]))
    ordered = [pending.pop(first)]
    bound = set().union(*(row.keys() for row in ordered[0]))
    while pending:
        def score(table):
            schema = set().union(*(row.keys() for row in table))
            return (len(schema & bound), -len(schema - bound), -len(table))
        idx = max(range(len(pending)), key=lambda i: score(pending[i]))
        table = pending.pop(idx)
        ordered.append(table)
        bound |= set().union(*(row.keys() for row in table))

    rows = [{}]
    for table in ordered:
        merged = {}
        for left in rows:
            shared_left = left.keys()
            for right in table:
                if all(left[k] == right[k] for k in shared_left & right.keys()):
                    row = left | right
                    merged[tuple(sorted(row.items()))] = row
        rows = list(merged.values())
        if not rows:
            break
    return rows


def quantify(kind, matches, domain=None, closed=False, k=None):
    """Absence establishes NONE/exact counts only for a closed domain."""
    found = set(matches)
    domain = set(domain) if domain is not None else None
    if domain is not None and not found <= domain:
        raise ValueError("matches must belong to the supplied domain")
    if closed and domain is None:
        raise ValueError("closed quantification requires an explicit finite domain")
    if kind not in ("ANY", "NONE", "EXACT", "ALL"):
        raise ValueError("unknown quantifier")
    if kind == "EXACT" and (not isinstance(k, int) or isinstance(k, bool) or k < 0):
        raise ValueError("EXACT requires a nonnegative integer k")
    if kind == "ANY" and found:
        return Answer("ANSWER", (True,))
    if kind == "NONE" and found:
        return Answer("ANSWER", (False,))
    if kind == "EXACT" and len(found) > k:
        return Answer("ANSWER", (False,))
    if not closed:
        return Answer("UNKNOWN")
    value = {"ANY": bool(found), "NONE": not found,
             "EXACT": len(found) == k, "ALL": found == domain}[kind]
    return Answer("ANSWER", (value,))
