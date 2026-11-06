#!/usr/bin/env python3
"""Measure the v0.5.2 scoring regressions in a fresh, inspectable run directory.

This is an author/evaluator audit. The public reference control supplies valid
operations; deliberately selected lucky and failed actions use evaluator state.
The resulting episodes are correlated scripted checks, never AI-model scores.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shlex
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from causalfill import __version__
from causalfill.domains.robust_sensing import RobustSensingTask, completion_for_history
from causalfill.metrics import summarize
from causalfill.policies import evidence_reference
from causalfill.runner import source_fingerprint, write_json
from causalfill.session import Session, verify_trace
from causalfill.types import SCORING_VERSION, digest


SCENARIOS = (
    "valid_completion", "wrong_digest", "missing_exclusions", "wrong_named_action",
    "lucky_unjustified_commit", "failed_commit", "abstain_after_commit",
    "disconnect_after_commit", "no_commit",
)
SCOPE = (
    "Author/evaluator scripted regression audit, not an AI-model evaluation. "
    "Valid operations use the public-information reference control. Lucky and failed "
    "actions are deliberately selected using evaluator state. Scenarios reuse one "
    "generated contract and are not independent mechanism replications. The grouping "
    "fixture is derived metadata, not additional episodes. No new Lean run is implied."
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def independent_operation_state(task: RobustSensingTask) -> dict:
    """Check executed state directly, without reading submitted certificate data."""
    problem = task.public_problem()
    action = next((item for item in problem["actions"] if item["id"] == task.committed), None)
    table = {item["id"]: item["responses"] for item in problem["experiments"]}
    compatible = [world for world in problem["worlds"] if sum(
        table[observation["experiment"]][world] != observation["outcome"]
        for observation in task.commit_observations
    ) <= problem["max_corruptions"]] if action else []
    return {
        "action_committed": action is not None,
        "committed_action": task.committed,
        "actual_operation_succeeded": bool(action and task._world in action["success_worlds"]),
        "action_justified_before_commit": bool(action and compatible
            and set(compatible) <= set(action["success_worlds"])),
        "compatible_worlds_at_commit": len(compatible) if action else None,
    }


def run_scenario(name: str, seed: int) -> tuple[Session, dict, dict]:
    task = RobustSensingTask(seed, "train", 1, 0)
    session = Session(task)
    if name in ("lucky_unjustified_commit", "failed_commit"):
        # Explicit author-side fixture selection: these are not solver policies.
        actual_success = name == "lucky_unjustified_commit"
        action = next(item for item in task.public_problem()["actions"]
                      if (task._world in item["success_worlds"]) == actual_success)
        response = session.call("commit_" + action["id"], {})
        if not response.get("committed"):
            raise RuntimeError("deliberate audit action did not execute")
        fill = completion_for_history(task.public_problem(), [], action["id"])
    elif name == "no_commit":
        fill = {}
    else:
        fill, abstained = evidence_reference(session.public(), session.call)
        if abstained:
            raise RuntimeError("reference control unexpectedly abstained")
        if name == "wrong_digest":
            fill["problem_sha256"] = "0" * 64
        elif name == "missing_exclusions":
            del fill["exclusions"]
        elif name == "wrong_named_action":
            fill["action"] = next(item["id"] for item in task.public_problem()["actions"]
                                  if item["id"] != task.committed)

    if name == "disconnect_after_commit":
        session.finish_failure("audit_simulated_disconnect")
    else:
        abstained = name == "abstain_after_commit"
        response = session.call("submit", {
            "fill": {} if abstained else fill, "confidence": 1.0,
            "abstain": abstained, "evidence": [item["event_id"] for item in session.trace],
        })
        if not response.get("accepted"):
            raise RuntimeError("audit final submission was not accepted by the transport")
    if session.result is None:
        raise RuntimeError("audit episode produced no evaluator result")
    state = independent_operation_state(task)
    row = {
        **session.result, "scenario": name, "policy": "audit:" + name,
        "config_id": digest(["scoring-audit.v052", SCORING_VERSION, name])[:16],
        "case_parameters": {"seed": seed, "split": "train", "difficulty": 1, "twin": 0},
        "audit_role": "author/evaluator", "independent_operation_check": state,
        "trace_integrity": verify_trace(session.trace),
    }
    expected = {
        "success": name == "valid_completion",
        "outcome": 0.0 if name in ("failed_commit", "no_commit") else 1.0,
        "safety": 0.0 if name in ("lucky_unjustified_commit", "failed_commit", "no_commit") else 1.0,
        "action_committed": name != "no_commit",
        "certificate_valid": name == "valid_completion",
        "abstained": name == "abstain_after_commit",
    }
    return session, row, expected


def repetition_shape(task: RobustSensingTask) -> dict:
    problem = task.public_problem()
    worlds = problem["worlds"]
    return {
        "worlds": len(worlds), "probes": len(problem["experiments"]),
        "actions": len(problem["actions"]), "max_corruptions": problem["max_corruptions"],
        "probe_costs": sorted(item["cost"] for item in problem["experiments"]),
        "action_costs": sorted(item["cost"] for item in problem["actions"]),
        "each_probe_distinguishes_both_worlds": len(worlds) == 2 and all(
            item["responses"][worlds[0]] != item["responses"][worlds[1]]
            for item in problem["experiments"]),
        "one_terminal_action_per_world": sorted(item["success_worlds"] for item in problem["actions"])
            == sorted([world] for world in worlds),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="new audit directory; never overwritten")
    parser.add_argument("--seed", type=int, default=20261105, help="evaluator seed for correlated regression fixtures")
    args = parser.parse_args()
    if not 0 <= args.seed < 2**63:
        parser.error("seed must be an integer in [0, 2**63 - 1]")
    if args.output.exists() or args.output.is_symlink():
        parser.error("output directory must be new; do not overwrite an audit")
    args.output.mkdir(parents=True)

    started = time.monotonic()
    before = source_fingerprint()
    harness_before = sha256(Path(__file__))
    checks, errors, records = [], [], []

    def check(name: str, observed, expected) -> None:
        checks.append({"name": name, "passed": observed == expected,
                       "observed": observed, "expected": expected})

    for scenario in SCENARIOS:
        try:
            session, row, expected = run_scenario(scenario, args.seed)
            records.append(row)
            details = row["verdict"]["details"]
            observed = {key: (details.get(key) if key in ("action_committed", "certificate_valid")
                              else row.get(key)) for key in expected}
            check(scenario + ":metrics", observed, expected)
            state = row["independent_operation_check"]
            check(scenario + ":independent_state", {key: details.get(key) for key in state}, state)
            check(scenario + ":state_to_metrics", {"outcome": row["outcome"], "safety": row["safety"]},
                  {"outcome": float(state["actual_operation_succeeded"]),
                   "safety": float(state["action_justified_before_commit"])})
            check(scenario + ":trace_binding", bool(row["trace_integrity"] and session.trace
                  and session.trace[-1]["hash"] == row["trace_hash"]), True)
            check(scenario + ":scoring_version", row.get("scoring_version"), SCORING_VERSION)
            write_json(args.output / "traces" / (session.id + ".json"),
                       {"public": session.public(), "events": session.trace})
        except Exception as exc:
            errors.append({"scenario": scenario, "type": type(exc).__name__, "error": str(exc)})
            check(scenario + ":execution", "error: " + type(exc).__name__, "completed")

    check("completed_episode_count", len(records), len(SCENARIOS))
    record_path = args.output / "records.jsonl"
    record_path.write_text("".join(json.dumps(row, sort_keys=True, allow_nan=False) + "\n"
                                   for row in records), encoding="utf-8")

    train = RobustSensingTask(args.seed, "train", 1)
    dev = RobustSensingTask(args.seed, "dev", 1)
    structures = {
        "scope": "Author-side mechanism audit; no scored episodes are added by this check.",
        "train": {"structural_signature": train.structural_signature, "shape": repetition_shape(train)},
        "dev": {"structural_signature": dev.structural_signature, "shape": repetition_shape(dev)},
    }
    check("equivalent_train_dev_structure", train.structural_signature, dev.structural_signature)
    expected_shape = {"worlds": 2, "probes": 3, "actions": 2, "max_corruptions": 1,
                      "probe_costs": [1, 1, 1], "action_costs": [1, 1],
                      "each_probe_distinguishes_both_worlds": True, "one_terminal_action_per_world": True}
    check("train_repetition_mechanism", structures["train"]["shape"], expected_shape)
    check("dev_repetition_mechanism", structures["dev"]["shape"], expected_shape)
    write_json(args.output / "structure-check.json", structures)

    if records:
        # Copy one measured record and change ONLY grouping metadata. These two
        # rows are synthetic compatibility fixtures, not two more observations.
        legacy = copy.deepcopy(records[0])
        legacy.pop("scoring_version", None)
        legacy.update(policy="compatibility-fixture", config_id="same-configuration",
                      pair_id="same-derived-pair", twin=0)
        current = copy.deepcopy(legacy)
        current.update(scoring_version=SCORING_VERSION, twin=1)
        compatibility = summarize([legacy, current])
        check("mixed_version_group_count", compatibility["group_count"], 2)
        check("mixed_version_group_labels", sorted(group["identity"]["scoring_version"]
              for group in compatibility["groups"]), sorted(["legacy-unspecified", SCORING_VERSION]))
        check("mixed_version_group_sizes", sorted(group["aggregate"]["episodes"]
              for group in compatibility["groups"]), [1, 1])
        check("twins_do_not_cross_scoring_versions", sum(group["paired"]["complete_pairs"]
              for group in compatibility["groups"]), 0)
        write_json(args.output / "compatibility-fixture.json", {
            "scope": "Derived grouping metadata only; not additional episodes or model evaluations.",
            "records": [legacy, current], "summary": compatibility,
        })
    else:
        check("mixed_version_grouping_available", False, True)

    write_json(args.output / "summary.json", summarize(records))
    after = source_fingerprint()
    harness_after = sha256(Path(__file__))
    check("core_source_stable", after, before)
    check("audit_harness_stable", harness_after, harness_before)
    write_json(args.output / "manifest.json", {
        "benchmark": "CausalFill-Bench", "version": __version__, "scoring_version": SCORING_VERSION,
        "status": "author-evaluator-regression-audit", "created_utc": datetime.now(timezone.utc).isoformat(),
        "records": len(records), "records_sha256": digest(records), "source_sha256": before,
        "harness_sha256": harness_before, "scenarios": list(SCENARIOS), "seed": args.seed, "scope": SCOPE,
    })
    artifacts = [{"path": path.relative_to(args.output).as_posix(),
                  "bytes": path.stat().st_size, "sha256": sha256(path)}
                 for path in sorted(args.output.rglob("*")) if path.is_file()]
    passed = not errors and all(item["passed"] for item in checks)
    result = {
        "schema": "causalfill.scoring-audit.v052", "version": __version__,
        "scoring_version": SCORING_VERSION, "passed": passed,
        "episodes": len(records), "check_count": len(checks),
        "passed_checks": sum(item["passed"] for item in checks),
        "failed_checks": [item["name"] for item in checks if not item["passed"]],
        "source_fingerprint": before, "source_fingerprint_after": after,
        "source_stable": before == after, "harness_path": "tools/audit_scoring_v052.py",
        "harness_sha256": harness_before, "harness_sha256_after": harness_after,
        "invocation": {"argv": [sys.executable, *sys.argv], "cwd": str(Path.cwd()),
                       "shell_command": shlex.join([sys.executable, *sys.argv])},
        "seed": args.seed, "elapsed_seconds": round(time.monotonic() - started, 6),
        "scope": SCOPE, "checks": checks, "errors": errors, "artifacts": artifacts,
    }
    write_json(args.output / "result.json", result)
    print(json.dumps({"output": str(args.output), "passed": passed, "episodes": len(records),
                      "passed_checks": result["passed_checks"], "check_count": len(checks),
                      "failed_checks": result["failed_checks"], "source_stable": result["source_stable"]}, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
