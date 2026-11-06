#!/usr/bin/env python3
"""Audit the finite market model against actual tools, ledgers and sessions.

Every reachable model state is reached through primitive runtime calls. Each
outgoing transition is then executed and compared. Additional checks reconstruct
money and stock independently from ledger events, examine invalid actions and
stuttering observations, and replay attaining policies through real Sessions.
This is exhaustive for each generated finite graph, not a formal Python proof.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import copy, deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from causalfill.domains.vending_adaptive import VendingAdaptiveTask, market_action_request
from causalfill.belief_games import build_game_certificate, MODES
from causalfill.belief_certificates import verify_game_certificate, extract_game_strategy, verify_game_strategy
from causalfill.session import Session, verify_trace
from causalfill.types import canonical

RUNTIME_FIELDS = ("stage", "cash", "pending", "available", "calibration_observation", "sample",
                  "express_orders", "past_demand", "breach", "sold", "received", "expired",
                  "order_spend", "sales_revenue", "operating_paid", "events")


def runtime_snapshot(task):
    return canonical({name: getattr(task, name) for name in RUNTIME_FIELDS})


def fork_runtime(task):
    out = copy(task)
    for name in RUNTIME_FIELDS:
        setattr(out, name, deepcopy(getattr(task, name)))
    return out


def invoke(task, name, args):
    try:
        return task.query(name, deepcopy(args))
    except (ValueError, TypeError, KeyError, IndexError) as exc:
        return {"error": str(exc)[:240]}


def ledger_reduce(contract, terms, events):
    """Independent chronological inventory and cash reconstruction."""
    cash, spend, revenue, fees = contract["initial_cash_cents"], 0, 0, 0
    received, sold, expired, closed, express = 0, 0, 0, 0, 0
    inventory = {product: 0 for product in contract["products"]}
    pending, demands, issues = None, [], []
    size = contract["units_per_case"]
    for event in events:
        if event["event"] == "invoice":
            amount = (size * contract["unit_cost_cents"] + terms["fixed_shipping_cents"]
                      + terms["case_shipping_cents"] +
                      (contract["express_surcharge_cents"] if event["supplier"] == "express" else 0))
            lead = 1 if event["supplier"] == "express" else terms["standard_lead_days"]
            if (pending is not None or sum(inventory.values()) != 0 or event["quantity"] != size
                    or event["total_cents"] != amount or event["order_day"] != 2 * closed
                    or event["arrival_day"] != 2 * closed + lead):
                issues.append("invalid invoice or capacity")
            pending = event
            cash -= amount
            spend += amount
            express += int(event["supplier"] == "express")
        elif event["event"] == "delivery":
            if (pending is None or event["product"] != pending["product"] or event["quantity"] != size
                    or event["day"] != pending["arrival_day"] or event["day"] > 2 * (closed + 1)):
                issues.append("delivery inconsistent with prior invoice")
            inventory[event["product"]] += event["quantity"]
            received += event["quantity"]
            pending = None
        elif event["event"] == "market_close":
            product = event["demanded_product"]
            expected_sales = min(size, inventory[product])
            inventory[product] -= expected_sales
            expected_expiry = sum(inventory.values())
            gain = expected_sales * contract["selling_price_cents"]
            fee = contract["operating_fee_cents"]
            cash += gain - fee
            if (event["demand_units"] != size or event["sold_units"] != expected_sales
                    or event["expired_units"] != expected_expiry or event["revenue_cents"] != gain
                    or event["operating_fee_cents"] != fee or event["cash_cents"] != cash
                    or event["day"] != 2 * (closed + 1)):
                issues.append("market close inconsistent with inventory or cash")
            inventory = dict.fromkeys(inventory, 0)
            revenue += gain
            fees += fee
            sold += expected_sales
            expired += expected_expiry
            closed += 1
            demands.append(contract["products"].index(product))
        else:
            issues.append("unknown ledger event")
        if cash < 0 or sum(inventory.values()) > size:
            issues.append("negative cash or storage overflow")
    return {"cash": cash, "order_spend": spend, "sales_revenue": revenue, "operating_paid": fees,
            "received": received, "sold": sold, "expired": expired, "available": sum(inventory.values()),
            "stage": closed, "past_demand": demands, "express_orders": express, "issues": issues}


def source_hashes():
    paths = ["causalfill/domains/vending_adaptive.py", "causalfill/belief_games.py",
             "causalfill/belief_certificates.py", "causalfill/session.py",
             "causalfill/types.py", "tools/stress_adaptive_v04.py"]
    return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths}


def run(seeds):
    before, start = source_hashes(), time.monotonic()
    counts, failures, cases = Counter(), [], []

    def check(condition, label, context):
        counts["assertions"] += 1
        if not condition and len(failures) < 100:
            failures.append({"label": label, "context": context})
        if not condition:
            counts["failures"] += 1

    for seed in range(seeds):
        for split in ("train", "dev", "transfer"):
            for difficulty in (1, 2, 3):
                case = [seed, split, difficulty]
                base = VendingAdaptiveTask(seed, split, difficulty)
                contract = json.loads(base.files["/market/contract.json"])
                terms, game = base.reference_answer(), base.game_statement()
                action_cost = {a["id"]: a["cost"] for a in game["actions"]}
                all_actions = [a["id"] for a in game["actions"]]
                modes, strategy = {}, None
                for mode in MODES:
                    certificate = build_game_certificate(game, mode)
                    verdict = verify_game_certificate(game, certificate)
                    check(verdict["valid"], "finite_certificate", [*case, mode])
                    modes[mode] = verdict.get("optimal_cost")
                    counts["certificates"] += 1
                    if mode == "adaptive":
                        strategy = extract_game_strategy(game, certificate)
                        replay = verify_game_strategy(game, strategy)
                        check(replay["valid"] and replay["worst_case_cost"] == modes[mode],
                              "strategy_raw_world_replay", case)
                    else:
                        check(not verdict.get("winning", True), "restricted_class_unwinnable", [*case, mode])
                check(base.public() == base.clone_for_world(len(contract["worlds"]) - 1).public(),
                      "public_metadata_world_independent", case)

                # Histories, not current observation alone, are the solver's information.
                # Known past actions may legitimately make past invoice fields differ.
                observed, observed_transitions = {}, {}
                for node_id, node in enumerate(game["states"]):
                    witness = base.game_replay_witness(node_id)
                    runtime = base.clone_for_world(witness["world_index"])
                    for action in witness["actions"]:
                        tool, args = market_action_request(contract, action)
                        response = invoke(runtime, tool, args)
                        check("error" not in response, "witness_action_legal", [*case, node_id])
                    check(runtime.game_state_id() == node_id and runtime._observation() == node["observation"],
                          "reachable_state_matches", [*case, node_id])
                    check(runtime._outcome() == node["outcome"], "runtime_terminal_status", [*case, node_id])
                    ledger = ledger_reduce(contract, terms, runtime.events)
                    check(not ledger.pop("issues") and all(getattr(runtime, key) == value for key, value in ledger.items()),
                          "independent_ledger_accounting", [*case, node_id])
                    counts["reachable_states_replayed"] += 1

                    snapshot = runtime_snapshot(runtime)
                    stutters = [("status", {}), ("ledger", {"last_n": 100}),
                                ("quote", {"supplier": "standard", "cases": 2}),
                                ("quote", {"supplier": "express", "cases": 1})]
                    invalid = [("forecast", {"future": 1}), ("assay", {"stage": True}),
                               ("calibrate", {"calibration": 0}),
                               ("order", {"product": True, "supplier": "standard"}),
                               ("order", {"product": "tea", "supplier": None}),
                               ("order", {"product": "tea", "supplier": "standard", "cases": 2}),
                               ("quote", {"supplier": "standard", "cases": True}),
                               ("quote", {"supplier": "standard", "cases": 0}),
                               ("ledger", {"last_n": True}), ("status", {"world": 0}),
                               ("settle", {"stage": 0}), ("unknown", {})]
                    legal = {edge["action"] for edge in node["transitions"]}
                    invalid += [market_action_request(contract, action) for action in all_actions if action not in legal]
                    extra = []
                    for name, args in stutters:
                        response = invoke(runtime, name, args)
                        check("error" not in response and response.get("observation") == node["observation"]
                              and runtime_snapshot(runtime) == snapshot, "stuttering_tool", [*case, node_id, name])
                        extra.append(response)
                        counts["stuttering_tools_checked"] += 1
                    for name, args in invalid:
                        response = invoke(runtime, name, args)
                        check("error" in response and runtime_snapshot(runtime) == snapshot,
                              "invalid_action_atomic", [*case, node_id, name, args])
                        extra.append(response)
                        counts["invalid_actions_checked"] += 1
                    key = canonical([witness["actions"], node["observation"]])
                    value = canonical(extra)
                    if key in observed:
                        check(value == observed[key], "no_extra_hidden_information", [*case, node_id])
                        counts["equivalent_history_response_comparisons"] += 1
                    else:
                        observed[key] = value

                    for edge in node["transitions"]:
                        clone = fork_runtime(runtime)
                        name, args = market_action_request(contract, edge["action"])
                        response = invoke(clone, name, args)
                        target = game["states"][edge["next"]]
                        check("error" not in response and response.get("observation") == target["observation"]
                              and clone.game_state_id() == edge["next"],
                              "every_runtime_transition_matches", [*case, node_id, edge["action"]])
                        check(base.tools[name]["cost"] == action_cost[edge["action"]],
                              "primitive_action_cost_matches", [*case, edge["action"]])
                        response_key = canonical([witness["actions"], node["observation"],
                                                  edge["action"], target["observation"]])
                        response_value = canonical(response)
                        if response_key in observed_transitions:
                            check(response_value == observed_transitions[response_key],
                                  "no_extra_transition_information", [*case, node_id, edge["action"]])
                            counts["equivalent_transition_response_comparisons"] += 1
                        else:
                            observed_transitions[response_key] = response_value
                        counts["transitions_executed"] += 1

                # Full Session replay includes declared tool charges and accepted final fills.
                attained = []
                for world in range(len(game["initial"])):
                    runtime = base.clone_for_world(world)
                    session, cursor = Session(runtime), strategy["root"]
                    while "stop" not in strategy["nodes"][cursor]:
                        step = strategy["nodes"][cursor]
                        tool, args = market_action_request(contract, step["action"])
                        response = session.call(tool, args)
                        check("error" not in response, "attaining_session_action", [*case, world])
                        if "error" in response:
                            break
                        branches = {edge["observation"]: edge["next"] for edge in step["branches"]}
                        cursor = branches[response["observation"]]
                    operational_cost = session.cost
                    session.call("submit", {"fill": terms, "confidence": 1.0, "abstain": False,
                                             "evidence": [event["event_id"] for event in session.trace]})
                    check(session.result is not None and session.result["success"] and verify_trace(session.trace),
                          "attaining_session_success", [*case, world])
                    attained.append(operational_cost)
                    counts["attaining_session_worlds"] += 1
                check(max(attained) == modes["adaptive"], "attained_exact_worst_case_cost", case)

                # Public responses and state must remain unchanged by a refused over-budget action.
                budget_task = base.clone_for_world(0)
                budget_session = Session(budget_task)
                budget_session.cost = budget_task.budget - 1
                snapshot = runtime_snapshot(budget_task)
                denied = budget_session.call("order", {"product": "tea", "supplier": "standard"})
                check("budget_exhausted" in denied.get("error", "") and runtime_snapshot(budget_task) == snapshot,
                      "over_budget_irreversible_order_is_atomic", case)
                cases.append({"seed": seed, "split": split, "difficulty": difficulty,
                              "worlds": len(game["initial"]), "states": len(game["states"]),
                              "transitions": sum(len(state["transitions"]) for state in game["states"]),
                              "mode_values": modes, "attained_costs": attained})
                print(json.dumps({"completed": case, "states": len(game["states"]),
                                  "failures_so_far": counts["failures"]}), flush=True)

    after = source_hashes()
    check(before == after, "source_stable_during_run", None)
    return {"schema": "causalfill.adaptive-runtime-audit.v1",
            "status": "passed" if not counts["failures"] else "failed",
            "finished_utc": datetime.now(timezone.utc).isoformat(), "seconds": time.monotonic() - start,
            "source_sha256": after, "source_stable_during_run": before == after,
            "configuration": {"seeds": list(range(seeds)), "splits": ["train", "dev", "transfer"],
                              "difficulties": [1, 2, 3]}, "counts": dict(counts), "failures": failures,
            "cases": cases,
            "scope": "One canonical witness history per reachable projected state and every outgoing legal edge in each listed finite game; finite invalid-request battery and equivalent-history checks on full stuttering, invalid and transition responses.",
            "limitations": ["Not a proof of equivalence for arbitrary Python programs or all possible invalid byte strings.",
                            "The attaining strategy and final fill are evaluator-developed; Session replay is a conformance control, not an AI score.",
                            "Action-optimality certificates exclude setup file reads, static quotes, wall time and final answer reconstruction.",
                            "Correlated assertions and public development seeds do not establish frontier-model difficulty."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=1)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.seeds <= 10 or args.output.exists():
        parser.error("seeds must be1..10 and output must be fresh")
    result = run(args.seeds)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({k: result[k] for k in ("status", "seconds", "counts", "failures")}, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
