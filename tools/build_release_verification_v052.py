#!/usr/bin/env python3
"""Consolidate source-bound v0.5.2 development evidence without upgrading its scope.

The report is deterministic. Building refreshes only the current release report;
--check recomputes every gate and compares it with the stored report. No model
inference, Lean compilation, browser execution or missing gate is performed here.
"""
from __future__ import annotations

import argparse
from collections import Counter
import itertools
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
from causalfill import __version__
from causalfill.metrics import summarize
from causalfill.registry import factories
from causalfill.robust_decisions import verify_robust_certificate, verify_robust_policy
from causalfill.runner import source_fingerprint, write_json
from causalfill.session import verify_trace
from causalfill.types import SCORING_VERSION, canonical, digest
from build_release_verification_v05 import validate_suite
from build_release_verification_v051 import validate_formal
from release_integrity import (
    RESTORED_MANIFEST, hash_stream, no_symlink_path, parse_json, relative_name,
    validate_restored,
)

SCENARIOS = (
    "valid_completion", "wrong_digest", "missing_exclusions", "wrong_named_action",
    "lucky_unjustified_commit", "failed_commit", "abstain_after_commit",
    "disconnect_after_commit", "no_commit",
)
ABLATION_MODES = ("assume_no_corruption", "query_every_sensor")


class VerificationError(ValueError):
    def __init__(self, failures):
        self.failures = failures if isinstance(failures, list) else [failures]
        super().__init__("; ".join(self.failures))


def require(condition, message):
    if not condition:
        raise VerificationError(message)


def sha(path):
    with Path(path).open("rb") as stream:
        return hash_stream(stream)[1]


def read(path):
    return parse_json(Path(path).read_bytes(), str(path))


def read_rows(path):
    return [parse_json(line, f"{path}:{index}")
            for index, line in enumerate(Path(path).read_bytes().splitlines(), 1) if line.strip()]


def label(path):
    path = Path(path).resolve()
    return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)


def receipt(path):
    return {"file": label(path), "bytes": Path(path).stat().st_size, "sha256": sha(path)}


def bound_sources(mapping, base=ROOT):
    require(isinstance(mapping, dict) and bool(mapping), "missing checked source map")
    failures = []
    for name, expected in mapping.items():
        path = no_symlink_path(base, relative_name(name))
        if not path.is_file() or sha(path) != expected:
            failures.append("stale or missing checked source: " + name)
    require(not failures, "; ".join(failures))


def bound_files(entries, base):
    require(isinstance(entries, list) and bool(entries), "missing artifact inventory")
    names = []
    for entry in entries:
        name = relative_name(entry["path"])
        require(name not in names, "duplicate artifact: " + name)
        names.append(name)
        path = no_symlink_path(base, name)
        require(path.is_file(), "missing artifact: " + label(path))
        require(sha(path) == entry["sha256"], "artifact hash changed: " + label(path))
        if "bytes" in entry:
            require(path.stat().st_size == entry["bytes"], "artifact size changed: " + label(path))
    return names


def source_bound_gate(data, fingerprint, label_):
    require(data.get("version") == __version__, label_ + " release version mismatch")
    require(data.get("source_stable") is True, label_ + " source changed during its run")
    require(data.get("source_fingerprint") == fingerprint, label_ + " core fingerprint is stale")


