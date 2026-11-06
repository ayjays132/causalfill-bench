"""Finite procurement under hidden demand, with a separate arena projection.

The runtime records actual invoices, deliveries, sales, disposal and cash. The
pure compiler below constructs its small information/decision game separately.
It neither calls ``query`` nor copies a mutable Task to produce transitions.
All inputs used by a public solver are the contract and quoted economic terms.
"""
from __future__ import annotations

from collections import deque
from copy import deepcopy
import itertools
import json
import re
from typing import NamedTuple

from causalfill.types import Task, Verdict, canonical, fields, strict_int


PROFILE_VERSION = "vending_adaptive_v1"
_RULES = ("current", "xor_calibration", "xor_calibration_previous")
_TERM_KEYS = {"standard_lead_days", "fixed_shipping_cents", "case_shipping_cents", "receipt_event"}
_CONTRACT_KEYS = {
    "profile_version", "forecast_rule", "stages", "products", "worlds",
    "units_per_case", "capacity_units", "round_length_days", "selling_price_cents",
    "unit_cost_cents", "operating_fee_cents", "express_surcharge_cents",
    "initial_cash_cents", "cash_target_cents",
}


def _validate_terms(terms: dict) -> dict:
    fields(terms, _TERM_KEYS)
    strict_int(terms["standard_lead_days"], 1, 2, "standard_lead_days")
    strict_int(terms["fixed_shipping_cents"], 0, 1000, "fixed_shipping_cents")
    strict_int(terms["case_shipping_cents"], 0, 1000, "case_shipping_cents")
    if type(terms["receipt_event"]) is not str or terms["receipt_event"] != "delivery":
        raise ValueError("stock is received only at delivery")
    return terms


def _validate_contract(contract: dict, terms: dict) -> None:
    fields(contract, _CONTRACT_KEYS)
    _validate_terms(terms)
    if contract["profile_version"] != PROFILE_VERSION or type(contract["forecast_rule"]) is not str or contract["forecast_rule"] not in _RULES:
        raise ValueError("unsupported adaptive-market profile or forecast rule")
    stages = strict_int(contract["stages"], 2, 4, "stages")
    products = contract["products"]
    if (type(products) is not list or len(products) != 2 or any(type(x) is not str or
            re.fullmatch(r"[a-z][a-z0-9_]{0,15}", x) is None for x in products) or len(set(products)) != 2):
        raise ValueError("two distinct bounded product identifiers are required")
    size = strict_int(contract["units_per_case"], 1, 12, "units_per_case")
    if type(contract["capacity_units"]) is not int or contract["capacity_units"] != size:
        raise ValueError("one indivisible case exactly fills storage")
    if type(contract["round_length_days"]) is not int or contract["round_length_days"] != 2:
        raise ValueError("round length must be two days")
    for key in ("selling_price_cents", "unit_cost_cents", "operating_fee_cents", "express_surcharge_cents"):
        strict_int(contract[key], 1, 1000, key)
    strict_int(contract["initial_cash_cents"], 1, 1000000, "initial_cash_cents")
    strict_int(contract["cash_target_cents"], 1, 1000000, "cash_target_cents")
    worlds = contract["worlds"]
    if type(worlds) is not list or not 2 <= len(worlds) <= 32:
        raise ValueError("2..32 candidate worlds are required")
    seen = set()
    for world in worlds:
        fields(world, {"demand", "calibration"})
        if type(world["demand"]) is not list or len(world["demand"]) != stages:
            raise ValueError("each world needs one demand bit per stage")
        bits = tuple(strict_int(v, 0, 1, "demand bit") for v in world["demand"])
        key = strict_int(world["calibration"], 0, 1, "calibration")
        if contract["forecast_rule"] == "current" and key != 0:
            raise ValueError("the current forecast family has public zero calibration")
        if (bits, key) in seen:
            raise ValueError("duplicate candidate world")
        seen.add((bits, key))
    invoice = _standard_invoice(contract, terms)
    profit = size * contract["selling_price_cents"] - invoice - contract["operating_fee_cents"]
    if profit <= contract["express_surcharge_cents"]:
        raise ValueError("standard margin must exceed the express surcharge")
    target = contract["initial_cash_cents"] + stages * profit - contract["express_surcharge_cents"]
    if contract["cash_target_cents"] != target:
        raise ValueError("cash target must allow exactly one express surcharge")
    worst_spend = stages * (invoice + contract["express_surcharge_cents"] + contract["operating_fee_cents"])
    if contract["initial_cash_cents"] < worst_spend:
        raise ValueError("initial cash must fund every admissible order prefix without sales")


