#!/usr/bin/env python3
"""Evaluator-only shared-filesystem pilot host, with an explicit public mailbox.

Uses the strict core JSON parser and Session interface. No OS security boundary
is asserted: the evaluated agent is instructed to access only the public box.
File envelope limits equal the HTTP parser limits. Seeds and grades are written
only in the distinct evaluator output directory.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import secrets
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from causalfill.registry import make_task
from causalfill.runner import source_fingerprint
from causalfill.protocol_json import _strict_json, MAX_BODY_BYTES
from causalfill.session import Session


def write(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--public", type=Path, required=True)
    parser.add_argument("--seconds", type=int, default=1800)
    args = parser.parse_args()
    if args.out.exists() or args.public.exists():
        parser.error("both output directories must be fresh")
    args.out.mkdir(parents=True)
    args.public.mkdir(parents=True)
    shutil.copyfile(ROOT / "clients/mailbox_client.py", args.public / "mailbox_client.py")
    configurations = [("robust_sensing", split, level) for split, level in
                      [("train", 3), ("dev", 2), ("dev", 3), ("transfer", 1), ("transfer", 2), ("transfer", 3)]]
    rows, sessions = [], []
    for i, (family, split, difficulty) in enumerate(configurations):
        row = {"label": f"pilot-{i+1}", "family": family, "split": split, "difficulty": difficulty,
               "seed": secrets.randbits(48), "twin": 1}
        rows.append(row)
        session = Session(make_task(family, row["seed"], split, difficulty, row["twin"]), max_seconds=args.seconds)
        sessions.append(session)
        directory = args.public / row["label"]
        directory.mkdir()
        write(directory / "public.json", session.public())
    manifest = {"schema": "causalfill.robust-public-mailbox-pilot.v051", "version": "0.5.1", "transport": "public-json-mailbox",
                "created_utc": datetime.now(timezone.utc).isoformat(), "source_sha256": source_fingerprint(),
                "roster": rows, "roster_sha256": hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
                "status": "running", "certified_benchmark_model_score": False,
                "scope": "Fresh-context assistant via public requests only; no OS-enforced isolation or full model-inference telemetry.",
                "solver_received_author_context": False, "deadline_seconds": args.seconds,
                "os_enforced_isolation": False, "model_inference_telemetry_available": False,
                "transport_predecessor": "HTTP pilot unreachable before any episode delivery",
                "all_cases_assign_maximum_faults": True}
    write(args.out / "manifest.json", manifest)
    print(json.dumps({"public_mailbox": str(args.public), "episodes": len(rows)}), flush=True)
    processed = [set() for _ in rows]
    persisted = set()
    deadline = time.monotonic() + args.seconds
    try:
        while time.monotonic() < deadline and len(persisted) < len(rows):
            for i, (row, session) in enumerate(zip(rows, sessions)):
                directory = args.public / row["label"]
                for path in sorted(directory.glob("request-*.json")):
                    if path.name in processed[i]:
                        continue
                    processed[i].add(path.name)
                    try:
                        if path.stat().st_size > MAX_BODY_BYTES:
                            raise ValueError("oversized envelope")
                        request = _strict_json(path.read_bytes())
                        if (type(request) is not dict or set(request) != {"tool", "arguments"}
                                or type(request["tool"]) is not str or not 1 <= len(request["tool"]) <= 80
                                or type(request["arguments"]) is not dict):
                            raise ValueError("invalid envelope")
                        response = session.call(request["tool"], request["arguments"])
                    except (ValueError, UnicodeError, RecursionError, OverflowError):
                        response = session.call("__protocol_error__", {"reason": "invalid_json_or_envelope"})
                    write(directory / path.name.replace("request-", "response-"), response)
                if session.closed and i not in persisted:
                    write(args.out / f"{row['label']}.result.json", session.result)
                    write(args.out / f"{row['label']}.trace.json", session.trace)
                    persisted.add(i)
            time.sleep(0.05)
    finally:
        for row, session in zip(rows, sessions):
            if not session.closed:
                session.finish_failure("pilot_host_stopped_without_submission")
            write(args.out / f"{row['label']}.result.json", session.result)
            write(args.out / f"{row['label']}.trace.json", session.trace)
        manifest["status"] = "completed"
        manifest["finished_utc"] = datetime.now(timezone.utc).isoformat()
        manifest["source_stable_during_run"] = manifest["source_sha256"] == source_fingerprint()
        manifest["results"] = [{"label": row["label"], **session.result} for row, session in zip(rows, sessions)]
        manifest["episodes"] = len(rows)
        manifest["successes"] = sum(r["success"] for r in manifest["results"])
        write(args.out / "manifest.json", manifest)
        print(json.dumps({"completed": len(rows), "successes": sum(r["success"] for r in manifest["results"])}), flush=True)


if __name__ == "__main__":
    main()