def trace_corpus(directory, rows):
    """Bind every retained trace's bytes, public episode and final hash to its row."""
    names = [relative_name(row["episode_id"] + ".json") for row in rows]
    require(len(names) == len(set(names)), "duplicate episode IDs")
    require({path.name for path in directory.glob("*.json")} == set(names),
            "stored trace population does not match the record population")
    files = []
    for row, name in zip(rows, names):
        path = no_symlink_path(directory, name)
        data = read(path)
        events, public = data["events"], data["public"]
        require(row.get("trace_integrity") is True and bool(events) and verify_trace(events),
                "invalid trace chain: " + name)
        require(events[-1]["hash"] == row["trace_hash"], "final trace hash differs from result: " + name)
        require(public["episode_id"] == row["episode_id"] and public["family"] == row["family"]
                and public["difficulty"] == row["difficulty"], "public episode binding differs: " + name)
        require(events[-1]["response"].get("episode_closed") is True,
                "trace has no terminal episode event: " + name)
        require(events[-1]["response"]["cost_used"] == row["tool_cost"], "final tool cost differs: " + name)
        files.append({"path": name, "sha256": sha(path)})
    files.sort(key=lambda entry: entry["path"])
    return {"files": len(files), "sha256": digest(files),
            "binding": "SHA-256 of canonical sorted [{path, sha256}] for every trace file; all chains, public episode IDs and final result hashes rechecked."}


def validate_units(directory, fingerprint):
    path = directory / "result.json"
    unit = read(path)
    require(unit.get("schema") == "causalfill.unit-gate.v052", "wrong unit gate schema")
    source_bound_gate(unit, fingerprint, "unit gate")
    require(unit["passed"] is True and unit["tests"] > 0, "unit gate did not pass")
    require(all(unit[key] == 0 for key in ("failures", "errors", "skipped", "expected_failures", "unexpected_successes")),
            "unit gate contains a failure, error, skip or expected/unexpected outcome")
    bound_sources(unit["checked_source_sha256"])
    # Recompute the intended coverage, not merely a caller-supplied subset.
    from run_unit_gate_v052 import checked_source_hashes
    require(unit["checked_source_sha256"] == checked_source_hashes(), "unit checked-source inventory is incomplete")
    require(sha(directory / "unittest.log") == unit["log_sha256"], "unit log hash changed")
    return {"tests": unit["tests"], "passed": unit["tests"], "failed": 0, "errors": 0,
            "skipped": 0, "source_stable": True, "checked_source_files": len(unit["checked_source_sha256"]),
            "elapsed_seconds": unit["elapsed_seconds"], "python": unit["python"],
            "scope": unit["scope"], "result": receipt(path), "log": receipt(directory / "unittest.log")}


def validate_controls(directory, fingerprint):
    result = validate_suite(directory, fingerprint)
    rows, manifest = read_rows(directory / "records.jsonl"), result["manifest"]
    require(len(rows) == 4050 and len(factories()) == 15, "release requires 4,050 episodes across 15 configurations")
    require(len(manifest["seeds"]) == len(set(manifest["seeds"])) == 5, "release requires five distinct suite seeds")
    require(manifest.get("scoring_version") == SCORING_VERSION, "suite scoring semantics are stale")
    require(manifest["skill"] is True and manifest["tools"] is True and manifest["mask_strategy"] == "causal",
            "suite condition differs from the declared release control condition")
    require(all(row.get("scoring_version") == SCORING_VERSION for row in rows), "mixed suite scoring versions")
    require(all(row["condition"] == {"skill": True, "tools": True} for row in rows), "mixed suite tool/skill conditions")
    summary = summarize(rows)
    require(read(directory / "summary.json") == summary, "suite summary differs from current metrics.summarize")
    require(summary["group_count"] == 3, "suite must retain the three separate control groups")
    result["summary_recomputed"] = True
    result["scoring_version"] = SCORING_VERSION
    result["trace_corpus"] = trace_corpus(directory / "traces", rows)
    result["artifacts"] = [receipt(directory / name) for name in ("manifest.json", "records.jsonl", "summary.json")]
    return result


