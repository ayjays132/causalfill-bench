"""Original finite-horizon procurement simulator; not a Vending-Bench port.

All monetary values are integer cents. The task and reference controller belong
to the evaluator. Agents interact only through the public session tools.
"""
from __future__ import annotations

import copy
import math
from typing import Any

from causalfill.types import Task, Verdict


class VendingTask(Task):
    """Recover a masked procurement rule and keep a small business operating."""

    def __init__(self, seed: int, split: str = "dev", difficulty: int = 2, twin: int = 0):
        super().__init__(seed, split, difficulty, twin)
        if split not in {"train", "dev", "transfer"}:
            raise ValueError("split must be train, dev, or transfer")
        if type(difficulty) is not int or not 1 <= difficulty <= 3:
            raise ValueError("difficulty must be an integer from 1 to 3")
        if type(twin) is not int or twin not in {0, 1}:
            raise ValueError("twin must be 0 or 1")
        self.family = "vending"
        self.horizon = 12 + 4 * difficulty
        self.case_size = 6
        self.capacity = 180
        self.shelf_life = 6
        self.initial_cash = 15000
        self.cash_target = self.initial_cash + 1500 + 500 * difficulty
        self.service_target = 0.60
        self.selling_days_target = math.ceil(self.horizon * 0.60)
        self.daily_fee = 25 + 5 * difficulty
        self.unit_cost = self.rng.randint(70, 100)
        self._lead_base = self.rng.randint(1, 3)
        self._fixed_fee = self.rng.randint(60, 150)
        self._case_fee = 0 if split == "train" else self.rng.randint(8, 25)
        self._weekend_extra = self.rng.randint(1, 2) if split == "transfer" else 0
        # Consume the same random draws before changing this ONE causal variable.
        self._demand_cycle = [self.rng.randint(8, 12) for _ in range(7)]
        self._demand_noise = [self.rng.choice((-1, 0, 0, 1)) for _ in range(self.horizon + 1)]
        self._lead_base += twin
        structure = {
            "train": "fixed-transit.fixed-fee",
            "dev": "fixed-transit.case-fee",
            "transfer": "weekend-transit.case-fee",
        }[split]
        self.structural_signature = "vending:" + structure + ":v1"
        self.answerable = True
        self.day = 0
        self.cash = self.initial_cash
        self.price = 280
        self.batches: list[dict[str, int]] = []
        self.pending: list[dict[str, int]] = []
        self.events: list[dict[str, Any]] = []
        self.orders = 0
        self.received = 0
        self.sold = 0
        self.selling_days = 0
        self.expired = 0
        self.opportunities = 0
        self.order_spend = 0
        self.gross_sales = 0
        self.operating_paid = 0
        self.unpaid_fees = 0
        self.budget = 6 * self.horizon + 18
        self.max_calls = 3 * self.horizon + 15
        self.slots = {
            "lead_base_days": {"type": "integer", "description": "Base transit days, independent of case count."},
            "weekend_extra_days": {"type": "integer", "description": "Extra transit days when order_day modulo 7 is 5 or 6."},
            "fixed_fee_cents": {"type": "integer", "description": "Fixed shipping charge per order, in integer cents."},
            "case_fee_cents": {"type": "integer", "description": "Additional shipping charge per ordered case, in cents."},
            "receipt_event": {"type": "string", "description": "The event that adds stock: order, invoice, or delivery."},
        }
        self.tools = {
            "quote": {"description": "Ask a supplier for an itemized quote, including promised arrival. Quotes do not place orders.",
                      "arguments": {"supplier": "cedar or express", "cases": "integer 1..30", "order_day": "integer 0..horizon-1"}, "cost": 2},
            "order": {"description": "Pay now for cases; stock arrives later. No overdrafts or warehouse overbooking.",
                      "arguments": {"supplier": "cedar or express", "cases": "integer 1..30"}, "cost": 3},
            "set_price": {"description": "Set the next simulated days' unit selling price in cents.",
                          "arguments": {"price_cents": "integer 100..550"}, "cost": 1},
            "advance": {"description": "Advance 1..7 days. Each day receives due deliveries, expires old stock, makes sales, and pays operating fees.",
                        "arguments": {"days": "integer 1..7, without passing the horizon"}, "cost": 1},
            "status": {"description": "Observe current cash, available stock, paid pending deliveries, and cumulative outcomes.",
                       "arguments": {}, "cost": 1},
            "market": {"description": "Read the recurring demand forecast and price response; actual daily demand can differ by one.",
                       "arguments": {}, "cost": 1},
            "ledger": {"description": "Read actual past purchases, receipts, expiry, sales, and operating charges.",
                       "arguments": {"last_n": "integer 1..100"}, "cost": 1},
        }
        self.prompt = (
            "Repair the five holes in Cedar's procurement skill AND operate the business through the full horizon. "
            "Gather quotes and receipts, place and price orders, and advance time. Submit the five repaired fields once. "
            f"The business opens on day 0 with {self.initial_cash} cents and no stock. Finish day {self.horizon} "
            f"with cash at least {self.cash_target} cents, serve at least 60% of all price-dependent purchase requests, "
            f"make at least one sale on at least {self.selling_days_target} distinct days, "
            "and leave no unpaid operating fees. Inventory has no terminal liquidation value. "
            "Both repair correctness and actual business outcomes are required for strict success. "
            "Read /skills/procurement.txt and /docs/accounting.txt for rules. This is an original symbolic simulation."
        )
        self.files = {
            "/skills/procurement.txt": (
                "CEDAR PROCUREMENT — five missing fields\n"
                "All values are integer days or integer cents. Day 0 is Monday.\n"
                "arrival_day = order_day + [[lead_base_days]]\n"
                "  + ([[weekend_extra_days]] if order_day % 7 in (5, 6) else 0)\n"
                "shipping = [[fixed_fee_cents]] + [[case_fee_cents]] * cases\n"
                "stock becomes available at [[receipt_event]] (order, invoice, or delivery).\n"
                "Coefficients do not change during an episode. Quoted arrival dates are honored.\n"
                "You may request hypothetical quotes for future order days without placing an order.\n"
                "Compare at least two case counts and a weekday versus weekend if you need to identify coefficients.\n"
                "Express is a different supplier with a fully specified one-day transit and higher costs.\n"
            ),
            "/docs/accounting.txt": (
                f"Case size: {self.case_size}. Warehouse capacity: {self.capacity} units, including pending orders.\n"
                f"Operating fee: {self.daily_fee} cents per simulated day. Shelf life: {self.shelf_life} days after arrival.\n"
                "Payment and invoice occur when an order is placed; the warehouse records a separate physical receipt on delivery.\n"
                "An invoice is a claim on goods in transit and does not make goods available for sale.\n"
                "A batch is sellable on its arrival day through arrival_day + shelf_life, inclusive.\n"
                "For each newly advanced day: receive deliveries, remove expired stock, sell FIFO, then pay the operating fee.\n"
                "Demand depends on the currently set selling price. Missed demand is lost, never backlogged.\n"
                "Orders debit all item and shipping costs immediately. Invalid operations never change world state.\n"
                "No terminal inventory valuation, refunds, loans, or liquidation. Remaining stock and orders are worth zero for scoring.\n"
                "A cash shortage pays the available balance and records unpaid operating fees; any unpaid fee fails strict success.\n"
            ),
        }

    @staticmethod
    def _keys(args: dict, required: set[str]) -> None:
        if not isinstance(args, dict) or set(args) != required:
            raise ValueError("arguments must match the documented tool fields")

    @staticmethod
    def _integer(value: Any, low: int, high: int, field: str) -> int:
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f"{field} must be an integer in [{low}, {high}]")
        return value

    @staticmethod
    def _supplier(value: Any) -> str:
        if type(value) is not str or value not in {"cedar", "express"}:
            raise ValueError("supplier must be cedar or express")
        return value

    def _available(self) -> int:
        return sum(batch["quantity"] for batch in self.batches)

    def _in_transit(self) -> int:
        return sum(order["quantity"] for order in self.pending)

    def _quotation(self, supplier: str, cases: int, day: int) -> dict[str, Any]:
        quantity = cases * self.case_size
        if supplier == "cedar":
            lead = self._lead_base + (self._weekend_extra if day % 7 in (5, 6) else 0)
            unit_cost = self.unit_cost
            shipping = self._fixed_fee + self._case_fee * cases
        else:
            lead = 1
            unit_cost = self.unit_cost + 55
            shipping = 180 + 30 * cases
        return {
            "supplier": supplier, "order_day": day, "cases": cases,
            "units_per_case": self.case_size, "quantity": quantity,
            "unit_cost_cents": unit_cost, "shipping_cents": shipping,
            "total_cents": unit_cost * quantity + shipping, "arrival_day": day + lead,
        }

    def _forecast(self, day: int, actual: bool = False) -> int:
        base = self._demand_cycle[day % 7]
        if self.price < 180:
            shift = 5
        elif self.price < 240:
            shift = 2
        elif self.price < 300:
            shift = 0
        elif self.price < 360:
            shift = -3
        elif self.price < 450:
            shift = -7
        else:
            return 0
        noise = self._demand_noise[day] if actual else 0
        return max(0, base + shift + noise)

    def _status(self) -> dict[str, Any]:
        return {
            "day": self.day, "horizon_days": self.horizon, "cash_cents": self.cash,
            "cash_target_cents": self.cash_target, "price_cents": self.price,
            "available_units": self._available(), "pending_units": self._in_transit(),
            "batches": copy.deepcopy(self.batches), "pending_deliveries": copy.deepcopy(self.pending),
            "units_sold": self.sold, "units_expired": self.expired,
            "selling_days": self.selling_days, "selling_days_target": self.selling_days_target,
            "purchase_requests": self.opportunities, "unpaid_fees_cents": self.unpaid_fees,
            "service_rate": self.sold / self.opportunities if self.opportunities else 0.0,
        }

    def _next_day(self) -> dict[str, Any]:
        self.day += 1
        deliveries = [order for order in self.pending if order["arrival_day"] <= self.day]
        self.pending = [order for order in self.pending if order["arrival_day"] > self.day]
        for order in deliveries:
            self.batches.append({"quantity": order["quantity"], "expiry_day": self.day + self.shelf_life})
            self.received += order["quantity"]
            self.events.append({"event": "delivery", "day": self.day, "order_id": order["order_id"], "quantity": order["quantity"]})
        expired = sum(batch["quantity"] for batch in self.batches if batch["expiry_day"] < self.day)
        self.batches = [batch for batch in self.batches if batch["expiry_day"] >= self.day]
        self.expired += expired
        demand = self._forecast(self.day, actual=True)
        sales = min(demand, self._available())
        remaining = sales
        self.batches.sort(key=lambda batch: batch["expiry_day"])
        for batch in self.batches:
            count = min(remaining, batch["quantity"])
            batch["quantity"] -= count
            remaining -= count
        self.batches = [batch for batch in self.batches if batch["quantity"]]
        revenue = sales * self.price
        self.cash += revenue
        self.sold += sales
        self.selling_days += int(sales > 0)
        self.gross_sales += revenue
        self.opportunities += demand
        fee_paid = min(self.cash, self.daily_fee)
        self.cash -= fee_paid
        self.operating_paid += fee_paid
        self.unpaid_fees += self.daily_fee - fee_paid
        event = {"event": "day_close", "day": self.day, "demand": demand, "sold": sales,
                 "expired": expired, "revenue_cents": revenue, "operating_fee_paid_cents": fee_paid,
                 "cash_cents": self.cash}
        self.events.append(event)
        return dict(event)

    def query(self, name: str, args: dict) -> dict:
        if name == "quote":
            self._keys(args, {"supplier", "cases", "order_day"})
            supplier = self._supplier(args["supplier"])
            cases = self._integer(args["cases"], 1, self.capacity // self.case_size, "cases")
            day = self._integer(args["order_day"], 0, self.horizon - 1, "order_day")
            return self._quotation(supplier, cases, day)
        if name == "order":
            self._keys(args, {"supplier", "cases"})
            supplier = self._supplier(args["supplier"])
            cases = self._integer(args["cases"], 1, self.capacity // self.case_size, "cases")
            if self.day >= self.horizon:
                raise ValueError("the business horizon is already complete")
            quote = self._quotation(supplier, cases, self.day)
            if quote["arrival_day"] > self.horizon:
                raise ValueError("this order would arrive after the business horizon")
            if quote["total_cents"] > self.cash:
                raise ValueError("insufficient available cash")
            if self._available() + self._in_transit() + quote["quantity"] > self.capacity:
                raise ValueError("order would overbook the warehouse")
            self.orders += 1
            self.cash -= quote["total_cents"]
            self.order_spend += quote["total_cents"]
            record = {"order_id": self.orders, "arrival_day": quote["arrival_day"], "quantity": quote["quantity"]}
            self.pending.append(record)
            self.events.append({"event": "invoice", "day": self.day, "order_id": self.orders,
                                "supplier": supplier, "quantity": quote["quantity"], "debit_cents": quote["total_cents"]})
            return {"invoice": dict(quote), "order_id": self.orders,
                    "available_units": self._available(), "cash_cents": self.cash}
        if name == "set_price":
            self._keys(args, {"price_cents"})
            price = self._integer(args["price_cents"], 100, 550, "price_cents")
            if self.day >= self.horizon:
                raise ValueError("the business horizon is already complete")
            self.price = price
            return {"price_cents": price, "takes_effect_on_next_advanced_day": True}
        if name == "advance":
            self._keys(args, {"days"})
            days = self._integer(args["days"], 1, 7, "days")
            if self.day + days > self.horizon:
                raise ValueError("advance would pass the business horizon")
            observations = [self._next_day() for _ in range(days)]
            return {"days": observations, "status": self._status()}
        if name == "status":
            self._keys(args, set())
            return self._status()
        if name == "market":
            self._keys(args, set())
            return {"day_zero_weekday": "Monday", "base_demand_by_weekday": list(self._demand_cycle),
                    "noise": "Each day adds -1, 0, or +1 demand; exact future noise is not observable.",
                    "price_bands_cents": [
                        {"from": 100, "to": 179, "demand_offset": 5},
                        {"from": 180, "to": 239, "demand_offset": 2},
                        {"from": 240, "to": 299, "demand_offset": 0},
                        {"from": 300, "to": 359, "demand_offset": -3},
                        {"from": 360, "to": 449, "demand_offset": -7},
                        {"from": 450, "to": 550, "demand": 0},
                    ]}
        if name == "ledger":
            self._keys(args, {"last_n"})
            count = self._integer(args["last_n"], 1, 100, "last_n")
            return {"events": copy.deepcopy(self.events[-count:])}
        raise ValueError("unknown vending tool")

    def evaluate(self, fill: dict) -> Verdict:
        expected = self.reference_answer()
        schema_ok = isinstance(fill, dict) and set(fill) == set(expected)
        if schema_ok:
            schema_ok = all(type(fill[key]) is int and 0 <= fill[key] <= 5000
                            for key in expected if key != "receipt_event")
            schema_ok = schema_ok and type(fill["receipt_event"]) is str
        repaired = sum(fill[key] == value for key, value in expected.items()) if schema_ok else 0
        # Field values have documented units and meanings, so their unique values
        # are identifiable from the permitted quote and accounting observations.
        recovery = repaired / len(expected)
        balance_ok = self.cash == self.initial_cash + self.gross_sales - self.order_spend - self.operating_paid
        stock_ok = self._available() == self.received - self.sold - self.expired
        invariant_ok = (balance_ok and stock_ok and self.cash >= 0 and self._available() >= 0
                        and self._available() + self._in_transit() <= self.capacity and self.unpaid_fees == 0)
        service = self.sold / self.opportunities if self.opportunities else 0.0
        finished = self.day == self.horizon
        profitable = self.cash >= self.cash_target
        served = service >= self.service_target and self.selling_days >= self.selling_days_target
        outcome = (int(finished) + int(profitable) + int(served)) / 3
        return Verdict(
            success=bool(schema_ok and repaired == len(expected) and finished and profitable and served and invariant_ok),
            recovery=recovery, outcome=outcome, safety=float(invariant_ok),
            details={"fill_schema_valid": schema_ok, "repaired_fields": repaired,
                     "final_cash_cents": self.cash, "cash_target_cents": self.cash_target,
                     "day": self.day, "horizon_days": self.horizon, "service_rate": service,
                     "units_sold": self.sold, "unpaid_fees_cents": self.unpaid_fees,
                     "selling_days": self.selling_days, "selling_days_target": self.selling_days_target,
                     "accounting_invariants_hold": invariant_ok},
        )

    def reference_answer(self) -> dict:
        return {"lead_base_days": self._lead_base, "weekend_extra_days": self._weekend_extra,
                "fixed_fee_cents": self._fixed_fee, "case_fee_cents": self._case_fee,
                "receipt_event": "delivery"}

    def reference_actions(self) -> list[tuple[str, dict]]:
        """Evaluator-only constructive solvability witness, not AI performance.

        Plan by running an independent copy, then replay the resulting actions.
        It uses expected demand, never the hidden future daily noise array.
        """
        sim = copy.deepcopy(self)
        actions: list[tuple[str, dict]] = []

        def do(name: str, args: dict) -> None:
            sim.query(name, args)
            actions.append((name, args))

        for cases, day in ((1, 0), (2, 0), (1, 5)):
            do("quote", {"supplier": "cedar", "cases": cases, "order_day": day})
        do("set_price", {"price_cents": 280})
        while sim.day < sim.horizon:
            quote = sim._quotation("cedar", 1, sim.day)
            arrival = quote["arrival_day"]
            lead = arrival - sim.day
            desired = sum(sim._forecast(day) + 1 for day in range(sim.day + 1, min(sim.horizon, sim.day + lead + 2) + 1))
            position = sim._available() + sim._in_transit()
            cases = max(0, math.ceil((desired - position) / sim.case_size))
            if cases and arrival <= sim.horizon:
                cases = min(cases, (sim.capacity - position) // sim.case_size)
                while cases and sim._quotation("cedar", cases, sim.day)["total_cents"] > sim.cash:
                    cases -= 1
                if cases:
                    do("order", {"supplier": "cedar", "cases": cases})
            do("advance", {"days": 1})
        return actions
