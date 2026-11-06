#!/usr/bin/env python3
"""Recheck and consolidate completed v0.5.1 evidence without upgrading its scope."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/"tools"))
from causalfill import __version__
from causalfill.registry import factories
from causalfill.runner import source_fingerprint, write_json
from causalfill.session import verify_trace
from build_release_verification_v05 import validate_suite


def read(path): return json.loads(path.read_text())
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def require(value, message):
    if not value: raise ValueError(message)


def source_bound(mapping, root=ROOT):
    require(bool(mapping), "empty source map")
    for name, expected in mapping.items():
        require((root/name).is_file() and sha(root/name) == expected, "checked source changed: "+name)


def historical_inventory():
    old = read(ROOT/"reports/source-file-inventory-v0.5.json")
    modified, missing, unchanged = [], [], 0
    for item in old["files"]:
        path = ROOT/item["path"]
        if not path.is_file(): missing.append(item["path"])
        elif sha(path) == item["sha256"]: unchanged += 1
        else: modified.append(item["path"])
    require(not missing, "restored source files disappeared")
    known = {item["path"] for item in old["files"]}
    known.add("reports/source-file-inventory-v0.5.json")
    from package_release import eligible
    current = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if eligible(p)}
    return {"version": "0.5.0", "source_archive_sha256":
            "2f8a05b6204b4bf9b353f89c883f80e16044f8e773f9b9b336a4b61c2d1d5974",
            "source_inventory_files_verified": len(old["files"]),
            "unchanged_files": unchanged, "modified_files": modified,
            "new_files": len(current-known),
            "scope": "Restored v0.5.0 source inventory retained and compared byte-for-byte. Changed integration/docs are listed; earlier evidence retains its original version and was not silently relabeled as a new formal run."}


def validate_formal(path):
    result = read(path)
    require(result["status"] == "passed", "formal gate incomplete")
    source_bound(result["source_sha256"], ROOT/"formal")
    require(len(result["required_roots"]) == len(set(result["required_roots"])) == 14,
            "unexpected bounded-fault theorem inventory")
    require(result["statement_bindings"]["all_root_types_checked"], "missing statement audit")
    require(set(result["axioms"]) == set(result["required_roots"]), "axiom inventory root mismatch")
    allowed = set(result["allowed_axioms"])
    require(allowed == {"propext", "Classical.choice", "Quot.sound"}, "unexpected axiom whitelist")
    for axioms in result["axioms"].values():
        require(set(axioms) <= allowed, "unapproved axiom")
    require(not result["export"]["unsafe_declarations"], "unsafe exported declarations")
    require(sha(path.parent/"bounded-fault.ndjson") == result["export"]["sha256"], "formal export changed")
    controls = result["negative_controls"]
    for key in ("DebtResurrection", "DuplicateOccurrence", "FalseTheorem", "InsufficientContradictions", "PerQueryReset"):
        require(controls[key]["rejected"] and controls[key]["intended_diagnostic"], "semantic control failed: "+key)
    require(controls["custom_axiom_inventory"]["whitelist_rejected"], "custom axiom accepted")
    require(controls["omitted_required_export_root"]["rejected"], "missing root accepted")
    for key in ("safe_action_sound", "capped_live_iff"):
        record = result["statement_bindings"][key]
        require(record["weakened_statement_compiles"] and record["unchanged_expected_type_audit_rejects"],
                "statement substitution control failed")
    replay = result["kernel_replay"]
    require(replay["valid_acceptances"] == replay["intended_corruption_rejections"] == 6,
            "incomplete exported kernel checks")
    for command in replay["commands"]:
        require(command["expected_verdict_met"], "kernel verdict not met")
        require(sha(path.parent/command["log"]) == command["log_sha256"], "kernel log changed")
    return {"status": "passed", "roots": len(result["required_roots"]),
            "root_inventory": result["required_roots"],
            "valid_kernel_checks": replay["valid_acceptances"],
            "negative_kernel_checks": replay["intended_corruption_rejections"],
            "checker_configurations": sorted({c["checker"] for c in replay["commands"]}),
            "allowed_axioms": result["allowed_axioms"], "negative_controls": controls,
            "statement_bindings": result["statement_bindings"],
            "scope": "Generic fault accounting, occurrence-supported exclusions and safe action. No proof of Python optimizer/runtime refinement or physical sensing. Six configurations are not six wholly independent stacks.",
            "backend": result["backend"], "toolchain_version": result["toolchain_version"],
            "source_file": path.relative_to(ROOT).as_posix(), "export": result["export"]}


def validate_pilot(path, fingerprint):
    result = read(path)
    require(result["status"] == "completed", "public pilot incomplete")
    require(result["source_stable_during_run"] and result["source_sha256"] == fingerprint, "pilot source changed")
    require(result["os_enforced_isolation"] is False, "unexpected isolation claim")
    rows = result["results"]
    require(len(rows) == result["episodes"] == 6, "pilot case count")
    require(sum(r["success"] for r in rows) == result["successes"], "pilot score aggregation")
    for row in rows:
        events = read(path.parent/(row["label"]+".trace.json"))
        stored = read(path.parent/(row["label"]+".result.json"))
        require(verify_trace(events), "pilot trace integrity")
        require(events[-1]["hash"] == row["trace_hash"] == stored["trace_hash"], "pilot result/trace binding")
        require(row["success"] == stored["success"], "pilot per-case result disagreement")
    return {"episodes": result["episodes"], "successes": result["successes"],
            "source_stable_during_run": True, "os_enforced_isolation": False,
            "model_inference_telemetry_available": False, "scope": result["scope"],
            "transport": result["transport"], "roster_sha256": result["roster_sha256"],
            "results": rows, "is_benchmark_leaderboard_score": False,
            "calibration_limit": "Six related generated cases, one fresh-context assistant, solver-instruction boundary on a shared host; no human calibration or broad hardness inference."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT/"reports/v051/release-verification.json")
    args = parser.parse_args()
    fingerprint = source_fingerprint()
    paths = {"units": ROOT/"reports/v051/unit-tests/result.json",
             "stress": ROOT/"reports/robust-stress-v0.5.1/result.json",
             "ablation": ROOT/"reports/v051/robust-ablation/summary.json",
             "formal": ROOT/"formal/verification-v051-fault/run-02/results.json",
             "pilot": ROOT/"reports/public-mailbox-pilot-v0.5.1/manifest.json",
             "http_block": ROOT/"reports/public-pilot-v0.5.1/infrastructure-status.json",
             "suite": ROOT/"reports/v051/suite/manifest.json",
             "retained_verification": ROOT/"reports/v05/release-verification.json"}
    unit, stress, ablation = (read(paths[key]) for key in ("units", "stress", "ablation"))
    require(unit["passed"] and unit["source_stable"], "unit gate failed")
    require(unit["source_fingerprint"] == fingerprint, "unit core source changed")
    source_bound(unit["checked_source_sha256"])
    require(sha(paths["units"].parent/"unittest.log") == unit["log_sha256"], "unit log changed")
    require(stress["passed"] and not stress["failures"] and stress["source_stable"], "robust stress failed")
    require(stress["source_fingerprint"] == fingerprint, "stress core source changed")
    require(sha(ROOT/"tools/stress_robust_v051.py") == stress["harness_sha256"], "stress harness changed")
    require(ablation["source_stable"] and ablation["source_fingerprint"] == fingerprint, "ablation core changed")
    require(ablation["trace_integrity"], "ablation trace gate failed")
    ablation_records = read(paths["ablation"].parent/"records.json")
    require(len(ablation_records) == ablation["episodes"], "ablation count")
    for row in ablation["policies"]:
        group = [r for r in ablation_records if r["mode"] == row["mode"]]
        require(len(group) == row["episodes"], "ablation mode denominator")
        for key in ("strict_success", "actual_operation_succeeded", "justified_at_commit", "committed"):
            require(sum(r[key] for r in group) == row[key], "ablation mode numerator")
    for trace_path in (paths["ablation"].parent/"traces").glob("*.json"):
        require(verify_trace(read(trace_path)["events"]), "ablation trace changed")
    formal = validate_formal(paths["formal"])
    pilot = validate_pilot(paths["pilot"], fingerprint)
    suite = validate_suite(ROOT/"reports/v051/suite", fingerprint)
    report = {"schema": "causalfill.release-verification.v051", "version": __version__,
              "status": "passed", "generated_utc": datetime.now(timezone.utc).isoformat(),
              "source_fingerprint": fingerprint, "task_configurations": len(factories()), "conceptual_domains": 9,
              "unit_and_integration_tests": {"passed": unit["tests"]-unit["failures"]-unit["errors"]-unit["skipped"],
                  "tests": unit["tests"], "failed": unit["failures"], "errors": unit["errors"], "skipped": unit["skipped"],
                  "elapsed_seconds": unit["elapsed_seconds"]},
              "scripted_controls": suite,
              "robust_sensing": {key: stress[key] for key in ("checks", "complete_tiny_corpus", "random_models",
                  "analytic_cases", "independent_oracle_states", "verified_certificate_state_occurrences",
                  "mutation_rejections", "runtime", "source_stable", "elapsed_seconds")},
              "robust_ablation": ablation, "formal_assurance": formal,
              "assistant_pilot": pilot, "http_transport_attempt": read(paths["http_block"]),
              "retained_evidence": historical_inventory(),
              "artifacts": {key: {"file": path.relative_to(ROOT).as_posix(), "sha256": sha(path),
                                    "bytes": path.stat().st_size} for key, path in paths.items()},
              "claim_boundaries": [
                  "The scripted suite and restricted controls are implementation diagnostics, not model intelligence scores.",
                  "Finite exact costs apply only to the declared fixed-world, once-only, bounded-flip contracts.",
                  "The 14 new Lean roots prove generic accounting and action soundness; optimizer exactness and Python refinement are not formalized by them.",
                  "The fresh-context pilot has no OS-enforced isolation, full inference telemetry, human comparison or independent mechanism holdout.",
                  "Prior Lean and rendered-vision evidence retain their original versions; the complete behavioral suite was rerun on the new core.",
                  "No physical robot, natural-image generalization, adversarial desktop or certified hosted leaderboard was evaluated.",
                  "Original generators and branding combine established ideas; mathematical or scientific novelty is not established by these checks.",
                  "The 100D tracks are finite-field algebra; five vector probes return 500 field residues."]}
    write_json(args.output, report)
    print(json.dumps({"status": report["status"], "version": __version__, "tests": unit["tests"],
                      "suite_records": suite["records"], "pilot_successes": pilot["successes"],
                      "formal_roots": formal["roots"], "output": str(args.output)}, indent=2))


if __name__ == "__main__":
    main()