def _standard_invoice(contract: dict, terms: dict) -> int:
    return (contract["units_per_case"] * contract["unit_cost_cents"]
            + terms["fixed_shipping_cents"] + terms["case_shipping_cents"])


def _forecast_value(contract: dict, world: dict, stage: int) -> int:
    value = world["demand"][stage]
    if contract["forecast_rule"] != "current":
        value ^= world["calibration"]
    if contract["forecast_rule"] == "xor_calibration_previous" and stage:
        value ^= world["demand"][stage - 1]
    return value


def market_action_request(contract: dict, action_id: str) -> tuple[str, dict]:
    """Translate a finite-arena action to its exact primitive public tool call."""
    if type(action_id) is not str:
        raise ValueError("action id must be a string")
    if action_id in ("calibrate", "forecast", "assay", "settle"):
        return action_id, {}
    match = re.fullmatch(r"order:([01]):(standard|express)", action_id)
    if match is None:
        raise ValueError("unknown market action")
    return "order", {"product": contract["products"][int(match.group(1))], "supplier": match.group(2)}


class _ArenaState(NamedTuple):
    world: int
    stage: int = 0
    calibrated: bool = False
    sample: str = ""
    pending_product: int = -1
    pending_supplier: str = ""
    express_orders: int = 0
    breach: str = ""


def _arena_outcome(contract: dict, state: _ArenaState) -> str:
    return "failure" if state.breach else "success" if state.stage == contract["stages"] else "live"


def _arena_observation(contract: dict, terms: dict, state: _ArenaState) -> str:
    """Closed-form projection, separate from the runtime's financial ledger."""
    world, size = contract["worlds"][state.world], contract["units_per_case"]
    pending = state.pending_product >= 0
    unserved = state.breach in ("unserved_no_order", "unserved_wrong_stock")
    skipped = state.breach == "unserved_no_order"
    orders = state.stage + int(pending) - int(skipped)
    sold = (state.stage - int(unserved)) * size
    cash = (contract["initial_cash_cents"] + sold * contract["selling_price_cents"]
            - orders * _standard_invoice(contract, terms)
            - state.express_orders * contract["express_surcharge_cents"]
            - state.stage * contract["operating_fee_cents"])
    sample = None
    if state.sample:
        value = _forecast_value(contract, world, state.stage) if state.sample == "forecast" else world["demand"][state.stage]
        sample = {"kind": state.sample, "value": value}
    order = None
    if pending:
        lead = 1 if state.pending_supplier == "express" else terms["standard_lead_days"]
        order = {"product": contract["products"][state.pending_product], "supplier": state.pending_supplier,
                 "units": size, "arrival_day": state.stage * 2 + lead}
    return canonical({
        "profile_version": PROFILE_VERSION, "stage": state.stage, "stages": contract["stages"],
        "day": state.stage * 2, "status": _arena_outcome(contract, state),
        "phase": "closed" if _arena_outcome(contract, state) != "live" else "ordered" if pending else "open",
        "calibration_observation": world["calibration"] if state.calibrated else None,
        "sample": sample, "pending_order": order, "available_units": 0,
        "pending_units": size if pending else 0, "cash_cents": cash,
        "cash_target_cents": contract["cash_target_cents"], "express_orders": state.express_orders,
        "past_demand": world["demand"][:state.stage], "units_sold": sold,
        "units_received": (state.stage - int(skipped)) * size,
        "units_expired": size if state.breach == "unserved_wrong_stock" else 0,
        "breach": state.breach or None,
    })


def _arena_actions(contract: dict, state: _ArenaState) -> list[str]:
    if _arena_outcome(contract, state) != "live":
        return []
    if state.pending_product >= 0:
        return ["settle"]
    actions = []
    if not state.calibrated:
        actions.append("calibrate")
    if not state.sample:
        actions.extend(("forecast", "assay"))
    actions.extend(f"order:{product}:{supplier}" for product in (0, 1) for supplier in ("standard", "express"))
    return actions + ["settle"]


