"""Behavioral and accounting checks for the original vending simulation."""
import copy
import unittest

from causalfill.domains.vending import VendingTask


class VendingTests(unittest.TestCase):
    def test_reference_reaches_real_outcome_across_structures(self):
        for split in ("train", "dev", "transfer"):
            for seed in (0, 1, 17, 101):
                for twin in (0, 1):
                    with self.subTest(split=split, seed=seed, twin=twin):
                        task = VendingTask(seed, split=split, difficulty=2, twin=twin)
                        actions = task.reference_actions()
                        cost = sum(task.tools[name]["cost"] for name, _ in actions)
                        self.assertLessEqual(cost, task.budget)
                        self.assertLessEqual(len(actions), task.max_calls)
                        for name, args in actions:
                            task.query(name, args)
                        verdict = task.evaluate(task.reference_answer())
                        self.assertTrue(verdict.success, verdict.details)
                        self.assertEqual(task.cash, task.initial_cash + task.gross_sales - task.order_spend - task.operating_paid)

    def test_correct_fill_alone_does_not_pass(self):
        task = VendingTask(9)
        result = task.evaluate(task.reference_answer())
        self.assertEqual(result.recovery, 1.0)
        self.assertFalse(result.success)

    def test_receipt_is_delayed_not_invoice_stock(self):
        task = VendingTask(7)
        quote = task.query("quote", {"supplier": "cedar", "cases": 1, "order_day": 0})
        task.query("set_price", {"price_cents": 500})
        task.query("order", {"supplier": "cedar", "cases": 1})
        self.assertEqual(task.query("status", {})["available_units"], 0)
        for _ in range(quote["arrival_day"]):
            task.query("advance", {"days": 1})
        self.assertEqual(task.query("status", {})["available_units"], task.case_size)
        self.assertEqual(task.received, task.case_size)

    def test_malformed_actions_are_atomic(self):
        task = VendingTask(8)
        invalid = [
            ("order", {"supplier": "cedar", "cases": -1}),
            ("order", {"supplier": "cedar", "cases": True}),
            ("order", {"supplier": "cedar", "cases": 1, "discount": 999}),
            ("quote", {"supplier": [], "cases": 1, "order_day": 0}),
            ("advance", {"days": 0}),
            ("advance", {"days": 100}),
            ("set_price", {"price_cents": float("nan")}),
            ("set_price", {"price_cents": 0}),
            ("status", {"reveal_secret": True}),
        ]
        for name, args in invalid:
            with self.subTest(name=name, args=args):
                before = copy.deepcopy(task.__dict__)
                with self.assertRaises(ValueError):
                    task.query(name, args)
                for key in before:
                    if key != "rng":
                        self.assertEqual(before[key], task.__dict__[key], key)

    def test_twin_changes_only_pivotal_lead_parameter(self):
        first = VendingTask(23, split="transfer", twin=0)
        second = VendingTask(23, split="transfer", twin=1)
        answer_a, answer_b = first.reference_answer(), second.reference_answer()
        self.assertEqual(answer_b["lead_base_days"], answer_a["lead_base_days"] + 1)
        for key in answer_a:
            if key != "lead_base_days":
                self.assertEqual(answer_a[key], answer_b[key])
        self.assertEqual(first._demand_noise, second._demand_noise)
        self.assertEqual(first._demand_cycle, second._demand_cycle)
        self.assertEqual(first.unit_cost, second.unit_cost)
        quote_a = first.query("quote", {"supplier": "cedar", "cases": 2, "order_day": 5})
        quote_b = second.query("quote", {"supplier": "cedar", "cases": 2, "order_day": 5})
        self.assertEqual(quote_b["arrival_day"], quote_a["arrival_day"] + 1)
        self.assertEqual(quote_b["total_cents"], quote_a["total_cents"])

    def test_split_structures_are_distinct(self):
        tasks = [VendingTask(3, split=split) for split in ("train", "dev", "transfer")]
        self.assertEqual(len({t.structural_signature for t in tasks}), 3)
        self.assertEqual(tasks[0].reference_answer()["case_fee_cents"], 0)
        self.assertGreater(tasks[1].reference_answer()["case_fee_cents"], 0)
        self.assertEqual(tasks[1].reference_answer()["weekend_extra_days"], 0)
        self.assertGreater(tasks[2].reference_answer()["weekend_extra_days"], 0)

    def test_unserved_business_cannot_game_service_denominator(self):
        task = VendingTask(2)
        task.query("set_price", {"price_cents": 500})
        while task.day < task.horizon:
            task.query("advance", {"days": 1})
        self.assertEqual(task.opportunities, 0)
        self.assertFalse(task.evaluate(task.reference_answer()).success)

    def test_closing_after_early_profit_does_not_satisfy_horizon(self):
        task = VendingTask(22, difficulty=3)
        task.query("order", {"supplier": "express", "cases": 15})
        task.query("advance", {"days": 7})
        task.query("set_price", {"price_cents": 500})
        while task.day < task.horizon:
            task.query("advance", {"days": 1})
        result = task.evaluate(task.reference_answer())
        self.assertGreaterEqual(task.cash, task.cash_target)
        self.assertGreater(result.details["service_rate"], task.service_target)
        self.assertLess(task.selling_days, task.selling_days_target)
        self.assertFalse(result.success)

    def test_bool_and_extra_submission_fields_are_invalid(self):
        task = VendingTask(1)
        answer = task.reference_answer()
        answer["lead_base_days"] = True
        self.assertFalse(task.evaluate(answer).details["fill_schema_valid"])
        answer = task.reference_answer()
        answer["refund_me"] = 1
        self.assertFalse(task.evaluate(answer).details["fill_schema_valid"])


if __name__ == "__main__":
    unittest.main()
