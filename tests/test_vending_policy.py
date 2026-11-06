"""The scripted policy must work through the budgeted public tool interface."""
import json
import unittest

from causalfill.domains.vending import VendingTask
from causalfill.session import Session, verify_trace
from causalfill.vending_policy import solve_vending


class VendingEvidencePolicyTests(unittest.TestCase):
    def test_public_evidence_policy_across_splits_difficulties_and_twins(self):
        for difficulty in (1, 2, 3):
            for split in ("train", "dev", "transfer"):
                for twin in (0, 1):
                    with self.subTest(difficulty=difficulty, split=split, twin=twin):
                        task = VendingTask(37, split=split, difficulty=difficulty, twin=twin)
                        session = Session(task)
                        public = json.loads(json.dumps(session.public()))
                        observed = []

                        def call(name, args):
                            response = session.call(name, json.loads(json.dumps(args)))
                            observed.append((name, response))
                            return json.loads(json.dumps(response))

                        # Answer generation is deliberately inaccessible while the
                        # policy operates. Only final evaluator grading may use it.
                        original_answer = task.reference_answer

                        def unavailable():
                            raise AssertionError("hidden reference access during policy execution")

                        task.reference_answer = unavailable
                        try:
                            fill = solve_vending(public, call)
                        finally:
                            task.reference_answer = original_answer
                        self.assertFalse(session.closed)
                        self.assertNotIn("submit", [name for name, _ in observed])
                        self.assertTrue(all("error" not in response for _, response in observed))
                        evidence = [response["event_id"] for _, response in observed]
                        accepted = session.call("submit", {"fill": fill, "confidence": 1.0,
                                                          "abstain": False, "evidence": evidence})
                        self.assertTrue(accepted.get("accepted"))
                        self.assertTrue(session.result["success"], session.result)
                        self.assertEqual(session.result["invalid_calls"], 0)
                        self.assertLessEqual(session.result["tool_cost"], public["budget"])
                        self.assertLessEqual(session.result["tool_calls"], public["max_calls"])
                        self.assertTrue(verify_trace(session.trace))

    def test_tool_error_stops_without_submission(self):
        public = Session(VendingTask(4)).public()
        called = []

        def denied(name, args):
            called.append(name)
            return {"error": "evidence tools disabled", "event_id": "e0001", "cost_used": 1}

        with self.assertRaises(ValueError):
            solve_vending(public, denied)
        self.assertEqual(called, ["read_file"])

    def test_rejects_unrelated_public_task(self):
        with self.assertRaises(ValueError):
            solve_vending({"family": "robotics"}, lambda name, args: {})


if __name__ == "__main__":
    unittest.main()
