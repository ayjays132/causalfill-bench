"""Independent economic, information and public-controller checks.

These tests do not take runtime success from the compiler. Expected cash and
inventory totals are rebuilt from public invoices and market records, while
fixed procurement scripts are compared with every listed demand trajectory.
The release stress harness separately replays every finite-arena transition.
"""
from __future__ import annotations

from copy import deepcopy
import itertools
import json
import unittest
from unittest.mock import patch

from causalfill.domains.vending_adaptive import (
    VendingAdaptiveTask, compile_market_game, market_action_request,
    solve_vending_adaptive,
)
from causalfill.session import Session, verify_trace
from causalfill.types import canonical


def quoted_terms(task):
    first = task.query("quote", {"supplier": "standard", "cases": 1})["quote"]
    second = task.query("quote", {"supplier": "standard", "cases": 2})["quote"]
    variable = second["shipping_cents"] - first["shipping_cents"]
    return {"standard_lead_days": first["arrival_day"] - first["order_day"],
            "fixed_shipping_cents": first["shipping_cents"] - variable,
            "case_shipping_cents": variable, "receipt_event": "delivery"}


def snapshot(task):
    # Include hidden fields for the evaluator's atomicity audit; never expose
    # this snapshot to the public controller or its tool callback.
    values = {key: value for key, value in task.__dict__.items()
              if key not in ("rng", "_arena_cache")}
    return canonical(values), task.rng.getstate()


