#!/usr/bin/env python3
"""Independent finite-game stress with an analytic weighted-set-cover oracle.

The complete hidden bit cube has no outcome-dependent sensor costs. Every
successful branch must cover every uncertain bit before selecting a word, so
the minimum robust cost is a minimum weighted set cover plus the selection
cost. This oracle enumerates sensor subsets, not Bellman belief recurrences.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import itertools
import json
from pathlib import Path
import random
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from causalfill.belief_games import build_game_certificate, validate_game
from causalfill.belief_certificates import (
    extract_game_strategy, verify_game_certificate, verify_game_strategy,
)


def sensor_game(bits, masks, costs, selection_cost):
    worlds, used_count = 1 << bits, 1 << len(masks)
    actions = ([{"id": f"sample_{i}", "kind": "observe", "cost": c}
                for i, c in enumerate(costs)] +
               [{"id": f"select_{w}", "kind": "act", "cost": selection_cost}
                for w in range(worlds)])
    states = [{"rank": 0, "observation": "terminal", "outcome": outcome,
               "transitions": []} for outcome in ("success", "failure")]
    index = lambda word, used: 2 + word * used_count + used
    for word in range(worlds):
        for used in range(used_count):
            known = 0
            for i, mask in enumerate(masks):
                if used & (1 << i):
                    known |= mask
            transitions = [{"action": f"sample_{i}", "next": index(word, used | (1 << i))}
                           for i in range(len(masks)) if not used & (1 << i)]
            transitions += [{"action": f"select_{w}", "next": 0 if word == w else 1}
                            for w in range(worlds)]
            states.append({"rank": len(masks) - used.bit_count() + 1,
                           "observation": json.dumps([used, known, word & known]),
                           "outcome": "live", "transitions": transitions})
    return {"schema_version": "finite-belief-game-v1", "actions": actions,
            "states": states, "initial": [index(w, 0) for w in range(worlds)]}


def cover_cost(required, masks, costs):
    best = None
    for chosen in itertools.product((False, True), repeat=len(masks)):
        covered, total = 0, 0
        for take, mask, cost in zip(chosen, masks, costs):
            if take:
                covered |= mask
                total += cost
        if covered & required == required and (best is None or total < best):
            best = total
    return best


def renamed(game, rng):
    out = deepcopy(game)
    order = list(range(len(out["states"])))
    rng.shuffle(order)
    mapping = {old: new for new, old in enumerate(order)}
    out["states"] = [out["states"][old] for old in order]
    names = {action["id"]: f"action_{i}" for i, action in enumerate(reversed(out["actions"]))}
    tokens = {state["observation"] for state in out["states"]}
    token_map = {old: f"token_{i}" for i, old in enumerate(sorted(tokens))}
    for action in out["actions"]:
        action["id"] = names[action["id"]]
    rng.shuffle(out["actions"])
    for state in out["states"]:
        state["observation"] = token_map[state["observation"]]
        for transition in state["transitions"]:
            transition["action"] = names[transition["action"]]
            transition["next"] = mapping[transition["next"]]
        rng.shuffle(state["transitions"])
    out["initial"] = [mapping[s] for s in out["initial"]]
    rng.shuffle(out["initial"])
    return out


def source_hashes():
    paths = ["causalfill/belief_games.py", "causalfill/belief_certificates.py",
             "tools/stress_belief_v04.py"]
    return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths}


def run(cases):
    started = time.monotonic()
    before = source_hashes()
    rng = random.Random(904173)
    counts, failures, rows = Counter(), [], []

    def check(condition, label, context):
        counts["assertions"] += 1
        if not condition:
            failures.append({"label": label, "case": context})

    for case in range(cases):
        bits = 2 + case % 3
        masks = [1 << bit for bit in range(bits)]
        masks += [rng.randrange(1, 1 << bits), (1 << bits) - 1]
        costs = [rng.randrange(1, 10) for _ in masks]
        selection = rng.randrange(1, 5)
        expected = cover_cost((1 << bits) - 1, masks, costs) + selection
        game = sensor_game(bits, masks, costs, selection)
        base_cert = None
        modes = {}
        for mode in ("adaptive", "no_observe", "open_loop", "open_loop_no_observe"):
            cert = build_game_certificate(game, mode)
            result = verify_game_certificate(game, cert)
            counts["certificates"] += 1
            counts["beliefs_checked"] += result.get("checked_beliefs", 0)
            check(result["valid"], "certificate_valid", [case, mode])
            want = expected if mode == "adaptive" else None
            check(result.get("optimal_cost") == want, "analytic_optimum", [case, mode])
            modes[mode] = result.get("optimal_cost")
            if mode == "adaptive":
                base_cert = cert
                strategy = extract_game_strategy(game, cert)
                replay = verify_game_strategy(game, strategy)
                check(replay["valid"] and replay.get("worst_case_cost") == expected,
                      "independent_world_replay", case)
                counts["initial_worlds_replayed"] += replay.get("initial_states_checked", 0)

        transform = renamed(game, rng)
        transformed = verify_game_certificate(transform, build_game_certificate(transform))
        check(transformed["valid"] and transformed.get("optimal_cost") == expected,
              "state_action_observation_permutation", case)
        counts["metamorphic_cases"] += 1

        scaled = deepcopy(game)
        for action in scaled["actions"]:
            action["cost"] *= 3
        result = verify_game_certificate(scaled, build_game_certificate(scaled))
        check(result["valid"] and result.get("optimal_cost") == expected * 3,
              "uniform_cost_scaling", case)
        counts["metamorphic_cases"] += 1

        refined = deepcopy(game)
        refined["initial"] = refined["initial"][::2]  # The least bit is known zero.
        ref_expected = cover_cost(((1 << bits) - 1) ^ 1, masks, costs) + selection
        result = verify_game_certificate(refined, build_game_certificate(refined))
        check(result["valid"] and result.get("optimal_cost") == ref_expected <= expected,
              "public_prior_refinement", case)
        counts["metamorphic_cases"] += 1

        root = next(i for i, n in enumerate(base_cert["nodes"]) if n["belief"] == sorted(game["initial"]))
        mutations = []
        for value in (False, True, -1, expected - 1, expected + 1, None):
            bad = deepcopy(base_cert)
            bad["nodes"][root]["value"] = value
            mutations.append(("root_value_" + repr(value), bad))
        bad = deepcopy(base_cert)
        bad["root"] = bad["root"][:-1]
        mutations.append(("omit_possible_world", bad))
        bad = deepcopy(base_cert)
        bad["nodes"].pop(0)
        mutations.append(("omit_alternative_leaf", bad))
        bad = deepcopy(base_cert)
        bad["nodes"].append(deepcopy(bad["nodes"][root]))
        mutations.append(("duplicate_belief", bad))
        bad = deepcopy(base_cert)
        bad["game_sha256"] = "0" * 64
        mutations.append(("wrong_game_binding", bad))
        bad = deepcopy(base_cert)
        bad["mode"] = "no_observe"
        mutations.append(("policy_class_relabel", bad))
        for name, bad in mutations:
            verdict = verify_game_certificate(game, bad)
            check(not verdict["valid"], "forgery_" + name, case)
            counts["forged_certificates_rejected"] += not verdict["valid"]

        check(not verify_game_certificate(scaled, base_cert)["valid"], "changed_statement_binding", case)
        counts["forged_certificates_rejected"] += 1
        rows.append({"case": case, "bits": bits, "sensors": len(masks),
                     "sensor_masks": masks, "sensor_costs": costs,
                     "selection_cost": selection, "expected_cost": expected,
                     "states": len(game["states"]), "mode_values": modes})

    after = source_hashes()
    check(before == after, "source_stable_during_run", None)
    return {"schema": "causalfill.belief-analytic-audit.v1", "status": "passed" if not failures else "failed",
            "finished_utc": datetime.now(timezone.utc).isoformat(), "seconds": time.monotonic() - started,
            "source_sha256": after, "source_stable_during_run": before == after,
            "configuration": {"cases": cases, "deterministic_seed": 904173},
            "counts": dict(counts), "failures": failures, "cases": rows,
            "oracle": "minimum weighted sensor-set cover over a complete hidden bit cube; independent subset enumeration",
            "limitations": ["Assertions and mutated certificates are correlated engineering checks, not model task scores.",
                            "This analytic family validates the finite planner/checker; economic runtime conformance is audited separately."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=int, default=24)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.cases <= 300:
        parser.error("cases must be between 1 and 300")
    if args.output.exists():
        parser.error("output must be a fresh path")
    result = run(args.cases)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({k: result[k] for k in ("status", "seconds", "counts", "failures")}, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
