"""Integration: learned/versioned macros execute directly against current facts.

Experimental exact-condition engine: no global sticky status flags.  Functional
alternatives are carried as exact symbolic conditions and simplified when they
reconverge.  No probabilities or external solver are used.
"""
import itertools
import math
from collections import defaultdict
from .ledger import Ledger, Answer
from .search import VersionedRules
from .algebra import MAX_MIN


class Engine:
    def __init__(self, functional=()):
        self.ledger = Ledger(functional)
        self.macros = VersionedRules()

    def teach_macro(self, name, relations, time=0):
        self.macros.learn(name, time, tuple(relations))

    @staticmethod
    def _cell(active):
        """Return positive edges and negative objects from one active() call."""
        pos = {}
        neg = set()
        for ev in active:
            if not ev.positive:
                neg.add(ev.object)
                continue
            old = pos.get(ev.object)
            if old is None or ev.confidence > old[0]:
                pos[ev.object] = (ev.confidence, [ev.id])
            elif ev.confidence == old[0]:
                old[1].append(ev.id)
        return {o: (c, tuple(ids)) for o, (c, ids) in pos.items()}, frozenset(neg)

    @staticmethod
    def _merge_variant(table, cond, value, taint, algebra):
        old = table.get(cond)
        if old is None:
            table[cond] = (value, taint)
        else:
            table[cond] = (algebra.merge(old[0], value), old[1] and taint)

    @classmethod
    def _simplify_node(cls, entries, domains, algebra):
        """Drop a choice condition when every option gives the exact same contribution.

        This is exact Boolean-style reduction, not fuzzy pruning.  It prevents
        reconverged alternatives from carrying obsolete branch history forever.
        """
        entries = dict(entries)
        changed = True
        while changed:
            changed = False
            keys = {k for cond in entries for k, _ in cond}
            for key in tuple(keys):
                domain = domains.get(key, ())
                if len(domain) < 2:
                    continue
                groups = defaultdict(dict)
                for cond, payload in list(entries.items()):
                    chosen = [v for k, v in cond if k == key]
                    if len(chosen) != 1:
                        continue
                    base = frozenset((k, v) for k, v in cond if k != key)
                    groups[base][chosen[0]] = (cond, payload)
                for base, by_choice in groups.items():
                    if set(by_choice) != set(domain):
                        continue
                    payloads = [by_choice[o][1] for o in domain]
                    if not all(p == payloads[0] for p in payloads[1:]):
                        continue
                    for cond, _ in by_choice.values():
                        entries.pop(cond, None)
                    value, taint = payloads[0]
                    cls._merge_variant(entries, base, value, taint, algebra)
                    changed = True
                    break
                if changed:
                    break
        return entries

    @staticmethod
    def _world_frontier(frontier, assignment, algebra):
        world = {}
        taints = {}
        for obj, variants in frontier.items():
            for cond, (value, taint) in variants.items():
                if any(assignment.get(k) != v for k, v in cond):
                    continue
                if obj in world:
                    world[obj] = algebra.merge(world[obj], value)
                    taints[obj] = taints[obj] and taint
                else:
                    world[obj] = value
                    taints[obj] = taint
        return world, taints

    @staticmethod
    def _outcome_key(frontier, taints):
        return tuple(sorted(((repr(k), k, v, bool(taints.get(k, False)))
                            for k, v in frontier.items()), key=lambda x: x[0]))

    @staticmethod
    def _minimal_witness(dag, target, depth):
        """Return one shortest proof whose symbolic choice conditions are consistent.

        The proof DAG may contain edges from mutually exclusive functional worlds.
        A naive predecessor walk can splice those worlds after reconvergence.  Search
        backward while accumulating exact choice assignments and reject conflicts.
        Public witness edges retain the original compact five-field format.
        """
        def compatible(assign, cond):
            merged = dict(assign)
            for key, value in cond:
                old = merged.get(key)
                if old is not None and old != value:
                    return None
                merged[key] = value
            return merged

        def visit(node, d, assign):
            if d == 0:
                return ()
            preds = dag.get((d, node), ())
            for pred in sorted(preds, key=repr):
                prev_depth, subject, ids, cond = pred
                merged = compatible(assign, cond)
                if merged is None:
                    continue
                prefix = visit(subject, prev_depth, merged)
                if prefix is not None:
                    return prefix + ((prev_depth, subject, d, node, ids),)
            return None

        result = visit(target, depth, {})
        return () if result is None else result

    def walk(self, start, relations, *, time=math.inf, context="default",
             algebra=MAX_MIN, proof=False):
        relations = tuple(relations)
        # node -> {frozenset((functional-cell, chosen-object)): (support, all_paths_contradicted)}
        frontier = {start: {frozenset(): (algebra.one, False)}}
        domains = {}
        dag = {} if proof else None
        maximum = 1
        # Final-step nonpositive outcomes keyed by the exact symbolic conditions
        # under which they occur.  This generalizes direct NEGATED handling to
        # arbitrary positive prefixes without treating missing evidence as negation.
        terminal_markers = []

        for depth, relation in enumerate(relations, 1):
            following = defaultdict(dict)
            for subject, variants in frontier.items():
                active = self.ledger.active(subject, relation, time, context)
                neighbors, negatives = self._cell(active)
                key = (context, subject, relation)
                is_choice = relation in self.ledger.functional and len(neighbors) > 1
                if is_choice:
                    domain = tuple(sorted(neighbors, key=repr))
                    old = domains.setdefault(key, domain)
                    if old != domain:
                        # Active() is deterministic for one query time; this is an invariant guard.
                        raise RuntimeError("functional choice domain changed during one walk")

                for cond, (support, prior_taint) in variants.items():
                    chosen = dict(cond).get(key) if is_choice else None
                    if is_choice:
                        options = ((chosen, neighbors[chosen]),) if chosen in neighbors else tuple(neighbors.items()) if chosen is None else ()
                    else:
                        options = tuple(neighbors.items())
                    if depth == len(relations) and not options:
                        terminal_markers.append((cond, "NEGATED" if negatives else "UNKNOWN"))
                    for obj, (confidence, ids) in options:
                        weight = confidence if algebra.name == "max_min" else 1
                        value = algebra.extend(support, weight)
                        if value == algebra.zero:
                            continue
                        new_cond = cond if not is_choice or chosen is not None else cond | {(key, obj)}
                        taint = prior_taint or obj in negatives
                        self._merge_variant(following[obj], new_cond, value, taint, algebra)
                        if dag is not None:
                            dag.setdefault((depth, obj), []).append((depth - 1, subject, ids, new_cond))

            frontier = {obj: self._simplify_node(v, domains, algebra)
                        for obj, v in following.items() if v}
            maximum = max(maximum, len(frontier))
            if not frontier:
                break

        # Only choices still present in terminal positive/negative conditions can
        # affect the final result.  Outcome identity includes the terminal truth
        # status, so an empty NEGATED world is not collapsed with an empty UNKNOWN world.
        relevant_keys = sorted(
            {k for variants in frontier.values() for cond in variants for k, _ in cond}
            | {k for cond, _ in terminal_markers for k, _ in cond}, key=repr)

        def terminal_status(assignment, wf, wt):
            if wf:
                return "CONTRADICTED" if any(wt.get(v, False) for v in wf) else "ANSWER"
            matched = [status for cond, status in terminal_markers
                       if not any(assignment.get(k) != v for k, v in cond)]
            return "NEGATED" if "NEGATED" in matched else "UNKNOWN"

        outcome_map = {}
        assignments = [()] if not relevant_keys else itertools.product(*(domains[k] for k in relevant_keys))
        for chosen in assignments:
            assignment = {} if not relevant_keys else dict(zip(relevant_keys, chosen))
            wf, wt = self._world_frontier(frontier, assignment, algebra)
            world_status = terminal_status(assignment, wf, wt)
            outcome_key = (world_status, self._outcome_key(wf, wt))
            outcome_map.setdefault(outcome_key, (world_status, wf, wt))

        outcomes = list(outcome_map.values()) or [("UNKNOWN", {}, {})]
        if len(outcomes) == 1:
            status, exact_frontier, taints = outcomes[0]
            values = tuple(sorted(exact_frontier))
            returned_frontier = exact_frontier
        else:
            # Multiple exact possible outcomes.  Keep endpoint possibilities in Answer,
            # but do not fabricate one numeric frontier by adding/min/maxing across worlds.
            values = tuple(sorted({obj for _, wf, _ in outcomes for obj in wf}))
            status = "AMBIGUOUS"
            returned_frontier = {}

        minimal = None
        minimal_edges = 0
        # A single unconditional witness is only honest for a definite outcome.
        # Ambiguous answers need condition/world-qualified proofs; the full DAG is
        # retained, but we deliberately do not manufacture one mixed witness.
        if proof and values and status != "AMBIGUOUS":
            minimal = {target: self._minimal_witness(dag, target, len(relations)) for target in values}
            minimal_edges = min((len(p) for p in minimal.values() if p), default=0)

        return Answer(status, values), returned_frontier, {
            "max_frontier": maximum,
            "proof_nodes": len(dag) if proof else 0,
            "proof": dag,
            "minimal_witness": minimal,
            "minimal_witness_edges": minimal_edges,
            "possible_frontiers": tuple(wf for _, wf, _ in outcomes) if len(outcomes) > 1 else None,
            "possible_statuses": tuple(st for st, _, _ in outcomes) if len(outcomes) > 1 else None,
            "possible_outcomes": len(outcomes),
        }

    def query_macro(self, name, start, *, time=math.inf, **kwargs):
        program = self.macros.at(name, time)
        if program is None:
            return Answer("UNKNOWN"), {}, {"max_frontier": 0, "proof_nodes": 0, "proof": None}
        return self.walk(start, program, time=time, **kwargs)

    def state_counts(self):
        return self.ledger.storage_counts() | {"macro_versions": self.macros.state_size()}
