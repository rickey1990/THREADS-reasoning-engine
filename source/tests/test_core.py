import unittest
import itertools
import random
import copy
import math
import os
import numpy as np
from srmh import *
from srmh.engine import Engine
from srmh.evidence import Claim, assess
from srmh.language import GroundedInterpreter
from tests.oracles import temporal_oracle, enumerate_walks, relational_oracle

SEED = int(os.environ.get("SRMH_TEST_SEED", "1729"))


class LedgerTests(unittest.TestCase):
    def test_supersession_and_history(self):
        ledger = Ledger(["at"])
        for e in [Event("a", "cup", "at", "crate", 1),
                  Event("b", "cup", "at", "van", 2),
                  Event("c", "cup", "at", "van", 3, "RETRACT")]:
            ledger.add(e)
        self.assertEqual(ledger.lookup("cup", "at", 1).values, ("crate",))
        self.assertEqual(ledger.lookup("cup", "at", 2).values, ("van",))
        self.assertEqual(ledger.lookup("cup", "at").status, "UNKNOWN")

    def test_ties_targets_reassertions(self):
        events = [Event("a", "s", "r", "x", 1), Event("b", "s", "r", "y", 1),
                  Event("c", "s", "r", "x", 2, "RETRACT", target="a"),
                  Event("d", "s", "r", "x", 3)]
        for permutation in itertools.permutations(events):
            ledger = Ledger(["r"])
            for e in permutation: ledger.add(e)
            self.assertEqual(ledger.lookup("s", "r", 1).status, "AMBIGUOUS")
            self.assertEqual(ledger.lookup("s", "r", 2).values, ("y",))
            self.assertEqual(ledger.lookup("s", "r", 3).values, ("x",))
        ledger.add(Event("e", "s", "r", "x", 3, "RETRACT"))
        self.assertEqual(ledger.lookup("s", "r").status, "UNKNOWN")

    def test_identity_context_negation_and_no_query_mutation(self):
        ledger = Ledger()
        e = Event("1", "X", "r", "a", 0)
        self.assertTrue(ledger.add(e)); self.assertFalse(ledger.add(e))
        with self.assertRaises(ValueError): ledger.add(Event("1", "X", "r", "b", 0))
        ledger.add(Event("2", "X", "r", "a", 1, positive=False))
        ledger.add(Event("3", "X", "r", "b", 1, context="other"))
        self.assertEqual(ledger.lookup("X", "r").status, "CONTRADICTED")
        self.assertEqual(ledger.lookup("x", "r").status, "UNKNOWN")
        self.assertEqual(ledger.lookup("X", "r", context="other").values, ("b",))
        before = copy.deepcopy(ledger.__dict__)
        ledger.lookup("missing", "r"); ledger.subjects("r", "missing")
        ledger.neighbors("missing", "r")
        self.assertEqual(before, ledger.__dict__)

    def test_random_temporal_1000_worlds_5_shuffles(self):
        rng = random.Random(SEED)
        for world in range(1000):
            functional = {"f"}
            events = []
            for i in range(18):
                op = "RETRACT" if rng.random() < .35 else "ASSERT"
                target = str(rng.randrange(i)) if i and op == "RETRACT" and rng.random() < .3 else None
                events.append(Event(str(i), rng.choice(["s", "t"]), rng.choice(["f", "m"]),
                                    rng.choice(["a", "b", "c"]), rng.randrange(7), op,
                                    positive=rng.random() > .2, target=target))
            questions = [(rng.choice(["s", "t"]), rng.choice(["f", "m"]), t)
                         for t in (0, 1, 3, 5, 8)]
            expected = [temporal_oracle(events, functional, s, r, t) for s, r, t in questions]
            for _ in range(5):
                rng.shuffle(events)
                ledger = Ledger(functional)
                for e in events: ledger.add(e)
                for (s, r, t), truth in zip(questions, expected):
                    self.assertEqual({e.id for e in ledger.active(s, r, t)}, truth,
                                     f"world={world}, query={(s,r,t)}, seed={SEED}")


