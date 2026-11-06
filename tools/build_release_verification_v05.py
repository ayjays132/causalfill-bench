#!/usr/bin/env python3
"""Consolidate completed v0.5 development gates, checking their stored evidence.

This does not execute missing gates or upgrade historical evidence to a new
source revision. An incomplete or stale release is a hard failure.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import itertools
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from causalfill import __version__
from causalfill.registry import factories
from causalfill.runner import source_fingerprint, write_json
from causalfill.session import verify_trace
from causalfill.types import digest


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_source_map(mapping):
    require(bool(mapping), "empty source hash map")
    for name, expected in mapping.items():
        path = ROOT/name
        require(path.is_file() and sha(path) == expected,
                "stale or absent checked source: "+name)


def validate_suite(directory, fingerprint):
    manifest = read(directory/"manifest.json")
    records = [json.loads(line) for line in (directory/"records.jsonl").read_text().splitlines()]
    require(manifest["source_sha256"] == fingerprint, "suite source is stale")
    require(manifest["version"] == __version__, "suite version is stale")
    require(manifest["twins"] is True, "suite must include both twins")
    require(set(manifest["families"]) == set(factories()), "suite does not cover every registered family")
    require(set(manifest["splits"]) == {"train", "dev", "transfer"}, "suite split coverage")
    require(set(manifest["difficulties"]) == {1,2,3}, "suite difficulty coverage")
    require(set(manifest["policies"]) == {"evidence", "blind", "abstain"}, "suite policy coverage")
    expected = set(itertools.product(manifest["policies"], manifest["families"],
        manifest["splits"], manifest["difficulties"], manifest["seeds"], (0,1)))
    actual = [(r["policy"],r["kind"],r["split"],r["difficulty"],r["seed"],r["twin"]) for r in records]
    require(len(actual) == len(set(actual)) and set(actual) == expected, "suite missing/duplicate cells")
    require(len(records) == manifest["records"] and digest(records) == manifest["records_sha256"],
            "suite record binding mismatch")
    policies = {}
    for policy in manifest["policies"]:
        rows = [r for r in records if r["policy"] == policy]
        pairs = defaultdict(list)
        for row in rows:
            trace_path = directory/"traces"/(row["episode_id"]+".json")
            events = read(trace_path)["events"]
            require(row["trace_integrity"] and verify_trace(events), "suite trace hash chain")
            require(bool(events) and events[-1]["hash"] == row["trace_hash"], "suite trace/result binding")
            require(row["invalid_calls"] == 0, "unexpected invalid call in suite")
            pairs[row["pair_id"]].append(row)
        require(all(len(p) == 2 and {r["twin"] for r in p} == {0,1} for p in pairs.values()),
                "suite complete pair structure")
        answerable = [r for r in rows if r["answerable"]]
        unanswerable = [r for r in rows if not r["answerable"]]
        answerable_pairs = [p for p in pairs.values() if all(r["answerable"] for r in p)]
        policies[policy] = {
            "episodes":len(rows), "answerable_episodes":len(answerable),
            "answerable_successes":sum(r["success"] for r in answerable),
            "unanswerable_episodes":len(unanswerable),
            "correct_unanswerable_abstentions":sum(r["abstained"] and r["decision_correct"] for r in unanswerable),
            "complete_pairs":len(pairs),"answerable_pairs":len(answerable_pairs),
            "answerable_pair_successes":sum(all(r["success"] for r in p) for p in answerable_pairs),
            "valid_traces":len(rows),
            "mean_tool_cost":sum(r["tool_cost"] for r in rows)/len(rows),
            "canonical_response_bytes":sum(r["canonical_response_bytes"] for r in rows),
        }
    evidence = policies["evidence"]
    require(evidence["answerable_successes"] == evidence["answerable_episodes"], "public reference failed answerable suite case")
    require(evidence["correct_unanswerable_abstentions"] == evidence["unanswerable_episodes"], "public reference ambiguity failure")
    return {"records":len(records),"policies":policies,"manifest":manifest,
            "all_stored_trace_chains_reverified":True,
            "scope":"Scripted development controls. No learned-model scores or enforced isolation claim."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory",type=Path,default=ROOT/"reports/v05")
    parser.add_argument("--output",type=Path,default=ROOT/"reports/v05/release-verification.json")
    args = parser.parse_args()
    base = args.directory
    fingerprint = source_fingerprint()
    paths = {
        "units":base/"unit-tests/result.json",
        "baseline":base/"legacy-baseline-summary.json",
        "visual_qa":base/"visual-qa/manifest.json",
        "robotics_qa":base/"robotics-qa/manifest.json",
        "independent_audit":base/"independent-vision-audit-final.json",
        "decision_sufficiency":base/"decision-stress-final.json",
        "visual_interventions":base/"visual-interventions/summary.json",
        "robotics_controls":base/"robotics-controls/summary.json",
        "manual_visual_review":base/"visual-qa/manual-review-root.json",
        "manual_robotics_review":base/"robotics-qa/manual-review-agent.json",
        "qa_atlas":base/"qa-atlas.build.json",
    }
    data = {key:read(path) for key,path in paths.items()}
    unit = data["units"]
    require(unit["passed"] and unit["source_stable"], "unit gate did not pass")
    require(unit["source_fingerprint"] == fingerprint, "unit core source changed")
    validate_source_map(unit["checked_source_sha256"])
    for name in ("visual_qa","robotics_qa","decision_sufficiency","visual_interventions","robotics_controls","manual_visual_review","manual_robotics_review"):
        item = data[name]
        require(item["passed"], name+" did not pass")
        if "source_fingerprint" in item:
            require(item["source_fingerprint"] == fingerprint, name+" source changed")
        if "source_sha256" in item and isinstance(item["source_sha256"],dict):
            validate_source_map(item["source_sha256"])
    audit = data["independent_audit"]
    require(audit["failure_count"] == 0 and sum(audit["counts"].values()) > 0, "independent audit failed")
    require(audit["source_sha256_before"] == audit["source_sha256_after"], "audit source mutated")
    validate_source_map(audit["source_sha256_after"])
    qa = data["visual_qa"]
    for key,dirname in (("visual_qa","visual-qa"),("robotics_qa","robotics-qa")):
        for item in data[key]["images"]+data[key]["sheets"]:
            require(sha(base/dirname/item["file"]) == item["sha256"], key+" image hash mismatch")
    manual = data["manual_visual_review"]
    require(manual["manifest_sha256"] == sha(paths["visual_qa"]), "manual review manifest changed")
    require(manual["contact_sheets_reviewed"] == len(qa["sheets"]), "manual review sheet coverage")
    require(manual["panels_reviewed"] == len(qa["images"]), "manual review panel coverage")
    for item in manual["sheets"]:
        require(sha(base/"visual-qa"/item["file"]) == item["sha256"], "manually reviewed sheet changed")
    atlas = data["qa_atlas"]
    require(sha(base/atlas["html"]) == atlas["html_sha256"], "QA atlas changed")
    require(sha(ROOT/"tools/build_qa_atlas_v05.py") == atlas["builder_sha256"], "QA atlas builder changed")
    for source in atlas["sources"]:
        require(sha(base/source["file"]) == source["sha256"], "QA atlas source manifest changed")
    manual["report_summary"] = f"{manual['contact_sheets_reviewed']} sheets / {manual['panels_reviewed']} panels; AI visual inspection"
    robot_manual = data["manual_robotics_review"]
    require(robot_manual["manifest_sha256"] == sha(paths["robotics_qa"]), "robot manual review manifest changed")
    require(robot_manual["contact_sheets_reviewed"] == len(data["robotics_qa"]["sheets"]), "robot manual sheet coverage")
    require(robot_manual["panels_reviewed"] == len(data["robotics_qa"]["images"]), "robot manual panel coverage")
    for item in robot_manual["sheets"]:
        require(sha(base/"robotics-qa"/item["file"]) == item["sha256"], "robot reviewed sheet changed")
    combined_review = {"passed":True,"contact_sheets_reviewed":manual["contact_sheets_reviewed"]+robot_manual["contact_sheets_reviewed"],
        "panels_reviewed":manual["panels_reviewed"]+robot_manual["panels_reviewed"],
        "reviewer_scope":"AI assistant direct visual inspection, not a human-subject study or external laboratory replication."}
    suite = validate_suite(base/"suite",fingerprint)
    artifacts = {key:{"file":str(path.relative_to(ROOT)),"sha256":sha(path),"bytes":path.stat().st_size}
                 for key,path in paths.items()}
    artifacts["suite_records"] = {"file":"reports/v05/suite/records.jsonl",
        "sha256":sha(base/"suite/records.jsonl"),"bytes":(base/"suite/records.jsonl").stat().st_size}
    report = {
        "schema":"causalfill.release-verification.v05", "version":__version__,
        "status":"passed-development-verification", "generated_utc":datetime.now(timezone.utc).isoformat(),
        "source_fingerprint":fingerprint,"task_configurations":len(factories()),
        "unit_and_integration_tests":{"passed":unit["tests"]-unit["failures"]-unit["errors"]-unit["skipped"],
            "tests":unit["tests"],"failed":unit["failures"],"errors":unit["errors"],"skipped":unit["skipped"],
            "source_stable":unit["source_stable"],"elapsed_seconds":unit["elapsed_seconds"]},
        "scripted_controls":suite,
        "new_evidence":{**{key:data[key] for key in ("visual_qa","robotics_qa","independent_audit","decision_sufficiency",
            "visual_interventions","robotics_controls","manual_visual_review","manual_robotics_review","qa_atlas")},
            "combined_visual_review":combined_review},
        "original_release_baseline":data["baseline"],"artifacts":artifacts,
        "claim_boundaries":[
            "All controller scores are transparent scripted controls; no frontier model or learned world model was evaluated.",
            "Finite camera support and exact decision checks apply to the declared synthetic models, not general natural imagery.",
            "The rendered robot family uses a finite planar abstraction; no rigid-body simulation, physical trial or safety certification was performed.",
            "Independent checkers were written within this AI-assisted development session; this is not external laboratory replication.",
            "Historical Lean artifacts were preserved, not rebuilt or extended by this release.",
            "The 100D finite-field tracks use mathematical variables; five vector probes return 500 field values.",
            "Counts of assertions, pixels, represented paths and correlated seeds are different units and are not summed into a model score."]}
    write_json(args.output,report)
    print(json.dumps({"status":report["status"],"version":__version__,"tests":unit["tests"],
        "suite_records":suite["records"],"source_fingerprint":fingerprint,"output":str(args.output)},indent=2))


if __name__ == "__main__": main()
