"""Integrity tests for the finite-field identification task."""

import copy
import unittest

from causalfill.domains.latent import (
    LatentTask,
    SparseLatentTask,
    MODULUS,
    _candidate_output,
    _parse_fill,
    basis_probe_plan,
    recover_affine_operator,
    recover_sparse_operator,
    sparse_probe_plan,
)
from causalfill.session import Session


class LatentTests(unittest.TestCase):
    def test_known_modular_arithmetic_and_public_recovery(self):
        # f(x0,x1) = (100*x0 + 3*x1 + 4, 8*x1 + 100) mod 101.
        recovered = recover_affine_operator([[4, 100], [3, 100], [7, 7]], 2)
        offset, rows = _parse_fill(recovered, 2, 101)
        self.assertEqual(_candidate_output(offset, rows, [100, 2], 101), [11, 15])

    def test_all_structures_have_exact_reference_solution(self):
        for split in ("train", "dev", "transfer"):
            for difficulty in (1, 2, 3):
                task = LatentTask(94, split, difficulty)
                result = task.evaluate(task.reference_answer())
                self.assertTrue(result.success, (split, difficulty))
                self.assertEqual(result.recovery, 1.0)
                self.assertEqual(result.outcome, 1.0)
                self.assertLessEqual(len(basis_probe_plan(task.dimension)), task.budget)

    def test_bool_float_overflow_and_bad_lengths_are_rejected(self):
        task = LatentTask(8, "dev", 1)
        valid = [0] * task.dimension
        for bad in (True, 1.0, -1, MODULUS, "1", None):
            vector = list(valid)
            vector[2] = bad
            with self.assertRaises(ValueError):
                task.query("probe", {"vector": vector})
        for args in ({}, {"vector": valid, "secret": 1}, {"vector": []}):
            with self.assertRaises(ValueError):
                task.query("probe", args)
        with self.assertRaises(ValueError):
            task.query("reveal", {"vector": valid})
        self.assertEqual(task.query("probe", {"vector": valid})["output"], task.query("probe", {"vector": valid})["output"])

    def test_invalid_submission_types_and_duplicate_columns(self):
        task = LatentTask(6, "train", 1)
        reference = task.reference_answer()
        malformed = copy.deepcopy(reference)
        malformed["offset"][0] = True
        self.assertFalse(task.evaluate(malformed).success)
        malformed = copy.deepcopy(reference)
        malformed["rows"][0].append(dict(malformed["rows"][0][0]))
        self.assertFalse(task.evaluate(malformed).success)
        malformed = copy.deepcopy(reference)
        malformed["arbitrary_python"] = "__import__('os')"
        self.assertFalse(task.evaluate(malformed).success)
        for invalid in (None, [], "answer", {"offset": [], "rows": []}):
            self.assertFalse(task.evaluate(invalid).success)

    def test_visible_fit_is_not_sufficient(self):
        task = LatentTask(13, "transfer", 1)
        wrong = task.reference_answer()
        row = {term["column"]: term["coefficient"] for term in wrong["rows"][0]}
        row[0] = (row.get(0, 0) + 1) % MODULUS
        row[1] = (row.get(1, 0) - 1) % MODULUS
        wrong["rows"][0] = [{"column": column, "coefficient": coefficient} for column, coefficient in row.items()]
        offset, rows = _parse_fill(wrong, task.dimension, MODULUS)
        for vector in ([0] * task.dimension, [1] * task.dimension):
            self.assertEqual(_candidate_output(offset, rows, vector, MODULUS), task.query("probe", {"vector": vector})["output"])
        result = task.evaluate(wrong)
        self.assertFalse(result.success)
        self.assertLess(result.recovery, 1.0)
        self.assertLess(result.outcome, 1.0)

    def test_equivalent_sparse_order_is_accepted(self):
        task = LatentTask(72, "transfer", 1)
        answer = task.reference_answer()
        answer["rows"] = [list(reversed(row)) for row in answer["rows"]]
        self.assertTrue(task.evaluate(answer).success)

    def test_twin_changes_exactly_one_coefficient(self):
        for split in ("train", "dev", "transfer"):
            original = LatentTask(701, split, 1, 0)
            twin = LatentTask(701, split, 1, 1)
            a = original.reference_answer()
            b = twin.reference_answer()
            self.assertEqual(a["offset"], b["offset"])
            changes = 0
            for row_a, row_b in zip(a["rows"], b["rows"]):
                da = {term["column"]: term["coefficient"] for term in row_a}
                db = {term["column"]: term["coefficient"] for term in row_b}
                self.assertEqual(set(da), set(db))
                changes += sum(da[column] != db[column] for column in da)
            self.assertEqual(changes, 1)
            self.assertEqual(original.files, twin.files)
            self.assertEqual(original._heldout, twin._heldout)
            self.assertFalse(twin.evaluate(a).success)

    def test_zero_matrix_does_not_get_high_recovery_for_structural_zeros(self):
        task = LatentTask(9, "train", 3)
        result = task.evaluate({"offset": [0] * 100, "rows": [[] for _ in range(100)]})
        self.assertEqual(result.recovery, 0.0)
        self.assertFalse(result.success)

    def test_public_content_has_no_seed_or_solution(self):
        task = LatentTask(9128374, "dev", 1)
        self.assertNotIn("9128374", task.prompt + str(task.files))
        self.assertIn("[MASK:", task.files["/workspace/operator.masked.json"])
        self.assertNotIn("seed", task.tools)

    def test_evidence_only_solver_completes_100d_through_budgeted_session(self):
        session = Session(LatentTask(441, "transfer", 3))
        public = session.public()
        manual = session.call("read_file", {"path": "/docs/field.txt"})
        self.assertNotIn("error", manual)
        observations, evidence = [], [manual["event_id"]]
        for vector in basis_probe_plan(100):
            response = session.call("probe", {"vector": vector})
            self.assertNotIn("error", response)
            observations.append(response["output"])
            evidence.append(response["event_id"])
        fill = recover_affine_operator(observations, 100)
        response = session.call("submit", {"fill": fill, "confidence": 1.0, "abstain": False, "evidence": evidence})
        self.assertTrue(response["accepted"])
        self.assertNotIn("success", response)
        self.assertTrue(session.result["success"])
        self.assertLessEqual(session.result["tool_cost"], public["budget"])