class AlgebraTests(unittest.TestCase):
    def test_random_oracles_100_trials_per_algebra(self):
        rng = random.Random(SEED + 1)
        for algebra in (MAX_MIN, COUNT, MIN_PLUS, BOOLEAN):
            for trial in range(100):
                graph = Graph(); edges = []
                for _ in range(16):
                    weight = (rng.random() if algebra == MAX_MIN else
                              rng.randrange(1, 5) if algebra == MIN_PLUS else 1)
                    e = (rng.randrange(5), rng.choice(["r", "s"]), rng.randrange(5), weight)
                    edges.append(e); graph.add(*e)
                relations = [rng.choice(["r", "s"]) for _ in range(4)]
                expected = enumerate_walks(edges, 0, relations, algebra.name)
                actual, _ = graph.propagate({0: algebra.one}, relations, algebra)
                self.assertEqual(actual, expected)
                if algebra == MAX_MIN:
                    self.assertEqual(graph.max_min({0: 1}, relations), expected)

    def test_exponential_paths_merged_and_big_integer_counting(self):
        graph = Graph(); width = 8; depth = 40
        for layer in range(depth):
            for a in range(width):
                for b in range(width): graph.add((layer, a), "r", (layer+1, b))
        actual, stats = graph.propagate({(0,0): 1}, ["r"]*depth, COUNT, proof=True)
        self.assertEqual(set(actual.values()), {width**(depth-1)})
        self.assertEqual(stats["max_frontier"], width)
        self.assertEqual(stats["proof_nodes"], width*depth)

    def test_joins_and_quantifiers_10000_queries(self):
        rng = random.Random(SEED+2)
        for _ in range(2500):
            parent = {(rng.randrange(7), rng.randrange(7)) for _ in range(14)}
            male = {x for x in range(7) if rng.random() < .5}; child = rng.randrange(7)
            tables = [[{"a":a,"p":p} for a,p in parent],
                      [{"b":b,"p":p} for b,p in parent], [{"b":b} for b in male],
                      [{"b":b} for b,c in parent if c == child]]
            actual = {(r["a"],r["b"],r["p"]) for r in join(tables)}
            self.assertEqual(actual, relational_oracle(parent, male, child))
            found = {a for a, _, _ in actual}; domain = set(range(7))
            for kind, truth in [("ANY",bool(found)),("NONE",not found),
                                ("EXACT",len(found)==2),("ALL",found==domain)]:
                self.assertEqual(quantify(kind, found, domain, True, 2).values, (truth,))

    def test_open_world_quantifiers(self):
        for kind in ("ALL", "NONE", "EXACT", "ANY"):
            self.assertEqual(quantify(kind, [], k=0).status, "UNKNOWN")
        self.assertEqual(quantify("ALL", [], [], True).values, (True,))
        self.assertEqual(quantify("EXACT", [1,2], k=1).values, (False,))


class CompilerTests(unittest.TestCase):
    def test_fft_random_and_dispatch(self):
        rng = np.random.default_rng(SEED+3)
        for _ in range(100):
            x = rng.normal(size=rng.integers(2, 200)); h = rng.normal(size=rng.integers(2,80))
            result, _ = convolve(x,h,"fft")
            np.testing.assert_allclose(result, np.convolve(x,h), atol=1e-10, rtol=1e-10)
        x = rng.normal(size=32768); h = rng.normal(size=1024)
        result, backend = convolve(x,h)
        self.assertEqual(backend,"fft")
        np.testing.assert_allclose(result,np.convolve(x,h),atol=1e-10,rtol=1e-10)
        self.assertEqual(convolve([1,2],[2,3])[1], "direct")

    def test_scan_random_cancellation_and_dispatch(self):
        rng = np.random.default_rng(SEED+4)
        for _ in range(100):
            a = rng.uniform(-1,1, size=300); b = rng.normal(size=300)
            scan, _ = affine_recurrence(a,b,2,"scan")
            sequential, _ = affine_recurrence(a,b,2,"direct")
            np.testing.assert_allclose(scan, sequential, atol=1e-10, rtol=1e-10)
        a = np.full(4096,.9); b = rng.normal(size=4096)
        scan, route = affine_recurrence(a,b)
        self.assertEqual(route,"scan")
        np.testing.assert_allclose(scan,affine_recurrence(a,b,backend="direct")[0],atol=1e-10,rtol=1e-10)
        self.assertEqual(affine_recurrence([],[])[0].size,0)

    def test_invalid_and_overflow(self):
        with self.assertRaises(ValueError): convolve([], [1])
        with self.assertRaises(ValueError): affine_recurrence([1], [1,2])
        with self.assertRaises(ValueError): convolve([float("nan")],[1])
        with self.assertRaises(FloatingPointError): affine_recurrence([1e200]*4,[1]*4,1,"scan")


class SearchTests(unittest.TestCase):
    def test_preserves_equal_training_behavior(self):
        search = ProgramSearch([Operator("identity",lambda x:x), Operator("square",lambda x:x*x)])
        result = search.fit([(0,0),(1,1)],max_depth=1)
        self.assertTrue(result.complete)
        self.assertEqual(search.predict(result,2).status,"AMBIGUOUS")
        probe, entropy = search.active_probe(result,[0,1,2])
        self.assertEqual(probe,2); self.assertGreater(entropy,0)
        resolved = search.fit([(0,0),(1,1),(2,4)],max_depth=1)
        self.assertEqual(search.predict(resolved,3).values,(9,))

    def test_budget_exhaustion_not_false_certainty(self):
        search = ProgramSearch([Operator("inc",lambda x:x+1), Operator("double",lambda x:x*2)])
        result = search.fit([(0,0)], max_depth=8, max_states=1)
        self.assertFalse(result.complete)
        self.assertEqual(search.predict(result,3).status,"UNKNOWN")

    def test_list_programs_and_renamed_operators(self):
        functions = [lambda x:tuple(reversed(x)),lambda x:tuple(v+1 for v in x),lambda x:tuple(sorted(x))]
        for names in [("reverse","inc","sort"),("q9","z2","h4")]:
            search = ProgramSearch([Operator(n,f) for n,f in zip(names,functions)])
            examples = [((3,1,2),(3,2,4)),((1,5),(6,2)),((0,),(1,))]
            result = search.fit(examples,max_depth=3)
            self.assertTrue(result.programs)
            self.assertEqual(search.predict(result,(8,2,3)).values,((4,3,9),))

    def test_rule_versions_and_nonforgetting(self):
        rules = VersionedRules()
        for i in range(1000): rules.learn(str(i),0,("original",i))
        for i in range(0,1000,3): rules.learn(str(i),10,("changed",i))
        before = copy.deepcopy(rules.__dict__)
        for i in range(1000):
            self.assertEqual(rules.at(str(i),5),("original",i))
            self.assertEqual(rules.at(str(i),15),("changed" if i%3 == 0 else "original",i))
        self.assertEqual(before,rules.__dict__)


