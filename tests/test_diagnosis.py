"""Independent certificate, evidence-origin and finite-diagnosis integrity tests."""
import copy
import json
import unittest
from unittest.mock import patch

from causalfill.decision_certificates import (
    build_decision_certificate, elimination_certificate, extract_decision_tree,
    information_lower_bound, solve_diagnosis, table_digest, validate_table,
    verify_decision_certificate, verify_decision_tree,
)
from causalfill.domains.diagnosis import DiagnosisTask
from causalfill.session import Session, verify_trace


class DecisionCertificateTests(unittest.TestCase):
    def test_balanced_table_has_exact_two_query_certificate(self):
        table = [[0, 0], [0, 1], [1, 0], [1, 1]]
        certificate = build_decision_certificate(table)
        checked = verify_decision_certificate(table, certificate)
        self.assertTrue(checked["valid"])
        self.assertEqual(checked["optimal_depth"], 2)
        self.assertEqual(checked["information_lower_bound"], 2)
        tree = extract_decision_tree(table, certificate)
        self.assertEqual(verify_decision_tree(table, tree),
                         {"valid": True, "depth": 2, "leaves": 4, "nodes": 7})

    def test_exact_lower_bound_can_exceed_binary_information_bound(self):
        # Each available query isolates one nonzero row; no first query splits 2:2.
        table = [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]]
        certificate = build_decision_certificate(table)
        checked = verify_decision_certificate(table, certificate)
        self.assertEqual(checked["information_lower_bound"], 2)
        self.assertEqual(checked["optimal_depth"], 3)
        forged = copy.deepcopy(certificate)
        for node in forged["nodes"]:
            if node[0] == forged["root_mask"]:
                node[1] = 2
        self.assertFalse(verify_decision_certificate(table, forged)["valid"])

    def test_checker_covers_alternative_queries_not_just_chosen_tree(self):
        table = [[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]]
        certificate = build_decision_certificate(table)
        chosen = extract_decision_tree(table, certificate)
        self.assertEqual(chosen["query"], 0)
        # Mask 11 is the 0-outcome child of alternative root query1, not the
        # selected query0's child (13). Omitting it invalidates the lower bound.
        broken = copy.deepcopy(certificate)
        broken["nodes"] = [node for node in broken["nodes"] if node[0] != 11]
        checked = verify_decision_certificate(table, broken)
        self.assertFalse(checked["valid"])
        self.assertIn("child state absent", checked["error"])

    def test_checker_is_independent_of_optimizer(self):
        table = [[0, 0], [0, 1], [1, 0], [1, 1]]
        certificate = build_decision_certificate(table)
        with patch("causalfill.decision_certificates._optimize", side_effect=AssertionError("optimizer consulted")):
            self.assertTrue(verify_decision_certificate(table, certificate)["valid"])
            self.assertTrue(verify_decision_tree(table, extract_decision_tree(table, certificate))["valid"])

    def test_digest_depth_query_and_leaf_tampering_are_rejected(self):
        table = [[0, 0], [0, 1], [1, 0], [1, 1]]
        certificate = build_decision_certificate(table)
        for mutation in ("digest", "depth", "query", "duplicate"):
            altered = copy.deepcopy(certificate)
            if mutation == "digest": altered["table_sha256"] = "0" * 64
            elif mutation == "depth": altered["nodes"][-1][1] += 1
            elif mutation == "query": altered["nodes"][0][2] = 0
            else: altered["nodes"].append(altered["nodes"][0])
            self.assertFalse(verify_decision_certificate(table, altered)["valid"], mutation)
        tree = extract_decision_tree(table, certificate)
        leaf = tree
        while "query" in leaf: leaf = leaf["zero"]
        leaf["world"] = (leaf["world"] + 1) % 4
        self.assertFalse(verify_decision_tree(table, tree)["valid"])

    def test_malformed_tables_and_certificate_sizes_are_bounded(self):
        for table in ([], [[0]], [[0], [0]], [[False], [True]], [[0.0], [1]], [[0, 1], [1]],
                      [[0] * 13, [1] * 13], [[0]] * 33):
            with self.assertRaises(ValueError): validate_table(table)
        with self.assertRaises(ValueError): information_lower_bound(True)
        table = [[0], [1]]
        certificate = build_decision_certificate(table)
        certificate["nodes"] = [[1, 0, None]] * 100_001
        self.assertFalse(verify_decision_certificate(table, certificate)["valid"])

    def test_elimination_requires_unique_observational_identification(self):
        table = [[0, 0], [0, 1], [1, 0], [1, 1]]
        with self.assertRaises(ValueError): elimination_certificate(table, [(0, 0)], 0)
        with self.assertRaises(ValueError): elimination_certificate(table, [(0, 0), (0, 1)], 0)
        result = elimination_certificate(table, [(0, 0), (1, 0)], 0)
        self.assertEqual({item["world"] for item in result}, {1, 2, 3})