def _arena_step(contract: dict, state: _ArenaState, action: str) -> _ArenaState:
    if action == "calibrate":
        return state._replace(calibrated=True)
    if action in ("forecast", "assay"):
        return state._replace(sample=action)
    if action.startswith("order:"):
        _, product, supplier = action.split(":")
        return state._replace(pending_product=int(product), pending_supplier=supplier,
                              express_orders=state.express_orders + int(supplier == "express"))
    demand = contract["worlds"][state.world]["demand"][state.stage]
    breach = ("unserved_no_order" if state.pending_product < 0 else
              "unserved_wrong_stock" if state.pending_product != demand else
              "cash_target_unreachable" if state.express_orders > 1 else "")
    return state._replace(stage=state.stage + 1, sample="", pending_product=-1,
                          pending_supplier="", breach=breach)


def _compile_market_game(contract: dict, terms: dict):
    _validate_contract(contract, terms)
    actions = [{"id": name, "cost": cost, "kind": "observe"}
               for name, cost in (("calibrate", 1), ("forecast", 1), ("assay", 2))]
    actions += [{"id": f"order:{product}:{supplier}", "cost": 2, "kind": "act"}
                for product in (0, 1) for supplier in ("standard", "express")]
    actions.append({"id": "settle", "cost": 1, "kind": "act"})
    concrete: list[_ArenaState] = []
    index: dict[_ArenaState, int] = {}
    predecessors: list[tuple[int, str] | None] = []
    queue = deque()

    def intern(state, predecessor=None):
        if state not in index:
            index[state] = len(concrete)
            concrete.append(state)
            predecessors.append(predecessor)
            queue.append(state)
        return index[state]

    initial = [intern(_ArenaState(world)) for world in range(len(contract["worlds"]))]
    states = []
    while queue:
        state = queue.popleft()
        node_id = index[state]
        transitions = [{"action": action, "next": intern(_arena_step(contract, state, action), (node_id, action))}
                       for action in _arena_actions(contract, state)]
        outcome = _arena_outcome(contract, state)
        rank = (6 * (contract["stages"] - state.stage) + int(not state.calibrated)
                + int(not state.sample) + int(state.pending_product < 0)) if outcome == "live" else 0
        states.append({"rank": rank, "observation": _arena_observation(contract, terms, state),
                       "outcome": outcome, "transitions": transitions})
    return {"schema_version": "finite-belief-game-v1", "actions": actions,
            "states": states, "initial": initial}, index, concrete, predecessors


def compile_market_game(contract: dict, recovered_terms: dict) -> dict:
    """Compile only public hypotheses and observed economic terms into an arena.

    This exposes all possible worlds, never which world is current. It is an
    evaluator/constructive-reference utility, not an episode tool.
    """
    return _compile_market_game(deepcopy(contract), deepcopy(recovered_terms))[0]


