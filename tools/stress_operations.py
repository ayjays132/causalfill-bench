#!/usr/bin/env python3
"""Deterministic evaluator-development stress tests, not a solver benchmark.

Run from the repository root, for example::

    python tools/stress_operations.py --seed-count 64 --metamorphic-seed-count 16 \
        --geometry-cases 20000 --actions-per-episode 80 \
        --output reports/stress-v0.3/operations.json

The independent oracles are a unit-by-unit inventory/accounting simulator, an
exact decimal-rational segment/face geometry check, a separate grid interpreter,
and a dense affine operator reconstructed by full-basis interventions. Internal
state is inspected only as an evaluator-development check. These are not model
runs, and the full-basis sparse audit deliberately does not claim budgeted play.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from fractions import Fraction
import hashlib
import itertools
import json
import math
from pathlib import Path
import random
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from causalfill.domains.grid import GridTask  # noqa: E402
from causalfill.domains.latent import (  # noqa: E402
    LatentTask, SparseLatentTask, recover_sparse_operator, sparse_probe_plan,
)
from causalfill.domains.robotics import RoboticsTask, segment_intersects_box  # noqa: E402
from causalfill.domains.robotics_barrier import (  # noqa: E402
    RoboticsBarrierTask, build_barrier_pair_certificate, verify_barrier_certificate,
)
from causalfill.domains.vending import VendingTask  # noqa: E402
from causalfill.domains.workflow import WorkflowTask, expression  # noqa: E402
from causalfill.session import Session  # noqa: E402
from causalfill.types import digest  # noqa: E402

SPLITS = ("train", "dev", "transfer")


@dataclass
class Results:
    name: str
    counters: Counter = field(default_factory=Counter)
    failure_counts: Counter = field(default_factory=Counter)
    examples: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    started: float = field(default_factory=time.perf_counter)
    _examples_per_label: Counter = field(default_factory=Counter)

    def check(self, condition: bool, label: str, case: Any = None,
              kind: str = "oracle_mismatch", **details: Any) -> None:
        self.counters["checks"] += 1
        self.counters[f"check:{label}"] += 1
        if condition:
            self.counters["passed_checks"] += 1
            return
        self.failure_counts[kind] += 1
        self.failure_counts[f"{kind}:{label}"] += 1
        if self._examples_per_label[label] < 5 and len(self.examples) < 100:
            self._examples_per_label[label] += 1
            self.examples.append({"kind": kind, "label": label, "case": case, **details})

    def acceptance(self, actual: bool, expected: bool, label: str,
                   case: Any = None, **details: Any) -> None:
        self.counters["verdict_checks"] += 1
        self.counters["expected_accepts" if expected else "expected_rejects"] += 1
        self.check(actual == expected, label, case,
                   "false_accept" if actual else "false_reject", **details)

    def exception(self, label: str, case: Any, exc: Exception) -> None:
        self.check(False, label, case, "unexpected_exception",
                   exception_type=type(exc).__name__, exception=str(exc)[:300])

    def export(self) -> dict[str, Any]:
        return {"name": self.name, "elapsed_seconds": round(time.perf_counter()-self.started, 6),
                "counters": dict(sorted(self.counters.items())),
                "failure_counts": dict(sorted(self.failure_counts.items())),
                "examples": self.examples, "notes": self.notes}


def seed_list(count: int, master: int) -> list[int]:
    fixed = [0, 1, 2, 17, 101, 2**63 - 1]
    rng = random.Random(master)
    while len(fixed) < count:
        candidate = rng.randrange(2**16, 2**63 - 1)
        if candidate not in fixed:
            fixed.append(candidate)
    return fixed[:count]


def configurations(seeds: list[int]):
    return itertools.product(seeds, SPLITS, (1, 2, 3), (0, 1))


def case_id(seed: int, split: str, difficulty: int, twin: int) -> dict[str, Any]:
    return dict(seed=seed, split=split, difficulty=difficulty, twin=twin)


def decimal(value: int | float) -> Fraction:
    """JSON decimal semantics, including finite floats' shortest decimal form."""
    return Fraction(str(value))


def exact_segment_box(start, end, lower, upper, clearance=0) -> bool:
    """Independent endpoint / six-face intersection oracle; no slab intervals."""
    start, end = list(map(decimal, start)), list(map(decimal, end))
    clearance = decimal(clearance)
    lower = [decimal(x) - clearance for x in lower]
    upper = [decimal(x) + clearance for x in upper]

    def inside(point):
        return all(lo <= value <= hi for value, lo, hi in zip(point, lower, upper))

    if inside(start) or inside(end):
        return True
    direction = [b-a for a, b in zip(start, end)]
    for axis in range(3):
        if direction[axis] == 0:
            continue
        for face in (lower[axis], upper[axis]):
            parameter = (face-start[axis])/direction[axis]
            if 0 <= parameter <= 1:
                point = [a+parameter*d for a, d in zip(start, direction)]
                if inside(point):
                    return True
    return False


def exact_path(start, target, waypoints, obstacles, bounds, clearance):
    points = [start, *waypoints, target]
    margin = decimal(clearance)
    inside = all(decimal(bounds[0][axis])+margin <= decimal(point[axis])
                 <= decimal(bounds[1][axis])-margin
                 for point in points for axis in range(3))
    hit = any(exact_segment_box(a, b, box["lower"], box["upper"], clearance)
              for a, b in zip(points, points[1:]) for box in obstacles)
    return not hit, inside


def linear_solve(matrix, rhs):
    """Small exact Gaussian elimination used only by the independent audit."""
    rows = [[decimal(x) for x in row]+[decimal(y)] for row, y in zip(matrix, rhs)]
    for column in range(len(rows)):
        pivot = next(index for index in range(column, len(rows)) if rows[index][column])
        rows[column], rows[pivot] = rows[pivot], rows[column]
        divisor = rows[column][column]
        rows[column] = [value/divisor for value in rows[column]]
        for index in range(len(rows)):
            if index != column:
                factor = rows[index][column]
                rows[index] = [a-factor*b for a, b in zip(rows[index], rows[column])]
    return [row[-1] for row in rows]


def recover_camera_target(task):
    workspace = json.loads(task.files["/scene/workspace.json"])
    known = [[], [], []]
    material = None
    for view in workspace["camera_views"]:
        reading = task.query("camera", {"view": view})
        axes = reading["projection_axes"]
        anchors = reading["fiducials"]
        design = [[anchor["world"][axes[0]], anchor["world"][axes[1]], 1]
                  for anchor in anchors]
        image_x = linear_solve(design, [anchor["image"][0] for anchor in anchors])
        image_y = linear_solve(design, [anchor["image"][1] for anchor in anchors])
        for obj in reading["objects"]:
            if obj["id"] != workspace["target_id"]:
                continue
            projected = [decimal(obj["image"][0])-image_x[2],
                         decimal(obj["image"][1])-image_y[2]]
            position = linear_solve([image_x[:2], image_y[:2]], projected)
            for axis, value in zip(axes, position):
                known[axis].append(value)
            material = obj["material"]
    if any(not values or len(set(values)) != 1 for values in known):
        raise AssertionError("camera evidence is incomplete or inconsistent")
    return workspace, [float(values[0]) for values in known], material


