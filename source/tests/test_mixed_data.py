import copy
import random
import unittest

from srmh import BOOLEAN, COUNT, Event
from srmh.engine import Engine


class MixedDataTests(unittest.TestCase):
    @staticmethod
    def event(event_id, subject, relation, object_, time, **kwargs):
        return Event(event_id, subject, relation, object_, time, **kwargs)

    def mixed_events(self):
        events = [
            self.event("story-a-1", "cup", "at", "crate", 1),
            self.event("story-a-2", "cup", "at", "van", 3),
            self.event("story-a-3", "cup", "at", "van", 5, operation="RETRACT"),
            self.event("story-b-1", "alice", "parent", "bob", 1),
            self.event("story-b-2", "bob", "parent", "cara", 1),
            self.event("story-c-1", "sensor", "state", "on", 1),
            self.event("story-c-2", "sensor", "state", "on", 2, positive=False),
            self.event("story-d-1", "x", "link", "d1", 1, context="A"),
            self.event("story-d-2", "x", "link", "d2", 1, context="B"),
            self.event("story-e-1", "s", "owner", "a", 10),
            self.event("story-e-2", "s", "owner", "b", 10),
            self.event("story-e-3", "a", "next", "z", 10),
            self.event("story-e-4", "b", "next", "z", 10),
        ]
        for index in range(200):
            relation = ("at", "parent", "state", "link", "owner", "next")[index % 6]
            context = ("default", "A", "B")[index % 3]
            events.append(self.event(
                f"distractor-{index}",
                f"unrelated-subject-{index}",
                relation,
                f"unrelated-object-{index}",
                index % 13,
                context=context,
            ))
        return events

    @staticmethod
    def answers(engine):
        return {
            "cup_at_2": engine.walk("cup", ["at"], time=2, algebra=BOOLEAN)[0],
            "cup_at_4": engine.walk("cup", ["at"], time=4, algebra=BOOLEAN)[0],
            "cup_current": engine.walk("cup", ["at"], algebra=BOOLEAN)[0],
            "alice_parent": engine.walk("alice", ["parent", "parent"], algebra=BOOLEAN)[0],
            "sensor_state": engine.walk("sensor", ["state"], algebra=BOOLEAN)[0],
            "context_a": engine.walk("x", ["link"], context="A", algebra=BOOLEAN)[0],
            "context_b": engine.walk("x", ["link"], context="B", algebra=BOOLEAN)[0],
            "owner_reconverges": engine.walk("s", ["owner", "next"], algebra=BOOLEAN)[0],
        }

    def test_mixed_data_is_order_invariant_and_queries_do_not_mutate(self):
        events = self.mixed_events()
        expected = {
            "cup_at_2": ("ANSWER", ("crate",)),
            "cup_at_4": ("ANSWER", ("van",)),
            "cup_current": ("UNKNOWN", ()),
            "alice_parent": ("ANSWER", ("cara",)),
            "sensor_state": ("CONTRADICTED", ("on",)),
            "context_a": ("ANSWER", ("d1",)),
            "context_b": ("ANSWER", ("d2",)),
            "owner_reconverges": ("ANSWER", ("z",)),
        }
        for seed in range(100):
            shuffled = list(events)
            random.Random(seed).shuffle(shuffled)
            engine = Engine(["at", "owner"])
            for event in shuffled:
                engine.ledger.add(event)
            before = copy.deepcopy(engine.state_counts())
            actual = {
                name: (answer.status, answer.values)
                for name, answer in self.answers(engine).items()
            }
            self.assertEqual(actual, expected, f"seed={seed}")
            self.assertEqual(before, engine.state_counts(), f"seed={seed}")

    def test_mixed_adversarial_semantics(self):
        engine = Engine(["owner"])
        events = [
            self.event("same-time-assert", "same", "r", "x", 4),
            self.event("same-time-retract", "same", "r", "x", 4, operation="RETRACT"),
            self.event("target-old", "target", "r", "x", 1),
            self.event("target-new", "target", "r", "x", 2),
            self.event("target-retract", "target", "r", "x", 3, operation="RETRACT", target="target-old"),
            self.event("untargeted-retract", "target", "r", "x", 4, operation="RETRACT"),
            self.event("negative", "negative", "r", "blocked", 1, positive=False),
            self.event("positive-other", "negative", "r", "allowed", 1),
            self.event("ambiguous-a", "ambiguous", "owner", "a", 1),
            self.event("ambiguous-b", "ambiguous", "owner", "b", 1),
            self.event("next-a", "a", "next", "z", 1),
            self.event("next-b", "b", "next", "y", 1),
            self.event("context-a", "same-id", "link", "same-object", 1, context="A"),
            self.event("context-b", "same-id", "link", "same-object", 1, context="B"),
            self.event("history-old", "history", "owner", "old", 1),
            self.event("history-new", "history", "owner", "new", 2),
            self.event("copy-1", "count", "r", "b", 1, lineage="copied"),
            self.event("copy-2", "count", "r", "b", 1, lineage="copied"),
            self.event("independent-1", "count-independent", "r", "b", 1, lineage="lineage-a"),
            self.event("independent-2", "count-independent", "r", "b", 1, lineage="lineage-b"),
        ]
        for event in events:
            engine.ledger.add(event)

        self.assertEqual(engine.walk("same", ["r"], algebra=BOOLEAN)[0].status, "UNKNOWN")
        self.assertEqual(engine.walk("target", ["r"], algebra=BOOLEAN)[0].status, "UNKNOWN")
        negative = engine.walk("negative", ["r"], algebra=BOOLEAN)[0]
        self.assertEqual((negative.status, negative.values), ("ANSWER", ("allowed",)))
        ambiguous = engine.walk("ambiguous", ["owner", "next"], algebra=BOOLEAN)[0]
        self.assertEqual((ambiguous.status, ambiguous.values), ("AMBIGUOUS", ("y", "z")))
        self.assertEqual(engine.ledger.lookup("same-id", "link", context="A").values, ("same-object",))
        self.assertEqual(engine.ledger.lookup("same-id", "link", context="B").values, ("same-object",))
        self.assertEqual(engine.walk("history", ["owner"], time=1, algebra=BOOLEAN)[0].values, ("old",))
        self.assertEqual(engine.walk("history", ["owner"], time=3, algebra=BOOLEAN)[0].values, ("new",))
        self.assertEqual(engine.walk("count", ["r"], algebra=COUNT)[1], {"b": 1})
        self.assertEqual(engine.walk("count-independent", ["r"], algebra=COUNT)[1], {"b": 1})

        before = copy.deepcopy(engine.state_counts())
        answer, _, metadata = engine.walk("ambiguous", ["owner", "next"], algebra=BOOLEAN, proof=True)
        self.assertEqual((answer.status, answer.values), ("AMBIGUOUS", ("y", "z")))
        self.assertIsNone(metadata["minimal_witness"])
        reconverging = Engine(["owner"])
        for event in (
            self.event("proof-owner-a", "proof", "owner", "a", 1),
            self.event("proof-owner-b", "proof", "owner", "b", 1),
            self.event("proof-next-a", "a", "next", "z", 1),
            self.event("proof-next-b", "b", "next", "z", 1),
        ):
            reconverging.ledger.add(event)
        answer, _, metadata = reconverging.walk("proof", ["owner", "next"], algebra=BOOLEAN, proof=True)
        self.assertEqual((answer.status, answer.values), ("ANSWER", ("z",)))
        witness = metadata["minimal_witness"]["z"]
        witness_ids = {event_id for edge in witness for event_id in edge[4]}
        self.assertTrue(witness_ids <= {"proof-owner-a", "proof-owner-b", "proof-next-a", "proof-next-b"})
        self.assertEqual(before, engine.state_counts())


if __name__ == "__main__":
    unittest.main()