def validate_stress(directory, fingerprint):
    report = read(directory / "result.json")
    source_bound_gate(report, fingerprint, "robust stress")
    require(report["passed"] is True and report["failures"] == [], "robust stress reported failures")
    require(sha(ROOT / "tools/stress_robust_v051.py") == report["harness_sha256"], "stress harness changed")
    require(report["random_models"] == 256 and report["analytic_cases"] == 180, "stress corpus counts changed")
    tiny = report["complete_tiny_corpus"]
    require(tiny["models"] == 1536 and tiny["objectives_per_model"] == 2, "tiny complete corpus is incomplete")
    require(report["checks"]["independent_optimum"] == 3584, "independent optimum comparison count differs")
    require(set(report["mutation_rejections"]) == {"stale_digest", "wrong_optimum", "duplicate_state", "missing_root", "untrusted_objective_switch"}
            and all(count == 256 for count in report["mutation_rejections"].values()), "mutation rejection coverage is incomplete")
    random_rows, analytic = read(directory / "random-cases.json"), read(directory / "analytic-cases.json")
    require(len(random_rows) == 256 and len(analytic) == 180, "stored stress corpus count mismatch")
    require(all(row["expected"] == row["certified"] for row in analytic), "analytic formula disagreement")
    profiles = report["runtime"]["profiles"]
    identities = [(row["seed"], row["split"], row["difficulty"]) for row in profiles]
    expected = set(itertools.product((4103, 4104, 4105), ("train", "dev", "transfer"), (1, 2, 3)))
    require(len(identities) == len(set(identities)) == 27 and set(identities) == expected,
            "runtime profile coverage is incomplete")
    require(sum(row["cases"] for row in profiles) == report["runtime"]["cases"] == 2652, "runtime case count mismatch")
    require(report["checks"]["runtime_bound_attained"] == 27, "not every profile attained its bound")
    for key in ("runtime_commit_accepted", "runtime_case_success", "runtime_trace_integrity", "runtime_within_bound"):
        require(report["checks"][key] == 2652, "runtime check count mismatch: " + key)
    stored = []
    for profile in profiles:
        name = f"{profile['split']}-{profile['difficulty']}-seed{profile['seed']}.json"
        path = directory / "profiles" / name
        data = read(path)
        require(data["profile"] == profile, "stored runtime profile differs: " + name)
        require(profile["worst_runtime_cost"] == profile["certified_operational_budget"], "worst cost differs from bound: " + name)
        problem, certificate, policy = data["problem"], data["certificate"], data["policy"]
        require(verify_robust_certificate(problem, certificate, expected_objective="action")["valid"],
                "stored finite cost certificate rejected: " + name)
        require(verify_robust_policy(problem, policy, expected_objective="action")["valid"],
                "stored finite policy rejected: " + name)
        require(certificate["value"] == profile["certified_operational_budget"]
                and len(certificate["nodes"]) == profile["certificate_states"], "profile/certificate binding mismatch: " + name)
        worst = data["worst_case"]
        require(worst["result"]["scoring_version"] == SCORING_VERSION and worst["result"]["success"] is True,
                "stored worst-case result is stale or failed: " + name)
        require(bool(worst["trace"]) and verify_trace(worst["trace"])
                and worst["trace"][-1]["hash"] == worst["result"]["trace_hash"], "stored worst-case trace mismatch: " + name)
        stored.append(receipt(path))
    require({path.name for path in (directory / "profiles").glob("*.json")} == {Path(item["file"]).name for item in stored},
            "extra or missing stored runtime profiles")
    return {**report, "harness": receipt(ROOT / "tools/stress_robust_v051.py"),
            "retained_profile_certificates_reverified": 27, "retained_worst_case_traces_reverified": 27,
            "retention_scope": "The fresh stress harness checked 2,652 runtime cases. Only the 27 retained worst-case traces are rechecked by this release aggregator; it does not claim a retained trace for every runtime case.",
            "artifacts": [receipt(directory / name) for name in ("result.json", "random-cases.json", "analytic-cases.json")] + stored}


