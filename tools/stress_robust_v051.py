#!/usr/bin/env python3
"""Independent finite-fault oracle and complete live-case replay audit.

The oracle expands every whole-episode fault subset into a separate latent
atom. It never uses mismatch counts, the planner state, or its recurrence code.
This is an evaluator development tool, not a model performance evaluation.
"""
from __future__ import annotations
import argparse
import copy
from functools import lru_cache
import hashlib
import itertools
import json
from pathlib import Path
import random
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from causalfill import __version__
from causalfill.domains.robust_sensing import RobustSensingTask, completion_for_history
from causalfill.robust_decisions import (
    SCHEMA, build_robust_certificate, extract_robust_policy,
    verify_robust_certificate, verify_robust_policy,
)
from causalfill.runner import source_fingerprint, write_json
from causalfill.session import Session, verify_trace


def fault_subsets(queries, k):
    for size in range(min(k, len(queries)) + 1):
        yield from itertools.combinations(queries, size)


def explicit_atom_optimum(problem, objective="action"):
    """Exact independent oracle: filter fixed (world, full fault pattern) atoms."""
    worlds, queries = problem["worlds"], problem["experiments"]
    atoms = [(wi, frozenset(pattern)) for wi in range(len(worlds))
             for pattern in fault_subsets(range(len(queries)), problem["max_corruptions"])]
    reported = [tuple(q["responses"][worlds[wi]] ^ int(qi in faults)
                      for qi, q in enumerate(queries)) for wi, faults in atoms]
    success_sets = [set(action["success_worlds"]) for action in problem["actions"]]

    @lru_cache(maxsize=None)
    def best(remaining, possible_atoms):
        live_worlds = {worlds[atoms[index][0]] for index in possible_atoms}
        terminal = ([0] if len(live_worlds) == 1 else []) if objective == "identification" else [
            action["cost"] for action, good in zip(problem["actions"], success_sets)
            if live_worlds <= good]
        options = list(terminal)
        for qi in remaining:
            rest = tuple(q for q in remaining if q != qi)
            child_costs = []
            for bit in (0, 1):
                branch = tuple(index for index in possible_atoms if reported[index][qi] == bit)
                if branch:
                    child_costs.append(best(rest, branch))
            if all(value is not None for value in child_costs):
                options.append(queries[qi]["cost"] + max(child_costs))
        return min(options) if options else None

    result = best(tuple(range(len(queries))), tuple(range(len(atoms))))
    return result, best.cache_info().currsize


def random_problem(rng, index):
    n, m = rng.randint(2, 6), rng.randint(1, 5)
    worlds = [f"w{i}" for i in range(n)]
    actions = [{"id": f"a{i}", "cost": rng.randrange(5),
                "success_worlds": [w for w in worlds if rng.randrange(2)]}
               for i in range(rng.randint(1, 6))]
    if index % 5 == 0:
        actions.append({"id": "common", "cost": rng.randrange(9), "success_worlds": worlds[:]})
    return {"schema": SCHEMA, "worlds": worlds, "max_corruptions": index % 3,
            "actions": actions, "experiments": [
                {"id": f"q{i}", "cost": rng.randint(1, 5),
                 "responses": {w: rng.randrange(2) for w in worlds}}
                for i in range(m)]}


def complement_problem(bits, k, costs, terminal, bypass=None):
    worlds = [f"w{i}" for i in range(1 << bits)]
    actions = [{"id": f"a{i}", "cost": terminal,
                "success_worlds": [w for w in worlds if w != worlds[i]]}
               for i in range(len(worlds))]
    if bypass is not None:
        actions.append({"id": "bypass", "cost": bypass, "success_worlds": worlds[:]})
    return {"schema": SCHEMA, "worlds": worlds, "max_corruptions": k,
            "actions": actions, "experiments": [
                {"id": f"q{i}", "cost": costs[i],
                 "responses": {w: (j >> i) & 1 for j, w in enumerate(worlds)}}
                for i in range(bits)]}


