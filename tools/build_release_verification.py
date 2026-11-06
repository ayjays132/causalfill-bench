#!/usr/bin/env python3
"""Assemble v0.3 evidence after checking its recorded source/artifact bindings.

This reads completed audits; it does not rerun Lean, unit tests, or stress work.
Hashes are integrity checks relative to trusted inputs, not authentication.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from causalfill import __version__
from causalfill.runner import source_fingerprint
from causalfill.session import verify_trace
from causalfill.types import digest


def read(relative):
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_sources(mapping, base=ROOT):
    for relative, expected in mapping.items():
        path = base / relative
        require(path.is_file(), f"Missing audited source: {path}")
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        require(actual == expected, f"Audited source changed: {relative}")
    return len(mapping)


def main():
    require(__version__ == "0.3.0", "This assembler is specific to the v0.3 release.")
    source = source_fingerprint()
    freeze = read("reports/stress-v0.3/release-freeze.json")
    require(source == freeze["source_sha256"], "Evaluator changed after the release freeze.")

    log_path = "reports/unittest-v0.3.txt"
    log = (ROOT / log_path).read_text()
    count, seconds = re.findall(r"Ran (\d+) tests in ([\d.]+)s", log)[-1]
    require(log.rstrip().endswith("OK"), "Unit/integration test log did not pass.")

    suite_path = "reports/development-run-v0.3-final"
    manifest = read(suite_path + "/manifest.json")
    records = [json.loads(line) for line in (ROOT / suite_path / "records.jsonl").read_text().splitlines()]
    require(manifest["source_sha256"] == source, "Control suite source fingerprint differs.")
    require(manifest["version"] == __version__, "Control suite version differs.")
    require(manifest["records"] == len(records) == 2970, "Unexpected control roster size.")
    require(digest(records) == manifest["records_sha256"], "Control records differ from their commitment.")
    require(len({r["episode_id"] for r in records}) == len(records), "Duplicate episode IDs.")
    for record in records:
        trace = read(suite_path + "/traces/" + record["episode_id"] + ".json")
        require(verify_trace(trace["events"]), "Stored trace hash chain is invalid.")
        require(trace["events"][-1]["hash"] == record["trace_hash"], "Record/trace commitment differs.")
        require(trace["public"]["family"] == record["family"], "Public/record family differs.")
    controls = {}
    for policy in manifest["policies"]:
        rows = [r for r in records if r["policy"] == policy]
        answerable = [r for r in rows if r["answerable"]]
        unanswerable = [r for r in rows if not r["answerable"]]
        pair_sizes = Counter(r["pair_id"] for r in rows)
        require(set(pair_sizes.values()) == {2}, "Incomplete control pairs.")
        controls[policy] = {
            "episodes": len(rows), "answerable": len(answerable),
            "answerable_successes": sum(r["success"] for r in answerable),
            "unanswerable": len(unanswerable),
            "correct_unanswerable_abstentions": sum(r["abstained"] and r["decision_correct"] for r in unanswerable),
            "complete_pairs": len(pair_sizes),
            "successes_by_family": dict(sorted(Counter(r["family"] for r in rows if r["success"]).items())),
        }
    require(controls["evidence"]["answerable_successes"] == 900, "Constructive reference has a failure.")
    require(controls["evidence"]["correct_unanswerable_abstentions"] == 90, "Reference abstention failed.")
    require(controls["blind"]["answerable_successes"] == controls["abstain"]["answerable_successes"] == 0,
            "A negative control unexpectedly passed.")

    paths = {"formal": "reports/stress-v0.3/formal-results.json",
             "operations": "reports/stress-v0.3/operations-final.json",
             "protocol": "reports/stress-v0.3/protocol-final.json",
             "workflow_independent": "reports/stress-v0.3/workflow-independent-audit.json",
             "barrier_independent": "reports/stress-v0.3/barrier-independent-audit.json"}
    reports = {key: read(path) for key, path in paths.items()}
    formal = reports["formal"]
    require(formal["source_stable_during_run"], "Formal audit source changed during the run.")
    check_sources(formal["source_sha256_after"])
    require(all(formal["totals"][key] == 0 for key in ("false_accepts", "false_rejects", "invariant_failures", "exceptions")),
            "Formal stress audit contains failures.")
    operations = reports["operations"]
    require(operations["source_stable_during_run"], "Operations audit source changed during the run.")
    check_sources(operations["source_sha256"])
    require(len(operations["sections"]) == 7, "Final operations audit is incomplete.")
    for section in operations["sections"]:
        require(not any(section["failure_counts"].values()), "Operations failure in " + section["name"])
    protocol = reports["protocol"]
    require(protocol["source_sha256"] == source and protocol["failure_count"] == 0, "Protocol final audit did not pass on this source.")
    workflow = reports["workflow_independent"]
    require(workflow["status"] == "passed" and not workflow["findings"], "Workflow independent audit failed.")
    check_sources(workflow["source_sha256"])
    barrier = reports["barrier_independent"]
    check_sources(barrier["source_snapshot_sha256"])
    require(barrier["baseline"]["verification"]["valid"], "Valid barrier certificate was rejected.")
    require(all(not item["verification"]["valid"] for item in barrier["after_fix"]["alias_retests"]),
            "A barrier observation alias still passed.")
    require(not barrier["after_fix"]["separator_inside_goal_tolerance_rejected"]["valid"],
            "Invalid barrier separator was accepted.")

    lean_path = "formal/verification/results.json"
    lean = read(lean_path)
    require(lean["status"] == "passed" and all(c["exit_code"] == 0 for c in lean["commands"]), "Lean gate failed.")
    check_sources(lean["source_sha256"], ROOT / "formal")
    for cert in lean["certificates"].values():
        require(cert["exact_roundtrip"] and cert["input_and_generated_source_hashes_match"], "Lean certificate binding failed.")
    allowed = {"propext", "Classical.choice", "Quot.sound"}
    require(all(set(axioms) <= allowed for axioms in lean["axioms"].values()), "Unexpected Lean axiom dependency.")

    result = {
        "schema": "causalfill.release-verification.v3", "benchmark": "CausalFill-Bench",
        "version": __version__, "status": "passed-development-verification",
        "verified_utc": datetime.now(timezone.utc).isoformat(), "source_sha256": source,
        "platform": manifest["platform"], "python": manifest["python"],
        "task_configurations": 11, "conceptual_domains": 8,
        "unit_and_integration_tests": {"passed": int(count), "failed": 0, "errors": 0,
                                       "seconds": float(seconds), "log": log_path},
        "scripted_controls": {"path": suite_path, "records": len(records),
                              "stored_traces_rechecked": len(records), "policies": controls,
                              "source_and_record_hashes_verified": True,
                              "interpretation": "Task-aware constructive and negative controls; not LLM scores."},
        "stress_reports": paths,
        "stress_summary": {
            "formal": formal["totals"],
            "operations": {"checks": sum(s["counters"]["checks"] for s in operations["sections"]),
                           "failures": 0,
                           "sections": {s["name"]: {"checks": s["counters"]["checks"],
                                        "episodes": s["counters"].get("episodes"),
                                        "counters": s["counters"]} for s in operations["sections"]}},
            "protocol": {key: protocol[key] for key in ("checks", "failure_count", "configuration", "counts")},
            "workflow_independent": {"exact_expression_values": sum(x["exact_expression_values"] for x in workflow["lattices"].values()),
                                     "exact_intermediate_values": workflow["mixed_ast_bounds"]["exact_intermediate_values_checked"],
                                     "false_certifications": 0, "bound_violations": 0},
            "units_note": "Checks are correlated assertions, not independent tasks, model solves, or statistical samples."},
        "formal_assurance": {"path": lean_path, "status": lean["status"], "lean_version": lean["lean_version"],
                             "certificates": lean["certificates"], "audited_theorems": len(lean["axioms"]),
                             "allowed_standard_axioms": sorted(allowed), "python_lean_equivalence_proved": False,
                             "no_custom_axioms_sorry_or_native_decide": True},
        "robotics_barrier": {"profile": "robotics_barrier_v1", "audit_path": paths["barrier_independent"],
                             "claim": "Individually feasible worlds with no common admissible path; geometry-dependent evidence is necessary for guaranteed pair success.",
                             "hardness_claim": False},
        "repairs": [
            {"issue": "Geometry tolerance false accepts and false rejects", "baseline": "reports/stress-v0.3/operations-baseline.json",
             "change": "Exact decimal-rational workspace and closed-obstacle predicates."},
            {"issue": "Workflow expressions agreeing on all finite tests but diverging elsewhere", "baseline": "reports/stress-v0.3/operations.json",
             "change": "Sufficient symbolic equality plus original-intermediate Fraction bounds on the declared input domain."},
            {"issue": "Duplicate JSON keys accepted by stdio but rejected by HTTP", "baseline": "reports/stress-v0.3/protocol-baseline.json",
             "change": "Shared strict bounded JSON parser and raw UTF-8 byte limit."},
            {"issue": "Finite mean overflow", "baseline": "reports/stress-v0.3/protocol-baseline.json",
             "change": "Exact-intermediate statistics.mean aggregation, including subnormal regression coverage."},
            {"issue": "Boolean/numeric alias invalidating barrier observation-equivalence claim", "baseline": paths["barrier_independent"],
             "change": "Canonical typed JSON equality and strict metadata validation."}],
        "valid_shortcuts_retained": ["Fixed Express procurement schedule meets original vending goals.",
                                     "High-clearance route and common grip force solve original robotics after target recovery."],
        "new_model_solver_trials": 0,
        "github_hosted_ci_run": False, "external_github_publication": False,
        "limitations": ["All released tasks, seeds and certificates are public development material.",
                        "Independent checker/reviewer work is within this AI-assisted build, not external human or laboratory replication.",
                        "Python/Lean refinement, full Python implementation verification, physical robot transfer and frontier difficulty remain unestablished."]}
    for relative in ("reports/build-verification-v0.3.json", "reports/build-verification.json"):
        (ROOT / relative).write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"status": result["status"], "tests": int(count), "controls": len(records),
                      "source_sha256": source, "stress_checks_by_harness": {
                          "formal": formal["totals"]["checks"],
                          "operations": result["stress_summary"]["operations"]["checks"],
                          "protocol": protocol["checks"]}}, indent=2))


if __name__ == "__main__":
    main()
