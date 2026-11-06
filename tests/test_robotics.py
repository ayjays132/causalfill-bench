"""Meaningful geometry, observation-boundary, and counterfactual regression tests."""

from copy import deepcopy
import json
import math
import unittest

from causalfill.domains.robotics import RoboticsTask, invert_camera_point, path_assessment, segment_intersects_box, solve_from_observations


class GeometryTests(unittest.TestCase):
    def test_positive_decimal_gaps_are_clear_and_exact_contact_collides(self):
        lo, hi = [1, 1, 1], [2, 2, 2]
        for height, collision in ((2.15, True), (math.nextafter(2.15, math.inf), False),
                                  (math.nextafter(2.15, -math.inf), True)):
            with self.subTest(height=height):
                self.assertEqual(segment_intersects_box([0, height, 1.5], [3, height, 1.5],
                                                        lo, hi, 0.15), collision)
        # A tiny gap at an edge must not be erased by an epsilon in path time.
        self.assertFalse(segment_intersects_box([0, 1.999999999, 1.5],
                                                [1.999999999, 0, 1.5], lo, hi))
        self.assertTrue(segment_intersects_box([0, 2, 1.5], [2, 0, 1.5], lo, hi))

    def test_workspace_clearance_is_not_relaxed_by_a_numerical_epsilon(self):
        start, target = [1, 1, 1], [10, 10, 2]
        bounds = [[0, 0, 0], [12, 12, 12]]
        for x, expected_inside in ((0.15, True), (math.nextafter(0.15, 0), False),
                                   (11.85, True), (math.nextafter(11.85, math.inf), False)):
            with self.subTest(x=x):
                clear, inside = path_assessment(start, target, [[x, 1, 10]], [], bounds, 0.15)
                self.assertTrue(clear)
                self.assertEqual(inside, expected_inside)

    def test_segment_slab_crossing_grazing_and_near_miss(self):
        lo, hi = [1.0, 1.0, 1.0], [2.0, 2.0, 2.0]
        self.assertTrue(segment_intersects_box([0, 1.5, 1.5], [3, 1.5, 1.5], lo, hi))
        self.assertTrue(segment_intersects_box([0, 1, 1], [3, 1, 1], lo, hi))
        self.assertTrue(segment_intersects_box([1.5, 1.5, 1.5], [1.5, 1.5, 1.5], lo, hi))
        self.assertFalse(segment_intersects_box([0, 0.9, 1.5], [3, 0.9, 1.5], lo, hi))
        self.assertTrue(segment_intersects_box([0, 0.9, 1.5], [3, 0.9, 1.5], lo, hi, 0.2))
        self.assertFalse(segment_intersects_box([0, 0, 0], [0.5, 0.5, 0.5], lo, hi))

    def test_affine_calibration_recovers_sheared_coordinates(self):
        # image = [[2, 1],[-1, 3]] * [x,z] + [11,17].
        fiducials = [
            {"world": [0, 0, 0], "image": [11, 17]},
            {"world": [10, 0, 0], "image": [31, 7]},
            {"world": [0, 0, 10], "image": [21, 47]},
        ]
        x, z = invert_camera_point([23, 32], fiducials, [0, 2])
        self.assertAlmostEqual(x, 3)
        self.assertAlmostEqual(z, 6)