def validate_ablation(directory, fingerprint):
    report, rows = read(directory / "summary.json"), read(directory / "records.json")
    source_bound_gate(report, fingerprint, "robust ablation")
    require(report["trace_integrity"] is True and len(rows) == report["episodes"] == 180, "ablation count or trace gate failed")
    identity = lambda row: (row["mode"], row["split"], row["difficulty"], row["seed"], row["twin"])
    identities = [identity(row) for row in rows]
    expected = set(itertools.product(ABLATION_MODES, ("train", "dev", "transfer"), (1, 2, 3), range(9101, 9106), (0, 1)))
    require(len(identities) == len(set(identities)) and set(identities) == expected, "ablation missing or duplicate cells")
    require({row["mode"] for row in report["policies"]} == set(ABLATION_MODES) and len(report["policies"]) == 2,
            "ablation policy summary population mismatch")
    for summary in report["policies"]:
        selected = [row for row in rows if row["mode"] == summary["mode"]]
        expected_summary = {"mode": summary["mode"], "episodes": len(selected),
            **{key: sum(row[key] for row in selected) for key in
               ("strict_success", "committed", "actual_operation_succeeded", "justified_at_commit", "invalid_calls")},
            "clean": {"episodes": sum(row["twin"] == 0 for row in selected),
                      "strict_success": sum(row["strict_success"] and row["twin"] == 0 for row in selected)},
            "assigned_fault": {"episodes": sum(row["twin"] == 1 for row in selected),
                               "strict_success": sum(row["strict_success"] and row["twin"] == 1 for row in selected)}}
        require(summary == expected_summary, "ablation policy summary does not match records: " + summary["mode"])
    trace_rows, trace_files = [], []
    for path in sorted((directory / "traces").glob("*.json")):
        data = read(path)
        events, public, row = data["events"], data["public"], data["record"]
        require(row["trace_integrity"] is True and bool(events) and verify_trace(events), "ablation trace chain failed: " + path.name)
        require(public["episode_id"] == path.stem and public["family"] == "robust_sensing"
                and public["difficulty"] == row["difficulty"], "ablation public episode binding failed: " + path.name)
        require(events[-1]["tool"] == "submit" and events[-1]["response"].get("episode_closed") is True,
                "ablation final submission missing: " + path.name)
        committed = [event for event in events if event["tool"].startswith("commit_") and event["response"].get("committed") is True]
        probes = [event for event in events if event["tool"].startswith("probe_") and "outcome" in event["response"]]
        require(bool(committed) == row["committed"] and len(committed) <= 1 and len(probes) == row["queries"],
                "ablation operation/observation counts differ from trace: " + path.name)
        trace_rows.append(row)
        trace_files.append({"path": path.name, "sha256": sha(path)})
    require(len(trace_rows) == 180 and Counter(canonical(row) for row in trace_rows) == Counter(canonical(row) for row in rows),
            "ablation trace/record multiset mismatch")
    harness = ROOT / "tools/stress_robust_ablation_v051.py"
    original = read(ROOT / "reports/source-file-inventory-v0.5.1.json")
    original_hash = next(item["sha256"] for item in original["files"] if item["path"] == label(harness))
    require(sha(harness) == original_hash, "legacy ablation harness differs from its preserved v0.5.1 source")
    return {**report, "summary_recomputed": True, "trace_record_multiset_verified": True,
            "trace_corpus": {"files": 180, "sha256": digest(trace_files)},
            "harness": receipt(harness), "harness_unchanged_from_v051_archive": True,
            "provenance_limit": "The unchanged legacy ablation harness records core version/fingerprint/stability but does not record a separate run-time harness digest or per-row scoring_version. Current harness bytes and the complete stored trace/record population are bound here; missing telemetry is not invented.",
            "artifacts": [receipt(directory / name) for name in ("summary.json", "records.json")]}


