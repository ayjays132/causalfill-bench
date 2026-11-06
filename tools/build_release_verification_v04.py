#!/usr/bin/env python3
"""Assemble v0.4 evidence only after checking its source and artifact bindings.

This does not pretend to rerun Lean or model inference. It verifies completed
source-bound gates, all scripted traces, the finite certificate modes and the
exact theorem inventory before writing the release evidence record.
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
FORMAL = ROOT / "formal"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(FORMAL))
from causalfill import __version__
from causalfill.runner import source_fingerprint
from causalfill.session import verify_trace
from causalfill.types import digest
from verify_information import compare_arena


def read(path):
    return json.loads((ROOT / path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sources(mapping, base=ROOT, overrides=None):
    for name, expected in mapping.items():
        path = base / (overrides or {}).get(name, name)
        require(path.is_file() and sha(path) == expected, "audited source changed or missing: " + str(path))


def compile_gate(report, path, overrides=None):
    require(report["status"] == "passed", "formal gate did not pass: " + path)
    sources(report["source_sha256"], FORMAL, overrides)
    for command in report["commands"]:
        require((command["exit_code"] == 0) == command["expected_success"], "formal command verdict mismatch")
        log = ROOT / path / (command["name"] + ".log")
        require(sha(log) == command["output_sha256"], "formal command log changed")
    allowed = {"propext", "Classical.choice", "Quot.sound"}
    require(all(set(values) <= allowed for values in report["axioms"].values()), "unexpected logical assumption")
    require(report["trust_level"] == 0 and report["false_theorem_rejected"] and report["custom_axiom_gate_rejected"],
            "formal smoke/assumption gate did not pass")


def main():
    require(__version__ == "0.4.0", "This evidence assembler is specific to v0.4.0")
    source = source_fingerprint()
    freeze = read("reports/stress-v0.4/release-freeze.json")
    require(freeze["source_sha256"] == source, "Python evaluator changed after freeze")
    log = (ROOT / "reports/unittest-v0.4.txt").read_text()
    count, seconds = re.findall(r"Ran (\d+) tests in ([\d.]+)s", log)[-1]
    require(log.rstrip().endswith("OK") and int(count) == 214, "unit/integration gate failed")

    suite_path = "reports/development-run-v0.4-final"
    suite = read(suite_path + "/manifest.json")
    records = [json.loads(line) for line in (ROOT / suite_path / "records.jsonl").read_text().splitlines()]
    require(suite["version"] == __version__ and suite["source_sha256"] == source, "control source/version mismatch")
    require(suite["records"] == len(records) == 3240 and digest(records) == suite["records_sha256"], "control roster binding failed")
    require(len({row["episode_id"] for row in records}) == len(records), "duplicate control episodes")
    for row in records:
        trace = read(suite_path + "/traces/" + row["episode_id"] + ".json")
        require(verify_trace(trace["events"]), "control trace chain failed")
        require(trace["events"][-1]["hash"] == row["trace_hash"], "control result trace commitment differs")
    controls = {}
    for policy in suite["policies"]:
        rows = [r for r in records if r["policy"] == policy]
        answerable = [r for r in rows if r["answerable"]]
        unanswerable = [r for r in rows if not r["answerable"]]
        pairs = Counter(r["pair_id"] for r in rows)
        require(set(pairs.values()) == {2}, "incomplete control pairs")
        controls[policy] = {"episodes": len(rows), "answerable": len(answerable),
                            "answerable_successes": sum(r["success"] for r in answerable),
                            "unanswerable": len(unanswerable),
                            "correct_unanswerable_abstentions": sum(r["abstained"] and r["decision_correct"] for r in unanswerable),
                            "complete_pairs": len(pairs)}
    require(controls["evidence"]["answerable_successes"] == 990 and
            controls["evidence"]["correct_unanswerable_abstentions"] == 90, "scripted reference failure")
    require(controls["blind"]["answerable_successes"] == controls["abstain"]["answerable_successes"] == 0,
            "negative control unexpectedly succeeded")

    paths = {
        "runtime": "reports/stress-v0.4/adaptive-runtime-complete-responses.json",
        "analytic": "reports/stress-v0.4/belief-analytic-final.json",
        "policy_enumeration": "reports/stress-v0.4/belief-games-independent-audit.json",
        "protocol": "reports/stress-v0.4/protocol-final.json",
        "formal_current": "formal/verification-v04-current/results.json",
        "formal_binding": "formal/verification-v04-binding/results.json",
        "formal_stress": "formal/verification-v04-stress/results.json",
        "formal_retained_regression": "formal/verification-v04-final/results.json",
        "formal_binding_review": "reports/stress-v0.4/formal-binding-review.json",
        "independent_kernels": "formal/verification-v04-kernels/replay/results.json",
        "pilot": "reports/public-interface-pilot-v0.4/manifest.json",
    }
    reports = {name: read(path) for name, path in paths.items()}
    for name in ("runtime", "analytic", "policy_enumeration"):
        report = reports[name]
        require(report["status"] == "passed" and not report["failures"], "failed audit: " + name)
        sources(report["source_sha256"])
        if name != "policy_enumeration":
            require(report["source_stable_during_run"], "audit source changed during run")
    protocol = reports["protocol"]
    require(protocol["source_sha256"] == source and protocol["failure_count"] == 0, "protocol gate failed")

    current = reports["formal_current"]
    compile_gate(current, "formal/verification-v04-current")
    snapshot = read("formal/verification-v04-final/source-snapshot.json")
    require(sha(ROOT / paths["formal_retained_regression"]) == snapshot["immutable_verification_report_sha256"],
            "retained full-gate record changed")
    overrides = {name: item["archived_path"] for name, item in snapshot["source_archives"].items()}
    for name, item in snapshot["source_archives"].items():
        require(sha(FORMAL / item["archived_path"]) == item["sha256"], "executed verifier snapshot changed")
    retained = reports["formal_retained_regression"]
    compile_gate(retained, "formal/verification-v04-final", overrides)
    require(set(retained["resolution_regression"]) == {"model", "reference"}, "retained proof regression incomplete")
    for result in retained["resolution_regression"].values():
        require(result["exact_roundtrip"] and result["input_and_generated_source_hashes_match"], "retained proof data mismatch")

    binding = reports["formal_binding"]
    require(binding["status"] == "passed" and len(binding["bindings"]) == 4, "concrete binding gate incomplete")
    sources(binding["source_sha256"], FORMAL)
    for theorem, result in binding["bindings"].items():
        require(result["status"] == "passed" and result["exit_code"] == 0, "binding theorem failed")
        for path_key, hash_key in (("binding_source", "binding_source_sha256"), ("original_source", "original_source_sha256"),
                                   ("expected_data", "expected_data_file_sha256"), ("manifest", "manifest_sha256")):
            require(sha(FORMAL / result[path_key]) == result[hash_key], "concrete binding artifact changed")
        compared = compare_arena(FORMAL / result["manifest"])
        require(compared["semantic_arena_sha256"] == result["expected_semantic_sha256"], "binding expected data changed")
        require(compared["mode"] == result["audited_metadata"]["mode"], "binding policy mode differs")
        require(set(result["axioms"]) <= {"propext", "Quot.sound", "Classical.choice"}, "binding theorem has an unexpected axiom")

    stress = reports["formal_stress"]
    require(stress["status"] == "passed" and len(stress["controls"]) == 10 and all(c["passed"] for c in stress["controls"]),
            "formal adversarial controls failed")
    require(sha(FORMAL / "stress_information.py") == stress["script_sha256"], "formal stress script changed")
    for item in stress["controls"]:
        for key in ("source", "altered_data"):
            if key in item:
                require(sha(FORMAL / item[key]) == item[key + "_sha256"], "formal stress artifact changed")

    export = read("formal/verification-v04-kernels/export-build.json")
    require(export["exit_code"] == 0 and export["source_stable_during_run"], "final export failed or changed")
    sources(export["source_sha256"], FORMAL)
    export_path = FORMAL / "verification-v04-kernels/release-theorems.ndjson"
    require(sha(export_path) == export["export_sha256"], "final export bytes changed")
    kernels = reports["independent_kernels"]
    require(kernels["status"] == "passed" and kernels["export_sha256"] == export["export_sha256"], "independent replay failed")
    roots = read("formal/expected-export-roots.json")
    require(len(roots) == 29 and kernels["required_theorem_roots"] == roots and
            kernels["all_required_roots_present_as_theorems"], "final theorem inventory incomplete")
    require(kernels["omitted_required_root_rejected"] and kernels["injected_axiom_inventory_rejected"], "kernel inventory negative controls failed")
    sources(kernels["source_sha256"])
    for item in kernels["commands"]:
        require(item["expected_verdict_met"], "unexpected independent checker verdict")
        require(sha(FORMAL / "verification-v04-kernels/replay" / item["log"]) == item["log_sha256"], "checker log changed")
    require(len(kernels["commands"]) == 12, "six valid and six invalid checker runs required")

    pilot = reports["pilot"]
    require(pilot["status"] == "completed" and pilot["source_sha256"] == source and pilot["source_stable_during_run"],
            "pilot evaluator source/result changed")
    pilot_rows = []
    op_tools = {"calibrate", "forecast", "assay", "order", "settle"}
    for row in pilot["results"]:
        trace = read("reports/public-interface-pilot-v0.4/" + row["label"] + ".trace.json")
        require(verify_trace(trace) and trace[-1]["hash"] == row["trace_hash"], "pilot trace binding failed")
        require(sum(event["tool"] == "submit" and event["response"].get("accepted", False) for event in trace) == 1,
                "pilot did not submit exactly once")
        result = {key: row[key] for key in ("label", "family", "split", "difficulty", "success", "tool_cost", "invalid_calls")}
        if row["family"] == "vending_adaptive":
            previous, operational = 0, 0
            for event in trace:
                cost = event["response"]["cost_used"]
                if event["tool"] in op_tools:
                    operational += cost - previous
                previous = cost
            result["operational_cost"] = operational
            result["setup_and_static_cost"] = row["tool_cost"] - operational
            result["certified_worst_case_operational_cost_for_profile"] = 16 if row["split"] == "train" else 17
            result["comparison_scope"] = "post-hoc observed operational cost compared with the profile's certified minimax bound; not a pointwise regret claim"
        pilot_rows.append(result)

    result = {
        "schema": "causalfill.release-verification.v4", "benchmark": "CausalFill-Bench", "version": __version__,
        "status": "passed-development-verification", "verified_utc": datetime.now(timezone.utc).isoformat(),
        "source_sha256": source, "task_configurations": 12, "conceptual_domains": 8,
        "unit_and_integration_tests": {"passed": int(count), "failed": 0, "errors": 0, "seconds": float(seconds),
                                       "log": "reports/unittest-v0.4.txt"},
        "scripted_controls": {"path": suite_path, "records": len(records), "traces_rechecked": len(records),
                              "policies": controls, "interpretation": "task-aware scripted controls, not LLM scores"},
        "reports": paths, "report_sha256": {name: sha(ROOT / path) for name, path in paths.items()},
        "stress_summary": {"runtime": reports["runtime"]["counts"], "analytic": reports["analytic"]["counts"],
                           "policy_enumeration": {key: reports["policy_enumeration"][key] for key in
                                                  ("games", "complete_syntactic_policies_enumerated", "exact_optimum_comparisons")},
                           "protocol": {"checks": protocol["checks"], "failures": 0},
                           "formal_mutation_controls": len(stress["controls"]),
                           "units_note": "Correlated assertions, states, edges, syntactic policies and model episodes are distinct units; do not add them into an intelligence score."},
        "formal_assurance": {"lean_version": "4.35.0", "kernel_trust_level": 0, "new_generic_roots": 21,
                             "concrete_profile_roots": 4, "concrete_binding_roots": 4,
                             "concrete_fixture": "four policy-mode arenas of ONE two-round, four-world market (448 raw states)",
                             "concrete_adaptive_cost": 8, "concrete_restricted_modes_unwinnable": True,
                             "independent_export_roots": len(roots), "checker_configurations": 6,
                             "external_checker_implementations": 4, "valid_export_acceptances": 6,
                             "corrupted_proof_nonacceptances_with_type_diagnostics": 6,
                             "exported_axioms": kernels["declaration_inventory"]["axioms"],
                             "retained_resolution_steps": [865, 6018],
                             "retained_resolution_independent_export_included": False,
                             "trusted_python_projection_and_runtime_refinement_proved": False,
                             "lake_paranoid_sandbox_run": False,
                             "full_gates_source_snapshot": "formal/verification-v04-final/source-snapshot.json"},
        "public_interface_pilot": {"episodes": len(pilot_rows), "successes": sum(row["success"] for row in pilot_rows),
                                   "rows": pilot_rows, "transport": "public-json-mailbox", "fresh_solver_context": True,
                                   "os_enforced_isolation": False, "exact_model_snapshot_available": False,
                                   "token_compute_telemetry_available": False, "certified_leaderboard_score": False,
                                   "access_evidence": "solver self-report and saved public-only scripts; no OS access attestation",
                                   "http_attempts": "excluded infrastructure failure before any task observation",
                                   "interpretation": "limited exploratory pilot; six successes are not evidence that these profiles are frontier-hard"},
        "repairs": ["Bind reported mode, root, node count and root value to the rechecked source certificate.",
                    "Add kernel equality of whole imported arenas to independent expected literals, defeating an exporter-controlled JSON echo."],
        "historical_v03": {"archive_sha256": "6371248c901580654d5ed4cd0740fd9ad3221e496b6d01f61012bafa73f627d6",
                           "preserved_verification": "reports/build-verification-v0.3.json",
                           "historical_stress_counts_relabelled_as_v04": False},
        "github_hosted_ci_run": False, "external_github_publication": False,
        "limitations": ["Public small development generators and fixtures are not a private held-out evaluation set.",
                        "Classical belief-space planning and weighted-cover methods are prior art; no first/hardest/breakthrough claim is established.",
                        "Internal AI-assisted reviewers and independent implementations are not external laboratory replication.",
                        "Robotics remains symbolic; no camera-image, motor-dynamics or physical robot experiment was performed.",
                        "Operational finite-game cost excludes setup/static reads and final masked-term reconstruction."]}
    for name in ("reports/build-verification-v0.4.json", "reports/build-verification.json"):
        (ROOT / name).write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"status": result["status"], "tests": int(count), "controls": len(records),
                      "formal_export_roots": len(roots), "checker_configurations": 6,
                      "exploratory_pilot_successes": result["public_interface_pilot"]["successes"], "source_sha256": source}, indent=2))


if __name__ == "__main__":
    main()
