"""Bounded program induction with behavior sharing and retained alternatives."""
from dataclasses import dataclass
from collections import defaultdict, Counter
import math
from .ledger import Answer


@dataclass(frozen=True)
class Operator:
    name: str
    function: object


@dataclass(frozen=True)
class SearchResult:
    programs: tuple
    complete: bool
    expanded: int
    max_depth: int


class ProgramSearch:
    """Operators must be pure deterministic functions of hashable states.

    Equal demonstration behavior shares execution, never erases programs.
    Answers are conditional on the declared operator library and depth bound.
    A resource-truncated search cannot certify a unanimous answer.
    """
    def __init__(self, operators):
        operators = tuple(operators)
        if len({o.name for o in operators}) != len(operators):
            raise ValueError("operator names must be unique")
        self.operators = {o.name: o.function for o in operators}

    def execute(self, program, value):
        for name in program:
            value = self.operators[name](value)
        return value

    def fit(self, examples, max_depth=4, max_states=10000, max_programs=50000,
            max_errors=0):
        examples = tuple(examples)
        if not examples or max_depth < 0 or max_states < 1 or max_programs < 1:
            raise ValueError("nonempty evidence and valid bounds required")
        if max_errors < 0 or max_errors >= len(examples):
            raise ValueError("invalid demonstration error budget")
        initial = tuple(x for x, _ in examples)
        target = tuple(y for _, y in examples)
        hash(initial)
        groups = {initial: [()]}
        accepted = []
        expanded = 0
        program_count = 1
        for depth in range(max_depth + 1):
            for behavior, programs in groups.items():
                if sum(a != b for a, b in zip(behavior, target)) <= max_errors:
                    accepted.extend(programs)
            if depth == max_depth:
                break
            following = defaultdict(list)
            for behavior, programs in groups.items():
                for name, op in self.operators.items():
                    if expanded >= max_states or program_count + len(programs) > max_programs:
                        return SearchResult(tuple(accepted), False, expanded, max_depth)
                    expanded += 1
                    try:
                        child = tuple(op(x) for x in behavior)
                        hash(child)
                    except (ValueError, TypeError, IndexError, ArithmeticError):
                        continue
                    following[child].extend(p + (name,) for p in programs)
                    program_count += len(programs)
            groups = following
        return SearchResult(tuple(sorted(set(accepted), key=lambda p: (len(p), p))),
                            True, expanded, max_depth)

    def predict(self, result, value):
        outputs = set()
        for program in result.programs:
            try:
                outputs.add(self.execute(program, value))
            except (ValueError, TypeError, IndexError, ArithmeticError):
                return Answer("UNKNOWN")
        if len(outputs) > 1:
            return Answer("AMBIGUOUS", tuple(sorted(outputs, key=repr)))
        if not outputs or not result.complete:
            return Answer("UNKNOWN")
        return Answer("ANSWER", tuple(outputs))

    def active_probe(self, result, inputs):
        """Maximum output entropy under a uniform prior over retained programs."""
        best = None
        best_entropy = 0.0
        for value in inputs:
            try:
                counts = Counter(self.execute(p, value) for p in result.programs)
            except (ValueError, TypeError, IndexError, ArithmeticError):
                continue
            n = sum(counts.values())
            entropy = -sum((v / n) * math.log2(v / n) for v in counts.values()) if n else 0
            if entropy > best_entropy:
                best, best_entropy = value, entropy
        return best, best_entropy


class VersionedRules:
    """Explicit rule updates preserve old-time queries; no automatic drift detector."""
    def __init__(self):
        self._rules = {}

    def learn(self, name, time, rule):
        if not math.isfinite(time):
            raise ValueError("version time must be finite")
        versions = self._rules.setdefault(name, {})
        if time in versions and versions[time] != rule:
            raise ValueError("conflicting rule versions at the same time")
        versions[time] = rule

    def at(self, name, time=math.inf):
        if math.isnan(time):
            raise ValueError("query time must not be NaN")
        versions = self._rules.get(name, {})
        eligible = [t for t in versions if t <= time]
        return versions[max(eligible)] if eligible else None

    def state_size(self):
        return sum(map(len, self._rules.values()))