def validate_scoring_audit(directory, fingerprint):
    report, manifest = read(directory / "result.json"), read(directory / "manifest.json")
    rows = read_rows(directory / "records.jsonl")
    source_bound_gate(report, fingerprint, "scoring audit")
    require(report["schema"] == "causalfill.scoring-audit.v052" and report["scoring_version"] == SCORING_VERSION,
            "scoring audit schema or semantics mismatch")
    require(report["passed"] is True and report["failed_checks"] == [] and report["errors"] == [], "scoring audit failed")
    require(report["source_fingerprint_after"] == fingerprint, "scoring audit final source fingerprint changed")
    harness = ROOT / "tools/audit_scoring_v052.py"
    require(report["harness_path"] == label(harness) and report["harness_sha256"] == report["harness_sha256_after"] == sha(harness),
            "scoring audit harness changed")
    checks = report["checks"]
    require(len(checks) == report["check_count"] == report["passed_checks"] == 55
            and len({item["name"] for item in checks}) == 55, "scoring audit check inventory differs")
    require(all(item["passed"] is True and canonical(item["observed"]) == canonical(item["expected"]) for item in checks),
            "scoring audit contains an inconsistent passing check")
    names = bound_files(report["artifacts"], directory)
    actual = {path.relative_to(directory).as_posix() for path in directory.rglob("*") if path.is_file() and path.name != "result.json"}
    require(set(names) == actual, "scoring audit artifact inventory is incomplete")
    require(len(rows) == report["episodes"] == manifest["records"] == 9, "scoring audit episode count mismatch")
    require(manifest["version"] == __version__ and manifest["scoring_version"] == SCORING_VERSION
            and manifest["source_sha256"] == fingerprint and manifest["harness_sha256"] == sha(harness), "scoring audit manifest source binding mismatch")
    require(manifest["records_sha256"] == digest(rows) and manifest["scenarios"] == list(SCENARIOS), "scoring audit manifest population mismatch")
    require([row["scenario"] for row in rows] == list(SCENARIOS)
            and all(row["scoring_version"] == SCORING_VERSION for row in rows), "scoring audit scenario/semantics mismatch")
    for row in rows:
        state, details = row["independent_operation_check"], row["verdict"]["details"]
        require(all(details.get(key) == value for key, value in state.items()), "stored operation diagnostics disagree: " + row["scenario"])
        require(row["outcome"] == float(state["actual_operation_succeeded"])
                and row["safety"] == float(state["action_justified_before_commit"]), "diagnostic scoring disagrees with stored independent state")
    require(read(directory / "summary.json") == summarize(rows), "scoring audit summary is stale")
    structures = read(directory / "structure-check.json")
    require(structures["train"]["structural_signature"] == structures["dev"]["structural_signature"]
            and structures["train"]["shape"] == structures["dev"]["shape"], "equivalent structures were separated")
    compatibility = read(directory / "compatibility-fixture.json")
    comparison = summarize(compatibility["records"])
    require(compatibility["summary"] == comparison and comparison["group_count"] == 2, "compatibility fixture grouping mismatch")
    require({group["identity"]["scoring_version"] for group in comparison["groups"]} == {"legacy-unspecified", SCORING_VERSION}
            and sum(group["paired"]["complete_pairs"] for group in comparison["groups"]) == 0, "scoring versions were pooled or cross-paired")
    return {"passed": True, "episodes": 9, "checks": 55, "passed_checks": 55,
            "scenarios": list(SCENARIOS), "source_stable": True, "scoring_version": SCORING_VERSION,
            "trace_corpus": trace_corpus(directory / "traces", rows), "summary_recomputed": True,
            "artifact_hashes_verified": len(names), "scope": report["scope"],
            "elapsed_seconds": report["elapsed_seconds"], "result": receipt(directory / "result.json")}


