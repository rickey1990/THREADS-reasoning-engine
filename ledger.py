"""Exact, indexed event-time storage. Queries never modify the ledger.

Policy choices not fully specified by the blueprint:
* simultaneous distinct functional assertions remain ambiguous;
* a retraction at the assertion's timestamp closes that assertion;
* untargeted retractions close matching assertions at or before that time;
* explicit negations are observations, distinct from retractions;
* functional supersession does not undo itself after retraction.
"""
from dataclasses import dataclass
from bisect import bisect_right
from collections import defaultdict
import math


@dataclass(frozen=True)
class Event:
    id: str
    subject: str
    relation: str
    object: str
    time: float
    operation: str = "ASSERT"
    source: str = "unspecified"
    context: str = "default"
    confidence: float = 1.0
    positive: bool = True
    lineage: str | None = None
    target: str | None = None

    def __post_init__(self):
        for name in ("id", "subject", "relation", "object", "source", "context"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name):
                raise ValueError(f"{name} must be a nonempty exact string ID")
        if self.operation not in ("ASSERT", "RETRACT"):
            raise ValueError("operation must be ASSERT or RETRACT")
        if not math.isfinite(self.time):
            raise ValueError("event time must be finite")
        if not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be finite and in [0, 1]")
        if self.operation == "ASSERT" and self.target is not None:
            raise ValueError("only retractions may have targets")


@dataclass(frozen=True)
class Answer:
    status: str
    values: tuple = ()
    evidence: tuple = ()


class Ledger:
    def __init__(self, functional=()):
        self.functional = frozenset(functional)
        self._events = {}
        self._by_subject = {}
        self._by_object = {}

    def __len__(self):
        return len(self._events)

    def add(self, event):
        if not isinstance(event, Event):
            raise TypeError("expected Event")
        old = self._events.get(event.id)
        if old is not None:
            if old != event:
                raise ValueError("event ID already used for different content")
            return False
        key = (event.context, event.subject, event.relation)
        timeline = self._by_subject.setdefault(key, [])
        timeline.insert(bisect_right(timeline, (event.time, event.id),
                                    key=lambda e: (e.time, e.id)), event)
        self._events[event.id] = event
        self._by_object.setdefault((event.context, event.relation, event.object), set()).add(event.subject)
        return True

    def events(self):
        return tuple(sorted(self._events.values(), key=lambda e: (e.time, e.id)))

    def active(self, subject, relation, time=math.inf, context="default"):
        if math.isnan(time):
            raise ValueError("query time must not be NaN")
        timeline = self._by_subject.get((context, subject, relation), ())
        end = bisect_right(timeline, time, key=lambda e: e.time)
        eligible = timeline[:end]
        assertions = [e for e in eligible if e.operation == "ASSERT"]
        retractions = [e for e in eligible if e.operation == "RETRACT"]
        untargeted = {}
        targeted = {}
        for r in retractions:
            table = untargeted if r.target is None else targeted
            key = (r.object, r.positive) if r.target is None else (r.target, r.object, r.positive)
            table[key] = max(table.get(key, -math.inf), r.time)
        if relation in self.functional:
            latest = max((e.time for e in assertions if e.positive), default=-math.inf)
            assertions = [e for e in assertions if not e.positive or e.time == latest]
        return tuple(e for e in assertions
                     if untargeted.get((e.object, e.positive), -math.inf) < e.time
                     and targeted.get((e.id, e.object, e.positive), -math.inf) < e.time)

    def lookup(self, subject, relation, time=math.inf, context="default"):
        active = self.active(subject, relation, time, context)
        positive = {e.object for e in active if e.positive}
        negative = {e.object for e in active if not e.positive}
        if positive & negative:
            status = "CONTRADICTED"
        elif len(positive) > 1 and relation in self.functional:
            status = "AMBIGUOUS"
        elif positive:
            status = "ANSWER"
        elif negative:
            status = "NEGATED"
        else:
            status = "UNKNOWN"
        return Answer(status, tuple(sorted(positive)), tuple(e.id for e in active))

    def subjects(self, relation, object, time=math.inf, context="default"):
        return frozenset(s for s in self._by_object.get((context, relation, object), ())
                         if object in self.lookup(s, relation, time, context).values)

    def neighbors(self, subject, relation, time=math.inf, context="default"):
        """Possible positive edges, retaining assertion provenance.

        Call lookup for ambiguity/contradiction before treating them as certain.
        """
        result = defaultdict(list)
        for e in self.active(subject, relation, time, context):
            if e.positive:
                result[e.object].append(e)
        return {o: (max(e.confidence for e in es), tuple(e.id for e in es))
                for o, es in result.items()}

    def storage_counts(self):
        return {"events": len(self), "subject_keys": len(self._by_subject),
                "object_keys": len(self._by_object), "learned_parameters": 0}