class SparseLatentTests(unittest.TestCase):
    def test_exact_sparse_reference_across_structures_and_dimensions(self):
        for split in ("train", "dev", "transfer"):
            for difficulty in (1, 2, 3):
                for seed in (0, 17, 901):
                    task = SparseLatentTask(seed, split, difficulty)
                    verdict = task.evaluate(task.reference_answer())
                    self.assertTrue(verdict.success, (seed, split, difficulty))
                    self.assertEqual(verdict.recovery, 1.0)

    def test_cancellation_and_coordinate_zero(self):
        # First row has coefficients 7 and -7, so m0 = 0 despite two terms.
        # Include a singleton at coordinate zero and a completely zero row.
        offset = [1, 2, 3, 4]
        rows = [[(0, 7), (3, 94)], [(0, 81)], [], [(1, 5), (2, 6)]]
        outputs = [_candidate_output(offset, rows, vector, 101) for vector in sparse_probe_plan(4)]
        answer = recover_sparse_operator(outputs, 4)
        recovered_offset, recovered_rows = _parse_fill(answer, 4, 101)
        self.assertEqual(recovered_offset, offset)
        for vector in basis_probe_plan(4) + [[100, 27, 50, 19]]:
            self.assertEqual(_candidate_output(offset, rows, vector, 101), _candidate_output(recovered_offset, recovered_rows, vector, 101))

    def test_bad_moments_are_rejected(self):
        with self.assertRaises(ValueError):
            recover_sparse_operator([[0], [1], [0], [1], [0]], 1)
        with self.assertRaises(ValueError):
            recover_sparse_operator([[0], [0], [0], [0]], 1)
        with self.assertRaises(ValueError):
            recover_sparse_operator([[0], [1], [False], [0], [0]], 1)
        with self.assertRaises(ValueError):
            recover_sparse_operator([[0], [1], [0], [0], [0]], 1, 97)

    def test_five_paid_probes_solve_100d(self):
        session = Session(SparseLatentTask(674, "transfer", 3))
        manual = session.call("read_file", {"path": "/docs/field.txt"})
        self.assertNotIn("basis", manual["content"].lower())
        self.assertNotIn("prony", manual["content"].lower())
        observations, evidence = [], [manual["event_id"]]
        for vector in sparse_probe_plan(100):
            observed = session.call("probe", {"vector": vector})
            self.assertNotIn("error", observed)
            observations.append(observed["output"])
            evidence.append(observed["event_id"])
        response = session.call("submit", {"fill": recover_sparse_operator(observations, 100), "confidence": 1.0, "abstain": False, "evidence": evidence})
        self.assertTrue(response["accepted"])
        self.assertTrue(session.result["success"])
        self.assertEqual(session.result["tool_cost"], 6)

    def test_budget_prevents_full_100d_coordinate_scan(self):
        session = Session(SparseLatentTask(881, "transfer", 3))
        probes = basis_probe_plan(100)
        for vector in probes[:9]:
            self.assertNotIn("error", session.call("probe", {"vector": vector}))
        self.assertIn("error", session.call("probe", {"vector": probes[9]}))
        self.assertEqual(session.cost, 9)

    def test_sparse_twin_is_one_coefficient_intervention(self):
        original = SparseLatentTask(99, "transfer", 3, 0)
        twin = SparseLatentTask(99, "transfer", 3, 1)
        a, b = original.reference_answer(), twin.reference_answer()
        self.assertEqual(a["offset"], b["offset"])
        changes = 0
        for row_a, row_b in zip(a["rows"], b["rows"]):
            da = {term["column"]: term["coefficient"] for term in row_a}
            db = {term["column"]: term["coefficient"] for term in row_b}
            self.assertEqual(set(da), set(db))
            changes += sum(da[column] != db[column] for column in da)
        self.assertEqual(changes, 1)
        self.assertTrue(twin.evaluate(b).success)
        self.assertFalse(twin.evaluate(a).success)


if __name__ == "__main__":
    unittest.main()