class Audit:
    def __init__(self, output):
        self.output, self.failures, self.counts = output, [], {}
        self.oracle_states = 0
        self.artifact_nodes = 0
        self.mutation_rejections = {}

    def check(self, condition, label, **details):
        self.counts[label] = self.counts.get(label, 0) + 1
        if not condition:
            self.failures.append({"check": label, **details})

    def certified(self, problem, objective="action", oracle=True):
        certificate = build_robust_certificate(problem, objective)
        checked = verify_robust_certificate(problem, certificate, expected_objective=objective)
        self.check(checked["valid"], "certificate_valid", check_result=checked)
        self.artifact_nodes += len(certificate["nodes"])
        if oracle:
            expected, states = explicit_atom_optimum(problem, objective)
            self.oracle_states += states
            self.check(expected == certificate["value"], "independent_optimum",
                       problem=problem, objective=objective, expected=expected,
                       received=certificate["value"])
        if certificate["value"] is not None:
            policy = extract_robust_policy(problem, certificate)
            result = verify_robust_policy(problem, policy, expected_objective=objective)
            self.check(result["valid"], "independent_policy_replay", result=result)
        return certificate


def complete_tiny_corpus(audit):
    # All truth tables and two labeled action success sets for 2 worlds,
    # 2 queries, three corruption caps, and two declared cost profiles.
    count = 0
    for truth_bits, action_bits, k, weighted in itertools.product(range(16), range(16), range(3), (False, True)):
        worlds = ["u", "v"]
        problem = {"schema": SCHEMA, "worlds": worlds, "max_corruptions": k,
                   "experiments": [{"id": f"q{q}", "cost": (q + 2 if weighted else 1),
                       "responses": {w: (truth_bits >> (2*q + wi)) & 1 for wi, w in enumerate(worlds)}}
                       for q in range(2)],
                   "actions": [{"id": f"a{a}", "cost": (a + 1 if weighted else 0),
                       "success_worlds": [w for wi, w in enumerate(worlds) if action_bits >> (2*a+wi) & 1]}
                       for a in range(2)]}
        for objective in ("action", "identification"):
            audit.certified(problem, objective)
        count += 1
    return {"models": count, "objectives_per_model": 2,
            "scope": "complete 2-world/2-query/2-action binary tables, k=0..2, two explicit cost profiles"}


def analytic_cases(audit):
    rows = []
    for bits, k, scale, terminal, bypass in itertools.product(range(1, 6), range(3), (1, 3), (0, 2), (None, 0, 5)):
        costs = [scale * (2*i + 1) for i in range(bits)][::-1]
        problem = complement_problem(bits, k, costs, terminal, bypass)
        expected = terminal + sum(sorted(costs)[:k+1]) if k < bits else None
        if bypass is not None:
            expected = bypass if expected is None else min(expected, bypass)
        certificate = audit.certified(problem, oracle=False)
        audit.check(certificate["value"] == expected, "analytic_cube_formula",
                    problem=problem, expected=expected, received=certificate["value"])
        rows.append({"bits": bits, "k": k, "costs": costs, "terminal_cost": terminal,
                     "bypass_cost": bypass, "expected": expected, "certified": certificate["value"]})
    return rows


def mutate_certificate(audit, problem, certificate):
    alterations = {}
    forged = copy.deepcopy(certificate); forged["problem_sha256"] = "0" * 64
    alterations["stale_digest"] = forged
    forged = copy.deepcopy(certificate)
    forged["value"] = 0 if certificate["value"] is None else certificate["value"] + 1
    alterations["wrong_optimum"] = forged
    forged = copy.deepcopy(certificate); forged["nodes"].append(copy.deepcopy(forged["nodes"][0]))
    alterations["duplicate_state"] = forged
    forged = copy.deepcopy(certificate)
    forged["nodes"] = [row for row in forged["nodes"] if row[:2] != forged["root"]]
    alterations["missing_root"] = forged
    forged = copy.deepcopy(certificate); forged["objective"] = "identification"
    alterations["untrusted_objective_switch"] = forged
    for label, altered in alterations.items():
        result = verify_robust_certificate(problem, altered, expected_objective="action")
        rejected = not result["valid"]
        audit.check(rejected, "certificate_mutation_rejected", mutation=label, result=result)
        audit.mutation_rejections[label] = audit.mutation_rejections.get(label, 0) + int(rejected)