class DiagnosisTests(unittest.TestCase):
    def test_evidence_only_reference_across_structures_dimensions_and_twins(self):
        for split in ("train", "dev", "transfer"):
            for difficulty in (1, 2, 3):
                for twin in (0, 1):
                    task = DiagnosisTask(17, split, difficulty, twin)
                    session = Session(task)
                    # Public reference must never need these evaluator entry points.
                    task.reference_answer = lambda: (_ for _ in ()).throw(AssertionError("oracle"))
                    task.decision_certificate = lambda: (_ for _ in ()).throw(AssertionError("private certificate"))
                    fill = solve_diagnosis(session.public(), session.call)
                    response = session.call("submit", {"fill": fill, "confidence": 1.0,
                        "abstain": False, "evidence": [e["event_id"] for e in session.trace]})
                    self.assertTrue(response["accepted"])
                    self.assertTrue(session.result["success"], (split, difficulty, twin))
                    self.assertEqual(session.invalid, 0)
                    self.assertLessEqual(task.query_count, task.query_budget)
                    self.assertLessEqual(session.cost, task.budget)
                    self.assertTrue(verify_trace(session.trace))

    def test_oracle_reference_requires_and_replays_real_experiments(self):
        task = DiagnosisTask(9, "dev", 2)
        with self.assertRaises(ValueError): task.reference_answer()
        for name, args in task.reference_actions(): task.query(name, args)
        self.assertTrue(task.evaluate(task.reference_answer()).success)

    def test_lucky_correct_guess_and_unobserved_witnesses_do_not_pass(self):
        task = DiagnosisTask(2)
        world = task._world
        fake = {"world": world, "eliminations": [
            {"world": other, "experiment": 0} for other in range(len(task._table)) if other != world]}
        verdict = task.evaluate(fake)
        self.assertFalse(verdict.success)
        self.assertEqual(verdict.recovery, 0)
        self.assertEqual(task.query_count, 0)

    def test_incomplete_duplicate_and_wrong_world_certificates_fail(self):
        task = DiagnosisTask(12, "transfer", 2)
        session = Session(task)
        fill = solve_diagnosis(session.public(), session.call)
        self.assertTrue(task.evaluate(fill).success)
        incomplete = copy.deepcopy(fill); incomplete["eliminations"].pop()
        self.assertFalse(task.evaluate(incomplete).success)
        duplicate = copy.deepcopy(fill); duplicate["eliminations"][1] = duplicate["eliminations"][0]
        self.assertFalse(task.evaluate(duplicate).success)
        wrong = copy.deepcopy(fill); wrong["world"] = (wrong["world"] + 1) % len(task._table)
        self.assertFalse(task.evaluate(wrong).success)

    def test_invalid_experiments_are_atomic_and_cap_is_separate_from_file_budget(self):
        task = DiagnosisTask(6, "train", 1)
        for args in ({"id": True}, {"id": -1}, {"id": 99}, {}, {"id": 0, "extra": 1}):
            with self.assertRaises(ValueError): task.query("experiment", args)
        self.assertEqual(task.query_count, 0)
        self.assertEqual(task.observations, [])
        session = Session(task)
        for _ in range(task.query_budget): self.assertNotIn("error", session.call("experiment", {"id": 0}))
        self.assertLess(session.cost, task.budget)
        before = list(task.observations)
        self.assertIn("error", session.call("experiment", {"id": 1}))
        self.assertEqual(task.observations, before)
        self.assertEqual(task.query_count, task.query_budget)
        self.assertEqual(session.invalid, 1)

    def test_twin_changes_only_current_world_and_public_table_is_target_independent(self):
        a = DiagnosisTask(92183745, "dev", 3, 0)
        b = DiagnosisTask(92183745, "dev", 3, 1)
        self.assertNotEqual(a._world, b._world)
        self.assertEqual(a.files, b.files)
        self.assertEqual(a.public(), b.public())
        self.assertEqual(a.decision_certificate(), b.decision_certificate())
        self.assertNotIn("92183745", a.prompt + str(a.files))
        self.assertEqual(a.twin_kind, "diagnostic_state")
        metadata = json.loads(a.files["/formal/diagnosis.json"])
        self.assertNotIn("current_world", metadata)
        self.assertEqual(metadata["table_sha256"], table_digest(metadata["responses"]))

    def test_three_split_families_have_distinct_structures(self):
        tasks = [DiagnosisTask(42, split, 2) for split in ("train", "dev", "transfer")]
        self.assertEqual(len({t.structural_signature for t in tasks}), 3)
        self.assertEqual(len({table_digest(t._table) for t in tasks}), 3)

    def test_exported_certificate_is_a_defensive_copy(self):
        task = DiagnosisTask(2, "train", 1)
        certificate = task.decision_certificate()
        certificate["nodes"].clear()
        self.assertTrue(task.decision_certificate()["nodes"])


if __name__ == "__main__": unittest.main()