class NumericTests(unittest.TestCase):
    def test_all_feature_families_with_40_percent_corruption(self):
        rng = np.random.default_rng(SEED+5)
        for family in ("affine","controlled","gated","recurrence"):
            for trial in range(10):
                def data(n, scale):
                    x = rng.uniform(-scale,scale,size=(n,3) if family == "recurrence" else n)
                    return features(family,x,u=rng.normal(size=n),g=rng.integers(0,2,size=n))
                x = data(120,3); vx = data(80,8)
                coef = rng.uniform(-3,3,size=x.shape[1]); y = x@coef; vy=vx@coef
                corrupt = rng.choice(len(y),int(.4*len(y)),replace=False)
                y[corrupt] += rng.uniform(10,100,size=len(corrupt))
                model=fit_linear(x,y,vx,vy,seed=trial)
                self.assertEqual(model.status,"ANSWER",(family,trial,model))
                np.testing.assert_allclose(model.coefficients,coef,atol=1e-7,rtol=1e-7)

    def test_reject_nonlinear_and_unidentifiable(self):
        x = np.linspace(-3,3,120); vx=np.linspace(4,8,80)
        model=fit_linear(features("affine",x),x**3,features("affine",vx),vx**3)
        self.assertEqual(model.status,"UNKNOWN")
        x=np.zeros(40)
        model=fit_linear(features("affine",x),x,features("affine",x),x)
        self.assertEqual(model.status,"UNKNOWN")


class EvidenceTests(unittest.TestCase):
    def test_copies_do_not_manufacture_votes(self):
        claims = [Claim(True,.6,f"copy{i}","same") for i in range(100)]
        claims += [Claim(False,.8,"other","independent")]
        self.assertEqual(assess(claims,independent_lineages=True)["status"],"NEGATED")
        self.assertAlmostEqual(assess(claims,independent_lineages=True)["positive_support"][0],.6)

    def test_hidden_dependence_abstains_and_independence_combines(self):
        claims=[Claim(True,.6,"a","a"),Claim(True,.6,"b","b"),Claim(False,.8,"c","c")]
        self.assertEqual(assess(claims)["status"],"AMBIGUOUS")
        self.assertEqual(assess(claims,independent_lineages=True)["status"],"ANSWER")
        self.assertEqual(assess([Claim(True,.8,"a"),Claim(False,.8,"b")])["status"],"CONTRADICTED")


class IntegrationTests(unittest.TestCase):
    def test_macro_queries_current_facts_and_versions(self):
        engine=Engine(["in"])
        engine.ledger.add(Event("1","cup","in","box",1))
        engine.ledger.add(Event("2","box","in","van",1))
        engine.teach_macro("container2",["in","in"],0)
        self.assertEqual(engine.query_macro("container2","cup")[0].values,("van",))
        engine.ledger.add(Event("3","box","in","house",2))
        self.assertEqual(engine.query_macro("container2","cup")[0].values,("house",))
        self.assertEqual(engine.query_macro("container2","cup",time=1)[0].values,("van",))

    def test_language_learns_opaque_verb_from_consequence(self):
        interpreter=GroundedInterpreter(); ledger=Ledger()
        interpreter.teach("Lio daxed key to Nera.",Event("train","Nera","owns","key",0))
        self.assertEqual(interpreter.ingest("Pavo daxed coin to Sumi.",ledger,"1",1).status,"ANSWER")
        self.assertEqual(ledger.subjects("owns","coin"),frozenset(["Sumi"]))
        before=ledger.events()
        self.assertEqual(interpreter.ingest("Pavo zorped coin to Sumi.",ledger,"2",2).status,"UNKNOWN")
        self.assertEqual(interpreter.ingest("She daxed it to Sumi.",ledger,"3",3).status,"UNKNOWN")
        self.assertEqual(before,ledger.events())

    def test_language_ambiguous_roles_retained(self):
        interpreter=GroundedInterpreter()
        interpreter.teach("A daxed X to A.",Event("t","A","r","X",0))
        self.assertEqual(interpreter.interpret("B daxed Y to C.","1",1).status,"AMBIGUOUS")


if __name__ == "__main__":
    unittest.main()
