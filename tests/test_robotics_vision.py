"""Behavioral tests for the pixel-to-action simulator and public policies."""
from copy import deepcopy
import json
import unittest

from causalfill.domains.robotics_vision import RoboticsVisionTask, physical_outcome
from causalfill.robotics_vision_policy import recover_open_route, solve_robotics_vision
from causalfill.session import Session
from causalfill.vision import decode_envelope


def snapshot(task):
    state = deepcopy({key: value for key, value in task.__dict__.items() if key != "rng"})
    state["rng_state"] = task.rng.getstate()
    return state


class RoboticsVisionTests(unittest.TestCase):
    def run_policy(self, task, mode="adaptive"):
        session = Session(task)
        fill = solve_robotics_vision(session.public(), session.call, mode)
        return task.evaluate(fill), session

    def test_public_twins_and_preobservation_are_identical(self):
        for seed in (0, 1, 2, 3):
            a, b = [RoboticsVisionTask(seed, "transfer", 3, twin) for twin in (0, 1)]
            self.assertEqual(a.public(), b.public())
            self.assertEqual(a.files, b.files)
            self.assertEqual(a.query("robot_capture", {}), b.query("robot_capture", {}))
            self.assertEqual(a.query("robot_move_camera", {"view": "inspection"}),
                             b.query("robot_move_camera", {"view": "inspection"}))
            first = a.query("robot_capture", {})
            second = b.query("robot_capture", {})
            if a.twin_kind == "gate_lane":
                self.assertNotEqual(first["image"], second["image"])
                self.assertEqual(a._initial_friction, b._initial_friction)
            else:
                self.assertEqual(first, second)
                self.assertEqual(a._open_route, b._open_route)
                self.assertNotEqual(a._initial_friction, b._initial_friction)

    def test_actual_png_fixed_noise_and_no_annotation_keys(self):
        task = RoboticsVisionTask(2, "transfer", 3)
        first = task.query("robot_capture", {})
        repeat = task.query("robot_capture", {})
        self.assertEqual(first["image"], repeat["image"])
        self.assertEqual(set(first), {"view", "image", "resources"})
        self.assertEqual(set(first["image"]), {"mime_type", "width", "height", "png_base64", "sha256"})
        w, h, rgb = decode_envelope(first["image"])
        self.assertEqual((w, h, len(rgb)), (192, 192, 192*192*3))
        self.assertEqual(task.elapsed, 2)
        self.assertEqual(task.observation_cost, 6)

    def test_calibrated_pose_and_policies_across_split_noise_twins(self):
        for split in ("train", "dev", "transfer"):
            for difficulty in (1, 2, 3):
                for twin in (0, 1):
                    task = RoboticsVisionTask(2, split, difficulty, twin)
                    spec = json.loads(task.files["/scene/robotics_vision.json"])
                    route, support = recover_open_route(spec, task.image("inspection"))
                    self.assertEqual(route, task._open_route)
                    true_y = 26 if route == "upper" else 54
                    self.assertLessEqual(abs(support["estimated_center_world"][0]-60), 1.0)
                    self.assertLessEqual(abs(support["estimated_center_world"][1]-true_y), 1.0)
                    with self.assertRaises(ValueError):
                        recover_open_route(spec, task.image("overview"))
                    for mode in ("adaptive", "fixed", "fixed_minimal", "conditioning"):
                        fresh = RoboticsVisionTask(2, split, difficulty, twin)
                        verdict, session = self.run_policy(fresh, mode)
                        expected = mode != "conditioning" or fresh.contact_profile == "conditionable"
                        self.assertEqual(verdict.success, expected, (split, difficulty, twin, mode, verdict.details))
                        self.assertLessEqual(session.cost, fresh.budget)
                        self.assertEqual(fresh.elapsed, 16 if not expected else 10 if mode == "fixed" else 9)
                        self.assertFalse(verdict.details["collision"])
                        self.assertFalse(verdict.details["slip"])

    def test_relaxed_robust_route_needs_no_observation(self):
        for seed in (0, 3):
            for twin in (0, 1):
                task = RoboticsVisionTask(seed, "transfer", 3, twin)
                verdict, session = self.run_policy(task)
                self.assertTrue(verdict.success)
                self.assertEqual(verdict.details["observations"], 0)
                self.assertEqual(verdict.details["observation_cost"], 0)
                self.assertEqual(task.elapsed, 18)
                self.assertEqual(task.action, {"route": "detour", "mode": "slow"})
                self.assertEqual(session.cost, 3)
        task = RoboticsVisionTask(1)
        verdict, _ = self.run_policy(task, "robust")
        self.assertFalse(verdict.success)
        self.assertTrue(verdict.details["deadline_exceeded"])
        self.assertFalse(verdict.details["collision"])

    def test_strict_initial_terminal_action_sets_are_disjoint(self):
        actions = [(route, mode) for route in ("upper", "lower") for mode in ("roll", "grip", "slow")]
        actions.append(("detour", "slow"))
        for seed in (1, 2, 4, 5):
            successful = []
            for twin in (0, 1):
                accepted = set()
                for route, mode in actions:
                    task = RoboticsVisionTask(seed, "dev", 2, twin)
                    task.query("robot_execute", {"route": route, "mode": mode})
                    if task.evaluate({"delivered": True}).success:
                        accepted.add((route, mode))
                self.assertTrue(accepted)
                successful.append(accepted)
            self.assertFalse(successful[0] & successful[1], (seed, successful))

    def test_invalid_actions_are_atomic_including_terminal_phase(self):
        malformed = [
            ("robot_move_camera", {}), ("robot_move_camera", {"view": True}),
            ("robot_move_camera", {"view": float("nan")}),
            ("robot_move_camera", {"view": "inspection", "extra": 1}),
            ("robot_capture", {"extra": 1}), ("robot_capture", False),
            ("robot_probe", {"force": 1}), ("robot_probe", {"force": "hard"}),
            ("robot_probe", {"force": float("inf")}),
            ("robot_execute", {"route": "detour", "mode": "roll"}),
            ("robot_execute", {"route": "upper", "mode": True}),
            ("robot_execute", {"route": [], "mode": "slow"}),
            ("robot_execute", {"route": "upper", "mode": "slow", "extra": 1}),
            ("unknown", {}),
        ]
        task = RoboticsVisionTask(1)
        for name, args in malformed:
            before = snapshot(task)
            with self.assertRaises((ValueError, TypeError)):
                task.query(name, args)
            self.assertEqual(snapshot(task), before, (name, args))
        task.query("robot_execute", {"route": "detour", "mode": "slow"})
        for name, args in [("robot_capture", {}), ("robot_probe", {"force": "gentle"}),
                           ("robot_move_camera", {"view": "inspection"}),
                           ("robot_execute", {"route": "detour", "mode": "slow"})]:
            before = snapshot(task)
            with self.assertRaises(ValueError):
                task.query(name, args)
            self.assertEqual(snapshot(task), before)

    def test_session_invalid_cost_does_not_mutate_physics(self):
        task = RoboticsVisionTask(1)
        session = Session(task)
        before = task.resources()
        result = session.call("robot_probe", {"force": True})
        self.assertIn("error", result)
        self.assertEqual(task.resources(), before)
        self.assertEqual(session.cost, 4)
        self.assertEqual(session.invalid, 1)

    def test_probe_interval_encloses_post_wear_and_bias_is_correlated(self):
        for twin in (0, 1):
            task = RoboticsVisionTask(1, twin=twin)
            biases = []
            for force in ("gentle", "firm", "gentle"):
                before_wear = task.wear
                measurement = task.query("robot_probe", {"force": force})
                low, high = measurement["friction_interval"]
                self.assertLessEqual(low, task.friction)
                self.assertGreaterEqual(high, task.friction)
                self.assertEqual(task.wear-before_wear, 1 if force == "gentle" else 2)
                biases.append((low+high)/2-task.friction)
            self.assertLess(max(biases)-min(biases), 1e-12)
            self.assertEqual(task.elapsed, 6)
            self.assertEqual(task.energy_used, 4)

    def test_firm_probe_conditions_both_regimes_without_reading(self):
        for twin in (0, 1):
            task = RoboticsVisionTask(1, "transfer", 3, twin)
            session = Session(task)
            def corrupt_numeric_probe(name, args):
                response = session.call(name, args)
                if name == "robot_probe":
                    response["friction_interval"] = [999, 999]
                return response
            fill = solve_robotics_vision(session.public(), corrupt_numeric_probe, "conditioning")
            self.assertTrue(task.evaluate(fill).success)
            self.assertLessEqual(task.friction, 0.45)
            self.assertEqual(task.wear, 2)
            self.assertEqual(task.energy_used, 8)

    def test_conditioning_grip_control_exposes_resistant_stalls(self):
        for seed in (1, 7):
            outcomes = []
            for twin in (0, 1):
                task = RoboticsVisionTask(seed, "transfer", 3, twin)
                verdict, session = self.run_policy(task, "conditioning_grip")
                outcomes.append(verdict.success)
                self.assertEqual(task.action["mode"], "grip")
                self.assertEqual(task.elapsed, 9)
                self.assertFalse(verdict.details["collision"])
                self.assertFalse(verdict.details["slip"])
                self.assertEqual(verdict.details["stalled"], not verdict.success)
            self.assertEqual(sum(outcomes), 2 if seed == 1 else 1)

    def test_probe_can_change_a_previously_safe_rolling_action(self):
        # Locate a dry world without altering the generator or public interface.
        task = next(RoboticsVisionTask(seed) for seed in range(20)
                    if RoboticsVisionTask(seed)._initial_friction == 0.65)
        before = physical_outcome(task._open_route, task.friction, task._open_route, "roll", 5, 5, 26, 14)
        self.assertTrue(before["completed"])
        task.query("robot_probe", {"force": "firm"})
        task.query("robot_probe", {"force": "gentle"})
        after = physical_outcome(task._open_route, task.friction, task._open_route, "roll", 9, 8, 26, 14)
        self.assertTrue(after["slip"])
        self.assertFalse(after["completed"])

    def test_completion_requires_execution_and_oracle_answer_is_pure(self):
        task = RoboticsVisionTask(1)
        before = snapshot(task)
        self.assertEqual(task.reference_answer(), {"delivered": True})
        self.assertEqual(snapshot(task), before)
        self.assertFalse(task.evaluate({"delivered": True}).success)
        self.assertFalse(task.evaluate({"delivered": 1}).success)
        session = Session(task)
        for name, args in task.reference_actions():
            self.assertNotIn("error", session.call(name, args))
        self.assertTrue(task.evaluate(task.reference_answer()).success)
        self.assertEqual(session.cost, 11)
        self.assertEqual(task.primitive_steps, 4)

    def test_ground_truth_boundaries_and_independent_failure_flags(self):
        args = ("upper", 3.0/9.81, "upper", "roll", 10, 14, 10, 14)
        self.assertTrue(physical_outcome(*args)["completed"])
        self.assertTrue(physical_outcome("upper", 0.45, "upper", "grip", 10, 14, 10, 14)["completed"])
        self.assertTrue(physical_outcome("upper", 0.65, "upper", "grip", 5, 5, 10, 14)["stalled"])
        out = physical_outcome("upper", 0.25, "lower", "roll", 11, 15, 10, 14)
        self.assertTrue(all(out[k] for k in ("collision", "slip", "deadline_exceeded", "energy_exceeded")))


if __name__ == "__main__":
    unittest.main()
