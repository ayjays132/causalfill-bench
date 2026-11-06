"""Finite robust decision claims, independent analytic fixtures and forgeries."""
import copy
import itertools
import json
import random
import unittest
from unittest.mock import patch

import causalfill.robust_decisions as robust
from causalfill.decision_sufficiency import build_certificate as build_support_certificate
from causalfill.decision_sufficiency import SCHEMA as SUPPORT_SCHEMA


def repeated_bit(repetitions=3, faults=1, query_costs=None, action_cost=0):
    if query_costs is None:
        query_costs = [1] * repetitions
    return {"schema": robust.SCHEMA, "worlds": ["zero", "one"], "max_corruptions": faults,
            "actions": [{"id": "choose_zero", "cost": action_cost, "success_worlds": ["zero"]},
                        {"id": "choose_one", "cost": action_cost, "success_worlds": ["one"]}],
            "experiments": [{"id": f"q{i}", "cost": cost, "responses": {"zero": 0, "one": 1}}
                            for i, cost in enumerate(query_costs)]}


def exclude_pattern(bits=3, faults=1, costs=None, action_cost=0, duplicate_nuisance=False):
    """Independent family: k+1 coordinates suffice to exclude one complete pattern.

    Each action fails in exactly its named bit pattern, so identifying the true
    world is unnecessary. Up to k observations leave every world possible. With
    k+1 observations, the opposite observed pattern requires too many faults.
    """
    if costs is None:
        costs = [1] * bits
    patterns = list(itertools.product((0, 1), repeat=bits))
    copies = 2 if duplicate_nuisance else 1
    worlds = [f"w{i}_{j}" for i in range(len(patterns)) for j in range(copies)]
    labels = {f"w{i}_{j}": pattern for i, pattern in enumerate(patterns) for j in range(copies)}
    actions = [{"id": f"exclude_{i}", "cost": action_cost,
                "success_worlds": [w for w in worlds if labels[w] != pattern]}
               for i, pattern in enumerate(patterns)]
    return {"schema": robust.SCHEMA, "worlds": worlds, "max_corruptions": faults,
            "actions": actions, "experiments": [
                {"id": f"bit{i}", "cost": costs[i], "responses": {w: labels[w][i] for w in worlds}}
                for i in range(bits)]}


def simplex_problem(faults=1):
    worlds = [f"w{i}" for i in range(8)]
    return {"schema": robust.SCHEMA, "worlds": worlds, "max_corruptions": faults,
            "actions": [{"id": f"exclude_low_{j}", "cost": 0,
                         "success_worlds": [w for i, w in enumerate(worlds) if i & 3 != j]}
                        for j in range(4)],
            "experiments": [{"id": f"p{mask}", "cost": 1,
                             "responses": {w: (i & mask).bit_count() % 2 for i, w in enumerate(worlds)}}
                            for mask in range(1, 8)]}