class AdaptiveVendingTests(unittest.TestCase):
    def test_public_reference_every_world_and_configuration(self):
        for seed, split, level in itertools.product((0, 17), ("train", "dev", "transfer"), (1, 2, 3)):
            template = VendingAdaptiveTask(seed, split, level)
            contract = json.loads(template.files["/market/contract.json"])
            for world in range(len(contract["worlds"])):
                with self.subTest(seed=seed, split=split, level=level, world=world):
                    task = template.clone_for_world(world)
                    session = Session(task)
                    public = json.loads(json.dumps(session.public()))
                    with patch.object(task, "reference_answer", side_effect=AssertionError("private answer access")), \
                         patch.object(task, "game_statement", side_effect=AssertionError("private game access")):
                        fill, abstain = solve_vending_adaptive(public, session.call)
                        evidence = [event["event_id"] for event in session.trace]
                        accepted = session.call("submit", {"fill": fill, "confidence": 1.0,
                                                           "abstain": abstain, "evidence": evidence})
                    self.assertTrue(accepted["accepted"])
                    self.assertTrue(session.result["success"], session.result)
                    self.assertEqual(session.invalid, 0)
                    self.assertLessEqual(session.cost, task.budget)
                    self.assertLessEqual(session.calls, task.max_calls)
                    self.assertTrue(verify_trace(session.trace))

    def test_direct_assay_and_one_express_are_valid_alternatives(self):
        for split, level in itertools.product(("train", "dev", "transfer"), (1, 2, 3)):
            template = VendingAdaptiveTask(43, split, level)
            contract = json.loads(template.files["/market/contract.json"])
            for world in range(len(contract["worlds"])):
                task = template.clone_for_world(world)
                session = Session(task)
                observed_contract = json.loads(session.call("read_file", {"path": "/market/contract.json"})["content"])
                first = session.call("quote", {"supplier": "standard", "cases": 1})["quote"]
                second = session.call("quote", {"supplier": "standard", "cases": 2})["quote"]
                per_case = second["shipping_cents"] - first["shipping_cents"]
                fill = {"standard_lead_days": first["arrival_day"],
                        "fixed_shipping_cents": first["shipping_cents"] - per_case,
                        "case_shipping_cents": per_case, "receipt_event": "delivery"}
                for stage in range(observed_contract["stages"]):
                    obs = json.loads(session.call("assay", {})["observation"])
                    bit = obs["sample"]["value"]
                    session.call("order", {"product": observed_contract["products"][bit],
                                           "supplier": "express" if stage == 0 else "standard"})
                    session.call("settle", {})
                session.call("submit", {"fill": fill, "confidence": 1.0, "abstain": False, "evidence": []})
                self.assertTrue(session.result["success"], (split, level, world, session.result))
                self.assertEqual(task.cash, contract["cash_target_cents"])
                self.assertEqual(session.invalid, 0)
                self.assertLessEqual(session.cost, task.budget)
                self.assertNotIn("calibrate", [event["tool"] for event in session.trace])
                self.assertNotIn("forecast", [event["tool"] for event in session.trace])

    def test_invoice_delivery_sales_expiry_and_cash_are_real_events(self):
        task = VendingAdaptiveTask(17, "dev", 2)
        contract = json.loads(task.files["/market/contract.json"])
        terms = quoted_terms(task)
        expected_cash = contract["initial_cash_cents"]
        case = contract["units_per_case"]
        invoice_total = case * contract["unit_cost_cents"] + terms["fixed_shipping_cents"] + terms["case_shipping_cents"]
        for stage in range(contract["stages"]):
            bit = json.loads(task.query("assay", {})["observation"])["sample"]["value"]
            invoice = task.query("order", {"product": contract["products"][bit], "supplier": "standard"})
            expected_cash -= invoice_total
            order_obs = json.loads(invoice["observation"])
            self.assertEqual(invoice["invoice"]["total_cents"], invoice_total)
            self.assertEqual(order_obs["cash_cents"], expected_cash)
            self.assertEqual(order_obs["available_units"], 0)
            self.assertEqual(order_obs["pending_units"], case)
            self.assertEqual(order_obs["units_received"], stage * case)
            self.assertEqual(order_obs["units_sold"], stage * case)
            self.assertFalse(task.evaluate(terms).success)
            market = task.query("settle", {})["market"]
            expected_cash += case * contract["selling_price_cents"] - contract["operating_fee_cents"]
            self.assertEqual(market["sold_units"], case)
            self.assertEqual(market["revenue_cents"], case * contract["selling_price_cents"])
            self.assertEqual(market["cash_cents"], expected_cash)
        self.assertTrue(task.evaluate(terms).success)
        ledger = task.query("ledger", {"last_n": 100})["events"]
        self.assertEqual([event["event"] for event in ledger], ["invoice", "delivery", "market_close"] * contract["stages"])
        cash = contract["initial_cash_cents"]
        received = sold = disposed = 0
        for event in ledger:
            if event["event"] == "invoice":
                cash -= event["total_cents"]
            elif event["event"] == "delivery":
                received += event["quantity"]
                self.assertLessEqual(event["day"], 2 * (event["stage"] + 1))
            else:
                cash += event["revenue_cents"] - event["operating_fee_cents"]
                sold += event["sold_units"]
                disposed += event["expired_units"]
                self.assertEqual(cash, event["cash_cents"])
        self.assertEqual(cash, task.cash)
        self.assertEqual(received - sold - disposed, task.available)
        self.assertEqual(task.cash, contract["cash_target_cents"] + contract["express_surcharge_cents"])

    def test_wrong_stock_and_skipped_order_irreversibly_fail(self):
        for wrong_stock in (False, True):
            task = VendingAdaptiveTask(5, "train", 3)
            contract = json.loads(task.files["/market/contract.json"])
            fill = quoted_terms(task)
            bit = json.loads(task.query("assay", {})["observation"])["sample"]["value"]
            invoice = 0
            if wrong_stock:
                invoice = task.query("order", {"product": contract["products"][1-bit], "supplier": "standard"})["invoice"]["total_cents"]
            result = task.query("settle", {})
            obs = json.loads(result["observation"])
            self.assertEqual(obs["status"], "failure")
            self.assertEqual(obs["units_sold"], 0)
            self.assertEqual(obs["units_received"], contract["units_per_case"] if wrong_stock else 0)
            self.assertEqual(obs["units_expired"], contract["units_per_case"] if wrong_stock else 0)
            self.assertEqual(obs["cash_cents"], contract["initial_cash_cents"] - invoice - contract["operating_fee_cents"])
            self.assertFalse(task.evaluate(fill).success)
            before = snapshot(task)
            for tool, args in (("settle", {}), ("assay", {}), ("calibrate", {}),
                               ("order", {"product": "tea", "supplier": "standard"})):
                with self.assertRaises(ValueError):
                    task.query(tool, args)
                self.assertEqual(snapshot(task), before)

    def test_second_express_fails_published_cash_goal(self):
        task = VendingAdaptiveTask(11, "dev", 3)
        contract = json.loads(task.files["/market/contract.json"])
        fill = quoted_terms(task)
        for stage in range(2):
            bit = json.loads(task.query("assay", {})["observation"])["sample"]["value"]
            task.query("order", {"product": contract["products"][bit], "supplier": "express"})
            task.query("settle", {})
        self.assertEqual(task.sold, 2 * contract["units_per_case"])
        self.assertEqual(task.breach, "cash_target_unreachable")
        self.assertFalse(task.evaluate(fill).success)

    def test_fixed_product_scripts_match_raw_demand_table(self):
        for split, level in itertools.product(("train", "dev", "transfer"), (1, 2, 3)):
            template = VendingAdaptiveTask(3, split, level)
            contract = json.loads(template.files["/market/contract.json"])
            fill = quoted_terms(template)
            for script in itertools.product((0, 1), repeat=contract["stages"]):
                successes = 0
                for index, world in enumerate(contract["worlds"]):
                    task = template.clone_for_world(index)
                    for bit in script:
                        if task.breach:
                            break
                        task.query("order", {"product": contract["products"][bit], "supplier": "standard"})
                        task.query("settle", {})
                    observed = task.evaluate(fill).success
                    self.assertEqual(observed, list(script) == world["demand"])
                    successes += int(observed)
                self.assertLess(successes, len(contract["worlds"]))

    def test_forecast_truth_table_and_transferred_correlation(self):
        for split in ("train", "dev", "transfer"):
            template = VendingAdaptiveTask(29, split, 3)
            contract = json.loads(template.files["/market/contract.json"])
            for index, world in enumerate(contract["worlds"]):
                task = template.clone_for_world(index)
                calibration = json.loads(task.query("calibrate", {})["observation"])["calibration_observation"]
                self.assertEqual(calibration, world["calibration"])
                for stage, bit in enumerate(world["demand"]):
                    expected = bit
                    if split != "train":
                        expected = (expected + world["calibration"]) % 2
                    if split == "transfer" and stage:
                        expected = (expected + world["demand"][stage-1]) % 2
                    observed = json.loads(task.query("forecast", {})["observation"])["sample"]["value"]
                    self.assertEqual(observed, expected)
                    task.query("order", {"product": contract["products"][bit], "supplier": "standard"})
                    task.query("settle", {})
        transfer = VendingAdaptiveTask(29, "transfer", 1)
        session = Session(transfer)
        fill, _ = solve_vending_adaptive(session.public(), session.call)
        self.assertTrue(transfer.evaluate(fill).success)
        self.assertEqual(sum(event["tool"] == "forecast" for event in session.trace), 1)

    def test_static_reads_do_not_reveal_latent_world(self):
        template = VendingAdaptiveTask(31, "dev", 3)
        worlds = json.loads(template.files["/market/contract.json"])["worlds"]
        responses = []
        for index in range(len(worlds)):
            task = template.clone_for_world(index)
            row = [task.public(), task.files,
                   task.query("status", {}), task.query("ledger", {"last_n": 100})]
            for supplier, cases in itertools.product(("standard", "express"), (1, 2, 3)):
                row.append(task.query("quote", {"supplier": supplier, "cases": cases}))
            row.append(task.query("order", {"product": "tea", "supplier": "standard"}))
            row.append(task.query("status", {}))
            row.append(task.query("ledger", {"last_n": 100}))
            responses.append(canonical(row))
        self.assertEqual(len(set(responses)), 1)

    def test_invalid_actions_are_atomic_and_errors_cost_budget(self):
        task = VendingAdaptiveTask(7)
        bad = [("quote", {"supplier": "standard", "cases": True}),
               ("quote", {"supplier": "standard", "cases": 0}),
               ("quote", {"supplier": [], "cases": 1}),
               ("order", {"product": True, "supplier": "standard"}),
               ("order", {"product": "tea", "supplier": {}}),
               ("order", {"product": "tea", "supplier": "standard", "units": 1}),
               ("settle", {"advance": 100}), ("assay", {"hint": True}),
               ("ledger", {"last_n": False}), ("ledger", {"last_n": 101}),
               ("status", {"peek": True}), ("unknown", {})]
        for name, arguments in bad:
            before = snapshot(task)
            with self.assertRaises(ValueError):
                task.query(name, arguments)
            self.assertEqual(snapshot(task), before, name)
        task.query("calibrate", {})
        task.query("assay", {})
        for name in ("calibrate", "forecast", "assay"):
            before = snapshot(task)
            with self.assertRaises(ValueError):
                task.query(name, {})
            self.assertEqual(snapshot(task), before)
        task.query("order", {"product": "tea", "supplier": "standard"})
        before = snapshot(task)
        for name, args in (("order", {"product": "cocoa", "supplier": "express"}), ("forecast", {})):
            with self.assertRaises(ValueError):
                task.query(name, args)
            self.assertEqual(snapshot(task), before)
        session = Session(VendingAdaptiveTask(7))
        before = snapshot(session.task)
        response = session.call("order", {"product": False, "supplier": "standard"})
        self.assertIn("error", response)
        self.assertEqual(session.cost, 2)
        self.assertEqual(session.invalid, 1)
        self.assertEqual(snapshot(session.task), before)

    def test_defensive_copies_and_twins(self):
        for split, level in itertools.product(("train", "dev", "transfer"), (1, 2, 3)):
            left, right = (VendingAdaptiveTask(41, split, level, twin) for twin in (0, 1))
            self.assertEqual(left.public(), right.public())
            self.assertEqual(left.files, right.files)
            self.assertEqual(left.reference_answer(), right.reference_answer())
            a = left._contract["worlds"][left._world_index]
            b = right._contract["worlds"][right._world_index]
            self.assertEqual(a["calibration"], b["calibration"])
            self.assertEqual(a["demand"], [1-bit for bit in b["demand"]])
        task = VendingAdaptiveTask(5, "train", 1)
        invoice = task.query("order", {"product": "tea", "supplier": "standard"})
        before = snapshot(task)
        invoice["invoice"]["total_cents"] = -100000
        ledger = task.query("ledger", {"last_n": 100})
        ledger["events"][0]["product"] = "free-stock"
        task.public()["tools"]["order"]["cost"] = 0
        self.assertEqual(snapshot(task), before)

    def test_completion_schema_and_operations_are_both_required(self):
        task = VendingAdaptiveTask(53, "train", 1)
        fill = quoted_terms(task)
        self.assertFalse(task.evaluate(fill).success)
        session = Session(task)
        solved, _ = solve_vending_adaptive(session.public(), session.call)
        self.assertTrue(task.evaluate(solved).success)
        for corrupt in ({}, {**solved, "extra": 1}, {**solved, "standard_lead_days": True},
                        {**solved, "receipt_event": "invoice"}):
            self.assertFalse(task.evaluate(corrupt).success)

    def test_public_compilation_strict_values_and_defensive_graph(self):
        task = VendingAdaptiveTask(61, "train", 1)
        contract, fill = json.loads(task.files["/market/contract.json"]), quoted_terms(task)
        public_graph = compile_market_game(contract, fill)
        self.assertEqual(public_graph, task.game_statement())
        root = public_graph["initial"][0]
        public_graph["states"][root]["observation"] = "edited"
        self.assertNotEqual(public_graph, task.game_statement())
        for key, value in (("stages", True), ("capacity_units", True), ("cash_target_cents", 1),
                           ("worlds", contract["worlds"] * 20), ("round_length_days", 3)):
            invalid = deepcopy(contract)
            invalid[key] = value
            with self.assertRaises(ValueError):
                compile_market_game(invalid, fill)
        with self.assertRaises(ValueError):
            compile_market_game(contract, {**fill, "standard_lead_days": True})
        with self.assertRaises(ValueError):
            market_action_request(contract, "order:2:standard")
        clone = task.clone_for_world(0)
        self.assertIs(clone._arena_cache, task._arena_cache)

    def test_controller_rejects_wrong_task_and_stops_on_tool_error(self):
        with self.assertRaises(ValueError):
            solve_vending_adaptive({"family": "robotics"}, lambda _name, _args: {})
        called = []

        def denied(name, _args):
            called.append(name)
            return {"error": "tools unavailable"}

        with self.assertRaises(ValueError):
            solve_vending_adaptive(VendingAdaptiveTask(4).public(), denied)
        self.assertEqual(called, ["read_file"])


if __name__ == "__main__":
    unittest.main()