def validate_branding(directory):
    manifest = read(directory / "manifest.json")
    require(manifest["schema"] == "causalfill.brand-assets.v052" and manifest["release_version"] == __version__, "brand version/schema mismatch")
    require(manifest["model_results_asserted"] is False and manifest["new_proof_runs_asserted"] is False, "brand scope changed")
    require(manifest["registry_configuration_ids"] == list(factories()), "brand task icons differ from runtime registry")
    bound_sources({entry["path"]: entry["sha256"] for entry in manifest["source_bindings"]})
    bound_sources({manifest["builder"]["path"]: manifest["builder"]["sha256"]})
    names = bound_files(manifest["assets"], directory)
    svg_names = [name for name in names if name.endswith(".svg")]
    require({path.relative_to(directory).as_posix() for path in directory.rglob("*.svg")} == set(svg_names), "brand SVG inventory is incomplete")
    for name in svg_names:
        root = ET.fromstring((directory / name).read_bytes())
        namespace = "{http://www.w3.org/2000/svg}"
        require(root.tag == namespace + "svg" and root.find(namespace + "title") is not None
                and root.find(namespace + "desc") is not None, "SVG lacks accessible title/description: " + name)
        for element in root.iter():
            require(element.tag.split("}")[-1] not in {"script", "foreignObject", "image", "filter", "animate", "animateTransform", "set"}, "active/external SVG element: " + name)
            for key, value in element.attrib.items():
                local = key.split("}")[-1]
                require(not local.lower().startswith("on") and local not in {"href", "src"} and "url(" not in value,
                        "active/external SVG attribute: " + name)
    require(all(item["ratio"] >= 4.5 for item in manifest["contrast_checks"]), "recorded palette contrast below declared threshold")
    renders, qa, html = (read(directory / name) for name in ("render-record.json", "visual-qa.json", "html-structure-check.json"))
    for item in renders["renders"]:
        require(sha(directory / relative_name(item["render"])) == item["sha256"]
                and sha(directory / relative_name(item["source"])) == item["source_sha256"], "render/source hash mismatch")
    for item in renders["composites"]:
        require(sha(directory / relative_name(item["render"])) == item["sha256"], "contact sheet hash mismatch")
        require(all((directory / relative_name(name)).is_file() for name in item["sources"]), "contact sheet source missing")
    require(qa["release_version"] == __version__ and bool(qa["inspected_renders"]), "missing current visual inspection record")
    for item in qa["inspected_renders"]:
        require(sha(directory / relative_name(item["render"])) == item["sha256"], "inspected render changed")
        if item["source"] is not None:
            require(sha(directory / relative_name(item["source"])) == item["source_sha256"], "inspected SVG source changed")
    require(sha(directory / relative_name(qa["html_structure_check"]["path"])) == qa["html_structure_check"]["sha256"], "HTML inspection record changed")
    require(html["status"] == "pass" and sha(directory / relative_name(html["source"])) == html["source_sha256"], "gallery structural check is stale")
    checks = html["checks"]
    require(all(checks[key] == [] for key in ("missing_local_references", "remote_references", "duplicate_ids"))
            and checks["images_missing_alt"] == checks["script_elements"] == 0
            and checks["task_cards"] == checks["expandable_task_details"] == len(factories()), "gallery structural check failed")
    return {"assets": len(names), "svg_assets": len(svg_names), "task_icons": len(factories()),
            "source_bindings_verified": len(manifest["source_bindings"]), "svg_structure_rechecked": True,
            "rendered_previews": len(renders["renders"]), "contact_sheets": len(renders["composites"]),
            "retained_inspected_renders": len(qa["inspected_renders"]), "visual_review_scope": qa["scope"],
            "visual_reviewer": qa["reviewer"], "browser_render_check": qa["browser_render_check"],
            "limitations": qa["limitations"],
            "artifacts": [receipt(directory / name) for name in ("manifest.json", "render-record.json", "visual-qa.json", "html-structure-check.json")]}


