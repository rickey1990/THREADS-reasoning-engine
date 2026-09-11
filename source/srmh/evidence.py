"""Explicitly conditional evidence scores, not a general Bayesian calculus."""
from dataclasses import dataclass
from collections import defaultdict
import math


@dataclass(frozen=True)
class Claim:
    positive: bool
    confidence: float
    source: str
    lineage: str | None = None

    def __post_init__(self):
        if not math.isfinite(self.confidence) or not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be in [0, 1]")
        if not self.source:
            raise ValueError("source is required")


def assess(claims, *, independent_lineages=False):
    """Deduplicate known copies; otherwise return dependence-sensitive intervals.

    Caller may assert independence ONLY when lineage metadata establishes it.
    Noisy-OR is a support-combination convention, not posterior truth probability.
    With unknown dependence use Frechet union bounds [max(p), min(1,sum(p))].
    """
    groups = {True: {}, False: {}}
    claims = tuple(claims)
    if independent_lineages and any(c.lineage is None for c in claims):
        raise ValueError("independence requires explicit lineage IDs")
    for c in claims:
        key = ("lineage", c.lineage) if c.lineage is not None else ("source", c.source)
        groups[c.positive][key] = max(groups[c.positive].get(key, 0), c.confidence)
    intervals = {}
    for sign, scores in groups.items():
        values = list(scores.values())
        if independent_lineages:
            score = 1 - math.prod(1-p for p in values)
            intervals[sign] = (score, score)
        else:
            intervals[sign] = (max(values, default=0), min(1.0, sum(values)))
    positive, negative = intervals[True], intervals[False]
    if positive[1] == negative[1] == 0:
        status = "UNKNOWN"
    elif negative[1] == 0 or positive[0] > negative[1]:
        status = "ANSWER"
    elif positive[1] == 0 or negative[0] > positive[1]:
        status = "NEGATED"
    elif positive[0] == positive[1] == negative[0] == negative[1]:
        status = "CONTRADICTED"
    else:
        status = "AMBIGUOUS"
    return {"status": status, "positive_support": positive,
            "negative_support": negative,
            "has_conflicting_evidence": positive[1] > 0 and negative[1] > 0}
