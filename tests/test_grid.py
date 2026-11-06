import copy
import json
import unittest

from causalfill.domains.grid import (
    GridTask,
    apply_program,
    candidate_programs,
    diagnostic_grid,
    infer_program,
    validate_grid,
)
from causalfill.session import Session


class GridTests(unittest.TestCase):
    def test_known_rotation_rectangle_and_crop(self):
        self.assertEqual(apply_program([[1, 2, 3], [4, 0, 1]], [{"op": "rotate90", "turns": 1}]), [[4, 1], [0, 2], [1, 3]])
        self.assertEqual(apply_program([[0, 0, 0], [0, 2, 0], [0, 2, 0]], [{"op": "crop"}]), [[2], [2]])
        self.assertEqual(apply_program([[0, 0], [0, 0]], [{"op": "crop"}]), [[0]])
        self.assertEqual(apply_program([[1, 2], [3, 4]], [{"op": "keep_color", "color": 2}, {"op": "recolor", "source": 2, "target": 4}]), [[0, 4], [0, 0]])

    def test_diagnostic_distinguishes_every_grammar_candidate(self):
        grid = diagnostic_grid()
        for split in ("train", "dev", "transfer"):
            programs = candidate_programs(split)
            outputs = {json.dumps(apply_program(grid, program)) for program in programs}
            self.assertEqual(len(outputs), len(programs), split)
            for program in programs:
                observed = [{"input": grid, "output": apply_program(grid, program)}]
                self.assertEqual(infer_program(split, observed), program)

    def test_references_pass_all_structures_and_difficulties(self):
        for split in ("train", "dev", "transfer"):
            for difficulty in (1, 2, 3):
                task = GridTask(891, split, difficulty)
                self.assertTrue(task.evaluate(task.reference_answer()).success)

    def test_malformed_grids_and_dsl_are_rejected(self):
        task = GridTask(7, "dev", 1)
        for bad in ([], [[]], [[True]], [[1.0]], [[-1]], [[5]], [[1], [1, 2]], [[0] * 9], "grid"):
            with self.assertRaises(ValueError):
                task.query("transform", {"grid": bad})
        for program in ([{"op": "rotate90", "turns": True}], [{"op": "crop", "extra": 0}], [{"op": "recolor", "source": 0, "target": 1}], [{"op": "exec", "code": "print(1)"}], [{"op": "crop"}] * 5):
            self.assertFalse(task.evaluate({"program": program}).success)
        with self.assertRaises(ValueError):
            task.query("transform", {"grid": [[1]], "answer": 1})

    def test_demonstration_only_fit_fails_unseen_cases(self):
        task = GridTask(1024, "transfer", 3)
        right = task.reference_answer()["program"]
        wrong = copy.deepcopy(right)
        alternate = 1 + wrong[0]["color"] % 4
        wrong[0]["color"] = alternate
        wrong[-1]["source"] = alternate
        for example in json.loads(task.files["/data/demonstrations.json"]):
            self.assertEqual(apply_program(example["input"], wrong), example["output"])
        self.assertFalse(task.evaluate({"program": wrong}).success)

    def test_behaviorally_equivalent_alternative_is_accepted(self):
        task = GridTask(27, "train", 2)
        answer = task.reference_answer()
        answer["program"] = [{"op": "flip_h"}, {"op": "flip_h"}] + answer["program"]
        self.assertTrue(task.evaluate(answer).success)

    def test_twin_changes_only_final_recolor_target(self):
        for split in ("train", "dev", "transfer"):
            task = GridTask(804, split, 2, 0)
            twin = GridTask(804, split, 2, 1)
            original = task.reference_answer()["program"]
            changed = twin.reference_answer()["program"]
            self.assertEqual(original[:-1], changed[:-1])
            self.assertEqual(original[-1]["source"], changed[-1]["source"])
            self.assertNotEqual(original[-1]["target"], changed[-1]["target"])
            self.assertEqual(task._challenge_inputs, twin._challenge_inputs)
            self.assertEqual(task._random_inputs, twin._random_inputs)
            self.assertFalse(twin.evaluate({"program": original}).success)

    def test_budgeted_evidence_only_solver(self):
        session = Session(GridTask(188, "transfer", 3))
        observed = session.call("transform", {"grid": diagnostic_grid()})
        program = infer_program("transfer", [{"input": diagnostic_grid(), "output": observed["output"]}])
        response = session.call("submit", {"fill": {"program": program}, "confidence": 1.0, "abstain": False, "evidence": [observed["event_id"]]})
        self.assertTrue(response["accepted"])
        self.assertNotIn("success", response)
        self.assertTrue(session.result["success"])
        self.assertEqual(session.result["tool_cost"], 1)

    def test_input_is_not_mutated(self):
        grid = [[0, 1], [2, 3]]
        copied = copy.deepcopy(grid)
        validate_grid(grid)
        apply_program(grid, [{"op": "crop"}, {"op": "flip_h"}])
        self.assertEqual(grid, copied)


if __name__ == "__main__":
    unittest.main()