def validate_retained():
    count = validate_restored(ROOT)
    restored = read(ROOT / RESTORED_MANIFEST)
    formal_path = ROOT / "formal/verification-v051-fault/run-02/results.json"
    formal = validate_formal(formal_path)
    return {"restored_files_verified": count, "restored_logs": sum(item["path"].endswith(".log") for item in restored["files"]),
            "restored_c_sources": sum(item["path"].endswith(".c") for item in restored["files"]),
            "original_archive": restored["source_archive"], "original_publication": restored["original_publication"],
            "restoration_manifest": receipt(ROOT / RESTORED_MANIFEST),
            "formal_artifact_integrity": {"status": "archived-artifact-integrity-verified", "evidence_version": "0.5.1",
                "fresh_lean_compilation": False, "fresh_external_kernel_execution": False,
                "roots": formal["roots"], "toolchain_version": formal["toolchain_version"],
                "scope": formal["scope"], "result": receipt(formal_path),
                "interpretation": "Selected archived root inventories, source bindings, exports and stored checker logs were checked for consistency. This is not a new compiler or kernel run."}}


def validate_install_smoke(path, fingerprint):
    report = read(path)
    require(report["schema"] == "causalfill.install-smoke.v052" and report["passed"] is True,
            "installed-wheel smoke did not pass")
    require(report["version"] == "CausalFill-Bench " + __version__
            and report["source_fingerprint"] == fingerprint, "installed-wheel smoke source/version mismatch")
    expected = {"task_configurations": 15, "episodes": 30, "answerable_successes": 28,
                "answerable_episodes": 28, "correct_ambiguity_abstentions": 2,
                "ambiguity_episodes": 2, "verified_trace_chains": 30}
    require(all(report[key] == value for key, value in expected.items()), "installed-wheel smoke coverage/count mismatch")
    require(report["run_from_repository"] is False and report["third_party_runtime_dependencies"] == [],
            "installed-wheel smoke environment differs from the declared outside-repository condition")
    require(report["wheel_name"] == "causalfill_bench-" + __version__ + "-py3-none-any.whl",
            "installed-wheel smoke wheel identity mismatch")
    require(isinstance(report["wheel_sha256"], str) and len(report["wheel_sha256"]) == 64
            and all(char in "0123456789abcdef" for char in report["wheel_sha256"]), "invalid captured wheel digest")
    return {**report, "retained_trace_chains_reverified_by_release_aggregator": 0,
            "verification_scope": "Source-bound summary telemetry from the temporary installed-wheel smoke. Its 30 traces and external wheel are not retained in this report directory and are not reverified by this aggregator. The captured wheel digest identifies the separately delivered wheel.",
            "result": receipt(path)}


def validate_review_record(path, fingerprint):
    report = read(path)
    require(report["schema"] == "causalfill.review-validation.v052" and report["version"] == __version__
            and report["source_fingerprint"] == fingerprint, "review validation source/version mismatch")
    require(report["python_review_tests"] == 10 and report["suite_records"] == report["suite_trace_chains_checked"] == 4050
            and report["scoring_audit_records"] == report["scoring_trace_chains_checked"] == 9,
            "review validation record/trace counts differ")
    require(report["suite_manifest_binding_checked"] is True and report["javascript_syntax_check"]["passed"] is True,
            "review generation or syntax gate failed")
    require(report["browser_interaction_tested"] is False, "unexpected browser-pass claim in the retained review record")
    bound_sources(report["review_artifacts"])
    return {**report, "html_artifact_hashes_reverified": len(report["review_artifacts"]), "result": receipt(path)}