def metamorphic(audit, problem, original, index):
    def cost(model): return audit.certified(model, oracle=False)["value"]
    scaled = copy.deepcopy(problem)
    for item in scaled["experiments"] + scaled["actions"]: item["cost"] *= 3
    audit.check(cost(scaled) == (None if original is None else 3*original), "cost_scaling")
    renamed = copy.deepcopy(problem)
    mapping = {w: f"renamed_{index}_{i}" for i, w in enumerate(problem["worlds"])}
    renamed["worlds"] = [mapping[w] for w in reversed(problem["worlds"])]
    for i, q in enumerate(renamed["experiments"]):
        q["id"] = f"sensor_{i}"
        q["responses"] = {mapping[w]: value ^ (i % 2) for w, value in q["responses"].items()}
    renamed["experiments"].reverse()
    for i, action in enumerate(renamed["actions"]):
        action["id"] = f"operation_{i}"
        action["success_worlds"] = [mapping[w] for w in reversed(action["success_worlds"])]
    renamed["actions"].reverse()
    audit.check(cost(renamed) == original, "renaming_order_and_polarity")
    if problem["max_corruptions"] < 2:
        more_faults = copy.deepcopy(problem); more_faults["max_corruptions"] += 1
        altered = cost(more_faults)
        audit.check(altered is None or (original is not None and altered >= original), "corruption_monotonicity")
    extra = copy.deepcopy(problem)
    extra["experiments"].append({"id": "constant_extra", "cost": 2,
                                 "responses": {w: 0 for w in problem["worlds"]}})
    altered = cost(extra)
    audit.check(original is None or (altered is not None and altered <= original), "query_addition_monotonicity")


