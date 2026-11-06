"""Behavioral claims for the finite noisy decision-sufficiency certificate."""
import copy
import unittest

from causalfill.decision_sufficiency import (build_certificate, demo_problem,
    problem_digest, replay_certificate, validate_problem, verify_certificate)


class DecisionSufficiencyTests(unittest.TestCase):
    def test_decision_does_not_require_identifying_irrelevant_surface(self):
        model = demo_problem()
        decision = build_certificate(model)
        identification = build_certificate(model, "identification")
        self.assertEqual(decision["value"], 1)
        self.assertEqual(identification["value"], 4)
        for cert in (decision, identification):
            self.assertTrue(verify_certificate(model, cert)["valid"])
            replay = replay_certificate(model, cert)
            self.assertTrue(replay["valid"])
            self.assertEqual(replay["worst_cost"], cert["value"])

    def test_robust_action_needs_no_observation(self):
        model = demo_problem("robust")
        cert = build_certificate(model)
        self.assertEqual(cert["value"], 0)
        self.assertEqual(len(cert["nodes"]), 1)
        self.assertTrue(replay_certificate(model, cert)["valid"])

    def test_overlap_prevents_universal_guarantee(self):
        model = demo_problem("ambiguous")
        cert = build_certificate(model)
        checked = verify_certificate(model, cert)
        self.assertTrue(checked["valid"])
        self.assertIsNone(cert["value"])
        self.assertFalse(checked["guaranteed"])
        self.assertFalse(replay_certificate(model, cert)["valid"])

    def test_disjoint_supports_resolve_noisy_sensor(self):
        model = demo_problem("noisy_resolvable")
        cert = build_certificate(model)
        self.assertEqual(cert["value"], 2)
        self.assertTrue(verify_certificate(model, cert)["valid"])
        self.assertTrue(replay_certificate(model, cert)["valid"])

    def test_conditional_expensive_probe_cost(self):
        model = demo_problem("adaptive")
        cert = build_certificate(model)
        self.assertEqual(cert["value"], 3)
        self.assertTrue(replay_certificate(model, cert)["valid"])

    def test_success_can_be_guaranteed_when_full_identity_is_unobservable(self):
        model = demo_problem("action_ambiguity")
        action = build_certificate(model, "action")
        identify = build_certificate(model, "identification")
        self.assertEqual(action["value"], 1)
        self.assertIsNone(identify["value"])
        self.assertTrue(verify_certificate(model, identify)["valid"])
        replay = replay_certificate(model, action)
        self.assertTrue(replay["valid"])
        self.assertEqual(replay["supported_policy_leaves"], 4)

    def test_infeasible_world_and_no_experiments(self):
        model = demo_problem()
        model["experiments"] = []
        cert = build_certificate(model)
        self.assertIsNone(cert["value"])
        self.assertTrue(verify_certificate(model, cert)["valid"])
        model["actions"][0]["success_worlds"] = model["worlds"]
        model["actions"][0]["cost"] = 7
        cert = build_certificate(model)
        self.assertEqual(cert["value"], 7)
        self.assertTrue(verify_certificate(model, cert)["valid"])

    def test_selected_policy_does_not_replace_lower_bound_check(self):
        model = demo_problem()
        cert = build_certificate(model)
        missing = copy.deepcopy(cert)
        root = tuple(cert["root"])
        selected = {tuple(root)}
        # Removing any checked non-root subproblem must be rejected: all
        # alternatives, not only the chosen camera, contribute to the bound.
        self.assertGreater(len(cert["nodes"]), 4)
        for index, row in enumerate(cert["nodes"]):
            if tuple(row[:2]) == root:
                continue
            forged = copy.deepcopy(cert)
            del forged["nodes"][index]
            self.assertFalse(verify_certificate(model, forged)["valid"])

    def test_value_and_problem_binding_forgery_rejected(self):
        model = demo_problem()
        cert = build_certificate(model)
        forged = copy.deepcopy(cert)
        forged["value"] = 0
        self.assertFalse(verify_certificate(model, forged)["valid"])
        forged = copy.deepcopy(cert)
        forged["problem_sha256"] = "0" * 64
        self.assertFalse(verify_certificate(model, forged)["valid"])
        changed = copy.deepcopy(model)
        changed["experiments"][0]["cost"] += 1
        self.assertNotEqual(problem_digest(model), problem_digest(changed))
        self.assertFalse(verify_certificate(changed, cert)["valid"])

    def test_boolean_numbers_and_duplicate_supports_rejected(self):
        model = demo_problem()
        for path in ("action", "experiment", "support"):
            bad = copy.deepcopy(model)
            if path == "action":
                bad["actions"][0]["cost"] = True
            elif path == "experiment":
                bad["experiments"][0]["cost"] = False
            else:
                bad["experiments"][0]["supports"][model["worlds"][0]] = ["left", "left"]
            with self.assertRaises(ValueError):
                validate_problem(bad)
        cert = build_certificate(model)
        for field in ("value", "root", "node"):
            bad = copy.deepcopy(cert)
            if field == "value": bad["value"] = True
            elif field == "root": bad["root"][0] = True
            else: bad["nodes"][0][2] = False
            self.assertFalse(verify_certificate(model, bad)["valid"])

    def test_noisy_overlap_can_leave_belief_unchanged_and_still_terminate(self):
        model = demo_problem("ambiguous")
        model["actions"].append({"id": "expensive_bypass", "cost": 9,
                                  "success_worlds": model["worlds"]})
        cert = build_certificate(model)
        self.assertEqual(cert["value"], 9)
        self.assertTrue(verify_certificate(model, cert)["valid"])
        self.assertTrue(replay_certificate(model, cert)["valid"])


if __name__ == "__main__":
    unittest.main()