def build_report(directory):
    require(__version__ == "0.5.2", "this release verifier is pinned to package version 0.5.2")
    before = source_fingerprint()
    own_before = sha(Path(__file__))
    gates = {
        "unit_and_integration_tests": lambda: validate_units(directory / "unit-tests", before),
        "scripted_controls": lambda: validate_controls(directory / "suite", before),
        "robust_sensing": lambda: validate_stress(directory / "robust-stress", before),
        "robust_ablation": lambda: validate_ablation(directory / "robust-ablation", before),
        "scoring_audit": lambda: validate_scoring_audit(directory / "scoring-audit", before),
        "branding": lambda: validate_branding(ROOT / "branding/v052"),
        "retained_evidence": validate_retained,
    }
    if (directory / "install-smoke.json").is_file():
        gates["installed_wheel_smoke"] = lambda: validate_install_smoke(directory / "install-smoke.json", before)
    if (directory / "review-validation.json").is_file():
        gates["offline_review_validation"] = lambda: validate_review_record(directory / "review-validation.json", before)
    results, failures = {}, []
    for name, validate in gates.items():
        try:
            results[name] = validate()
        except (ValueError, KeyError, TypeError, OSError, StopIteration, ET.ParseError) as exc:
            failures.append(name + ": " + str(exc))
    if source_fingerprint() != before or sha(Path(__file__)) != own_before:
        failures.append("release verifier or core source changed during verification")
    require(not failures, failures)
    verifier_sources = [Path(__file__), ROOT / "tools/build_release_verification_v05.py",
                        ROOT / "tools/build_release_verification_v051.py", ROOT / "tools/release_integrity.py"]
    return {"schema": "causalfill.release-verification.v052", "version": __version__,
            "scoring_version": SCORING_VERSION, "status": "passed", "source_fingerprint": before,
            "source_stable_during_verification": True, "task_configurations": len(factories()),
            "validator_sources": [receipt(path) for path in verifier_sources], **results,
            "claim_boundaries": [
                "The 4,050 suite episodes, 180 ablation episodes and nine scoring-audit episodes are scripted author/evaluator evidence, not measured AI-model performance.",
                "Correlated seeds and twins do not establish independently authored hidden task mechanisms or external replication.",
                "Actual operational outcome, justification and strict completion acceptance are separate quantities under causalfill.scoring.v2; legacy records are not silently rescored.",
                "Stress checks concern declared finite, fixed-world, once-only bounded-corruption contracts. Assertion counts and state counts are not additional model evaluations.",
                "Fourteen selected Lean roots retain v0.5.1 evidence. No fresh Lean compilation or external kernel execution was performed for v0.5.2, and the proofs do not establish Python runtime/optimizer refinement or physical robot safety.",
                "Branding SVG exports have recorded AI visual inspection and structural checks. Browser rendering and interactive UI validation were blocked by the environment and are not claimed as passed.",
                "Trace hashes and file hashes establish internal byte consistency, not authenticated model authorship, enforced solver isolation or scientific novelty.",
                "The release report excludes itself, the current source-file inventory and archive digests to avoid hash cycles. The package inventory subsequently binds this report.",
            ]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=ROOT / "reports/v052")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/v052/release-verification.json")
    parser.add_argument("--check", action="store_true", help="recompute and compare with the stored report without writing")
    args = parser.parse_args()
    try:
        report = build_report(args.directory.resolve())
        if args.check:
            require(args.output.is_file(), "stored release report is missing")
            require(read(args.output) == report, "stored release report is stale; regenerate it after checking the changed evidence")
        else:
            write_json(args.output, report)
        print(json.dumps({"status": "passed", "mode": "check" if args.check else "build", "version": __version__,
              "tests": report["unit_and_integration_tests"]["tests"], "suite_records": report["scripted_controls"]["records"],
              "ablation_records": report["robust_ablation"]["episodes"], "scoring_audit_checks": report["scoring_audit"]["checks"],
              "svg_assets": report["branding"]["svg_assets"], "source_fingerprint": report["source_fingerprint"],
              "output": str(args.output)}, indent=2))
        return 0
    except (ValueError, KeyError, TypeError, OSError) as exc:
        failures = exc.failures if isinstance(exc, VerificationError) else [str(exc)]
        print(json.dumps({"status": "failed", "failures": failures}, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
