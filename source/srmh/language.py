"""Controlled-language grounding baseline; NOT a neural language interpreter.

Grammar: 'AGENT VERB OBJECT to RECIPIENT.' with single-token exact IDs.
Learn relation and role positions from observed assertion consequences.
Time/context are explicit API inputs; pronouns are deliberately unresolved.
"""
from collections import defaultdict
import re
from .ledger import Event, Answer


class GroundedInterpreter:
    def __init__(self):
        self._meanings = {}

    @staticmethod
    def parse(sentence):
        match = re.fullmatch(r"\s*([^\s.]+)\s+([^\s.]+)\s+([^\s.]+)\s+to\s+([^\s.]+)\.?\s*", sentence)
        if not match:
            return None
        agent, verb, obj, recipient = match.groups()
        if any(x.lower() in {"it", "she", "he", "they", "her", "him", "them"}
               for x in (agent, obj, recipient)):
            return None
        return verb, (agent, obj, recipient)

    def teach(self, sentence, consequence, context="default"):
        parsed = self.parse(sentence)
        if parsed is None or consequence.operation != "ASSERT" or not consequence.positive:
            raise ValueError("unsupported grounding example")
        verb, roles = parsed
        mappings = {(consequence.relation, i, j)
                    for i, value in enumerate(roles) if value == consequence.subject
                    for j, value2 in enumerate(roles) if value2 == consequence.object}
        if not mappings:
            raise ValueError("consequence does not bind sentence roles")
        key = (context, verb)
        previous = self._meanings.get(key)
        self._meanings[key] = mappings if previous is None else previous & mappings

    def interpret(self, sentence, id, time, context="default"):
        parsed = self.parse(sentence)
        if parsed is None:
            return Answer("UNKNOWN")
        verb, roles = parsed
        meanings = self._meanings.get((context, verb), ())
        candidates = {(relation, roles[i], roles[j]) for relation, i, j in meanings}
        if not candidates:
            return Answer("UNKNOWN")
        if len(candidates) != 1:
            return Answer("AMBIGUOUS")
        relation, subject, obj = next(iter(candidates))
        return Answer("ANSWER", (Event(id, subject, relation, obj, time,
                                      source="controlled-interpreter", context=context),))

    def ingest(self, sentence, ledger, id, time, context="default"):
        result = self.interpret(sentence, id, time, context)
        if result.status == "ANSWER":
            ledger.add(result.values[0])
        return result
