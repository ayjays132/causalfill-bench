#!/usr/bin/env python3
"""Host six frozen public HTTP tasks for an exploratory fresh-context pilot.

Separate process paths are not OS-enforced isolation. The manifest records
this limitation, commits the roster, and binds actual core source bytes.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import secrets
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from causalfill import __version__
from causalfill.registry import make_task
from causalfill.runner import source_fingerprint, write_json
from causalfill.server import create_server
from causalfill.session import Session


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--public", required=True, type=Path)
    parser.add_argument("--seconds", type=int, default=1800)
    args = parser.parse_args()
    if args.out.exists() or args.public.exists(): parser.error("both output paths must be new")
    args.out.mkdir(parents=True); args.public.mkdir(parents=True)
    configurations = [("train", 3), ("dev", 2), ("dev", 3),
                      ("transfer", 1), ("transfer", 2), ("transfer", 3)]
    roster = [{"label": f"signal-{i+1}", "family": "robust_sensing", "split": split,
               "difficulty": level, "seed": secrets.randbits(48), "twin": 1}
              for i, (split, level) in enumerate(configurations)]
    manifest = {"schema": "causalfill.robust-public-pilot.v051", "version": __version__,
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "source_sha256": source_fingerprint(), "roster": roster,
                "roster_sha256": hashlib.sha256(json.dumps(roster, sort_keys=True,
                    separators=(",", ":")).encode()).hexdigest(),
                "status": "running", "certified_benchmark_model_score": False,
                "scope": "Exploratory fresh-context assistant via public HTTP; six related generated mechanisms, shared-host access controlled by solver instructions only.",
                "solver_received_author_context": False, "model_inference_telemetry_available": False,
                "os_enforced_isolation": False, "repeated_attempts": False,
                "all_cases_assign_maximum_faults": True,
                "note": "An assigned fault may never be queried; actual exposure is scored separately.",
                "deadline_seconds": args.seconds}
    write_json(args.out/"manifest.json", manifest)
    servers, endpoints = [], []
    for row in roster:
        task = make_task(row["family"], row["seed"], row["split"], row["difficulty"], row["twin"])
        server = create_server(Session(task, max_seconds=args.seconds), port=0,
            token=(token := secrets.token_urlsafe(32)), output_dir=args.out/row["label"])
        servers.append(server)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        endpoints.append({"label": row["label"], "url": f"http://127.0.0.1:{server.server_port}", "token": token})
    write_json(args.public/"endpoints.json", {"endpoints": endpoints})
    print(json.dumps({"public_directory": str(args.public), "episodes": len(servers),
                      "source_fingerprint": manifest["source_sha256"]}), flush=True)
    deadline = time.monotonic() + args.seconds
    try:
        while time.monotonic() < deadline and not all(s.session.closed for s in servers):
            time.sleep(0.2)
    finally:
        for server in servers:
            with server._session_lock:
                if not server.session.closed: server.session.finish_failure("pilot_host_deadline")
                server._persist_closed()
            server.shutdown(); server.server_close()
        manifest["status"] = "completed"
        manifest["finished_utc"] = datetime.now(timezone.utc).isoformat()
        manifest["source_stable_during_run"] = manifest["source_sha256"] == source_fingerprint()
        manifest["results"] = [{"label": row["label"], **server.session.result}
                               for row, server in zip(roster, servers)]
        manifest["successes"] = sum(r["success"] for r in manifest["results"])
        manifest["episodes"] = len(servers)
        write_json(args.out/"manifest.json", manifest)
        print(json.dumps({"completed": len(servers), "successes": manifest["successes"],
                          "source_stable": manifest["source_stable_during_run"]}), flush=True)


if __name__ == "__main__":
    main()
