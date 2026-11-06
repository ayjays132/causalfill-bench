"""Route-sensing necessity, independent witnesses, and legal-plan regressions."""
from copy import deepcopy
import json
import math
import unittest
from unittest.mock import patch

from causalfill.domains.robotics import RoboticsTask
from causalfill.domains.robotics_barrier import (
    PROFILE_VERSION, RoboticsBarrierTask, build_barrier_pair_certificate,
    solve_robotics_barrier_from_observations, verify_barrier_certificate,
)
from causalfill.session import Session
from causalfill.types import digest


class BarrierTests(unittest.TestCase):
    def test_shared_public_files_cameras_and_single_changed_parameter(self):
        for split in ("train", "dev", "transfer"):
            for difficulty in (1, 2, 3):
                first, second = [RoboticsBarrierTask(42, split, difficulty, twin) for twin in (0, 1)]
                self.assertEqual(first.public(), second.public())
                self.assertEqual(first.files, second.files)
                self.assertEqual(first._target, second._target)
                for view in ("xy", "xz", "yz"):
                    self.assertEqual(first.query("camera", {"view": view}), second.query("camera", {"view": view}))
                low = first.query("lidar", {})["occupied_boxes"][0]
                high = second.query("lidar", {})["occupied_boxes"][0]
                shift = high["lower"][1]-low["lower"][1]
                self.assertGreater(shift, 0)
                self.assertEqual(high["upper"][1]-low["upper"][1], shift)
                for corner in ("lower", "upper"):
                    for axis in (0, 2):
                        self.assertEqual(low[corner][axis], high[corner][axis])
                self.assertEqual(low["lower"][1], 0)
                self.assertEqual(high["upper"][1], 12)

    def test_generated_matrix_has_two_valid_incompatible_routes_and_certificates(self):
        shapes = set()
        for split in ("train", "dev", "transfer"):
            for difficulty in (1, 2, 3):
                for seed in (0, 1, 2, 17, 101, 27001, 2**63-1):
                    with self.subTest(split=split, difficulty=difficulty, seed=seed):
                        first, second = [RoboticsBarrierTask(seed, split, difficulty, twin) for twin in (0, 1)]
                        artifact = build_barrier_pair_certificate(first, second)
                        checked = verify_barrier_certificate(artifact["statement"], artifact["certificate"])
                        self.assertTrue(checked["valid"], checked)
                        a, b = artifact["certificate"]["routes"]
                        self.assertTrue(first.evaluate(a).success)
                        self.assertTrue(second.evaluate(b).success)
                        self.assertFalse(first.evaluate(b).success)
                        self.assertFalse(second.evaluate(a).success)
                        self.assertFalse(first.evaluate(b).details["path_clear"])
                        self.assertFalse(second.evaluate(a).details["path_clear"])
                        wall = first.query("lidar", {})["occupied_boxes"][0]
                        shapes.add(tuple(wall["lower"]+wall["upper"]))
        self.assertGreater(len(shapes), 10)

    def test_original_height_ten_shortcut_cannot_solve_both_twins(self):
        for seed in range(12):
            first, second = [RoboticsBarrierTask(seed, "transfer", 3, twin) for twin in (0, 1)]
            answer = first.reference_answer()
            target = answer["target_world_position"]
            answer["safe_waypoints"] = [[1, 1, 10], [target[0], target[1], 10]]
            answer["grasp_precondition"]["force_limit_n"] = 0.5
            self.assertFalse(first.evaluate(answer).success)
            self.assertFalse(first.evaluate(answer).success and second.evaluate(answer).success)

    def test_camera_target_reconstruction_is_still_required(self):
        task = RoboticsBarrierTask(23, "transfer", 3)
        workspace = json.loads(task.files["/scene/workspace.json"])
        readings = [task.query("camera", {"view": view}) for view in workspace["camera_views"]]
        lidar = task.query("lidar", {})
        for reading in readings:
            reading["objects"] = [obj for obj in reading["objects"] if obj["id"] != workspace["target_id"]]
        with self.assertRaises(ValueError):
            solve_robotics_barrier_from_observations(workspace, readings, lidar)
        answer = task.reference_answer()
        answer["target_world_position"][0] += 0.01
        self.assertFalse(task.evaluate(answer).success)
        self.assertFalse(task.evaluate(answer).details["state_match"])

    def test_public_callback_solver_fits_budget_and_does_not_mutate_evidence(self):
        for twin in (0, 1):
            task = RoboticsBarrierTask(71, "transfer", 3, twin)
            session = Session(task)
            file = session.call("read_file", {"path": "/scene/workspace.json"})
            workspace = json.loads(file["content"])
            cameras = [session.call("camera", {"view": view}) for view in workspace["camera_views"]]
            lidar = session.call("lidar", {})
            evidence = deepcopy((workspace, cameras, lidar))
            # The solver accepts public responses including Session metadata.
            fill = solve_robotics_barrier_from_observations(workspace, cameras, lidar)
            self.assertEqual((workspace, cameras, lidar), evidence)
            session.call("submit", {"fill": fill, "confidence": 1.0, "abstain": False,
                                     "evidence": [file["event_id"], lidar["event_id"]]})
            self.assertTrue(session.result["success"], session.result)
            self.assertEqual(session.cost, 13)
            self.assertEqual(session.calls, 5)

    def test_geometry_probe_can_distinguish_worlds_without_lidar(self):
        first, second = [RoboticsBarrierTask(99, "dev", 2, twin) for twin in (0, 1)]
        fill = first.reference_answer()
        args = {key: fill[key] for key in ("target_world_position", "safe_waypoints")}
        self.assertTrue(first.query("probe_path", args)["collision_free"])
        self.assertFalse(second.query("probe_path", args)["collision_free"])

    def test_certificate_is_deterministic_from_either_twin_and_not_public_tool(self):
        first, second = [RoboticsBarrierTask(67, "train", 1, twin) for twin in (0, 1)]
        self.assertEqual(first.separation_certificate(), second.separation_certificate())
        self.assertEqual(set(first.tools), {"camera", "lidar", "probe_path"})
        workspace = json.loads(first.files["/scene/workspace.json"])
        self.assertEqual(workspace["profile_version"], PROFILE_VERSION)
        for private in ("seed", "twin", "wall_y_offset", "target_world_position", "occupied_boxes", "certificate"):
            self.assertNotIn(private, workspace)
            self.assertNotIn(private, first.public())
        with self.assertRaises(ValueError):
            first.query("separation_certificate", {})

    def test_independent_validator_does_not_call_production_geometry_or_reference(self):
        artifact = RoboticsBarrierTask(7).separation_certificate()
        with patch("causalfill.domains.robotics_barrier.path_assessment", side_effect=AssertionError("shared path checker")), \
             patch("causalfill.domains.robotics_barrier.recover_target_from_camera_readings", side_effect=AssertionError("shared camera helper")), \
             patch("causalfill.domains.robotics_barrier.solve_robotics_barrier_from_observations", side_effect=AssertionError("reference planner")), \
             patch.object(RoboticsBarrierTask, "__init__", side_effect=AssertionError("task constructor")):
            self.assertTrue(verify_barrier_certificate(artifact["statement"], artifact["certificate"])["valid"])

    def test_statement_binding_and_route_forgery_are_rejected(self):
        original = RoboticsBarrierTask(17, "transfer", 3).separation_certificate()
        altered = deepcopy(original)
        altered["statement"]["worlds"][0]["lidar"]["occupied_boxes"][0]["upper"][1] += 0.1
        result = verify_barrier_certificate(altered["statement"], altered["certificate"])
        self.assertFalse(result["valid"])
        self.assertIn("hash", result["reason"])
        altered = deepcopy(original)
        altered["certificate"]["routes"].reverse()
        self.assertFalse(verify_barrier_certificate(altered["statement"], altered["certificate"])["valid"])
        altered = deepcopy(original)
        altered["certificate"]["separator"]["coordinate"] = 1
        self.assertFalse(verify_barrier_certificate(altered["statement"], altered["certificate"])["valid"])
        altered = deepcopy(original)
        altered["statement"]["worlds"][1]["public"]["prompt"] += "changed"
        altered["certificate"]["statement_sha256"] = digest(altered["statement"])
        self.assertFalse(verify_barrier_certificate(altered["statement"], altered["certificate"])["valid"])

    def test_boolean_numeric_aliases_cannot_fake_observation_equivalence(self):
        original = RoboticsBarrierTask(17, "transfer", 3).separation_certificate()
        for first, second in ((1, True), (True, True), (1, 1.0)):
            artifact = deepcopy(original)
            artifact["statement"]["worlds"][0]["public"]["budget"] = first
            artifact["statement"]["worlds"][1]["public"]["budget"] = second
            artifact["certificate"]["statement_sha256"] = digest(artifact["statement"])
            self.assertFalse(verify_barrier_certificate(artifact["statement"], artifact["certificate"])["valid"])
        for first, second in ((1, True), (1, 1)):
            artifact = deepcopy(original)
            artifact["statement"]["worlds"][0]["cameras"][0]["occlusion_possible"] = first
            artifact["statement"]["worlds"][1]["cameras"][0]["occlusion_possible"] = second
            artifact["certificate"]["statement_sha256"] = digest(artifact["statement"])
            self.assertFalse(verify_barrier_certificate(artifact["statement"], artifact["certificate"])["valid"])

    def test_uncovered_cross_section_rejected_even_with_forged_matching_hash(self):
        for height in (5, 5.8499999999):
            artifact = RoboticsBarrierTask(17, "transfer", 3).separation_certificate()
            low, high = [world["lidar"]["occupied_boxes"][0] for world in artifact["statement"]["worlds"]]
            low["lower"][1], low["upper"][1] = 0, height
            high["lower"][1], high["upper"][1] = 12-height, 12
            artifact["certificate"]["statement_sha256"] = digest(artifact["statement"])
            checked = verify_barrier_certificate(artifact["statement"], artifact["certificate"])
            self.assertFalse(checked["valid"], checked)
        artifact = RoboticsBarrierTask(17, "transfer", 3).separation_certificate()
        for world in artifact["statement"]["worlds"]:
            world["lidar"]["occupied_boxes"][0]["upper"][2] = 11.6
        artifact["certificate"]["statement_sha256"] = digest(artifact["statement"])
        checked = verify_barrier_certificate(artifact["statement"], artifact["certificate"])
        self.assertFalse(checked["valid"])
        self.assertIn("cover", checked["reason"])

    def test_closed_cover_and_alternative_valid_witnesses_are_accepted(self):
        artifact = RoboticsBarrierTask(17, "transfer", 3).separation_certificate()
        low, high = [world["lidar"]["occupied_boxes"][0] for world in artifact["statement"]["worlds"]]
        low["lower"][1], low["upper"][1] = 0, 5.85
        high["lower"][1], high["upper"][1] = 6.15, 12
        # The expanded y intervals meet exactly at 6.0; their union is closed.
        artifact["certificate"]["statement_sha256"] = digest(artifact["statement"])
        for route in artifact["certificate"]["routes"]:
            route["grasp_precondition"]["force_limit_n"] = 0.5
            route["safe_waypoints"].insert(0, [1, 1, 1])
        checked = verify_barrier_certificate(artifact["statement"], artifact["certificate"])
        self.assertTrue(checked["valid"], checked)

    def test_malformed_certificate_payloads_fail_without_exceptions(self):
        artifact = RoboticsBarrierTask(4).separation_certificate()
        for malformed in (None, [], "proof", True, {}, {"axioms": True}):
            self.assertFalse(verify_barrier_certificate(malformed, artifact["certificate"])["valid"])
            self.assertFalse(verify_barrier_certificate(artifact["statement"], malformed)["valid"])
        for value in (True, math.nan, math.inf, -math.inf, "5", [], {}, 1001):
            altered = deepcopy(artifact["certificate"])
            altered["separator"]["coordinate"] = value
            self.assertFalse(verify_barrier_certificate(artifact["statement"], altered)["valid"])
        altered = deepcopy(artifact["certificate"])
        altered["separator"]["axis"] = True
        self.assertFalse(verify_barrier_certificate(artifact["statement"], altered)["valid"])
        altered = deepcopy(artifact["certificate"])
        altered["routes"][0]["safe_waypoints"] = [[1, 1, 1]]*17
        self.assertFalse(verify_barrier_certificate(artifact["statement"], altered)["valid"])

    def test_original_robotics_keeps_its_valid_default_behavior(self):
        for split in ("train", "dev", "transfer"):
            for twin in (0, 1):
                original = RoboticsTask(17, split, 3, twin)
                workspace = json.loads(original.files["/scene/workspace.json"])
                self.assertNotIn("profile_version", workspace)
                self.assertNotIn("/docs/barrier-profile.txt", original.files)
                answer = original.reference_answer()
                target = answer["target_world_position"]
                answer["safe_waypoints"] = [[1, 1, 10], [target[0], target[1], 10]]
                answer["grasp_precondition"]["force_limit_n"] = 0.5
                self.assertTrue(original.evaluate(answer).success)


if __name__ == "__main__":
    unittest.main()
