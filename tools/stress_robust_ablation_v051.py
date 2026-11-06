#!/usr/bin/env python3
"""Public-information scripted controls for sensing assumptions and oversensing.

These are deliberately restricted diagnostic policies, not learned agents.
Actual selected-world outcome is measured separately from justified success.
"""
from __future__ import annotations
import argparse
import copy
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from causalfill import __version__
from causalfill.domains.robust_sensing import RobustSensingTask, completion_for_history
from causalfill.robust_decisions import build_robust_certificate, extract_robust_policy
from causalfill.runner import source_fingerprint, write_json
from causalfill.session import Session, verify_trace


def restricted_policy(session, mode):
    contract = json.loads(session.call("read_file", {"path": "/formal/robust-sensing.json"})["content"])
    problem, observations = contract["problem"], []
    if mode == "assume_no_corruption":
        assumed = copy.deepcopy(problem); assumed["max_corruptions"] = 0
        certificate = build_robust_certificate(assumed)
        policy = extract_robust_policy(assumed, certificate)
        node = policy["root"]
        while policy["nodes"][node]["kind"] == "query":
            item = policy["nodes"][node]
            out = session.call("probe_" + item["id"], {})
            if "error" in out: return {}, "probe_error"
            observations.append({"experiment": item["id"], "outcome": out["outcome"]})
            if str(out["outcome"]) not in item["branches"]:
                return {}, "observation_impossible_under_wrong_assumption"
            node = item["branches"][str(out["outcome"])]
        action_id = policy["nodes"][node]["id"]
    elif mode == "query_every_sensor":
        for query in problem["experiments"]:
            out = session.call("probe_" + query["id"], {})
            if "error" in out: return {}, "operational_budget_or_session_budget"
            observations.append({"experiment": query["id"], "outcome": out["outcome"]})
        possible = [w for w in problem["worlds"] if sum(
            q["responses"][w] != o["outcome"] for q, o in zip(problem["experiments"], observations)
        ) <= problem["max_corruptions"]]
        safe = [a for a in problem["actions"] if possible and set(possible) <= set(a["success_worlds"])]
        if not safe: return {}, "no_justified_action"
        action_id = min(safe, key=lambda a: (a["cost"], a["id"]))["id"]
    else:
        raise ValueError("unknown restricted mode")
    out = session.call("commit_" + action_id, {})
    if "error" in out: return {}, "terminal_action_unaffordable"
    return completion_for_history(problem, observations, action_id), "submitted_action"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seeds", type=int, default=5)
    args = parser.parse_args()
    if args.output.exists(): parser.error("output directory must be new")
    args.output.mkdir(parents=True)
    before, started, records = source_fingerprint(), time.monotonic(), []
    for mode in ("assume_no_corruption", "query_every_sensor"):
        for split in ("train", "dev", "transfer"):
            for difficulty in (1, 2, 3):
                for seed in range(9101, 9101+args.seeds):
                    for twin in (0, 1):
                        task = RobustSensingTask(seed, split, difficulty, twin)
                        session = Session(task)
                        fill, reason = restricted_policy(session, mode)
                        session.call("submit", {"fill": fill, "confidence": 0.5, "abstain": False,
                            "evidence": [event["event_id"] for event in session.trace]})
                        action = task._actions.get(task.committed)
                        counts = task._mismatch_counts(task.commit_observations)
                        possible = [w for w, count in counts.items() if count <= task._problem["max_corruptions"]]
                        actual_success = bool(action and task._world in action["success_worlds"])
                        justified = bool(action and possible and set(possible) <= set(action["success_worlds"]))
                        row = {"mode": mode, "split": split, "difficulty": difficulty,
                               "seed": seed, "twin": twin, "reason": reason,
                               "strict_success": session.result["success"],
                               "committed": task.committed is not None,
                               "actual_operation_succeeded": actual_success,
                               "justified_at_commit": justified,
                               "queries": len(task.used), "operational_cost": task.operational_cost,
                               "certified_operational_budget": task.operational_budget,
                               "assigned_corruptions": len(task._faults),
                               "observed_corruptions": task._observed_faults,
                               "invalid_calls": session.invalid,
                               "trace_integrity": verify_trace(session.trace)}
                        records.append(row)
                        write_json(args.output/"traces"/(session.id+".json"),
                                   {"record": row, "public": session.public(), "events": session.trace})
    rows = []
    for mode in ("assume_no_corruption", "query_every_sensor"):
        selected = [r for r in records if r["mode"] == mode]
        rows.append({"mode": mode, "episodes": len(selected),
                     **{key: sum(r[key] for r in selected) for key in (
                         "strict_success", "committed", "actual_operation_succeeded", "justified_at_commit")},
                     "invalid_calls": sum(r["invalid_calls"] for r in selected),
                     "clean": {"episodes": sum(r["twin"] == 0 for r in selected),
                               "strict_success": sum(r["strict_success"] and r["twin"] == 0 for r in selected)},
                     "assigned_fault": {"episodes": sum(r["twin"] == 1 for r in selected),
                               "strict_success": sum(r["strict_success"] and r["twin"] == 1 for r in selected)}})
    write_json(args.output/"records.json", records)
    report = {"schema": "causalfill.robust-ablation.v051", "version": __version__,
              "source_fingerprint": before, "source_stable": before == source_fingerprint(),
              "episodes": len(records), "policies": rows,
              "trace_integrity": all(r["trace_integrity"] for r in records),
              "elapsed_seconds": round(time.monotonic()-started, 3),
              "scope": "Two deliberately restricted scripted controls. Outcome and justification have separate denominators. Paired generated fixtures are correlated; no AI score is implied."}
    write_json(args.output/"summary.json", report)
    print(json.dumps(report, indent=2))
    return 0 if report["source_stable"] and report["trace_integrity"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