def replay_runtime(audit, seeds):
    profiles, cases, transitions, worst_witnesses = [], 0, 0, []
    faults_seen, unexposed, terminal_choices = 0, 0, set()
    for seed, split, difficulty in itertools.product(seeds, ("train", "dev", "transfer"), (1, 2, 3)):
        base = RobustSensingTask(seed, split, difficulty)
        problem, policy = base.public_problem(), base.robust_policy()
        query_ids = [q["id"] for q in problem["experiments"]]
        largest, smallest, profile_cases, worst = 0, None, 0, None
        for world in problem["worlds"]:
            for faults in fault_subsets(query_ids, problem["max_corruptions"]):
                task = base.clone_for_case(world, faults)
                session = Session(task)
                session.call("read_file", {"path": "/formal/robust-sensing.json"})
                node, observations = policy["root"], []
                while policy["nodes"][node]["kind"] == "query":
                    item = policy["nodes"][node]
                    out = session.call("probe_" + item["id"], {})
                    audit.check("error" not in out, "runtime_probe_accepted")
                    if "error" in out: break
                    observations.append({"experiment": item["id"], "outcome": out["outcome"]})
                    # Independent truth check, using the whole fixed fault subset.
                    query = next(q for q in problem["experiments"] if q["id"] == item["id"])
                    audit.check(out["outcome"] == (query["responses"][world] ^ int(item["id"] in faults)),
                                "runtime_observation_matches_case")
                    node = item["branches"][str(out["outcome"])]
                    transitions += 1
                leaf = policy["nodes"][node]
                if leaf["kind"] != "act":
                    audit.check(False, "runtime_missing_terminal"); continue
                response = session.call("commit_" + leaf["id"], {})
                audit.check(response.get("committed") is True, "runtime_commit_accepted")
                fill = completion_for_history(problem, observations, leaf["id"])
                session.call("submit", {"fill": fill, "confidence": 1.0, "abstain": False,
                    "evidence": [event["event_id"] for event in session.trace]})
                audit.check(bool(session.result and session.result["success"]), "runtime_case_success",
                            split=split, difficulty=difficulty, seed=seed, world=world, faults=faults,
                            result=session.result)
                audit.check(verify_trace(session.trace), "runtime_trace_integrity")
                audit.check(task.operational_cost <= base.operational_budget, "runtime_within_bound")
                if task.operational_cost > largest:
                    largest = task.operational_cost
                    worst = {"world": world, "faults": list(faults), "trace": session.trace,
                             "result": session.result}
                smallest = task.operational_cost if smallest is None else min(smallest, task.operational_cost)
                observed = sum(q in task.used for q in faults)
                faults_seen += observed
                unexposed += int(bool(faults) and observed == 0)
                terminal_choices.add((split, difficulty, seed, leaf["id"]))
                cases += 1; profile_cases += 1; transitions += 1
        audit.check(largest == base.operational_budget, "runtime_bound_attained",
                    split=split, difficulty=difficulty, budget=base.operational_budget, attained=largest)
        profile = {"seed": seed, "split": split, "difficulty": difficulty,
                   "worlds": len(problem["worlds"]), "experiments": len(query_ids),
                   "max_corruptions": problem["max_corruptions"], "terminal_actions": len(problem["actions"]),
                   "cases": profile_cases, "minimum_runtime_cost": smallest, "worst_runtime_cost": largest,
                   "certified_operational_budget": base.operational_budget,
                   "certificate_states": len(base._certificate["nodes"])}
        profiles.append(profile)
        name = f"{split}-{difficulty}-seed{seed}"
        write_json(audit.output/"profiles"/(name+".json"), {"profile": profile, "problem": problem,
            "certificate": base.robust_certificate(), "policy": policy, "worst_case": worst})
        worst_witnesses.append(name)
        print(json.dumps({"runtime_profile": name, "cases": profile_cases,
                          "cost_range": [smallest, largest]}), flush=True)
    return {"profiles": profiles, "cases": cases, "executed_probe_and_commit_transitions": transitions,
            "observed_corruptions": faults_seen, "assigned_fault_cases_with_zero_exposure": unexposed,
            "distinct_profile_action_choices": len(terminal_choices), "worst_case_witnesses": worst_witnesses,
            "scope": "every fixed world and every whole fault subset of size at most k for the selected finite profiles; one certified policy, not every policy"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=int, default=256)
    parser.add_argument("--runtime-seeds", type=int, default=3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists(): parser.error("output must be a new directory")
    if not 1 <= args.cases <= 4096 or not 1 <= args.runtime_seeds <= 12:
        parser.error("cases must be 1..4096 and runtime-seeds 1..12")
    args.output.mkdir(parents=True)
    start, before = time.monotonic(), source_fingerprint()
    audit = Audit(args.output)
    tiny = complete_tiny_corpus(audit)
    print(json.dumps({"complete_tiny_models": tiny["models"]}), flush=True)
    analytic = analytic_cases(audit)
    rng = random.Random(20261105)
    random_rows = []
    for index in range(args.cases):
        problem = random_problem(rng, index)
        cert = audit.certified(problem)
        identity = audit.certified(problem, "identification")
        mutate_certificate(audit, problem, cert)
        if index < 128: metamorphic(audit, problem, cert["value"], index)
        random_rows.append({"problem": problem, "action_cost": cert["value"],
                            "identification_cost": identity["value"]})
    runtime = replay_runtime(audit, [4103+i for i in range(args.runtime_seeds)])
    write_json(args.output/"analytic-cases.json", analytic)
    write_json(args.output/"random-cases.json", random_rows)
    after = source_fingerprint()
    audit.check(before == after, "core_source_stable")
    report = {"schema": "causalfill.robust-stress.v051", "version": __version__,
              "passed": not audit.failures, "failures": audit.failures,
              "checks": audit.counts, "complete_tiny_corpus": tiny,
              "random_models": len(random_rows), "analytic_cases": len(analytic),
              "independent_oracle_states": audit.oracle_states,
              "verified_certificate_state_occurrences": audit.artifact_nodes,
              "mutation_rejections": audit.mutation_rejections, "runtime": runtime,
              "source_fingerprint": before, "source_stable": before == after,
              "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "elapsed_seconds": round(time.monotonic()-start, 3),
              "scope": "finite development checks; neither independent task samples nor AI performance"}
    write_json(args.output/"result.json", report)
    print(json.dumps({k: report[k] for k in ("passed", "checks", "random_models", "analytic_cases",
                                            "mutation_rejections", "elapsed_seconds")}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