class RoboticsTests(unittest.TestCase):
    def test_near_boundary_plans_follow_exact_geometry_contract(self):
        task = RoboticsTask(0, "transfer", 3)
        answer = task.reference_answer()
        target = answer["target_world_position"]
        answer["grasp_precondition"]["force_limit_n"] = 0.5
        answer["safe_waypoints"] = [[0.15-5e-9, 1, 10], [target[0], target[1], 10]]
        self.assertFalse(task.evaluate(answer).success)
        self.assertFalse(task.evaluate(answer).details["workspace_valid"])
        roof = task.query("lidar", {})["occupied_boxes"][0]["upper"][2]+0.15+5e-9
        answer["safe_waypoints"] = [[1, 1, roof], [target[0], target[1], roof]]
        self.assertTrue(task.evaluate(answer).success)

    def test_evidence_based_reference_solves_split_difficulty_matrix(self):
        for split in ("train", "dev", "transfer"):
            for difficulty in range(1, 4):
                for seed in range(12):
                    for twin in (0, 1):
                        task = RoboticsTask(seed, split, difficulty, twin)
                        with self.subTest(split=split, difficulty=difficulty, seed=seed, twin=twin):
                            self.assertTrue(task.evaluate(task.reference_answer()).success)

    def test_alternative_safe_path_and_force_are_accepted(self):
        task = RoboticsTask(17)
        answer = task.reference_answer()
        answer["grasp_precondition"]["force_limit_n"] = 0.75
        # Independently specified safe high route, with an extra collinear point.
        target = answer["target_world_position"]
        answer["safe_waypoints"] = [[1, 1, 10], [5, 1, 10], [target[0], target[1], 10]]
        self.assertTrue(task.evaluate(answer).success)

    def test_counterfactual_changes_only_vertical_obstacle_and_direct_validity(self):
        original = RoboticsTask(42, "transfer", 3, 0)
        twin = RoboticsTask(42, "transfer", 3, 1)
        self.assertEqual(original.files, twin.files)
        for view in ("xy", "xz", "yz"):
            self.assertEqual(original.query("camera", {"view": view}), twin.query("camera", {"view": view}))
        first = original.query("lidar", {})["occupied_boxes"][0]
        second = twin.query("lidar", {})["occupied_boxes"][0]
        for corner in ("lower", "upper"):
            self.assertEqual(first[corner][:2], second[corner][:2])
            self.assertAlmostEqual(second[corner][2] - first[corner][2], 4)
        answer = original.reference_answer()
        answer["safe_waypoints"] = []
        self.assertFalse(original.evaluate(answer).success)
        self.assertEqual(original.evaluate(answer).safety, 0)
        self.assertTrue(twin.evaluate(answer).success)

    def test_camera_occlusion_still_leaves_identifiable_observations(self):
        task = RoboticsTask(8, "transfer", 3)
        workspace = json.loads(task.files["/scene/workspace.json"])
        readings = [task.query("camera", {"view": view}) for view in ("xy", "xz", "yz")]
        visible = [r for r in readings if any(o["id"] == workspace["target_id"] for o in r["objects"])]
        self.assertEqual(len(visible), 2)
        recovered = solve_from_observations(workspace, visible, task.query("lidar", {}))
        self.assertTrue(task.evaluate(recovered).success)
        with self.assertRaises(ValueError):
            solve_from_observations(workspace, visible[:1], task.query("lidar", {}))

    def test_probe_is_non_destructive_and_does_not_judge_hidden_target(self):
        task = RoboticsTask(13)
        before = deepcopy(task.__dict__)
        result = task.query("probe_path", {"target_world_position": [1, 2, 1], "safe_waypoints": []})
        self.assertEqual(result, {"collision_free": True, "within_workspace": True, "non_destructive": True})
        self.assertEqual(task._target, before["_target"])
        self.assertEqual(task._obstacles, before["_obstacles"])

    def test_invalid_tool_arguments_do_not_mutate_scene(self):
        task = RoboticsTask(4)
        camera_before = task.query("camera", {"view": "xy"})
        lidar_before = task.query("lidar", {})
        invalid = [
            ("camera", {"view": True}),
            ("camera", {"view": ["xy"]}),
            ("lidar", {"reveal_answer": True}),
            ("probe_path", {"target_world_position": [True, 1, 2], "safe_waypoints": []}),
            ("probe_path", {"target_world_position": [1, math.nan, 2], "safe_waypoints": []}),
            ("probe_path", {"target_world_position": [1, 1, 2], "safe_waypoints": [[1, 1, 1]] * 17}),
        ]
        for name, args in invalid:
            with self.subTest(name=name, args=args):
                with self.assertRaises(ValueError):
                    task.query(name, args)
        self.assertEqual(camera_before, task.query("camera", {"view": "xy"}))
        self.assertEqual(lidar_before, task.query("lidar", {}))

    def test_submission_validation_rejects_nonfinite_bool_and_unknown_fields(self):
        task = RoboticsTask(4)
        original = task.reference_answer()
        invalid = []
        for value in (True, math.nan, math.inf, -math.inf, 1001, "1"):
            item = deepcopy(original)
            item["target_world_position"][0] = value
            invalid.append(item)
        for value in (True, math.nan, math.inf, "2"):
            item = deepcopy(original)
            item["grasp_precondition"]["force_limit_n"] = value
            invalid.append(item)
        item = deepcopy(original)
        item["safe_waypoints"] = [[1, 1, 1]] * 17
        invalid.append(item)
        item = deepcopy(original)
        item["oracle"] = True
        invalid.append(item)
        for item in invalid:
            self.assertFalse(task.evaluate(item).success)

    def test_world_bounds_and_material_force_are_real_outcome_constraints(self):
        task = RoboticsTask(7)
        answer = task.reference_answer()
        answer["safe_waypoints"] = [[1, 1, 13]]
        self.assertEqual(task.evaluate(answer).safety, 0)
        answer = task.reference_answer()
        answer["grasp_precondition"]["force_limit_n"] = 99
        self.assertEqual(task.evaluate(answer).safety, 0)
        answer = task.reference_answer()
        answer["grasp_precondition"]["force_limit_n"] = 0.1
        self.assertFalse(task.evaluate(answer).success)

    def test_observation_results_are_defensive_copies(self):
        task = RoboticsTask(22)
        reading = task.query("camera", {"view": "xy"})
        original = deepcopy(reading)
        reading["fiducials"][0]["world"][0] = 999
        reading["objects"].clear()
        self.assertEqual(original, task.query("camera", {"view": "xy"}))
        scan = task.query("lidar", {})
        scan["occupied_boxes"].clear()
        self.assertEqual(len(task.query("lidar", {})["occupied_boxes"]), 1)

    def test_distractor_objects_are_consistent_across_views(self):
        task = RoboticsTask(19, "transfer", 3)
        values = {}
        for view in ("xy", "xz", "yz"):
            reading = task.query("camera", {"view": view})
            for obj in reading["objects"]:
                observed = invert_camera_point(obj["image"], reading["fiducials"], reading["projection_axes"])
                for axis, value in zip(reading["projection_axes"], observed):
                    key = (obj["id"], axis)
                    if key in values:
                        self.assertAlmostEqual(values[key], value)
                    values[key] = value

    def test_public_description_contains_no_latent_scene_or_seed(self):
        task = RoboticsTask(9951)
        public = task.public()
        for key in ("seed", "rng", "_target", "_obstacles", "reference_answer", "hidden"):
            self.assertNotIn(key, public)
        workspace = json.loads(task.files["/scene/workspace.json"])
        self.assertNotIn("target_world_position", workspace)
        self.assertNotIn("occupied_boxes", workspace)
        self.assertNotIn("camera_matrix", workspace)
        self.assertTrue(all(type(value) is str for value in task.files.values()))


if __name__ == "__main__":
    unittest.main()