class VendingAdaptiveTask(Task):
    family = "vending_adaptive"

    def __init__(self, seed: int, split: str = "dev", difficulty: int = 2, twin: int = 0):
        super().__init__(seed, split, difficulty, twin)
        stages, size = difficulty + 1, self.rng.choice((4, 6))
        unit, price = self.rng.randint(45, 75), self.rng.randint(160, 190)
        fee, premium = self.rng.randint(10, 25), self.rng.randint(30, 60)
        self._terms = {"standard_lead_days": self.rng.randint(1, 2),
                       "fixed_shipping_cents": self.rng.randint(20, 50),
                       "case_shipping_cents": 0 if split == "train" else self.rng.randint(4, 12),
                       "receipt_event": "delivery"}
        words = [list(bits) for bits in itertools.product((0, 1), repeat=stages)
                 if split != "transfer" or len(set(bits)) == 2]
        worlds = [{"demand": bits, "calibration": key} for bits in words
                  for key in ((0,) if split == "train" else (0, 1))]
        self.rng.shuffle(worlds)
        chosen = self.rng.randrange(len(worlds))
        if twin:
            counterpart = {"demand": [1 - bit for bit in worlds[chosen]["demand"]],
                           "calibration": worlds[chosen]["calibration"]}
            chosen = worlds.index(counterpart)
        self._world_index = chosen
        standard = size * unit + self._terms["fixed_shipping_cents"] + self._terms["case_shipping_cents"]
        profit = size * price - standard - fee
        self._contract = {
            "profile_version": PROFILE_VERSION, "forecast_rule": _RULES[("train", "dev", "transfer").index(split)],
            "stages": stages, "products": ["tea", "cocoa"], "worlds": worlds,
            "units_per_case": size, "capacity_units": size, "round_length_days": 2,
            "selling_price_cents": price, "unit_cost_cents": unit,
            "operating_fee_cents": fee, "express_surcharge_cents": premium,
            "initial_cash_cents": 5000,
            "cash_target_cents": 5000 + stages * profit - premium,
        }
        _validate_contract(self._contract, self._terms)
        self.stage = 0
        self.cash = self._contract["initial_cash_cents"]
        self.pending: dict | None = None
        self.available = 0
        self.calibration_observation: int | None = None
        self.sample: dict | None = None
        self.express_orders = 0
        self.past_demand: list[int] = []
        self.breach = ""
        self.sold = self.received = self.expired = self.order_spend = self.sales_revenue = self.operating_paid = 0
        self.events: list[dict] = []
        self._arena_cache = None
        self.budget, self.max_calls = 5 * stages + 8, 6 * stages + 20
        self.twin_kind = "demand_trajectory"
        self.structural_signature = f"vending_adaptive:{self._contract['forecast_rule']}:rounds-{stages}:v1"
        self.slots = {
            "standard_lead_days": {"type": "integer", "description": "Standard shipping lead time in days."},
            "fixed_shipping_cents": {"type": "integer", "description": "Fixed standard shipping fee per order."},
            "case_shipping_cents": {"type": "integer", "description": "Additional standard shipping fee per indivisible case."},
            "receipt_event": {"type": "string", "description": "Event that makes invoiced goods physically available."},
        }
        self.tools = {
            "quote": {"cost": 1, "arguments": {"supplier": "standard or express", "cases": "integer 1..3"},
                      "description": "Hypothetical itemized quote. Static terms; no current/future demand is revealed."},
            "calibrate": {"cost": 1, "arguments": {}, "description": "Once per episode, before an order, observe the shared forecast calibration bit."},
            "forecast": {"cost": 1, "arguments": {}, "description": "Use this round's single diagnostic sample to observe its coded forecast bit."},
            "assay": {"cost": 2, "arguments": {}, "description": "Alternative diagnostic sample: observe the current demanded-product bit directly."},
            "order": {"cost": 2, "arguments": {"product": "tea or cocoa", "supplier": "standard or express"},
                      "description": "Pay for one indivisible case, irreversibly. One case fills storage. Invoice creates pending stock; no stock is available yet."},
            "settle": {"cost": 1, "arguments": {}, "description": "Advance to this round's day-2 market: receive deliveries, serve requests, dispose leftovers and pay the operating fee."},
            "status": {"cost": 1, "arguments": {}, "description": "Repeat the full public observation and accounting totals; no new latent information."},
            "ledger": {"cost": 1, "arguments": {"last_n": "integer 1..100"}, "description": "Read prior invoices, deliveries, sales, expiry and fees. No future events."},
        }
        self.prompt = (
            "Fill four holes in the procurement skill AND fulfill every round's real market requests. "
            "Each round demands one whole case of either tea or cocoa; a case fills the entire cold store. "
            "Buying the wrong product loses that service contract irreversibly. Quotes reveal economic terms, not demand. "
            "Use the public candidate-world table and any suitable observations to decide what to buy. "
            "Choose either supplier; the final cash goal allows one express surcharge in total. "
            f"Complete {stages} rounds with all requests served and cash at least {self._contract['cash_target_cents']} cents. "
            "No particular sensor or observation count is required for scoring. "
            "Read /market/contract.json, /skills/procurement.txt and /docs/accounting.txt."
        )
        self.files = {
            "/market/contract.json": json.dumps(self._contract, indent=2),
            "/skills/procurement.txt": (
                "STANDARD PROCUREMENT — four missing fields\n"
                "arrival_day = order_day + [[standard_lead_days]]\n"
                "shipping_cents = [[fixed_shipping_cents]] + [[case_shipping_cents]] * cases\n"
                "Stock becomes available at [[receipt_event]], not when payment and invoice occur.\n"
                "Terms are fixed within this episode. Compare hypothetical quotes for one and two cases.\n"
                "Actual orders accept one whole case only, because it fills the cold store.\n"
                "Express uses the same items/shipping terms plus the public fixed surcharge, and arrives in one day.\n"
            ),
            "/docs/accounting.txt": (
                "All money is integer cents. No borrowing, refunds, resale, or terminal stock value.\n"
                "The invoice debits the full item and shipping total immediately. Available stock stays zero until delivery.\n"
                "A round starts on day 2*stage and ends two days later. Both suppliers arrive by its market deadline.\n"
                "At settle: record physical delivery, sell only the demanded product at the fixed public price, "
                "expire every unsold unit, then pay the operating fee. No stock carries into the next round.\n"
                "Each round requires units_per_case requests of one product; price cannot suppress this denominator.\n"
                "The business service contract closes irreversibly on any missed request. It also closes if "
                "the maximum possible future cash cannot reach the published cash target.\n"
                "Status/ledger expose past accounting only. Invalid operations leave all domain state unchanged.\n"
                "Forecast rules: current = demand bit; xor_calibration = demand XOR calibration; "
                "xor_calibration_previous = demand XOR calibration XOR previous demand (previous=0 initially).\n"
                "A round offers one diagnostic sample, either forecast or assay. Calibration is separate and can "
                "be performed once in any open round. Sample/calibration must precede the irreversible order.\n"
                "The candidate-world list is complete and does not mark the true row. In the transfer family "
                "both products occur somewhere, so previous outcomes can occasionally determine a later demand.\n"
            ),
        }

    def _outcome(self) -> str:
        return "failure" if self.breach else "success" if self.stage == self._contract["stages"] else "live"

    def _observation(self) -> str:
        """Emit runtime facts, without calling any finite-arena projection code."""
        pending = ({key: self.pending[key] for key in ("product", "supplier", "units", "arrival_day")}
                   if self.pending else None)
        return canonical({
            "profile_version": PROFILE_VERSION, "stage": self.stage, "stages": self._contract["stages"],
            "day": self.stage * 2, "status": self._outcome(),
            "phase": "closed" if self._outcome() != "live" else "ordered" if self.pending else "open",
            "calibration_observation": self.calibration_observation, "sample": self.sample,
            "pending_order": pending, "available_units": self.available,
            "pending_units": self.pending["units"] if self.pending else 0, "cash_cents": self.cash,
            "cash_target_cents": self._contract["cash_target_cents"], "express_orders": self.express_orders,
            "past_demand": self.past_demand, "units_sold": self.sold, "units_received": self.received,
            "units_expired": self.expired, "breach": self.breach or None,
        })

    def _quote(self, supplier: str, cases: int) -> dict:
        quantity = cases * self._contract["units_per_case"]
        shipping = (self._terms["fixed_shipping_cents"] + cases * self._terms["case_shipping_cents"]
                    + (self._contract["express_surcharge_cents"] if supplier == "express" else 0))
        lead = 1 if supplier == "express" else self._terms["standard_lead_days"]
        return {"supplier": supplier, "cases": cases, "quantity": quantity,
                "unit_cost_cents": self._contract["unit_cost_cents"], "shipping_cents": shipping,
                "total_cents": quantity * self._contract["unit_cost_cents"] + shipping,
                "order_day": 2 * self.stage, "arrival_day": 2 * self.stage + lead}

    def _open(self):
        if self._outcome() != "live":
            raise ValueError("business service contract is closed")
        if self.pending is not None:
            raise ValueError("the irreversible order is pending; settle this round")

    def query(self, name: str, args: dict) -> dict:
        if name == "quote":
            fields(args, {"supplier", "cases"})
            supplier = args["supplier"]
            if type(supplier) is not str or supplier not in ("standard", "express"):
                raise ValueError("supplier must be standard or express")
            cases = strict_int(args["cases"], 1, 3, "cases")
            return {"quote": self._quote(supplier, cases), "observation": self._observation()}
        if name == "status":
            fields(args, set())
            return {"observation": self._observation(), "accounting": {
                "initial_cash_cents": self._contract["initial_cash_cents"],
                "order_spend_cents": self.order_spend, "sales_revenue_cents": self.sales_revenue,
                "operating_paid_cents": self.operating_paid}}
        if name == "ledger":
            fields(args, {"last_n"})
            count = strict_int(args["last_n"], 1, 100, "last_n")
            return {"events": deepcopy(self.events[-count:]), "observation": self._observation()}
        if name in ("calibrate", "forecast", "assay"):
            fields(args, set())
            self._open()
            if name == "calibrate":
                if self.calibration_observation is not None:
                    raise ValueError("calibration experiment already observed")
                self.calibration_observation = self._contract["worlds"][self._world_index]["calibration"]
            else:
                if self.sample is not None:
                    raise ValueError("this round's diagnostic sample is already consumed")
                world = self._contract["worlds"][self._world_index]
                value = _forecast_value(self._contract, world, self.stage) if name == "forecast" else world["demand"][self.stage]
                self.sample = {"kind": name, "value": value}
            return {"observation": self._observation()}
        if name == "order":
            fields(args, {"product", "supplier"})
            self._open()
            product, supplier = args["product"], args["supplier"]
            if type(product) is not str or product not in self._contract["products"]:
                raise ValueError("unknown product")
            if type(supplier) is not str or supplier not in ("standard", "express"):
                raise ValueError("supplier must be standard or express")
            quote = self._quote(supplier, 1)
            if quote["total_cents"] > self.cash:
                raise ValueError("insufficient available cash")
            self.cash -= quote["total_cents"]
            self.order_spend += quote["total_cents"]
            self.express_orders += int(supplier == "express")
            self.pending = {"product": product, "supplier": supplier, "units": quote["quantity"],
                            "arrival_day": quote["arrival_day"]}
            event = {"event": "invoice", "stage": self.stage, "product": product,
                     "supplier": supplier, **quote}
            self.events.append(event)
            return {"invoice": deepcopy(event), "observation": self._observation()}
        if name == "settle":
            fields(args, set())
            if self._outcome() != "live":
                raise ValueError("business service contract is closed")
            world = self._contract["worlds"][self._world_index]
            bit, size = world["demand"][self.stage], self._contract["units_per_case"]
            product = self._contract["products"][bit]
            sold = 0
            if self.pending is not None:
                self.available += self.pending["units"]
                self.received += self.pending["units"]
                self.events.append({"event": "delivery", "stage": self.stage,
                                    "day": self.pending["arrival_day"], "product": self.pending["product"],
                                    "quantity": self.pending["units"]})
                if self.pending["product"] == product:
                    sold = min(self.available, size)
                    self.available -= sold
            revenue = sold * self._contract["selling_price_cents"]
            self.cash += revenue
            self.sales_revenue += revenue
            self.sold += sold
            expired = self.available
            self.expired += expired
            self.available = 0
            fee = self._contract["operating_fee_cents"]
            self.cash -= fee
            self.operating_paid += fee
            record = {"event": "market_close", "stage": self.stage, "day": 2 * (self.stage + 1),
                      "demanded_product": product, "demand_units": size, "sold_units": sold,
                      "expired_units": expired, "revenue_cents": revenue,
                      "operating_fee_cents": fee, "cash_cents": self.cash}
            self.events.append(record)
            if sold != size:
                self.breach = "unserved_no_order" if self.pending is None else "unserved_wrong_stock"
            self.past_demand.append(bit)
            self.stage += 1
            self.pending, self.sample = None, None
            best_profit = (size * self._contract["selling_price_cents"]
                           - self._quote("standard", 1)["total_cents"] - fee)
            if not self.breach and self.cash + (self._contract["stages"] - self.stage) * best_profit < self._contract["cash_target_cents"]:
                self.breach = "cash_target_unreachable"
            return {"market": deepcopy(record), "observation": self._observation()}
        raise ValueError("unknown adaptive vending tool")

    def evaluate(self, fill: dict) -> Verdict:
        schema = type(fill) is dict and set(fill) == _TERM_KEYS
        if schema:
            schema = (all(type(fill[key]) is int for key in _TERM_KEYS if key != "receipt_event")
                      and type(fill["receipt_event"]) is str)
        repaired = sum(fill[key] == value for key, value in self._terms.items()) if schema else 0
        accounting = (self.cash == self._contract["initial_cash_cents"] + self.sales_revenue - self.order_spend - self.operating_paid
                      and self.available == self.received - self.sold - self.expired
                      and 0 <= self.available + (self.pending["units"] if self.pending else 0) <= self._contract["capacity_units"]
                      and self.cash >= 0)
        served = self.sold == self._contract["stages"] * self._contract["units_per_case"]
        finished = self.stage == self._contract["stages"]
        cash_goal = self.cash >= self._contract["cash_target_cents"]
        success = schema and repaired == len(_TERM_KEYS) and finished and served and cash_goal and accounting and not self.breach
        return Verdict(bool(success), repaired / len(_TERM_KEYS),
                       (int(finished) + int(served) + int(cash_goal)) / 3, float(accounting),
                       {"fill_schema_valid": schema, "repaired_fields": repaired,
                        "stages_completed": self.stage, "stages_required": self._contract["stages"],
                        "cash_cents": self.cash, "cash_target_cents": self._contract["cash_target_cents"],
                        "units_sold": self.sold, "required_units": self._contract["stages"] * self._contract["units_per_case"],
                        "express_orders": self.express_orders, "breach": self.breach or None,
                        "accounting_invariants_hold": accounting})

    def reference_answer(self) -> dict:
        return deepcopy(self._terms)

    def reference_actions(self) -> list[tuple[str, dict]]:
        sim = self.clone_for_world(self._world_index)
        actions = []

        def call(name, arguments):
            result = {"content": sim.files[arguments["path"]]} if name == "read_file" else sim.query(name, arguments)
            actions.append((name, deepcopy(arguments)))
            return result

        solve_vending_adaptive(sim.public(), call)
        return actions

    def _compiled(self):
        if self._arena_cache is None:
            self._arena_cache = _compile_market_game(self._contract, self._terms)
        return self._arena_cache

    def game_statement(self) -> dict:
        return deepcopy(self._compiled()[0])

    def game_state_id(self) -> int:
        pending_product = self._contract["products"].index(self.pending["product"]) if self.pending else -1
        state = _ArenaState(self._world_index, self.stage, self.calibration_observation is not None,
                            self.sample["kind"] if self.sample else "", pending_product,
                            self.pending["supplier"] if self.pending else "", self.express_orders, self.breach)
        return self._compiled()[1][state]

    def game_replay_witness(self, node_id: int) -> dict:
        game, _, states, predecessors = self._compiled()
        strict_int(node_id, 0, len(game["states"]) - 1, "node_id")
        actions, cursor = [], node_id
        while predecessors[cursor] is not None:
            cursor, action = predecessors[cursor]
            actions.append(action)
        return {"world_index": states[cursor].world, "actions": list(reversed(actions))}

    def clone_for_world(self, index: int):
        """Evaluator-only fresh instance; selecting a world is never a public tool."""
        strict_int(index, 0, len(self._contract["worlds"]) - 1, "world_index")
        task = VendingAdaptiveTask(self.seed, self.split, self.difficulty, 0)
        task._world_index = index
        # The compiled table depends only on the common contract/terms. Public
        # access returns a defensive copy and neither runtime mutates this cache.
        task._arena_cache = self._arena_cache
        return task


