"""Independent truth semantics exercise the resolution checker's soundness."""
import itertools
import unittest

from causalfill.logic_kernel import (
    MAX_INITIAL_CLAUSES, MAX_PROOF_STEPS, normalize_cnf,
    statement_digest, verify_model, verify_resolution,
)


def truth(clause, values):
    # Deliberately separate semantics from the checker's set operations.
    for literal in clause:
        bit = values[abs(literal)-1]
        if literal < 0:
            bit = not bit
        if bit:
            return True
    return False


class LogicKernelTests(unittest.TestCase):
    def test_normalization_preserves_indices_and_logical_edge_cases(self):
        raw = [[2, 1, 1], [], [-1, 1], [2, 1]]
        normalized = normalize_cnf(raw, 2)
        self.assertEqual(normalized, [(1, 2), (), (-1, 1), (1, 2)])
        self.assertEqual(normalize_cnf(normalized, 2), normalized)
        self.assertEqual(raw, [[2, 1, 1], [], [-1, 1], [2, 1]])

    def test_known_entailment_with_nonvacuity_model(self):
        premises = [[1], [-1, 2], [-2, 3]]
        # Add negation of goal 3 as premise index 3.
        steps = [[0, 1, 1], [4, 2, 2], [5, 3, 3]]
        result = verify_resolution(premises + [[-3]], steps, 3)
        self.assertTrue(result["valid"])
        self.assertTrue(result["derived_empty"])
        self.assertEqual(result["checked_steps"], 3)
        self.assertEqual(result["final_clause"], [])
        self.assertTrue(verify_model(premises, [True, True, True], 3))
        self.assertFalse(verify_model(premises, [True, True, False], 3))

    def test_every_small_accepted_resolvent_is_semantically_sound(self):
        # All 64 clauses over 3 variables, including tautologies and empty.
        literals = (-3, -2, -1, 1, 2, 3)
        clauses = [list(c) for r in range(7) for c in itertools.combinations(literals, r)]
        assignments = list(itertools.product((False, True), repeat=3))
        accepted = 0
        for left, right, pivot in itertools.product(clauses, clauses, range(1, 4)):
            result = verify_resolution([left, right], [[0, 1, pivot]], 3)
            if not result["valid"]:
                continue
            accepted += 1
            for bits in assignments:
                if truth(left, bits) and truth(right, bits):
                    self.assertTrue(truth(result["final_clause"], bits),
                        (left, right, pivot, result, bits))
        self.assertGreater(accepted, 0)

    def test_tautological_parent_cannot_manufacture_false(self):
        for step in ([0, 0, 1], [0, 1, 1], [1, 0, 1]):
            result = verify_resolution([[1, -1], [1]], [step], 1)
            self.assertTrue(result["valid"])
            self.assertFalse(result["derived_empty"])
            self.assertTrue(truth(result["final_clause"], [True]))

    def test_valid_prefix_is_distinct_from_refutation(self):
        result = verify_resolution([[1, 2], [-1, 3]], [[0, 1, 1]], 3)
        self.assertTrue(result["valid"])
        self.assertFalse(result["derived_empty"])
        self.assertEqual(result["final_clause"], [2, 3])

    def test_empty_formula_and_existing_empty_clause_are_distinguished(self):
        empty_formula = verify_resolution([], [], 1)
        self.assertTrue(empty_formula["valid"])
        self.assertFalse(empty_formula["derived_empty"])
        contradiction = verify_resolution([[], [1]], [], 1)
        self.assertTrue(contradiction["derived_empty"])
        self.assertEqual(contradiction["final_clause"], [])
        self.assertTrue(verify_model([], [False], 1))
        self.assertFalse(verify_model([[]], [False], 1))

    def test_bad_later_step_invalidates_an_already_refuting_prefix(self):
        result = verify_resolution([[1], [-1]], [[0, 1, 1], [2, 2, 1]], 1)
        self.assertFalse(result["valid"])
        self.assertFalse(result["derived_empty"])
        self.assertEqual(result["checked_steps"], 1)

    def test_future_and_unknown_references_are_rejected(self):
        for step in ([2, 1, 1], [-1, 0, 1], [0, 1000, 1], [True, 1, 1]):
            result = verify_resolution([[1], [-1]], [step], 1)
            self.assertFalse(result["valid"])
            self.assertEqual(result["checked_steps"], 0)

    def test_bad_pivots_and_non_resolution_inferences_are_rejected(self):
        for pivot in (True, False, 0, -1, 2, 1.0, "1"):
            self.assertFalse(verify_resolution([[1], [-1]], [[0, 1, pivot]], 1)["valid"])
        self.assertFalse(verify_resolution([[1], [1]], [[0, 1, 1]], 1)["valid"])

    def test_invented_premises_and_admission_payloads_are_rejected(self):
        for steps in ([{"axiom": []}], [[0, 1, 1, []]], ["sorry"], {"steps": []}, None):
            self.assertFalse(verify_resolution([[1], [-1]], steps, 1)["valid"])

    def test_malformed_cnf_and_model_inputs_fail_closed(self):
        malformed = (None, "x", {"clauses": []}, [[True]], [[0]], [[2]], [[1.0]], [["1"]], [[]]*2001)
        for clauses in malformed:
            with self.assertRaises(ValueError): normalize_cnf(clauses, 1)
            self.assertFalse(verify_resolution(clauses, [], 1)["valid"])
            self.assertFalse(verify_model(clauses, [True], 1))
        for assignment in (None, (True,), [1], [True, False], [], ["true"]):
            self.assertFalse(verify_model([[1]], assignment, 1))
        for nvars in (0, 201, True, 1.0, "1"):
            self.assertFalse(verify_model([], [], nvars))

    def test_bounded_resources_and_diagnostics(self):
        self.assertEqual(len(normalize_cnf([[]]*MAX_INITIAL_CLAUSES, 1)), MAX_INITIAL_CLAUSES)
        with self.assertRaises(ValueError): normalize_cnf([[1]*3], 1)
        self.assertFalse(verify_resolution([[1], [-1]], [[0, 1, 1]]*2, 1, max_steps=1)["valid"])
        self.assertFalse(verify_resolution([], [], 1, max_steps=MAX_PROOF_STEPS+1)["valid"])
        self.assertFalse(verify_resolution([], [], 1, max_steps=True)["valid"])
        self.assertFalse(verify_resolution([[1], [-1]], [[0, 1, 1]]*(MAX_PROOF_STEPS+1), 1)["valid"])
        error = verify_resolution([], [[10**200, 0, 1]], 1)["error"]
        self.assertLessEqual(len(error), 240)

    def test_statement_commitment_binds_premises_domain_and_signed_goal(self):
        base = statement_digest([[1, 2], [-1]], 2, 2)
        self.assertEqual(base, statement_digest([[2, 1, 1], [-1]], 2, 2))
        self.assertNotEqual(base, statement_digest([[1], [-1]], 2, 2))
        self.assertNotEqual(base, statement_digest([[-1], [1, 2]], 2, 2))
        self.assertNotEqual(base, statement_digest([[1, 2], [-1]], 3, 2))
        self.assertNotEqual(base, statement_digest([[1, 2], [-1]], 2, -2))
        for goal in (True, 0, 3, "2", 2.0):
            with self.assertRaises(ValueError):statement_digest([[1]], 2, goal)

    def test_satisfiable_small_formulas_cannot_refute_in_two_steps(self):
        # Exhaust all pairs of non-tautological clauses over two variables,
        # then all valid two-step continuations. Soundness is checked against
        # an explicit satisfying assignment, not a second proof implementation.
        literals = (-2, -1, 1, 2)
        clauses = [list(c) for r in range(5) for c in itertools.combinations(literals, r)
                   if not any(-x in c for x in c)]
        assignments = list(itertools.product((False, True), repeat=2))
        for formula in itertools.product(clauses, repeat=2):
            models = [bits for bits in assignments if all(truth(c,bits) for c in formula)]
            if not models: continue
            for first in itertools.product(range(2), range(2), range(1,3)):
                prefix = verify_resolution(list(formula), [list(first)], 2)
                if not prefix["valid"]:continue
                self.assertFalse(prefix["derived_empty"])
                for second in itertools.product(range(3), range(3), range(1,3)):
                    result=verify_resolution(list(formula), [list(first), list(second)], 2)
                    if result["valid"]:
                        self.assertFalse(result["derived_empty"])
                        self.assertTrue(truth(result["final_clause"], models[0]))


if __name__ == "__main__":
    unittest.main()
