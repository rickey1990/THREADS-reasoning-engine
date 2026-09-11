"""Additional failure-seeking cases, retained unchanged after repairs."""
import unittest
import numpy as np
from srmh import Event, MIN_PLUS, COUNT, affine_recurrence
from srmh.engine import Engine
from srmh.language import GroundedInterpreter


class AdversarialTests(unittest.TestCase):
    def test_integrated_min_plus_counts_unit_edge_distance(self):
        engine = Engine()
        engine.ledger.add(Event("1", "a", "r", "b", 0))
        engine.ledger.add(Event("2", "b", "r", "c", 0))
        answer, distances, _ = engine.walk("a", ["r", "r"], algebra=MIN_PLUS)
        self.assertEqual(distances, {"c": 2})

    def test_scan_cancellation_fixed_point(self):
        # Sequential recurrence is exactly x=1 for every step. Prefix transform
        # coefficients grow exponentially, so naive scan loses cancellation.
        a = np.full(128, 2.0); b = np.full(128, -1.0)
        actual, _ = affine_recurrence(a, b, initial=1, backend="scan")
        np.testing.assert_array_equal(actual, np.ones(128))

    def test_scan_intermediate_overflow_with_finite_solution(self):
        a = np.full(2048, 2.0); b = np.full(2048, -1.0)
        actual, _ = affine_recurrence(a, b, initial=1, backend="scan")
        np.testing.assert_array_equal(actual, np.ones(2048))

    def test_large_finite_cancellation_convolution(self):
        x = np.array([1e100, -1e100, 1e100, -1e100])
        actual, _ = __import__("srmh").convolve(x, [1e100, 1e100], "fft")
        expected = np.convolve(x, [1e100, 1e100])
        # Mixed tolerance scaled by input norm; absolute 1e-10 is meaningless here.
        self.assertLess(np.max(np.abs(actual-expected))/1e200, 1e-12)

    def test_counts_do_not_count_copied_observations_as_edges(self):
        engine = Engine()
        for i in range(100):
            engine.ledger.add(Event(str(i), "a", "r", "b", 0, lineage="same"))
        self.assertEqual(engine.walk("a", ["r"], algebra=COUNT)[1], {"b": 1})

    def test_grounded_transfer_preserves_current_and_history(self):
        interpreter = GroundedInterpreter(); engine = Engine(["owner"])
        interpreter.teach("Lio daxed key to Nera.", Event("demo", "key", "owner", "Nera", 0))
        interpreter.ingest("Pavo daxed coin to Sumi.", engine.ledger, "1", 1)
        interpreter.ingest("Sumi daxed coin to Hana.", engine.ledger, "2", 2)
        self.assertEqual(engine.ledger.lookup("coin", "owner").values, ("Hana",))
        self.assertEqual(engine.ledger.lookup("coin", "owner", 1).values, ("Sumi",))


if __name__ == "__main__":
    unittest.main()