def stress_geometry(count: int, master: int) -> dict:
    result = Results("geometry")
    rng = random.Random(master+31)
    result.notes.append("Exact decimal-rational oracle tests segment endpoints and all six box faces; the implementation under test uses its own predicate.")
    special = []
    for gap in (-1e-5, -1e-7, -2e-8, -1e-8, -5e-9, -1e-10, 0,
                1e-10, 5e-9, 1e-8, 2e-8, 1e-7, 1e-5):
        for z in (1, 1.5, 2):
            special.append(([0, 2+gap, z], [3, 2+gap, z], [1, 1, 1], [2, 2, 2], 0))
            special.append(([0, 2+gap, z], [2+gap, 0, z], [1, 1, 1], [2, 2, 2], 0))
        special.append(([2+gap, 1.5, 1.5], [2+gap, 1.5, 1.5], [1, 1, 1], [2, 2, 2], 0))
    for scale in (1, 10, 100, 400):
        for gap in (1e-9, 1e-8, 1e-7, 1e-6):
            special.append(([-scale, 2+gap, 1.5], [2+gap, -scale, 1.5],
                            [0, 0, 1], [1, 1, 2], 0))
    for index in range(count):
        if index < len(special):
            start, end, lo, hi, clearance = special[index]
        else:
            lo = [rng.randint(-80, 80)/4 for _ in range(3)]
            hi = [a+rng.randint(0, 40)/4 for a in lo]
            start = [rng.randint(-120, 120)/4 for _ in range(3)]
            end = [rng.randint(-120, 120)/4 for _ in range(3)]
            if index % 9 == 0:
                end = list(start)
            clearance = rng.choice((0, 0.25, 0.5, 1))
        expected = exact_segment_box(start, end, lo, hi, clearance)
        transforms = [(start, end, lo, hi, clearance),
                      (end, start, lo, hi, clearance),
                      (start[1:]+start[:1], end[1:]+end[:1], lo[1:]+lo[:1], hi[1:]+hi[:1], clearance)]
        for variant, values in enumerate(transforms):
            actual = segment_intersects_box(*values)
            result.counters["segment_comparisons"] += 1
            # Treat collision-free as the accepted/safe answer.
            result.acceptance(not actual, not expected, "exact_segment_geometry",
                              {"index": index, "variant": variant},
                              start=values[0], end=values[1], lower=values[2],
                              upper=values[3], clearance=values[4],
                              actual_collision=actual, expected_collision=expected)
    return result.export()


def stress_robotics(seeds: list[int], master: int) -> dict:
    result = Results("robotics")
    result.notes.append("Targets are reconstructed by independent exact Gaussian calibration from camera observations. All route verdicts use the independent face-intersection oracle.")
    result.notes.append("A fixed z=10 detour and fixed 0.5 N force is a legal shortcut control; successes are not classified as verifier false accepts.")
    for seed, split, difficulty, twin in configurations(seeds):
        identity = case_id(seed, split, difficulty, twin)
        result.counters["episodes"] += 1
        try:
            task = RoboticsTask(seed, split, difficulty, twin)
            workspace, target, material = recover_camera_target(task)
            obstacles = task.query("lidar", {})["occupied_boxes"]
            bounds, clearance = workspace["bounds"], workspace["gripper_clearance"]
            start = workspace["start"]
            force_max = workspace["material_force_limits_n"][material]
            base = {"target_world_position": target,
                    "safe_waypoints": [[start[0], start[1], 10], [target[0], target[1], 10]],
                    "grasp_precondition": {"gripper": "open", "force_limit_n": 0.5}}
            candidates = [("constant_route_force", deepcopy(base))]
            item = deepcopy(base)
            item["safe_waypoints"] = []
            candidates.append(("direct_route", item))
            for force in (0, math.nextafter(0.5, 0), 0.5, 0.75, force_max,
                          math.nextafter(force_max, math.inf), -0.001):
                item = deepcopy(base)
                item["grasp_precondition"]["force_limit_n"] = force
                candidates.append(("force_boundary", item))
            for gap in (-2e-8, -5e-9, 0, 5e-9, 2e-8):
                item = deepcopy(base)
                item["safe_waypoints"][0][0] = clearance+gap
                candidates.append(("workspace_boundary", item))
            roof = obstacles[0]["upper"][2]+clearance
            for gap in (-2e-8, -5e-9, 0, 5e-9, 2e-8, 0.1):
                item = deepcopy(base)
                item["safe_waypoints"] = [[start[0], start[1], roof+gap],
                                          [target[0], target[1], roof+gap]]
                candidates.append(("obstacle_grazing", item))
            for axis in range(3):
                item = deepcopy(base)
                item["target_world_position"][axis] += 2e-5
                candidates.append(("incorrect_target", item))
            item = deepcopy(base)
            item["grasp_precondition"]["gripper"] = "closed"
            candidates.append(("closed_gripper", item))
            item = deepcopy(base)
            item["safe_waypoints"] = [start[:] for _ in range(14)]+base["safe_waypoints"]
            candidates.append(("maximum_valid_waypoints", item))
            for label, fill in candidates:
                clear, inside = exact_path(start, fill["target_world_position"],
                                           fill["safe_waypoints"], obstacles, bounds, clearance)
                handling = fill["grasp_precondition"]
                expected = (all(abs(a-b) <= 1e-5 for a, b in zip(fill["target_world_position"], target))
                            and clear and inside and handling["gripper"] == "open"
                            and 0.5 <= handling["force_limit_n"] <= force_max)
                verdict = task.evaluate(fill)
                result.acceptance(verdict.success, expected, label, identity,
                                  fill=fill, independent_clear=clear, independent_inside=inside,
                                  verdict=asdict(verdict))
                if label == "constant_route_force":
                    result.counters["constant_route_force_successes"] += int(verdict.success)
                if label == "direct_route":
                    result.counters[f"direct_successes_twin_{twin}"] += int(verdict.success)
            # The probe must answer geometry, never target correctness.
            for probe_target in ([1, 2, 1], [2, 1, 1], target):
                response = task.query("probe_path", {"target_world_position": probe_target,
                                                      "safe_waypoints": []})
                clear, inside = exact_path(start, probe_target, [], obstacles, bounds, clearance)
                result.check(response == {"collision_free": clear, "within_workspace": inside,
                                          "non_destructive": True}, "probe_geometry_only", identity)
            scan = task.query("lidar", {})
            scan["occupied_boxes"].clear()
            result.check(task.query("lidar", {})["occupied_boxes"] == obstacles,
                         "defensive_lidar_copy", identity)
        except Exception as exc:
            result.exception("robotics_episode", identity, exc)
    return result.export()