class RobustDecisionTests(unittest.TestCase):
    def checked(self, problem, objective="action"):
        certificate = robust.build_robust_certificate(problem, objective)
        checked = robust.verify_robust_certificate(problem, certificate, expected_objective=objective)
        self.assertTrue(checked["valid"], checked)
        if certificate["value"] is not None:
            policy = robust.extract_robust_policy(problem, certificate)
            replay = robust.verify_robust_policy(problem, policy, expected_objective=objective)
            self.assertTrue(replay["valid"], replay)
            self.assertEqual(replay["worst_cost"], certificate["value"])
        return certificate

    def test_three_once_only_readings_correct_one_global_flip(self):
        model = repeated_bit()
        certificate = self.checked(model)
        self.assertEqual(certificate["value"], 3)
        policy = robust.extract_robust_policy(model, certificate)
        replay = robust.verify_robust_policy(model, policy)
        self.assertEqual(replay["worlds_checked"], 2)
        self.assertEqual(replay["best_cost"], 2)
        self.assertEqual(replay["worst_cost"], 3)
        self.assertEqual(replay["corruption_histories_checked"], 6)

    def test_two_readings_cannot_guarantee_a_binary_decision_with_one_flip(self):
        certificate = self.checked(repeated_bit(2))
        self.assertIsNone(certificate["value"])
        with self.assertRaisesRegex(ValueError, "no verified finite"):
            robust.extract_robust_policy(repeated_bit(2), certificate)

    def test_five_readings_correct_two_global_flips(self):
        certificate = self.checked(repeated_bit(5, faults=2, action_cost=2))
        self.assertEqual(certificate["value"], 7)
        self.assertIsNone(self.checked(repeated_bit(4, faults=2))["value"])

    def test_action_cost_is_included_and_identification_is_different(self):
        model = repeated_bit(query_costs=[4, 1, 2], action_cost=5)
        self.assertEqual(self.checked(model)["value"], 12)
        self.assertEqual(self.checked(model, "identification")["value"], 7)

    def test_independent_full_cube_exclusion_formula(self):
        # Formula is terminal cost plus the k+1 cheapest coordinate costs.
        for bits, faults, costs, terminal in [
                (1, 0, [3], 2), (2, 1, [5, 2], 3),
                (3, 1, [8, 1, 4], 2), (4, 2, [9, 1, 7, 3], 5)]:
            with self.subTest(bits=bits, faults=faults):
                model = exclude_pattern(bits, faults, costs, terminal)
                self.assertEqual(self.checked(model)["value"], terminal + sum(sorted(costs)[:faults+1]))

    def test_action_can_succeed_when_identification_is_impossible(self):
        model = exclude_pattern(2, 1)
        self.assertEqual(self.checked(model)["value"], 2)
        self.assertIsNone(self.checked(model, "identification")["value"])
        # Repeated nuisance labels do not force full hidden-state recovery.
        nuisance = exclude_pattern(2, 1, duplicate_nuisance=True)
        self.assertEqual(self.checked(nuisance)["value"], 2)
        self.assertIsNone(self.checked(nuisance, "identification")["value"])

    def test_fault_budget_at_least_number_of_bits_prevents_exclusion(self):
        self.assertIsNone(self.checked(exclude_pattern(2, 2))["value"])

    def test_simplex_anchor_has_separate_action_and_identification_costs(self):
        # With one lie, five binary queries cannot identify 8 worlds:
        # 8*(1+5) > 2**5. Any six simplex coordinates retain distance >=3.
        model = simplex_problem(1)
        self.assertEqual(self.checked(model)["value"], 2)
        self.assertEqual(self.checked(model, "identification")["value"], 6)
        noiseless = simplex_problem(0)
        self.assertEqual(self.checked(noiseless)["value"], 1)
        self.assertEqual(self.checked(noiseless, "identification")["value"], 3)

    def test_positive_cost_robust_bypass_competes_with_sensing(self):
        model = exclude_pattern(3, 1, [3, 4, 7], action_cost=2)
        model["actions"].append({"id": "bypass", "cost": 5, "success_worlds": model["worlds"][:]})
        certificate = self.checked(model)
        self.assertEqual(certificate["value"], 5)
        policy = robust.extract_robust_policy(model, certificate)
        self.assertEqual(policy["nodes"], [{"kind": "act", "id": "bypass"}])

    def test_zero_cost_robust_action_is_valid_without_queries(self):
        model = repeated_bit()
        model["actions"].append({"id": "bypass", "cost": 0, "success_worlds": model["worlds"][:]})
        certificate = self.checked(model)
        self.assertEqual(certificate["value"], 0)
        self.assertEqual(len(certificate["nodes"]), 1)

    def test_empty_query_or_action_collections_have_explicit_semantics(self):
        model = repeated_bit(0)
        self.assertIsNone(self.checked(model)["value"])
        model["actions"] = [{"id": "bypass", "cost": 7, "success_worlds": model["worlds"][:]}]
        self.assertEqual(self.checked(model)["value"], 7)
        self.assertIsNone(self.checked(model, "identification")["value"])
        model["worlds"] = ["zero"]
        model["actions"] = []
        self.assertIsNone(self.checked(model)["value"])
        self.assertEqual(self.checked(model, "identification")["value"], 0)

    def test_shared_fault_budget_is_not_independent_sensor_support(self):
        model = repeated_bit()
        independent = {"schema": SUPPORT_SCHEMA, "worlds": model["worlds"],
                       "actions": model["actions"], "experiments": [
                           {"id": q["id"], "cost": q["cost"],
                            "supports": {w: ["0", "1"] for w in model["worlds"]}}
                           for q in model["experiments"]]}
        self.assertEqual(self.checked(model)["value"], 3)
        self.assertIsNone(build_support_certificate(independent)["value"])

    def test_no_fault_objectives_match_existing_singleton_support_semantics(self):
        rng = random.Random(20817)
        for case in range(12):
            worlds = [f"w{i}" for i in range(4)]
            model = {"schema": robust.SCHEMA, "worlds": worlds, "max_corruptions": 0,
                     "actions": [{"id": f"a{i}", "cost": rng.randrange(4),
                                  "success_worlds": [w for w in worlds if rng.randrange(2)]}
                                 for i in range(4)],
                     "experiments": [{"id": f"q{i}", "cost": rng.randrange(1, 5),
                                      "responses": {w: rng.randrange(2) for w in worlds}}
                                     for i in range(4)]}
            other = {"schema": SUPPORT_SCHEMA, "worlds": worlds, "actions": model["actions"],
                     "experiments": [{"id": q["id"], "cost": q["cost"],
                                      "supports": {w: [str(value)] for w, value in q["responses"].items()}}
                                     for q in model["experiments"]]}
            for objective in ("action", "identification"):
                with self.subTest(case=case, objective=objective):
                    self.assertEqual(self.checked(model, objective)["value"],
                                     build_support_certificate(other, objective)["value"])

    def test_first_conflict_does_not_discard_a_world_under_one_fault(self):
        model = repeated_bit()
        seen = [{"experiment": "q0", "outcome": 1}]
        state = robust.evidence_state(model, seen)
        self.assertEqual(state["mismatch_counts"], {"zero": 1, "one": 0})
        self.assertEqual(state["possible_worlds"], ["zero", "one"])
        self.assertFalse(robust.verify_completion_evidence(model, seen, "choose_one")["valid"])

    def test_observed_exclusion_witnesses_accept_a_corrupted_reading(self):
        model = repeated_bit(action_cost=2)
        seen = [{"experiment": "q0", "outcome": 1}, {"experiment": "q1", "outcome": 0},
                {"experiment": "q2", "outcome": 0}]
        state = robust.evidence_state(model, seen)
        self.assertEqual(state["possible_worlds"], ["zero"])
        self.assertEqual(state["mismatch_counts"], {"zero": 1, "one": 2})
        witnesses = robust.completion_exclusions(model, seen, "choose_zero")
        self.assertEqual(witnesses, [{"world": "one", "conflicts": ["q1", "q2"]}])
        checked = robust.verify_completion_evidence(model, seen, "choose_zero", witnesses)
        self.assertTrue(checked["valid"], checked)
        self.assertTrue(checked["witnesses_checked"])
        self.assertEqual(checked["total_cost"], 5)

    def test_witnesses_must_be_distinct_actual_contradictions_and_cover_unsafe_worlds(self):
        model = repeated_bit()
        seen = [{"experiment": "q0", "outcome": 1}, {"experiment": "q1", "outcome": 0},
                {"experiment": "q2", "outcome": 0}]
        for witnesses in [[], [{"world": "one", "conflicts": ["q1"]}],
                          [{"world": "one", "conflicts": ["q1", "q1"]}],
                          [{"world": "one", "conflicts": ["q0", "q1"]}],
                          [{"world": "one", "conflicts": ["q1", "invented"]}],
                          [{"world": "zero", "conflicts": ["q1", "q2"]}]]:
            with self.subTest(witnesses=witnesses):
                self.assertFalse(robust.verify_completion_evidence(model, seen, "choose_zero", witnesses)["valid"])

    def test_shared_success_worlds_need_no_fabricated_identification_witness(self):
        model = exclude_pattern(2, 1)
        seen = [{"experiment": "bit0", "outcome": 0}, {"experiment": "bit1", "outcome": 0}]
        witnesses = robust.completion_exclusions(model, seen, "exclude_3")
        self.assertEqual(len(witnesses), 1)
        checked = robust.verify_completion_evidence(model, seen, "exclude_3", witnesses)
        self.assertTrue(checked["valid"], checked)
        self.assertEqual(len(checked["possible_worlds"]), 3)

    def test_empty_feasible_set_never_receives_vacuous_completion_credit(self):
        model = repeated_bit(2, faults=0)
        model["actions"].append({"id": "bypass", "cost": 0, "success_worlds": model["worlds"][:]})
        seen = [{"experiment": "q0", "outcome": 0}, {"experiment": "q1", "outcome": 1}]
        self.assertEqual(robust.evidence_state(model, seen)["possible_worlds"], [])
        self.assertFalse(robust.verify_completion_evidence(model, seen, "bypass", [])["valid"])

    def test_repeated_unknown_and_boolean_observations_are_rejected(self):
        model = repeated_bit()
        for seen in [[{"experiment": "q0", "outcome": 0}] * 2,
                     [{"experiment": "missing", "outcome": 0}],
                     [{"experiment": "q0", "outcome": True}],
                     [{"experiment": "q0", "outcome": 0, "truth": 0}]]:
            with self.subTest(seen=seen), self.assertRaises(ValueError):
                robust.evidence_state(model, seen)

    def test_every_alternative_certificate_state_is_required(self):
        model = repeated_bit()
        certificate = robust.build_robust_certificate(model)
        self.assertGreater(len(certificate["nodes"]), 10)
        for index in range(len(certificate["nodes"])):
            bad = copy.deepcopy(certificate)
            del bad["nodes"][index]
            self.assertFalse(robust.verify_robust_certificate(model, bad)["valid"])

    def test_changed_cost_fault_bound_or_response_breaks_binding(self):
        model = repeated_bit()
        certificate = robust.build_robust_certificate(model)
        policy = robust.extract_robust_policy(model, certificate)
        for field in ("cost", "faults", "response"):
            bad = copy.deepcopy(model)
            if field == "cost": bad["experiments"][0]["cost"] += 1
            elif field == "faults": bad["max_corruptions"] = 0
            else: bad["experiments"][0]["responses"]["zero"] = 1
            self.assertFalse(robust.verify_robust_certificate(bad, certificate)["valid"])
            self.assertFalse(robust.verify_robust_policy(bad, policy)["valid"])

    def test_objective_can_be_pinned_outside_the_claimant_artifact(self):
        model = repeated_bit()
        certificate = robust.build_robust_certificate(model, "identification")
        policy = robust.extract_robust_policy(model, certificate)
        self.assertFalse(robust.verify_robust_certificate(model, certificate, expected_objective="action")["valid"])
        self.assertFalse(robust.verify_robust_policy(model, policy, expected_objective="action")["valid"])
        self.assertTrue(robust.verify_robust_certificate(model, certificate, expected_objective="identification")["valid"])

    def test_wrong_certificate_values_choices_roots_duplicates_and_extra_fields_fail(self):
        model = repeated_bit()
        certificate = robust.build_robust_certificate(model)
        root_index = next(i for i, r in enumerate(certificate["nodes"]) if r[:2] == certificate["root"])
        for mutation in ("summary", "cost", "choice", "counts", "remaining", "duplicate", "schema", "extra"):
            bad = copy.deepcopy(certificate)
            row = bad["nodes"][root_index]
            if mutation == "summary": bad["value"] = 2
            elif mutation == "cost": row[2] = 2
            elif mutation == "choice": row[3] = {"kind": "act", "id": "choose_zero"}
            elif mutation == "counts": bad["root"][0][0] = 1
            elif mutation == "remaining": bad["root"][1] = 0
            elif mutation == "duplicate": bad["nodes"].append(copy.deepcopy(row))
            elif mutation == "schema": bad["schema"] = "other"
            else: bad["claimed_hard"] = True
            with self.subTest(mutation=mutation):
                self.assertFalse(robust.verify_robust_certificate(model, bad)["valid"])

    def test_null_cost_is_impossibility_and_requires_no_choice(self):
        model = repeated_bit(1)
        certificate = robust.build_robust_certificate(model)
        self.assertIsNone(certificate["value"])
        bad = copy.deepcopy(certificate)
        bad["nodes"][0][3] = {"kind": "act", "id": "choose_zero"}
        self.assertFalse(robust.verify_robust_certificate(model, bad)["valid"])

    def test_replay_independently_rejects_a_missing_fault_branch(self):
        model = repeated_bit()
        policy = robust.extract_robust_policy(model, robust.build_robust_certificate(model))
        del policy["nodes"][policy["root"]]["branches"]["1"]
        self.assertFalse(robust.verify_robust_policy(model, policy)["valid"])

    def test_replay_rejects_wrong_action_small_budget_cycles_and_unreachable_nodes(self):
        model = repeated_bit()
        policy = robust.extract_robust_policy(model, robust.build_robust_certificate(model))
        for mutation in ("leaf", "budget", "cycle", "extra"):
            bad = copy.deepcopy(policy)
            if mutation == "leaf":
                leaf = next(n for n in bad["nodes"] if n["kind"] == "act")
                leaf["id"] = "choose_one" if leaf["id"] == "choose_zero" else "choose_zero"
            elif mutation == "budget": bad["budget"] -= 1
            elif mutation == "cycle": bad["nodes"][0]["branches"]["0"] = 0
            else: bad["nodes"].append({"kind": "act", "id": "choose_zero"})
            with self.subTest(mutation=mutation):
                self.assertFalse(robust.verify_robust_policy(model, bad)["valid"])

    def test_policy_check_is_an_upper_bound_not_a_recomputed_optimum(self):
        model = repeated_bit()
        model["actions"].append({"id": "costly_bypass", "cost": 12, "success_worlds": model["worlds"][:]})
        self.assertEqual(self.checked(model)["value"], 3)
        policy = {"schema": robust.POLICY_SCHEMA, "problem_sha256": robust.problem_digest(model),
                  "objective": "action", "budget": 12, "root": 0,
                  "nodes": [{"kind": "act", "id": "costly_bypass"}]}
        checked = robust.verify_robust_policy(model, policy)
        self.assertTrue(checked["valid"], checked)
        self.assertEqual(checked["worst_cost"], 12)

    def test_checker_and_replay_do_not_call_the_optimizer(self):
        model = repeated_bit()
        certificate = robust.build_robust_certificate(model)
        policy = robust.extract_robust_policy(model, certificate)
        with patch.object(robust, "build_robust_certificate", side_effect=AssertionError("optimizer used")):
            self.assertTrue(robust.verify_robust_certificate(model, certificate)["valid"])
            with patch.object(robust, "verify_robust_certificate", side_effect=AssertionError("certificate used")), \
                    patch.object(robust, "evidence_state", side_effect=AssertionError("belief used")):
                self.assertTrue(robust.verify_robust_policy(model, policy)["valid"])

    def test_resource_exhaustion_fails_explicitly_instead_of_claiming_optimality(self):
        model = repeated_bit()
        certificate = robust.build_robust_certificate(model)
        policy = robust.extract_robust_policy(model, certificate)
        with patch.object(robust, "MAX_STATES", 1):
            with self.assertRaisesRegex(ValueError, "no optimum claimed"):
                robust.build_robust_certificate(model)
            self.assertFalse(robust.verify_robust_certificate(model, certificate)["valid"])
        with patch.object(robust, "MAX_REPLAY_STATES", 1):
            checked = robust.verify_robust_policy(model, policy)
            self.assertFalse(checked["valid"])
            self.assertIn("no complete replay claim", checked["error"])
        with patch.object(robust, "MAX_CERTIFICATE_BYTES", 64):
            with self.assertRaisesRegex(ValueError, "byte cap"):
                robust.build_robust_certificate(model)
            self.assertFalse(robust.verify_robust_certificate(model, certificate)["valid"])

    def test_invalid_models_reject_boolean_aliases_duplicates_and_missing_data(self):
        for mutation in ("fault_bool", "response_bool", "query_zero", "action_negative", "cost_bool",
                         "world_duplicate", "query_duplicate", "unknown_success", "success_duplicate",
                         "missing_response", "extra_response", "extra_field", "too_many_faults", "name"):
            bad = repeated_bit()
            if mutation == "fault_bool": bad["max_corruptions"] = True
            elif mutation == "response_bool": bad["experiments"][0]["responses"]["zero"] = False
            elif mutation == "query_zero": bad["experiments"][0]["cost"] = 0
            elif mutation == "action_negative": bad["actions"][0]["cost"] = -1
            elif mutation == "cost_bool": bad["actions"][0]["cost"] = True
            elif mutation == "world_duplicate": bad["worlds"].append("zero")
            elif mutation == "query_duplicate": bad["experiments"][1]["id"] = "q0"
            elif mutation == "unknown_success": bad["actions"][0]["success_worlds"] = ["missing"]
            elif mutation == "success_duplicate": bad["actions"][0]["success_worlds"] = ["zero", "zero"]
            elif mutation == "missing_response": del bad["experiments"][0]["responses"]["zero"]
            elif mutation == "extra_response": bad["experiments"][0]["responses"]["missing"] = 0
            elif mutation == "extra_field": bad["actual_world"] = "zero"
            elif mutation == "too_many_faults": bad["max_corruptions"] = 3
            else: bad["actions"][0]["id"] = "a" * 65
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                robust.validate_problem(bad)

    def test_boolean_aliases_in_certificate_and_policy_fields_fail(self):
        model = repeated_bit()
        certificate = robust.build_robust_certificate(model)
        policy = robust.extract_robust_policy(model, certificate)
        for mutation in ("root_count", "root_mask", "value", "node_count", "node_mask"):
            bad = copy.deepcopy(certificate)
            if mutation == "root_count": bad["root"][0][0] = False
            elif mutation == "root_mask": bad["root"][1] = True
            elif mutation == "value": bad["value"] = True
            elif mutation == "node_count": bad["nodes"][0][0][0] = False
            else: bad["nodes"][0][1] = False
            self.assertFalse(robust.verify_robust_certificate(model, bad)["valid"])
        for mutation in ("root", "budget", "child"):
            bad = copy.deepcopy(policy)
            if mutation == "child": bad["nodes"][0]["branches"]["0"] = True
            else: bad[mutation] = False
            self.assertFalse(robust.verify_robust_policy(model, bad)["valid"])

    def test_normalization_is_fresh_and_does_not_change_input(self):
        model = repeated_bit()
        before = copy.deepcopy(model)
        normalized = robust.validate_problem(model)
        normalized["experiments"][0]["responses"]["zero"] = 1
        self.assertEqual(model, before)
        self.assertEqual(robust.problem_digest(model), robust.problem_digest(copy.deepcopy(model)))

    def test_strict_json_rejects_duplicate_nonfinite_float_deep_and_oversized_inputs(self):
        value = repeated_bit()
        self.assertEqual(robust.load_robust_json(json.dumps(value).encode()), value)
        for raw in (b'{"x":0,"x":1}', b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1.0}',
                    b'{"x":1e999}', b'{"x":123456789012345678901}', b'\xff',
                    b'[' * 40 + b'0' + b']' * 40):
            with self.subTest(raw=raw[:32]), self.assertRaises(ValueError):
                robust.load_robust_json(raw)
        with self.assertRaises(ValueError):
            robust.load_robust_json(b'"1234567890"', max_bytes=5)


if __name__ == "__main__":
    unittest.main()
