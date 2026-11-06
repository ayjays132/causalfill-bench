"""Semantic, corruption, and complete-policy tests for finite belief games.

The small oracle enumerates full syntactic three-step observation policies and
replays their actions. It does not use a Bellman recurrence, optimizer helper,
certificate transition routine, or production policy verifier.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
import hashlib
import itertools
import json
from pathlib import Path
import random
import sys
import time
import unittest
from unittest.mock import patch

from causalfill.belief_games import (
    GAME_SCHEMA, MODES, MAX_BELIEF_NODES, MAX_INITIAL_STATES,
    build_game_certificate, game_digest, successor_beliefs, validate_game,
)
from causalfill.belief_certificates import (
    expand_game_certificate, extract_game_strategy, verify_game_certificate,
    verify_game_strategy,
)


def signal_game(*, sensor_kind="observe", robust_cost=None):
    actions = [{"id": "inspect", "cost": 2, "kind": sensor_kind},
               {"id": "buy0", "cost": 3, "kind": "act"},
               {"id": "buy1", "cost": 3, "kind": "act"}]
    if robust_cost is not None:
        actions.append({"id": "robust", "cost": robust_cost, "kind": "act"})
    states = []
    for state in range(4):
        bit = state % 2
        edges = [{"action": "buy0", "next": 4 if bit == 0 else 5},
                 {"action": "buy1", "next": 4 if bit == 1 else 5}]
        if state < 2:
            edges.insert(0, {"action": "inspect", "next": state+2})
        if robust_cost is not None:
            edges.append({"action": "robust", "next": 4})
        states.append({"rank": 2 if state < 2 else 1,
                       "observation": "unknown" if state < 2 else f"signal:{bit}",
                       "outcome": "live", "transitions": edges})
    states.extend([{"rank": 0, "observation": "done", "outcome": outcome, "transitions": []}
                   for outcome in ("success", "failure")])
    return {"schema_version": GAME_SCHEMA, "actions": actions, "states": states, "initial": [0, 1]}


def evolving_game(stages=2):
    """Independent stage construction: guessing wrong is irrevocable failure."""
    worlds = list(itertools.product((0, 1), repeat=stages))
    states = [{"rank": 0, "observation": "done", "outcome": "success", "transitions": []},
              {"rank": 0, "observation": "done", "outcome": "failure", "transitions": []}]
    ids = {}
    for world in range(len(worlds)):
        for stage in range(stages):
            for inspected in (False, True):
                ids[world, stage, inspected] = len(states)
                states.append({})
    for (world, stage, inspected), index in ids.items():
        bit = worlds[world][stage]
        target = 0 if stage == stages-1 else ids[world, stage+1, False]
        transitions = [{"action": f"buy{choice}", "next": target if choice == bit else 1}
                       for choice in (0, 1)]
        if not inspected:
            transitions.append({"action": "inspect", "next": ids[world, stage, True]})
        states[index] = {"rank": 2*(stages-stage)-int(inspected),
                         "observation": f"stage:{stage}" + (f":signal:{bit}" if inspected else ""),
                         "outcome": "live", "transitions": transitions}
    return {"schema_version": GAME_SCHEMA,
            "actions": [{"id": "inspect", "cost": 1, "kind": "observe"},
                        {"id": "buy0", "cost": 1, "kind": "act"},
                        {"id": "buy1", "cost": 1, "kind": "act"}],
            "states": states, "initial": [ids[w, 0, False] for w in range(len(worlds))]}


def layered_game(rng):
    """Eight states, three decisions and two possible initial worlds."""
    actions = [{"id": name, "cost": rng.randrange(1, 4), "kind": kind}
               for name, kind in (("sample", "observe"), ("left", "act"), ("right", "act"))]
    states = []
    for index in range(6):
        layer = index // 2
        offset = 2*(layer+1)
        states.append({"rank": 3-layer,
                       "observation": "start" if layer == 0 else ("lo" if rng.randrange(2) == 0 else "hi"),
                       "outcome": "live",
                       "transitions": [{"action": a["id"], "next": offset+rng.randrange(2)} for a in actions]})
    states.extend([{"rank": 0, "observation": "done", "outcome": outcome, "transitions": []}
                   for outcome in ("success", "failure")])
    return {"schema_version": GAME_SCHEMA, "actions": actions, "states": states, "initial": [0, 1]}


def complete_policy_oracle(game, mode):
    """Enumerate every depth-three contingency assignment and simulate it.

    These test games reach a terminal state only after exactly three decisions.
    The seven history slots cover all binary feedback histories of length <3;
    even unreachable slot assignments are enumerated. Thus the counted objects
    are syntactic policies and may induce the same realized behavior.
    """
    action_table = {item["id"]: item for item in game["actions"]}
    allowed = [name for name, item in action_table.items()
               if mode not in ("no_observe", "open_loop_no_observe") or item["kind"] == "act"]
    fixed = mode in ("open_loop", "open_loop_no_observe")
    histories = [()] if fixed else [(), ("lo",), ("hi",), ("lo", "lo"), ("lo", "hi"), ("hi", "lo"), ("hi", "hi")]
    width = 3 if fixed else len(histories)
    count, winning, best = 0, 0, None
    for assignment in itertools.product(allowed, repeat=width):
        count += 1
        controller = None if fixed else dict(zip(histories, assignment))
        costs = []
        for initial in game["initial"]:
            current, history, total = initial, (), 0
            for depth in range(3):
                action = assignment[depth] if fixed else controller[history]
                # Deliberately scan the raw transition rows. No production
                # parser, bit masks, belief update, or recurrence is reused.
                row = game["states"][current]
                next_rows = [edge["next"] for edge in row["transitions"] if edge["action"] == action]
                if len(next_rows) != 1:
                    break
                current = next_rows[0]
                total += action_table[action]["cost"]
                history += (game["states"][current]["observation"],)
            if game["states"][current]["outcome"] != "success":
                break
            costs.append(total)
        if len(costs) == len(game["initial"]):
            winning += 1
            value = max(costs)
            best = value if best is None else min(best, value)
    return {"optimal_cost": best, "syntactic_policies": count, "winning_syntactic_policies": winning}


class BeliefGameTests(unittest.TestCase):
    def assertCertificate(self, game, mode, expected):
        certificate = build_game_certificate(game, mode)
        checked = verify_game_certificate(game, certificate)
        self.assertTrue(checked["valid"], checked)
        self.assertEqual(checked["optimal_cost"], expected)
        if expected is not None:
            strategy = extract_game_strategy(game, certificate)
            replay = verify_game_strategy(game, strategy)
            self.assertTrue(replay["valid"], replay)
            self.assertEqual(replay["worst_case_cost"], expected)
        return certificate

    def test_sensing_cost_and_three_distinct_restrictions(self):
        game = signal_game()
        self.assertCertificate(game, "adaptive", 5)
        for mode in ("no_observe", "open_loop", "open_loop_no_observe"):
            self.assertCertificate(game, mode, None)

    def test_no_observe_keeps_operational_feedback(self):
        game = signal_game(sensor_kind="act")
        self.assertCertificate(game, "no_observe", 5)
        self.assertCertificate(game, "open_loop_no_observe", None)

    def test_robust_completion_can_win_without_sensing(self):
        game = signal_game(robust_cost=8)
        self.assertCertificate(game, "adaptive", 5)
        for mode in ("no_observe", "open_loop", "open_loop_no_observe"):
            self.assertCertificate(game, mode, 8)
        # A valid suboptimal strategy still passes the strategy-only verifier.
        strategy = {"schema_version": "finite-belief-strategy-v1", "game_sha256": game_digest(game),
                    "mode": "adaptive", "root": 0,
                    "nodes": [{"action": "robust", "branches": [{"observation": "done", "next": 1}]}, {"stop": True}]}
        checked = verify_game_strategy(game, strategy)
        self.assertTrue(checked["valid"], checked)
        self.assertEqual(checked["worst_case_cost"], 8)

    def test_evolving_world_requires_new_observations_after_actions(self):
        for stages in (2, 3, 4):
            game = evolving_game(stages)
            certificate = self.assertCertificate(game, "adaptive", 2*stages)
            self.assertCertificate(game, "no_observe", None)
            self.assertCertificate(game, "open_loop", None)
            arena = expand_game_certificate(game, certificate)
            for index, node in enumerate(arena["nodes"]):
                for choice in node["choices"]:
                    self.assertTrue(all(child < index for child in choice["children"]))

    def test_complete_policy_enumeration_matches_all_modes(self):
        rng = random.Random(2026110404)
        for case in range(20):
            game = layered_game(rng)
            for mode in MODES:
                oracle = complete_policy_oracle(game, mode)
                with self.subTest(case=case, mode=mode):
                    self.assertCertificate(game, mode, oracle["optimal_cost"])

    def test_bound_checker_does_not_use_optimizer_or_producer_transitions(self):
        game = signal_game()
        certificate = build_game_certificate(game)
        with patch("causalfill.belief_games.build_game_certificate", side_effect=AssertionError("optimizer used")), \
             patch("causalfill.belief_games._choices", side_effect=AssertionError("producer transitions used")):
            self.assertTrue(verify_game_certificate(game, certificate)["valid"])

    def test_policy_replay_does_not_use_bellman_checker(self):
        game = signal_game()
        strategy = extract_game_strategy(game, build_game_certificate(game))
        with patch("causalfill.belief_certificates._alternatives", side_effect=AssertionError("recurrence used")), \
             patch("causalfill.belief_certificates.verify_game_certificate", side_effect=AssertionError("bound checker used")):
            self.assertTrue(verify_game_strategy(game, strategy)["valid"])

    def test_alternative_optimal_action_is_accepted(self):
        game = signal_game(robust_cost=5)
        certificate = build_game_certificate(game)
        root = next(node for node in certificate["nodes"] if node["belief"] == certificate["root"])
        root["action"] = "robust"
        self.assertTrue(verify_game_certificate(game, certificate)["valid"])
        strategy = extract_game_strategy(game, certificate)
        self.assertTrue(verify_game_strategy(game, strategy)["valid"])

    def test_wrong_bounds_missing_alternatives_and_wrong_modes_fail(self):
        game = signal_game(robust_cost=8)
        original = build_game_certificate(game)
        for value in (0, 4, 6, 8, None, True):
            certificate = copy.deepcopy(original)
            next(node for node in certificate["nodes"] if node["belief"] == certificate["root"])["value"] = value
            self.assertFalse(verify_game_certificate(game, certificate)["valid"])
        omitted = copy.deepcopy(original)
        omitted["nodes"] = [node for node in omitted["nodes"] if node["belief"] != [4, 5]]
        self.assertFalse(verify_game_certificate(game, omitted)["valid"])
        changed_mode = copy.deepcopy(original)
        changed_mode["mode"] = "no_observe"
        self.assertFalse(verify_game_certificate(game, changed_mode)["valid"])
        swapped = copy.deepcopy(game)
        swapped["actions"][0]["cost"] += 1
        self.assertFalse(verify_game_certificate(swapped, original)["valid"])

    def test_infinity_cannot_be_forged_and_nonminimal_policy_is_not_a_bound(self):
        game = signal_game()
        cert = build_game_certificate(game, "open_loop")
        self.assertIsNone(verify_game_certificate(game, cert)["optimal_cost"])
        root = next(node for node in cert["nodes"] if node["belief"] == cert["root"])
        root.update(value=5, action="inspect")
        self.assertFalse(verify_game_certificate(game, cert)["valid"])
        with self.assertRaises(ValueError):
            extract_game_strategy(game, build_game_certificate(game, "no_observe"))

    def test_duplicate_unreachable_and_boolean_belief_forgery(self):
        game = signal_game()
        base = build_game_certificate(game)
        forged = copy.deepcopy(base); forged["nodes"].append(copy.deepcopy(forged["nodes"][0]))
        self.assertFalse(verify_game_certificate(game, forged)["valid"])
        forged = copy.deepcopy(base); forged["nodes"].append({"belief": [0], "value": 5, "action": "inspect"})
        self.assertFalse(verify_game_certificate(game, forged)["valid"])
        forged = copy.deepcopy(base); forged["root"] = [False, 1]
        self.assertFalse(verify_game_certificate(game, forged)["valid"])
        forged = copy.deepcopy(base); forged["nodes"] *= MAX_BELIEF_NODES+1
        self.assertFalse(verify_game_certificate(game, forged)["valid"])

    def test_strategy_cannot_use_private_world_ids_or_omit_observations(self):
        game = signal_game()
        base = extract_game_strategy(game, build_game_certificate(game))
        mutations = []
        broken = copy.deepcopy(base); broken["nodes"][0]["branches"].pop(); mutations.append(broken)
        broken = copy.deepcopy(base); broken["nodes"][0]["world"] = 0; mutations.append(broken)
        broken = copy.deepcopy(base); broken["mode"] = "open_loop"; mutations.append(broken)
        broken = copy.deepcopy(base); broken["nodes"].append({"stop": True}); mutations.append(broken)
        broken = copy.deepcopy(base); broken["nodes"] = [{"stop": True}]; mutations.append(broken)
        broken = copy.deepcopy(base)
        leaf = next(node for node in broken["nodes"] if "stop" in node); leaf["stop"] = 1; mutations.append(broken)
        for strategy in mutations:
            self.assertFalse(verify_game_strategy(game, strategy)["valid"])

    def test_public_successor_helper_and_defensive_data(self):
        game = signal_game(); before = copy.deepcopy(game)
        root = sorted(game["initial"])
        self.assertEqual(successor_beliefs(game, root, "inspect"), {"signal:0": [2], "signal:1": [3]})
        self.assertEqual(successor_beliefs(game, root, "inspect", "open_loop"), {"*": [2, 3]})
        with self.assertRaises(ValueError): successor_beliefs(game, root, "inspect", "no_observe")
        with self.assertRaises(ValueError): successor_beliefs(game, [1, 0], "inspect")
        build_game_certificate(game)
        self.assertEqual(before, game)

    def test_early_terminal_world_is_absorbing_for_fixed_scripts(self):
        game = {"schema_version": GAME_SCHEMA, "actions": [{"id": "step", "cost": 1, "kind": "act"}],
                "initial": [0, 1], "states": [
                    {"rank": 3, "observation": "start", "outcome": "live", "transitions": [{"action": "step", "next": 2}]},
                    {"rank": 1, "observation": "start", "outcome": "live", "transitions": [{"action": "step", "next": 4}]},
                    {"rank": 2, "observation": "mid", "outcome": "live", "transitions": [{"action": "step", "next": 3}]},
                    {"rank": 1, "observation": "mid", "outcome": "live", "transitions": [{"action": "step", "next": 4}]},
                    {"rank": 0, "observation": "done", "outcome": "success", "transitions": []}]}
        for mode in MODES:
            cert = self.assertCertificate(game, mode, 3)
            replay = verify_game_strategy(game, extract_game_strategy(game, cert))
            self.assertEqual(replay["per_initial_costs"], [3, 1])

    def test_strict_schema_and_rank_contract(self):
        mutations = []
        for location, key, value in (("action", "cost", True), ("action", "cost", 0), ("action", "cost", 1.5),
                                     ("state", "rank", True), ("state", "observation", 1)):
            game = signal_game(); game["actions" if location == "action" else "states"][0][key] = value; mutations.append(game)
        game = signal_game(); game["states"][0]["transitions"][0]["next"] = 0; mutations.append(game)
        game = signal_game(); game["states"][1]["transitions"].pop(); mutations.append(game)
        game = signal_game(); game["states"][0]["observation"] = "x"*4097; mutations.append(game)
        game = signal_game(); game["states"][0]["observation"] = "\ud800"; mutations.append(game)
        game = signal_game(); game["states"][4]["rank"] = 1; mutations.append(game)
        game = signal_game(); game["initial"] = [0, 0]; mutations.append(game)
        game = signal_game(); game["initial"] = [0, 2]; mutations.append(game)
        game = signal_game(); game["current_world"] = 0; mutations.append(game)
        for index, game in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises((ValueError, TypeError)):
                validate_game(game)

    def test_terminal_goal_and_terminal_failure_have_distinct_values(self):
        for outcome, value in (("success", 0), ("failure", None)):
            game = {"schema_version": GAME_SCHEMA, "actions": [{"id": "unused", "cost": 1, "kind": "act"}],
                    "states": [{"rank": 0, "observation": "done", "outcome": outcome, "transitions": []}], "initial": [0]}
            for mode in MODES:
                self.assertCertificate(game, mode, value)


def run_audit(output: Path, games: int = 256):
    started = datetime.now(timezone.utc).isoformat()
    clock = time.perf_counter()
    rng = random.Random(2026110404)
    counts = {mode: {"games": 0, "syntactic_policies": 0, "winning_syntactic_policies": 0,
                     "certificate_checks": 0, "strategy_replays": 0, "unsolvable_instances": 0} for mode in MODES}
    failures = []
    transcript = hashlib.sha256()
    for index in range(games):
        game = layered_game(rng)
        for mode in MODES:
            oracle = complete_policy_oracle(game, mode)
            certificate = build_game_certificate(game, mode)
            verdict = verify_game_certificate(game, certificate)
            row = counts[mode]
            row["games"] += 1
            row["syntactic_policies"] += oracle["syntactic_policies"]
            row["winning_syntactic_policies"] += oracle["winning_syntactic_policies"]
            row["certificate_checks"] += 1
            if not verdict["valid"] or verdict["optimal_cost"] != oracle["optimal_cost"]:
                failures.append({"case": index, "mode": mode, "oracle": oracle, "verifier": verdict})
            if verdict.get("valid") and verdict.get("winning"):
                strategy = extract_game_strategy(game, certificate)
                replay = verify_game_strategy(game, strategy)
                row["strategy_replays"] += 1
                if not replay["valid"] or replay["worst_case_cost"] != oracle["optimal_cost"]:
                    failures.append({"case": index, "mode": mode, "oracle": oracle, "strategy": replay})
            else:
                row["unsolvable_instances"] += 1
            transcript.update(json.dumps([index, mode, oracle, verdict.get("optimal_cost")], sort_keys=True).encode())
    root = Path(__file__).resolve().parents[1]
    sources = [root/"causalfill/belief_games.py", root/"causalfill/belief_certificates.py", Path(__file__)]
    report = {"schema": "causalfill.belief-game-independent-audit.v1", "status": "passed" if not failures else "failed",
              "seed": 2026110404, "games": games, "modes": counts, "failures": failures,
              "complete_syntactic_policies_enumerated": sum(row["syntactic_policies"] for row in counts.values()),
              "exact_optimum_comparisons": games*len(MODES),
              "deterministic_transcript_sha256": transcript.hexdigest(),
              "source_sha256": {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources},
              "started_at_utc": started, "finished_at_utc": datetime.now(timezone.utc).isoformat(),
              "elapsed_seconds": round(time.perf_counter()-clock, 6),
              "method": "Enumerate complete depth-three binary-feedback contingency assignments and replay the raw transitions for every initial world. No Bellman/production belief update is used by the numerical oracle.",
              "limits": ["Finite small-game coverage, not a proof of Python implementation soundness.",
                         "Syntactic policy assignments include unreachable histories and may induce identical realized behavior.",
                         "This internal AI-assisted audit is not an independent laboratory replication or model-solver evaluation."]}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False)+"\n")
    return report


if __name__ == "__main__":
    if "--audit-output" in sys.argv:
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--audit-output", type=Path, required=True)
        parser.add_argument("--games", type=int, default=256)
        args = parser.parse_args()
        if not 1 <= args.games <= 4096: parser.error("games must be 1..4096")
        result = run_audit(args.audit_output, args.games)
        print(json.dumps({key: result[key] for key in ("status", "games", "complete_syntactic_policies_enumerated", "exact_optimum_comparisons", "elapsed_seconds")}, indent=2))
        raise SystemExit(result["status"] != "passed")
    unittest.main()

