"""Check audit-oracle independence and sensitivity to deliberately broken checkers.

These are developer regression tests, not model runs or global correctness
proofs. The full corpus lives in the separately rerunnable tools/stress_formal.py.
"""
import random
import unittest
from unittest.mock import patch

from causalfill.decision_certificates import verify_decision_certificate, verify_decision_tree
from tools.stress_formal import (
    Audit, PolicyOracle, blocker_statement, exhaustive_resolution,
    independent_certificate, nonvacuity_cases, policy_tree,
    proof_task_for_statement, replay_tree, satisfiable_multistep_semantics,
    swap_and_duplicate_steps,
)


class FormalStressRegressions(unittest.TestCase):
    def test_complete_policy_oracle_detects_restricted_query_gap_without_optimizer(self):
        constrained = [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]]
        with patch("causalfill.decision_certificates._optimize", side_effect=AssertionError("optimizer consulted")):
            oracle = PolicyOracle(3, 3)
            depth, policies = oracle.solve(constrained)
            self.assertEqual(depth, 3)
            self.assertEqual(oracle.policies_enumerated, 2218)
            certificate, choices = independent_certificate(constrained, oracle)
            self.assertEqual(choices[15], {0, 1, 2})
            self.assertTrue(verify_decision_certificate(constrained, certificate)["valid"])
            for queries in (policies[0], policies[-1]):
                tree = policy_tree(constrained, queries, depth)
                self.assertEqual(replay_tree(constrained, tree), (True, 3))
                self.assertTrue(verify_decision_tree(constrained, tree)["valid"])

    def test_complete_policy_oracle_does_not_fabricate_solution_beyond_depth_limit(self):
        table = [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]]
        with self.assertRaises(ValueError):
            PolicyOracle(3, 2).solve(table)

    def test_independent_blocker_proofs_allow_redundancy_and_different_models(self):
        rng = random.Random(38021)
        with patch("causalfill.proof_search.resolution_refutation", side_effect=AssertionError("proof search consulted")):
            for ninputs in range(1, 8):
                statement, fill = blocker_statement(ninputs, rng)
                task = proof_task_for_statement(statement)
                self.assertTrue(task.evaluate(fill).success)
                transformed = swap_and_duplicate_steps(fill, len(statement["clauses"]) + 1, rng)
                self.assertTrue(task.evaluate(transformed).success)
                transformed["consistency_model"] = [not bit for bit in transformed["consistency_model"]]
                transformed["consistency_model"][abs(statement["goal"]) - 1] = statement["goal"] > 0
                self.assertTrue(task.evaluate(transformed).success)

    def test_resolution_semantic_audit_kills_accept_everything_mutant(self):
        audit = Audit()
        forged = {"valid": True, "derived_empty": True, "final_clause": [], "checked_steps": 1, "error": None}
        with patch("tools.stress_formal.verify_resolution", return_value=forged):
            exhaustive_resolution(audit, 2)
        totals = audit.report()["totals"]
        self.assertGreater(totals["false_accepts"], 0)
        self.assertGreater(totals["invariant_failures"], 0)
        self.assertEqual(totals["exceptions"], 0)

    def test_resolution_semantic_audit_kills_reject_everything_mutant(self):
        audit = Audit()
        forged = {"valid": False, "derived_empty": False, "final_clause": [], "checked_steps": 0, "error": "mutant"}
        with patch("tools.stress_formal.verify_resolution", return_value=forged):
            exhaustive_resolution(audit, 2)
        totals = audit.report()["totals"]
        self.assertGreater(totals["false_rejects"], 0)
        self.assertEqual(totals["exceptions"], 0)

    def test_satisfiable_multistep_oracle_and_nonvacuity_regressions(self):
        audit = Audit()
        satisfiable_multistep_semantics(audit, random.Random(41627), 40)
        nonvacuity_cases(audit)
        totals = audit.report()["totals"]
        for name in ("false_accepts", "false_rejects", "invariant_failures", "exceptions"):
            self.assertEqual(totals[name], 0, audit.failures)
        self.assertGreater(totals["expected_accepts"], 0)
        self.assertGreater(totals["expected_rejects"], 0)


if __name__ == "__main__":
    unittest.main()