def stress_robotics_barrier(seeds: list[int], master: int) -> dict:
    result = Results("robotics_barrier")
    result.notes.append("Separate versioned profile; original robotics routes remain valid. Both twins share public files and cameras. Exact paired certificates establish no common continuous route, while geometry-dependent probes or lidar can distinguish the worlds.")
    result.notes.append("The stress oracle independently reconstructs camera targets and checks route segments by exact face intersection. Forged certificates include recomputed hashes with an uncovered section, shortened walls, or changed shared observations.")
    for seed, split, difficulty in itertools.product(seeds, SPLITS, (1, 2, 3)):
        identity = dict(seed=seed, split=split, difficulty=difficulty)
        result.counters["pairs"] += 1
        result.counters["episodes"] += 2
        try:
            tasks = [RoboticsBarrierTask(seed, split, difficulty, twin) for twin in (0, 1)]
            artifact = build_barrier_pair_certificate(*tasks)
            statement, certificate = artifact["statement"], artifact["certificate"]
            checked = verify_barrier_certificate(statement, certificate)
            result.acceptance(checked["valid"], True, "barrier_pair_certificate", identity, verification=checked)
            result.counters["valid_pair_certificates"] += int(checked["valid"])
            result.check(tasks[0].public() == tasks[1].public() and tasks[0].files == tasks[1].files,
                         "barrier_shared_public_contract", identity)
            for view in ("xy", "xz", "yz"):
                result.check(tasks[0].query("camera", {"view": view}) == tasks[1].query("camera", {"view": view}),
                             "barrier_shared_camera_observations", {**identity, "view": view})
            fixed_successes = []
            for twin, task in enumerate(tasks):
                case = {**identity, "twin": twin}
                workspace, target, material = recover_camera_target(task)
                obstacles = task.query("lidar", {})["occupied_boxes"]
                fill = certificate["routes"][twin]
                clear, inside = exact_path(workspace["start"], fill["target_world_position"],
                                           fill["safe_waypoints"], obstacles, workspace["bounds"], workspace["gripper_clearance"])
                result.check(fill["target_world_position"] == target and clear and inside,
                             "barrier_independent_constructive_route", case)
                result.acceptance(task.evaluate(fill).success, True, "barrier_reference_route", case)
                result.counters["constructive_route_successes"] += int(task.evaluate(fill).success)
                swapped = certificate["routes"][1-twin]
                other_clear, other_inside = exact_path(workspace["start"], swapped["target_world_position"],
                                                       swapped["safe_waypoints"], obstacles, workspace["bounds"], workspace["gripper_clearance"])
                result.check(not other_clear and other_inside, "barrier_swapped_route_independently_collides", case)
                result.acceptance(task.evaluate(swapped).success, False, "barrier_swapped_route_rejected", case)
                fixed = {"target_world_position": target,
                         "safe_waypoints": [[1, 1, 10], [target[0], target[1], 10]],
                         "grasp_precondition": {"gripper": "open", "force_limit_n": 0.5}}
                fixed_clear, fixed_inside = exact_path(workspace["start"], target, fixed["safe_waypoints"],
                                                       obstacles, workspace["bounds"], workspace["gripper_clearance"])
                fixed_verdict = task.evaluate(fixed)
                result.acceptance(fixed_verdict.success, fixed_clear and fixed_inside,
                                  "barrier_fixed_roof_adjudication", case)
                fixed_successes.append(fixed_verdict.success)
                result.counters[f"fixed_roof_successes_twin_{twin}"] += int(fixed_verdict.success)
            result.check(not all(fixed_successes), "barrier_fixed_roof_never_solves_pair", identity)
            route = certificate["routes"][0]
            probe = {key: route[key] for key in ("target_world_position", "safe_waypoints")}
            result.check(tasks[0].query("probe_path", probe)["collision_free"]
                         and not tasks[1].query("probe_path", probe)["collision_free"],
                         "barrier_probe_is_distinguishing_geometry_evidence", identity)

            # Preserve valid alternative witnesses; a certificate is not a
            # comparison with the reference route's text or exact force choice.
            alternative = deepcopy(certificate)
            for route in alternative["routes"]:
                route["safe_waypoints"].insert(0, [1, 1, 1])
                route["grasp_precondition"]["force_limit_n"] = 0.5
            result.acceptance(verify_barrier_certificate(statement, alternative)["valid"], True,
                              "barrier_alternative_valid_certificate", identity)
            forged = []
            altered = deepcopy(artifact)
            altered["certificate"]["routes"].reverse()
            forged.append(("swapped_route_witnesses", altered))
            altered = deepcopy(artifact)
            altered["certificate"]["separator"]["coordinate"] = 1
            forged.append(("nonseparating_plane", altered))
            altered = deepcopy(artifact)
            altered["certificate"]["separator"]["axis"] = True
            forged.append(("boolean_axis", altered))
            altered = deepcopy(artifact)
            altered["statement"]["worlds"][0]["lidar"]["occupied_boxes"][0]["upper"][1] += 0.125
            forged.append(("broken_statement_hash", altered))
            for height in (5, 5.8499999999):
                altered = deepcopy(artifact)
                lo, hi = [world["lidar"]["occupied_boxes"][0] for world in altered["statement"]["worlds"]]
                lo["lower"][1], lo["upper"][1] = 0, height
                hi["lower"][1], hi["upper"][1] = 12-height, 12
                altered["certificate"]["statement_sha256"] = digest(altered["statement"])
                forged.append(("uncovered_positive_gap", altered))
            altered = deepcopy(artifact)
            for world in altered["statement"]["worlds"]:
                world["lidar"]["occupied_boxes"][0]["upper"][2] = 11.6
            altered["certificate"]["statement_sha256"] = digest(altered["statement"])
            forged.append(("uncovered_roof_gap", altered))
            altered = deepcopy(artifact)
            altered["statement"]["worlds"][1]["public"]["prompt"] += " changed"
            altered["certificate"]["statement_sha256"] = digest(altered["statement"])
            forged.append(("nonshared_public_observation", altered))
            for kind, altered in forged:
                check = verify_barrier_certificate(altered["statement"], altered["certificate"])
                result.acceptance(check["valid"], False, "barrier_certificate_forgery",
                                  {**identity, "mutation": kind}, verification=check)
                result.counters["certificate_forgery_attempts"] += 1
                result.counters["certificate_forgeries_rejected"] += int(not check["valid"])
        except Exception as exc:
            result.exception("robotics_barrier_pair", identity, exc)
    return result.export()


