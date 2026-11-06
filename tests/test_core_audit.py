"""White-box regression checks for concrete evaluator-integrity findings.

These are harness audits, never model-performance or independent solve results.
"""

import itertools
import unittest

from causalfill.domains.words import AmbiguousWordsTask, WordsTask
from causalfill.domains.workflow import WorkflowTask, expression
from causalfill.session import Session
from causalfill.types import finite_number


class CoreIntegrityAudit(unittest.TestCase):
    def test_masked_gate_is_not_revealed_in_public_structural_metadata(self):
        for split in ("train", "dev", "transfer"):
            task = WordsTask(9, split, 1)
            self.assertIn("gate_word", task.missing)
            public = Session(task).public()
            self.assertNotIn("structural_signature", public)
            self.assertNotIn("truth", public)
            self.assertNotIn("seed", public)

    def test_gate_is_not_a_deterministic_function_of_split_and_arity(self):
        for split in ("train", "dev", "transfer"):
            observed = {WordsTask(seed, split, 1).truth["gate_word"] for seed in range(20)}
            self.assertGreater(len(observed), 1)

    def test_workflow_does_not_accept_hardcoded_hidden_case_constants(self):
        wrong = {
            "train": "balance-amount*scale-3",
            "dev": "max(balance-amount*scale-3,10)",
            "transfer": "min(max(balance-amount*scale-3,10),50)",
        }
        for split, source in wrong.items():
            task = WorkflowTask(5, split)
            with self.subTest(split=split):
                self.assertFalse(task.evaluate({"expression": source}).success)
                self.assertTrue(task.evaluate(task.reference_answer()).success)

    def test_huge_integer_confidence_is_rejected_and_charged_without_crash(self):
        with self.assertRaises(ValueError):
            finite_number(10**400, 0, 1, "confidence")
        task = WordsTask(2)
        session = Session(task)
        response = session.call("submit", {
            "fill": task.reference_answer(), "confidence": 10**400,
            "abstain": False, "evidence": [],
        })
        self.assertIn("error", response)
        self.assertEqual(session.invalid, 1)
        self.assertEqual(session.cost, 1)

    def test_ambiguous_twins_have_identical_entire_permitted_evidence(self):
        original = AmbiguousWordsTask(11, "transfer", 3, 0)
        twin = AmbiguousWordsTask(11, "transfer", 3, 1)
        self.assertEqual(original.public(), twin.public())
        self.assertEqual(original.files, twin.files)
        self.assertNotEqual(original.reference_answer(), twin.reference_answer())
        for bits in itertools.product((False, True), repeat=original.n):
            args = {"inputs": list(bits)}
            self.assertEqual(original.query("experiment", args), twin.query("experiment", args))
        witness = original.ambiguity_witness()
        self.assertTrue(witness["observationally_equivalent"])
        self.assertTrue(witness["distinct_required_fills"])

    def test_expression_interpreter_rejects_execution_and_unbounded_arithmetic(self):
        values = dict(balance=40, amount=7, fee=3, reserve=10, ceiling=50, scale=2)
        for source in (
            "__import__('os').getcwd()", "(1).__class__", "[x for x in [1]][0]",
            "2**1000000", "lambda: balance", "True", "min(balance, amount, key=abs)",
            "10000*10000*10000*10000*10000*10000*10000*10000",
        ):
            with self.subTest(source=source):
                with self.assertRaises(ValueError):
                    expression(source, values)


if __name__ == "__main__":
    unittest.main()
