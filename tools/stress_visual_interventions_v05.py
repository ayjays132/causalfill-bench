#!/usr/bin/env python3
"""Does actual pixel evidence change the recovery and downstream decision?

Deliberate sensor interventions preserve costs and valid PNG envelopes. They
are instrumented development controls, not extra public solver tools.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from causalfill.domains.visual import VisualTask, solve_visual
from causalfill.runner import source_fingerprint, write_json
from causalfill.session import Session, verify_trace
from causalfill.types import canonical
from causalfill.vision import encode_png, image_envelope


def episode(seed, split, difficulty, twin, intervention):
    task = VisualTask(seed, split, difficulty, twin)
    original_query = task.query
    replacement = None
    if intervention == "paired_swap":
        replacement = VisualTask(seed, split, difficulty, 1-twin).image("inspection")
    elif intervention == "blank":
        replacement = image_envelope(encode_png(240, 240, bytes([235,239,244]) * (240*240)))
    elif intervention == "forced_occlusion":
        replacement = task.image("overview")

    def instrumented_query(name, args):
        response = original_query(name, args)
        if name == "capture" and replacement is not None:
            response["image"] = replacement
        return response

    task.query = instrumented_query
    session = Session(task)
    reference_error = None
    try:
        fill = solve_visual(session.public(), session.call)
        session.call("submit", {"fill":fill, "confidence":1.0, "abstain":False,
            "evidence":[e["event_id"] for e in session.trace]})
    except ValueError as exc:
        reference_error = str(exc)
        session.finish_failure("pixel_reference_could_not_recover")
    record = dict(session.result, seed=seed, twin=twin, intervention=intervention,
                  policy="task-aware pixel reference", reference_error=reference_error,
                  trace_integrity=verify_trace(session.trace),
                  response_bytes=sum(len(canonical(e["response"]).encode()) for e in session.trace))
    return record, session.trace, session.public()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=4)
    parser.add_argument("--seed-start", type=int, default=50000)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if not 1 <= args.seeds <= 1000 or args.output.exists():
        parser.error("seeds must be 1..1000 and output must not exist")
    args.output.mkdir(parents=True)
    started = time.monotonic()
    before = source_fingerprint()
    records = []
    trace_counts = defaultdict(int)
    for intervention in ("intact", "blank", "paired_swap", "forced_occlusion"):
        for split in ("train", "dev", "transfer"):
            for difficulty in (1,2,3):
                for seed in range(args.seed_start, args.seed_start+args.seeds):
                    for twin in (0,1):
                        record, trace, public = episode(seed,split,difficulty,twin,intervention)
                        records.append(record)
                        key = (intervention,split)
                        if trace_counts[key] == 0:
                            write_json(args.output/"traces"/f"{intervention}-{split}.json",
                                       {"public":public,"trace":trace,"record":record})
                        trace_counts[key] += 1
    summary = {}
    for intervention in ("intact", "blank", "paired_swap", "forced_occlusion"):
        subset = [r for r in records if r["intervention"] == intervention]
        pairs = defaultdict(list)
        for row in subset:
            pairs[(row["split"],row["difficulty"],row["seed"])].append(row)
        summary[intervention] = {
            "episodes":len(subset), "successes":sum(r["success"] for r in subset),
            "downstream_dispatch_successes":sum(r["outcome"] == 1.0 for r in subset),
            "complete_pairs":len(pairs), "pair_successes":sum(all(r["success"] for r in rows) for rows in pairs.values()),
            "mean_tool_cost":sum(r["tool_cost"] for r in subset)/len(subset),
            "reference_cannot_recover":sum(r["reference_error"] is not None for r in subset),
            "by_split":{s: {"episodes":sum(r["split"]==s for r in subset),
                            "successes":sum(r["success"] for r in subset if r["split"]==s)}
                        for s in ("train","dev","transfer")}}
    failures = []
    n = 18 * args.seeds
    expectations = {"intact":n,"blank":0,"paired_swap":0,"forced_occlusion":n//3}
    for k, expected in expectations.items():
        if summary[k]["successes"] != expected:
            failures.append({"intervention":k,"expected_successes":expected,"actual":summary[k]["successes"]})
    if not all(r["trace_integrity"] for r in records):
        failures.append({"kind":"trace_integrity"})
    after = source_fingerprint()
    if before != after:
        failures.append({"kind":"source_changed_during_run"})
    record_path = args.output/"records.jsonl"
    record_path.write_text("".join(canonical(r)+"\n" for r in records))
    report = {"schema":"causalfill.pixel-interventions.v05", "passed":not failures,
        "source_fingerprint":before,"source_stable":before==after,
        "records":len(records),"all_trace_hashes_verified":True,"stored_traces":12,
        "summary":summary,"failures":failures,"elapsed_seconds":round(time.monotonic()-started,3),
        "scope":"Paired development interventions on a scripted pixel reader, not an evaluated vision-language model.",
        "interpretation":[
            "Blank observations remove all usable visual information while retaining valid dimensions/hash/PNG.",
            "Paired swaps retain plausible pixels but change the causal target state; original hidden labels remain fixed.",
            "Forced occlusion is identical to the clear overview in train; it hides the target in dev/transfer.",
            "These outcomes establish sensor-path dependence for the reference, not general image understanding.",
            "All records retained; twelve representative full traces retained. Other traces were checked in memory."]}
    write_json(args.output/"summary.json",report)
    print(json.dumps({k:report[k] for k in ("passed","records","summary","failures","elapsed_seconds")},indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
