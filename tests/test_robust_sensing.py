"""Live task tests: evidence, irreversible action, and separate cost caps."""
import copy
import json
import unittest
from unittest.mock import patch

from causalfill.domains.robust_sensing import (
    RobustSensingTask, completion_for_history, solve_robust_sensing,
)
from causalfill.session import Session, verify_trace


def finish(session, fill):
    return session.call("submit", {"fill": fill, "confidence": 1.0,
        "abstain": False, "evidence": [e["event_id"] for e in session.trace]})


class RobustSensingRuntimeTests(unittest.TestCase):
    def test_public_reference_succeeds_across_all_profiles_and_twins(self):
        for split in ("train", "dev", "transfer"):
            for level in (1, 2, 3):
                for twin in (0, 1):
                    with self.subTest(split=split, level=level, twin=twin):
                        task = RobustSensingTask(4103, split, level, twin)
                        session = Session(task)
                        with patch.object(task, "reference_answer", side_effect=AssertionError("private answer")), \
                             patch.object(task, "robust_policy", side_effect=AssertionError("private policy")), \
                             patch.object(task, "robust_certificate", side_effect=AssertionError("private certificate")):
                            fill = solve_robust_sensing(session.public(), session.call)
                        self.assertTrue(finish(session, fill)["accepted"])
                        self.assertTrue(session.result["success"])
                        self.assertTrue(verify_trace(session.trace))
                        self.assertEqual(session.invalid, 0)
                        self.assertLessEqual(task.operational_cost, task.operational_budget)

    def test_twins_change_only_fault_assignment_and_preserve_public_contract(self):
        clean = RobustSensingTask(41, "transfer", 3, 0)
        noisy = RobustSensingTask(41, "transfer", 3, 1)
        self.assertEqual(clean.public(), noisy.public())
        self.assertEqual(clean._world, noisy._world)
        self.assertEqual(clean.files, noisy.files)
        self.assertEqual(len(clean._faults), 0)
        self.assertEqual(len(noisy._faults), 2)

    def test_returned_models_cannot_mutate_evaluator(self):
        task = RobustSensingTask(41, "train", 1)
        model = task.public_problem()
        model["worlds"].clear()
        task.robust_certificate()["nodes"].clear()
        task.robust_policy()["nodes"].clear()
        self.assertEqual(len(task._problem["worlds"]), 2)
        self.assertTrue(task._certificate["nodes"])
        self.assertTrue(task._policy["nodes"])

    def test_successful_lucky_action_without_robust_evidence_fails(self):
        task = RobustSensingTask(19, "train", 1)
        action = next(a for a in task._problem["actions"] if task._world in a["success_worlds"])
        task.query("commit_" + action["id"], {})
        fill = completion_for_history(task._problem, [], action["id"])
        self.assertFalse(task.evaluate(fill).success)
        self.assertEqual(task.used, set())

    def test_exclusion_certificates_need_distinct_real_observations(self):
        task = RobustSensingTask(29, "train", 2, 1)
        session = Session(task)
        good = solve_robust_sensing(session.public(), session.call)
        self.assertTrue(task.evaluate(good).success)
        for mutation in ("duplicate", "invented", "missing", "repeat_world", "wrong_digest", "bool_id"):
            bad = copy.deepcopy(good)
            if mutation == "duplicate":
                q = bad["exclusions"][0]["conflicts"][0]
                bad["exclusions"][0]["conflicts"] = [q, q]
            elif mutation == "invented": bad["exclusions"][0]["conflicts"][0] = "q_fake"
            elif mutation == "missing": bad["exclusions"].pop()
            elif mutation == "repeat_world": bad["exclusions"][1] = bad["exclusions"][0]
            elif mutation == "wrong_digest": bad["problem_sha256"] = "0" * 64
            else: bad["exclusions"][0]["conflicts"][0] = True
            self.assertFalse(task.evaluate(bad).success, mutation)

    def test_valid_certificate_without_execution_does_not_complete(self):
        task = RobustSensingTask(35, "train", 1)
        solved = task.clone_for_case(task._world, [])
        for name, args in solved.reference_actions(): solved.query(name, args)
        self.assertFalse(task.evaluate(solved.reference_answer()).success)

    def test_commitment_is_irreversible_and_hides_outcome(self):
        task = RobustSensingTask(35, "transfer", 1)
        action = task._problem["actions"][0]["id"]
        response = task.query("commit_" + action, {})
        self.assertEqual(set(response), {"action", "committed", "next_step"})
        before = (copy.deepcopy(task.observations), task.operational_cost, task.committed)
        for name in ("probe_q00", "commit_" + action):
            with self.assertRaisesRegex(ValueError, "already committed"):
                task.query(name, {})
        self.assertEqual(before, (task.observations, task.operational_cost, task.committed))

    def test_probe_is_one_use_and_rejected_calls_are_atomic(self):
        task = RobustSensingTask(37, "train", 1)
        for name, args in (("probe_q00", {"extra": 1}), ("probe_missing", {}), ("commit_missing", {})):
            with self.assertRaises(ValueError): task.query(name, args)
        self.assertEqual(task.observations, [])
        self.assertEqual(task.operational_cost, 0)
        first = task.query("probe_q00", {})
        with self.assertRaisesRegex(ValueError, "already consumed"): task.query("probe_q00", {})
        self.assertEqual(len(task.observations), 1)
        self.assertEqual(task.operational_cost, 1)
        self.assertNotIn("truth", first)
        self.assertNotIn("corrupted", first)

    def test_unused_setup_credits_do_not_override_operational_limit(self):
        task = RobustSensingTask(41, "transfer", 1)
        session = Session(task)
        self.assertEqual(task.operational_budget, 3)
        for q in ("q00", "q01", "q02"):
            self.assertNotIn("error", session.call("probe_" + q, {}))
        self.assertEqual(session.cost, 3)
        self.assertEqual(task.budget, 5)
        before = copy.deepcopy(task.observations)
        self.assertIn("error", session.call("probe_q03", {}))
        self.assertEqual(task.observations, before)
        self.assertIn("error", session.call("commit_" + task._problem["actions"][0]["id"], {}))
        self.assertIsNone(task.committed)
        self.assertEqual(task.operational_cost, 3)

    def test_exact_budget_succeeds_and_one_less_cannot_execute_same_policy(self):
        base = RobustSensingTask(43, "train", 1)
        q = base._problem["experiments"][0]["id"]
        for world in base._problem["worlds"]:
            full = base.clone_for_case(world, [q])
            for name, args in full.reference_actions(): full.query(name, args)
            if full.operational_cost == base.operational_budget:
                reduced = base.clone_for_case(world, [q])
                reduced.operational_budget -= 1
                with self.assertRaisesRegex(ValueError, "budget exhausted"):
                    for name, args in full.reference_actions(): reduced.query(name, args)
                self.assertTrue(full.evaluate(full.reference_answer()).success)
                return
        self.fail("expected a worst-case path")

    def test_decision_can_preserve_multiple_worlds(self):
        task = RobustSensingTask(47, "transfer", 1, 1)
        session = Session(task)
        fill = solve_robust_sensing(session.public(), session.call)
        verdict = task.evaluate(fill)
        self.assertTrue(verdict.success)
        self.assertGreater(verdict.details["compatible_worlds_at_commit"], 1)
        self.assertEqual(len(task.used), 2)

    def test_valid_bypass_needs_no_identification_or_exclusions(self):
        task = RobustSensingTask(4103, "transfer", 2, 1)
        bypass = next(a for a in task._problem["actions"]
                      if len(a["success_worlds"]) == len(task._problem["worlds"]))
        self.assertEqual(bypass["cost"], task.operational_budget)
        task.query("commit_" + bypass["id"], {})
        fill = completion_for_history(task._problem, [], bypass["id"])
        self.assertEqual(fill["exclusions"], [])
        self.assertTrue(task.evaluate(fill).success)
        self.assertEqual(task._observed_faults, 0)
        self.assertEqual(len(task._faults), 1)

    def test_alternative_justified_actions_are_accepted(self):
        task = RobustSensingTask(53, "transfer", 1)
        # This evaluator test provides more diagnostic budget so that multiple
        # legal successful actions can be compared; no optimality claim follows.
        task.operational_budget = 20
        for query in task._problem["experiments"]: task.query("probe_" + query["id"], {})
        safe = [a for a in task._problem["actions"] if task._world in a["success_worlds"]]
        self.assertGreater(len(safe), 1)
        for action in safe:
            clone = copy.deepcopy(task)
            clone.query("commit_" + action["id"], {})
            self.assertTrue(clone.evaluate(completion_for_history(
                clone._problem, clone.commit_observations, action["id"])).success)

    def test_clone_rejects_fault_sets_outside_declared_model(self):
        task = RobustSensingTask(59, "train", 1)
        for world, faults in (("missing", []), (task._world, ["q00", "q00"]),
                              (task._world, ["q00", "q01"]), (task._world, ["bad"])):
            with self.assertRaises(ValueError): task.clone_for_case(world, faults)

    def test_trace_contains_public_data_and_no_private_result_until_evaluation(self):
        task = RobustSensingTask(61, "train", 1, 1)
        session = Session(task)
        fill = solve_robust_sensing(session.public(), session.call)
        response = finish(session, fill)
        self.assertEqual(set(response), {"accepted", "episode_closed", "event_id", "cost_used"})
        self.assertNotIn("assigned_corruptions", json.dumps(session.trace))
        self.assertTrue(session.result["success"])


if __name__ == "__main__":
    unittest.main()