def solve_vending_adaptive(public: dict, call) -> tuple[dict, bool]:
    """Constructive controller using only the supplied public tool callback."""
    if type(public) is not dict or public.get("family") != "vending_adaptive":
        raise ValueError("expected an adaptive-vending public episode")

    def use(name, args):
        response = call(name, args)
        if "error" in response:
            raise ValueError(response["error"])
        return response

    contract = json.loads(use("read_file", {"path": "/market/contract.json"})["content"])
    first = use("quote", {"supplier": "standard", "cases": 1})["quote"]
    second = use("quote", {"supplier": "standard", "cases": 2})["quote"]
    per_case = second["shipping_cents"] - first["shipping_cents"]
    fill = {"standard_lead_days": first["arrival_day"] - first["order_day"],
            "fixed_shipping_cents": first["shipping_cents"] - per_case,
            "case_shipping_cents": per_case, "receipt_event": "delivery"}
    _validate_contract(contract, fill)
    calibration = 0
    if contract["forecast_rule"] != "current":
        observation = json.loads(use("calibrate", {})["observation"])
        calibration = observation["calibration_observation"]
    previous, possible = 0, deepcopy(contract["worlds"])
    for stage in range(contract["stages"]):
        possibilities = {row["demand"][stage] for row in possible}
        if len(possibilities) == 1:
            demand = next(iter(possibilities))
        else:
            observation = json.loads(use("forecast", {})["observation"])
            demand = observation["sample"]["value"]
            if contract["forecast_rule"] != "current":
                demand ^= calibration
            if contract["forecast_rule"] == "xor_calibration_previous":
                demand ^= previous
        use("order", {"product": contract["products"][demand], "supplier": "standard"})
        observation = json.loads(use("settle", {})["observation"])
        previous = observation["past_demand"][-1]
        possible = [row for row in possible if row["demand"][:stage + 1] == observation["past_demand"]]
    return fill, False