class InventoryOracle:
    """Separate one-record-per-unit simulator; no task transition helpers."""

    def __init__(self, task: VendingTask):
        first = task.query("quote", {"supplier": "cedar", "cases": 1, "order_day": 0})
        second = task.query("quote", {"supplier": "cedar", "cases": 2, "order_day": 0})
        weekend = task.query("quote", {"supplier": "cedar", "cases": 1, "order_day": 5})
        self.fill = {"lead_base_days": first["arrival_day"],
                     "weekend_extra_days": weekend["arrival_day"]-5-first["arrival_day"],
                     "fixed_fee_cents": 2*first["shipping_cents"]-second["shipping_cents"],
                     "case_fee_cents": second["shipping_cents"]-first["shipping_cents"],
                     "receipt_event": "delivery"}
        self.unit_cost = first["unit_cost_cents"]
        self.cycle = task.query("market", {})["base_demand_by_weekday"]
        # Hidden noise is copied as an exogenous scenario input, not inferred by
        # a policy; all transition, cash and inventory calculations are separate.
        self.noise = list(task._demand_noise)
        self.horizon, self.capacity, self.shelf_life = task.horizon, task.capacity, task.shelf_life
        self.case_size, self.fee = first["units_per_case"], task.daily_fee
        self.day, self.cash, self.price = 0, 15000, 280
        self.units: list[int] = []
        self.pending: list[tuple[int, int]] = []
        self.orders = self.received = self.sold = self.selling_days = self.expired = 0
        self.requests = self.spend = self.sales = self.paid = self.unpaid = 0

    def quote(self, supplier, cases, day):
        if supplier == "cedar":
            shipping = self.fill["fixed_fee_cents"]+cases*self.fill["case_fee_cents"]
            lead = self.fill["lead_base_days"]+(self.fill["weekend_extra_days"] if day % 7 in (5, 6) else 0)
            cost = self.unit_cost
        else:
            shipping, lead, cost = 180+30*cases, 1, self.unit_cost+55
        return cost*self.case_size*cases+shipping, day+lead

    def apply(self, name, args):
        fields = {"quote": {"supplier", "cases", "order_day"},
                  "order": {"supplier", "cases"}, "set_price": {"price_cents"},
                  "advance": {"days"}, "status": set(), "market": set(),
                  "ledger": {"last_n"}}
        if name not in fields or type(args) is not dict or set(args) != fields[name]:
            raise ValueError("malformed")

        def integer(value, lo, hi):
            if type(value) is not int or value < lo or value > hi:
                raise ValueError("integer outside contract")
            return value

        if name in ("order", "quote"):
            if type(args["supplier"]) is not str or args["supplier"] not in ("cedar", "express"):
                raise ValueError("supplier")
            cases = integer(args["cases"], 1, self.capacity//self.case_size)
            day = integer(args["order_day"], 0, self.horizon-1) if name == "quote" else self.day
            cost, arrival = self.quote(args["supplier"], cases, day)
            if name == "quote":
                return
            quantity = cases*self.case_size
            if (day >= self.horizon or arrival > self.horizon or cost > self.cash
                    or len(self.units)+sum(q for _, q in self.pending)+quantity > self.capacity):
                raise ValueError("unfulfillable order")
            self.pending.append((arrival, quantity))
            self.cash -= cost
            self.spend += cost
            self.orders += 1
        elif name == "set_price":
            price = integer(args["price_cents"], 100, 550)
            if self.day >= self.horizon:
                raise ValueError("closed")
            self.price = price
        elif name == "advance":
            days = integer(args["days"], 1, 7)
            if self.day+days > self.horizon:
                raise ValueError("past horizon")
            for _ in range(days):
                self.day += 1
                due = [(arrival, q) for arrival, q in self.pending if arrival <= self.day]
                self.pending = [(arrival, q) for arrival, q in self.pending if arrival > self.day]
                for arrival, quantity in due:
                    self.received += quantity
                    self.units.extend([arrival+self.shelf_life]*quantity)
                remaining = [expiry for expiry in self.units if expiry >= self.day]
                self.expired += len(self.units)-len(remaining)
                self.units = sorted(remaining)
                offset = next((delta for boundary, delta in ((180, 5), (240, 2), (300, 0),
                                                             (360, -3), (450, -7))
                               if self.price < boundary), None)
                demand = 0 if offset is None else max(0, self.cycle[self.day % 7]+offset+self.noise[self.day])
                sales = min(len(self.units), demand)
                del self.units[:sales]
                self.sold += sales
                self.selling_days += bool(sales)
                self.requests += demand
                self.sales += sales*self.price
                self.cash += sales*self.price
                paid = min(self.cash, self.fee)
                self.cash -= paid
                self.paid += paid
                self.unpaid += self.fee-paid
        elif name == "ledger":
            integer(args["last_n"], 1, 100)

    def snapshot(self):
        return dict(day=self.day, cash=self.cash, price=self.price, available=len(self.units),
                    pending=sorted(self.pending), expiries=sorted(self.units), orders=self.orders,
                    received=self.received, sold=self.sold, selling_days=self.selling_days,
                    expired=self.expired, requests=self.requests, spend=self.spend,
                    gross_sales=self.sales, operating_paid=self.paid, unpaid=self.unpaid)


def vending_snapshot(task):
    return dict(day=task.day, cash=task.cash, price=task.price,
                available=sum(batch["quantity"] for batch in task.batches),
                pending=sorted((order["arrival_day"], order["quantity"]) for order in task.pending),
                expiries=sorted(batch["expiry_day"] for batch in task.batches for _ in range(batch["quantity"])),
                orders=task.orders, received=task.received, sold=task.sold,
                selling_days=task.selling_days, expired=task.expired,
                requests=task.opportunities, spend=task.order_spend, gross_sales=task.gross_sales,
                operating_paid=task.operating_paid, unpaid=task.unpaid_fees)


def world_snapshot(task):
    return deepcopy({key: value for key, value in task.__dict__.items() if key != "rng"}), task.rng.getstate()


def random_vending_action(rng, day, horizon):
    name = rng.choices(["order", "advance", "set_price", "quote", "status", "market", "ledger"],
                       weights=[30, 18, 20, 12, 5, 5, 10])[0]
    if name == "order":
        args = {"supplier": rng.choice(("cedar", "express")), "cases": rng.choice((1, 2, 3, 5, 10, 20, 30))}
    elif name == "advance":
        args = {"days": rng.choice((1, 1, 2, 3, 7))}
    elif name == "set_price":
        args = {"price_cents": rng.choice((100, 179, 180, 239, 240, 299, 300, 359, 360, 449, 450, 550))}
    elif name == "quote":
        args = {"supplier": rng.choice(("cedar", "express")), "cases": rng.choice((1, 2, 30)),
                "order_day": rng.choice((0, 5, 6, max(0, horizon-1), day))}
    elif name == "ledger":
        args = {"last_n": rng.choice((1, 2, 100))}
    else:
        args = {}
    if rng.random() < 0.35:
        mutation = rng.randrange(6)
        if mutation == 0:
            args = rng.choice((None, [], "bad", 1))
        elif mutation == 1:
            args["refund"] = 999999
        elif mutation == 2 and args:
            del args[rng.choice(list(args))]
        elif mutation in (3, 4) and args:
            args[rng.choice(list(args))] = rng.choice((True, False, -1, 0, 31, 10**50, 1.5, "1", [], {}))
        else:
            name = "refund"
    return name, args


def audit_vending_action(result, task, oracle, name, args, identity):
    before = world_snapshot(task)
    try:
        oracle.apply(name, deepcopy(args))
        expected = True
    except ValueError:
        expected = False
    try:
        response = task.query(name, deepcopy(args))
        actual = True
    except ValueError:
        response, actual = None, False
    except Exception as exc:
        result.exception("vending_action_exception", {**identity, "name": name, "args": args}, exc)
        return
    result.counters["actions"] += 1
    result.counters["valid_actions" if expected else "invalid_actions"] += 1
    result.acceptance(actual, expected, "vending_action_contract", identity, action=[name, args])
    result.check(vending_snapshot(task) == oracle.snapshot(), "unit_inventory_and_cash_oracle", identity,
                 action=[name, args], actual_state=vending_snapshot(task), expected_state=oracle.snapshot())
    if not expected:
        result.check(world_snapshot(task) == before, "invalid_world_atomicity", identity, action=[name, args])
    result.check(task.cash == 15000+task.gross_sales-task.order_spend-task.operating_paid,
                 "cash_conservation", identity)
    result.check(sum(batch["quantity"] for batch in task.batches) == task.received-task.sold-task.expired,
                 "stock_conservation", identity)
    result.check(task.operating_paid+task.unpaid_fees == task.day*task.daily_fee,
                 "fee_obligation_conservation", identity)
    if name == "quote" and actual:
        result.check(world_snapshot(task) == before, "quote_does_not_mutate_world", identity)
        cost, arrival = oracle.quote(args["supplier"], args["cases"], args["order_day"])
        result.check(response["total_cents"] == cost and response["arrival_day"] == arrival,
                     "independent_quote_arithmetic", identity)


def fixed_express_controller(public, call):
    """An open-loop public-interface policy with an independently scored Session."""
    def observe(name, args):
        response = call(name, args)
        if "error" in response:
            raise AssertionError(f"fixed controller {name}: {response['error']}")
        return response

    first = observe("quote", {"supplier": "cedar", "cases": 1, "order_day": 0})
    second = observe("quote", {"supplier": "cedar", "cases": 2, "order_day": 0})
    weekend = observe("quote", {"supplier": "cedar", "cases": 1, "order_day": 5})
    fill = {"lead_base_days": first["arrival_day"],
            "weekend_extra_days": weekend["arrival_day"]-5-first["arrival_day"],
            "fixed_fee_cents": 2*first["shipping_cents"]-second["shipping_cents"],
            "case_fee_cents": second["shipping_cents"]-first["shipping_cents"],
            "receipt_event": "delivery"}
    initial = observe("status", {})
    observe("set_price", {"price_cents": 359})
    for day in range(initial["horizon_days"]):
        if day % 4 == 0:
            observe("order", {"supplier": "express", "cases": 5})
        observe("advance", {"days": 1})
    return fill


def stress_vending(seeds, master, actions_per_episode):
    result = Results("vending")
    result.notes.append("Independent unit inventory oracle uses three public quotes, public forecast and initial constants; hidden noise is copied once only as evaluator-side exogenous scenario data.")
    result.notes.append("The fixed Express controller sets price 359 and orders five cases on days 0,4,8,...; it receives three Cedar quotes solely to fill the required coefficients and one initial status for the horizon. It runs through the budgeted Session interface. It is a scripted shortcut control, not a model result.")
    control_twins = {}
    for seed, split, difficulty, twin in configurations(seeds):
        identity = case_id(seed, split, difficulty, twin)
        result.counters["fuzz_episodes"] += 1
        try:
            task = VendingTask(seed, split, difficulty, twin)
            oracle = InventoryOracle(task)
            rng = random.Random(f"{master}:vending:{seed}:{split}:{difficulty}:{twin}")
            for _ in range(actions_per_episode):
                name, args = random_vending_action(rng, task.day, task.horizon)
                audit_vending_action(result, task, oracle, name, args, identity)
            while task.day < task.horizon:
                audit_vending_action(result, task, oracle, "advance",
                                     {"days": min(7, task.horizon-task.day)}, identity)
            for name, args in (("advance", {"days": 1}), ("order", {"supplier": "express", "cases": 1}),
                               ("set_price", {"price_cents": 359})):
                audit_vending_action(result, task, oracle, name, args, identity)
            expected_success = (oracle.cash >= task.cash_target and oracle.unpaid == 0
                                and oracle.requests > 0 and oracle.sold/oracle.requests >= 0.6
                                and oracle.selling_days >= math.ceil(oracle.horizon*0.6))
            result.acceptance(task.evaluate(oracle.fill).success, expected_success,
                              "vending_final_outcome", identity)
            result.counters["reachable_unpaid_fee_episodes"] += int(task.unpaid_fees > 0)
            result.counters["reachable_expiry_episodes"] += int(task.expired > 0)

            # Inclusive shelf life, suppressed demand, and chunking equivalence.
            fresh = VendingTask(seed, split, difficulty, twin)
            unit_model = InventoryOracle(fresh)
            for name, args in (("set_price", {"price_cents": 550}),
                               ("order", {"supplier": "cedar", "cases": 1})):
                audit_vending_action(result, fresh, unit_model, name, args, identity)
            arrival = unit_model.pending[0][0]
            while fresh.day < min(fresh.horizon, arrival+fresh.shelf_life):
                audit_vending_action(result, fresh, unit_model, "advance", {"days": 1}, identity)
            result.check(fresh._available() == 6, "expiry_day_is_inclusive", identity)
            audit_vending_action(result, fresh, unit_model, "advance", {"days": 1}, identity)
            result.check(fresh._available() == 0 and fresh.expired == 6,
                         "expiry_next_day_removes_stock", identity)
            result.acceptance(fresh.evaluate(unit_model.fill).success, False,
                              "zero_demand_does_not_pass", identity)

            # A reachable insolvency trace, constructed solely from public
            # Express prices. Splitting shipments can consume the cash reserve.
            insolvent = VendingTask(seed, split, difficulty, twin)
            insolvent_model = InventoryOracle(insolvent)
            single = insolvent.query("quote", {"supplier": "express", "cases": 1, "order_day": 0})
            per_case = single["total_cents"]-180
            feasible = [(per_case*cases+180*orders, cases, orders)
                        for cases in range(1, 31) for orders in range(1, cases+1)
                        if per_case*cases+180*orders <= 15000]
            _, cases, orders = max(feasible)
            audit_vending_action(result, insolvent, insolvent_model, "set_price", {"price_cents": 550}, identity)
            for index in range(orders):
                count = 1 if index < orders-1 else cases-orders+1
                audit_vending_action(result, insolvent, insolvent_model, "order",
                                     {"supplier": "express", "cases": count}, identity)
            while insolvent.day < insolvent.horizon:
                audit_vending_action(result, insolvent, insolvent_model, "advance",
                                     {"days": min(7, insolvent.horizon-insolvent.day)}, identity)
            result.check(insolvent.cash == 0 and insolvent.unpaid_fees > 0,
                         "reachable_insolvency_records_unpaid_fees", identity)
            result.check(insolvent.evaluate(insolvent_model.fill).safety == 0,
                         "unpaid_fees_fail_invariant_score", identity)
            result.counters["constructed_insolvent_episodes"] += 1

            chunk = VendingTask(seed, split, difficulty, twin)
            daily = VendingTask(seed, split, difficulty, twin)
            for simulation in (chunk, daily):
                simulation.query("set_price", {"price_cents": 359})
                simulation.query("order", {"supplier": "express", "cases": 5})
            while chunk.day < chunk.horizon:
                days = min(7, chunk.horizon-chunk.day)
                chunk.query("advance", {"days": days})
                for _ in range(days):
                    daily.query("advance", {"days": 1})
            result.check(vending_snapshot(chunk) == vending_snapshot(daily)
                         and chunk.events == daily.events, "advance_chunking_equivalence", identity)

            # Entirely separate, nonadaptive business controller.
            control = VendingTask(seed, split, difficulty, twin)
            session = Session(control)
            control_fill = fixed_express_controller(session.public(), session.call)
            session.call("submit", {"fill": control_fill, "confidence": 1.0,
                                     "abstain": False, "evidence": []})
            verdict = control.evaluate(control_fill)
            cost, calls = session.cost, session.calls
            result.counters["fixed_express_episodes"] += 1
            result.counters["fixed_express_successes"] += int(verdict.success)
            result.counters[f"fixed_express_successes:{split}:d{difficulty}:t{twin}"] += int(verdict.success)
            result.check(cost <= control.budget and calls <= control.max_calls,
                         "fixed_controller_within_budget", identity, cost=cost, calls=calls)
            result.check(session.result["success"] == verdict.success,
                         "fixed_controller_session_result", identity)
            result.counters["fixed_controller_tool_cost_total"] += cost
            result.counters["fixed_controller_tool_calls_total"] += calls
            pair_key = (seed, split, difficulty)
            if twin == 0:
                control_twins[pair_key] = (vending_snapshot(control), control_fill)
            else:
                previous_state, previous_fill = control_twins[pair_key]
                result.check(vending_snapshot(control) == previous_state,
                             "express_trajectory_independent_of_cedar_twin", identity)
                result.check(control_fill["lead_base_days"] == previous_fill["lead_base_days"]+1
                             and all(control_fill[key] == previous_fill[key]
                                     for key in control_fill if key != "lead_base_days"),
                             "vending_twin_single_lead_parameter", identity)
            if not verdict.success:
                result.counters["fixed_controller_failures"] += 1
            for field in control_fill:
                mutant = dict(control_fill)
                mutant[field] = "invoice" if field == "receipt_event" else mutant[field]+1
                result.acceptance(control.evaluate(mutant).success, False,
                                  "wrong_procurement_field_rejected", {**identity, "field": field})
            status = control.query("status", {})
            before = world_snapshot(control)
            status["batches"].append({"quantity": 10**8, "expiry_day": 9999})
            status["pending_deliveries"].clear()
            ledger = control.query("ledger", {"last_n": 100})
            ledger["events"].clear()
            result.check(world_snapshot(control) == before, "vending_defensive_copies", identity)
        except Exception as exc:
            result.exception("vending_episode", identity, exc)
    return result.export()


def independent_workflow(case, split):
    value = Fraction(case["balance"])-Fraction(case["amount"])*Fraction(case["scale"])-Fraction(case["fee"])
    if split != "train" and value < case["reserve"]:
        value = Fraction(case["reserve"])
    if split == "transfer" and value > case["ceiling"]:
        value = Fraction(case["ceiling"])
    return value


def workflow_expression(split):
    body = "balance-amount*scale-fee"
    if split != "train":
        body = f"max({body},reserve)"
    if split == "transfer":
        body = f"min({body},ceiling)"
    return body


def stress_workflow(seeds, master):
    result = Results("workflow")
    result.notes.append("Acceptance is compared with explicit well-formed OOD witnesses, not merely disagreement with a reference string. Current strict success also requires a sufficient symbolic certificate over the declared integer domain [-1000000,1000000] with positive scale 1..1000000. Signed/fractional interpreter probes outside that contract are diagnostics only. Older baseline reports capture the original finite-suite-only verifier.")
    for seed, split, difficulty, twin in configurations(seeds):
        identity = case_id(seed, split, difficulty, twin)
        result.counters["episodes"] += 1
        try:
            task = WorkflowTask(seed, split, difficulty, twin)
            correct = workflow_expression(split)
            alternatives = [correct, f"({correct})+0", f"({correct})*1", f"({correct})/1"]
            if split == "train":
                alternatives.append("balance-fee-scale*amount")
            elif split == "dev":
                alternatives.append("max(reserve,balance-fee-scale*amount)")
            else:
                alternatives.append("max(reserve,min(ceiling,balance-fee-scale*amount))")
            for candidate in alternatives:
                result.acceptance(task.evaluate({"expression": candidate}).success, True,
                                  "equivalent_workflow_expression", identity, expression=candidate)
            calibration = json.loads(task.files["/observations/calibration.json"])["ledger_units"]
            frozen = correct.replace("scale", str(calibration))
            result.acceptance(task.evaluate({"expression": frozen}).success, False,
                              "frozen_calibration_rejected", identity)
            # Mutants exploit independently stated input domains, not hidden data.
            attacks = [
                (f"({correct})+max(0,scale-19)", dict(balance=40, amount=7, fee=3, reserve=10, ceiling=50, scale=20)),
                (f"({correct})+max(0,balance-249)", dict(balance=250, amount=7, fee=3, reserve=10, ceiling=50, scale=2)),
                (f"({correct})+max(0,amount-59)", dict(balance=40, amount=60, fee=3, reserve=10, ceiling=50, scale=2)),
                (f"({correct})+max(0,fee-19)", dict(balance=40, amount=7, fee=20, reserve=10, ceiling=50, scale=2)),
                (f"({correct})+max(0,scale-9999)", dict(balance=40, amount=7, fee=3, reserve=10, ceiling=50, scale=10000)),
            ]
            for candidate, witness in attacks:
                expected = independent_workflow(witness, split)
                actual = expression(candidate, witness)
                result.check(actual != expected, "workflow_attack_witness_differs", identity)
                verdict = task.evaluate({"expression": candidate})
                result.acceptance(verdict.success, False, "workflow_ood_range_attack", identity,
                                  expression=candidate, witness=witness, actual_output=str(actual),
                                  expected_output=str(expected), verdict=asdict(verdict))
            rng = random.Random(f"{master}:workflow:{identity}")
            for _ in range(30):
                reserve = rng.randrange(-100, 100)
                sample = dict(balance=Fraction(rng.randrange(-10000, 10000), rng.choice((1, 2, 3))),
                              amount=Fraction(rng.randrange(-1000, 1000), 3), fee=rng.randrange(-100, 100),
                              reserve=reserve, ceiling=reserve+rng.randrange(1000), scale=rng.randrange(-1000, 1001))
                result.check(expression(correct, sample) == independent_workflow(sample, split),
                             "independent_fractional_signed_ood", identity)
        except Exception as exc:
            result.exception("workflow_episode", identity, exc)
    return result.export()


def grid_oracle(grid, program):
    output = [list(row) for row in grid]
    for step in program:
        op = step["op"]
        if op == "rotate90":
            for _ in range(step["turns"]):
                h, w = len(output), len(output[0])
                output = [[output[h-1-column][row] for column in range(h)] for row in range(w)]
        elif op == "flip_h":
            output = [[row[len(row)-1-column] for column in range(len(row))] for row in output]
        elif op == "keep_color":
            output = [[cell*int(cell == step["color"]) for cell in row] for row in output]
        elif op == "recolor":
            output = [[step["target"] if cell == step["source"] else cell for cell in row] for row in output]
        elif op == "crop":
            occupied_rows = [i for i, row in enumerate(output) if any(row)]
            occupied_columns = [j for j in range(len(output[0])) if any(row[j] for row in output)]
            if not occupied_rows:
                output = [[0]]
            else:
                output = [[output[i][j] for j in range(occupied_columns[0], occupied_columns[-1]+1)]
                          for i in range(occupied_rows[0], occupied_rows[-1]+1)]
        else:
            raise AssertionError(op)
    return output


def grid_candidates(split):
    for source in range(1, 5):
        for target in range(1, 5):
            if source == target:
                continue
            for turns in ((0,) if split == "train" else range(4)):
                program = []
                if split == "transfer":
                    program.extend([{"op": "keep_color", "color": source}, {"op": "crop"}])
                if split != "train":
                    program.append({"op": "rotate90", "turns": turns})
                program.append({"op": "recolor", "source": source, "target": target})
                yield program


def stress_grid(seeds, master):
    result = Results("grid")
    result.notes.append("Uses an independent coordinate-index grid interpreter and evidence-filtered public grammar enumeration; no generator interpreter or reference-answer calls are used.")
    for seed, split, difficulty, twin in configurations(seeds):
        identity = case_id(seed, split, difficulty, twin)
        result.counters["episodes"] += 1
        try:
            task = GridTask(seed, split, difficulty, twin)
            rng = random.Random(f"{master}:grid:{identity}")
            candidates = list(grid_candidates(split))
            probes = []
            while len(candidates) > 1 and len(probes) < 4:
                grid = [[rng.randrange(5) for _ in range(8)] for _ in range(8)]
                output = task.query("transform", {"grid": grid})["output"]
                probes.append(grid)
                candidates = [program for program in candidates if grid_oracle(grid, program) == output]
            result.check(len(candidates) == 1, "public_observations_identify_grid_program", identity)
            if len(candidates) != 1:
                continue
            program = candidates[0]
            result.acceptance(task.evaluate({"program": program}).success, True,
                              "independently_recovered_grid_program", identity)
            alternative = deepcopy(program)
            if split == "train":
                alternative.insert(0, {"op": "rotate90", "turns": 0})
            elif split == "dev":
                alternative.reverse()
            else:
                alternative = [alternative[0], alternative[3], alternative[1], alternative[2]]
            result.acceptance(task.evaluate({"program": alternative}).success, True,
                              "equivalent_grid_composition", identity)
            for index in range(48):
                h, w = rng.randrange(1, 9), rng.randrange(1, 9)
                grid = [[rng.randrange(5) for _ in range(w)] for _ in range(h)]
                if index % 8 == 0:
                    grid = [[0]*w for _ in range(h)]
                actual = task.query("transform", {"grid": grid})["output"]
                result.check(actual == grid_oracle(grid, program), "independent_grid_semantics", identity)
                result.check(grid_oracle(grid, program) == grid_oracle(grid, alternative),
                             "grid_composition_metamorphism", identity)
            mutants = [[]]
            recolor = deepcopy(program)
            recolor[-1]["target"] = recolor[-1]["source"]
            mutants.append(recolor)
            if split != "train":
                turned = deepcopy(program)
                turned[-2]["turns"] = (turned[-2]["turns"]+1) % 4
                mutants.append(turned)
            for mutant in mutants:
                result.acceptance(task.evaluate({"program": mutant}).success, False,
                                  "incorrect_grid_program_rejected", identity, program=mutant)
            twin_task = GridTask(seed, split, difficulty, 1-twin)
            result.acceptance(twin_task.evaluate({"program": program}).success, False,
                              "cross_twin_grid_rejected", identity)
            default = [{"op": "recolor", "source": 1, "target": 2}]
            expected_default = all(grid_oracle(grid, default) == grid_oracle(grid, program) for grid in probes)
            verdict_default = task.evaluate({"program": default})
            result.counters["fixed_grid_default_successes"] += int(verdict_default.success)
            result.acceptance(verdict_default.success, expected_default,
                              "fixed_grid_default_adjudicated", identity)
        except Exception as exc:
            result.exception("grid_episode", identity, exc)
    return result.export()


def dense_affine(task):
    n = task.dimension
    offset = task.query("probe", {"vector": [0]*n})["output"]
    matrix = [[0]*n for _ in range(n)]
    for column in range(n):
        unit = [0]*n
        unit[column] = 1
        observed = task.query("probe", {"vector": unit})["output"]
        for row in range(n):
            matrix[row][column] = (observed[row]-offset[row]) % 101
    fill = {"offset": offset,
            "rows": [[{"column": column, "coefficient": coefficient}
                      for column, coefficient in enumerate(row) if coefficient] for row in matrix]}
    return offset, matrix, fill


def stress_latent(seeds, master):
    result = Results("latent")
    result.notes.append("Dense full-basis recovery is an evaluator-side exact oracle. For SparseLatentTask it exceeds the nine-unit solver budget and is never reported as budgeted policy success.")
    for constructor in (LatentTask, SparseLatentTask):
        for seed, split, difficulty, twin in configurations(seeds):
            identity = {**case_id(seed, split, difficulty, twin), "class": constructor.__name__}
            result.counters["episodes"] += 1
            try:
                task = constructor(seed, split, difficulty, twin)
                offset, matrix, fill = dense_affine(task)
                result.acceptance(task.evaluate(fill).success, True, "dense_basis_certificate_accepted", identity)
                equivalent = deepcopy(fill)
                for row in equivalent["rows"]:
                    row.reverse()
                    used = {term["column"] for term in row}
                    column = next(column for column in range(task.dimension) if column not in used)
                    row.append({"column": column, "coefficient": 0})
                result.acceptance(task.evaluate(equivalent).success, True,
                                  "reordered_zero_augmented_matrix", identity)
                moments = [task.query("probe", {"vector": vector})["output"]
                           for vector in sparse_probe_plan(task.dimension)]
                recovered = recover_sparse_operator(moments, task.dimension)
                sparse_matrix = [[0]*task.dimension for _ in range(task.dimension)]
                for index, row in enumerate(recovered["rows"]):
                    for term in row:
                        sparse_matrix[index][term["column"]] = term["coefficient"]
                result.check(recovered["offset"] == offset and sparse_matrix == matrix,
                             "five_probe_recovery_matches_dense_oracle", identity)
                rng = random.Random(f"{master}:latent:{identity}")
                for _ in range(20):
                    vector = [rng.randrange(101) for _ in range(task.dimension)]
                    expected = [(bias+sum(coefficient*x for coefficient, x in zip(row, vector))) % 101
                                for bias, row in zip(offset, matrix)]
                    result.check(task.query("probe", {"vector": vector})["output"] == expected,
                                 "dense_random_affine_interventions", identity)
                    other = [rng.randrange(101) for _ in range(task.dimension)]
                    mixed = [(a+b) % 101 for a, b in zip(vector, other)]
                    f_other = task.query("probe", {"vector": other})["output"]
                    f_mixed = task.query("probe", {"vector": mixed})["output"]
                    result.check(f_mixed == [(a+b-c) % 101 for a, b, c in zip(expected, f_other, offset)],
                                 "affine_addition_metamorphism", identity)
                for kind in ("offset", "coefficient", "empty", "duplicate"):
                    mutant = deepcopy(fill)
                    if kind == "offset":
                        mutant["offset"][0] = (mutant["offset"][0]+1) % 101
                    elif kind == "coefficient":
                        mutant["rows"][0][0]["coefficient"] = (mutant["rows"][0][0]["coefficient"]+1) % 101
                    elif kind == "empty":
                        mutant = {"offset": [0]*task.dimension, "rows": [[] for _ in range(task.dimension)]}
                    else:
                        mutant["rows"][0].append(deepcopy(mutant["rows"][0][0]))
                    result.acceptance(task.evaluate(mutant).success, False,
                                      "latent_mutation_rejected", {**identity, "mutation": kind})
                other = constructor(seed, split, difficulty, 1-twin)
                other_offset, other_matrix, _ = dense_affine(other)
                changed = [(r, c) for r in range(task.dimension) for c in range(task.dimension)
                           if matrix[r][c] != other_matrix[r][c]]
                result.check(offset == other_offset and len(changed) == 1,
                             "latent_single_coefficient_twin", identity, changed=changed)
                result.acceptance(other.evaluate(fill).success, False, "latent_cross_twin_rejected", identity)
            except Exception as exc:
                result.exception("latent_episode", identity, exc)
    return result.export()


def write_report(report, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False)+"\n")
    lines = ["# Operational stress audit", "", "Evaluator-development checks; no model-performance or certified-difficulty claim.", "",
             f"Master seed: `{report['master_seed']}`. Total wall time: {report['elapsed_seconds']:.3f} seconds.", "",
             "| Section | Checks | False accepts | False rejects | Oracle mismatches | Unexpected exceptions | Seconds |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for section in report["sections"]:
        failures = section["failure_counts"]
        lines.append(f"| {section['name']} | {section['counters'].get('checks', 0)} | {failures.get('false_accept', 0)} | {failures.get('false_reject', 0)} | {failures.get('oracle_mismatch', 0)} | {failures.get('unexpected_exception', 0)} | {section['elapsed_seconds']:.3f} |")
    for section in report["sections"]:
        lines.extend(["", f"## {section['name']}", ""])
        for note in section["notes"]:
            lines.extend([note, ""])
        lines.extend(["Counters:", "", "```json", json.dumps(section["counters"], indent=2, sort_keys=True), "```", ""])
        if section["failure_counts"]:
            lines.extend(["Failure counts:", "", "```json", json.dumps(section["failure_counts"], indent=2, sort_keys=True), "```", ""])
            lines.extend(["The JSON report contains bounded examples and exact witnesses for each failure label.", ""])
    lines.extend(["## Scope and interpretation", "",
                  "The source hashes, command arguments, actual seed lists, and bounded failure examples are in the adjacent JSON. Source files were not treated as a solver interface. Geometry checks cover sampled and targeted cases, not a formal proof of all possible JSON numeric inputs. Grid checks are finite and affine certificates are complete only inside the declared affine hypothesis class. Legal constant controls are reported as task-distribution shortcuts, not as false successes. Workflow threshold mutants supply explicit new-input counterexamples; older baseline reports capture finite-suite-only acceptance, while current strict success additionally requires a symbolic certificate over the declared integer domain.", ""])
    destination.with_suffix(".md").write_text("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--master-seed", type=int, default=371905)
    parser.add_argument("--seed-count", type=int, default=32)
    parser.add_argument("--metamorphic-seed-count", type=int, default=8)
    parser.add_argument("--geometry-cases", type=int, default=10000)
    parser.add_argument("--actions-per-episode", type=int, default=50)
    parser.add_argument("--sections", nargs="+", choices=("geometry", "robotics", "robotics_barrier", "vending", "workflow", "grid", "latent"),
                        default=["geometry", "robotics", "robotics_barrier", "vending", "workflow", "grid", "latent"])
    parser.add_argument("--output", type=Path, default=ROOT/"reports/stress-v0.3/operations.json")
    args = parser.parse_args()
    if min(args.seed_count, args.metamorphic_seed_count, args.geometry_cases, args.actions_per_episode) < 1:
        parser.error("counts must be positive")
    started = time.perf_counter()
    seeds = seed_list(args.seed_count, args.master_seed)
    metamorphic = seed_list(args.metamorphic_seed_count, args.master_seed+1)
    source_paths = [Path(__file__), *sorted((ROOT/"causalfill").rglob("*.py"))]
    source_hashes = lambda: {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                             for path in source_paths}
    report = {"audit_version": "operations-v0.3", "mode": "evaluator-development",
              "master_seed": args.master_seed, "episode_seeds": seeds,
              "metamorphic_episode_seeds": metamorphic,
              "arguments": {**vars(args), "output": str(args.output)}, "sections": [],
              "source_sha256": source_hashes()}
    runners = {
        "geometry": lambda: stress_geometry(args.geometry_cases, args.master_seed),
        "robotics": lambda: stress_robotics(seeds, args.master_seed),
        "robotics_barrier": lambda: stress_robotics_barrier(seeds, args.master_seed),
        "vending": lambda: stress_vending(seeds, args.master_seed, args.actions_per_episode),
        "workflow": lambda: stress_workflow(metamorphic, args.master_seed),
        "grid": lambda: stress_grid(metamorphic, args.master_seed),
        "latent": lambda: stress_latent(metamorphic, args.master_seed),
    }
    for name in args.sections:
        section = runners[name]()
        report["sections"].append(section)
        print(json.dumps({"section": name, "checks": section["counters"].get("checks", 0),
                          "seconds": section["elapsed_seconds"], "failures": section["failure_counts"]}), flush=True)
        report["elapsed_seconds"] = round(time.perf_counter()-started, 6)
        write_report(report, args.output)
    report["source_stable_during_run"] = report["source_sha256"] == source_hashes()
    write_report(report, args.output)
    print(f"Wrote {args.output}", flush=True)
    if not report["source_stable_during_run"]:
        raise SystemExit("source changed during the operations audit")


if __name__ == "__main__":
    main()
