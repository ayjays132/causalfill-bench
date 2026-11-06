#!/usr/bin/env python3
"""Host a small public-protocol development pilot; no OS isolation is claimed.

This is an evaluator entry point. Never expose its files, process memory,
results or source tree to a scored solver. The present development pilot's
shared-host limitation must accompany any result. Fresh secret seeds select
episodes; their commitment is written before any solver interaction.
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
from causalfill.registry import make_task
from causalfill.runner import source_fingerprint
from causalfill.server import create_server
from causalfill.session import Session


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seconds", type=int, default=1800)
    args = parser.parse_args()
    if args.out.exists():
        parser.error("fresh output directory required")
    args.out.mkdir(parents=True)
    configurations = [("vending_adaptive", split, 3) for split in ("train", "dev", "transfer")]
    configurations += [("robotics_barrier", "transfer", 3), ("diagnosis", "transfer", 3), ("proof", "transfer", 3)]
    roster = [{"label": f"pilot-{i+1}", "family": family, "split": split, "difficulty": difficulty,
               "seed": secrets.randbits(48), "twin": secrets.randbelow(2)}
              for i, (family, split, difficulty) in enumerate(configurations)]
    manifest = {"schema": "causalfill.public-interface-pilot.v1", "created_utc": datetime.now(timezone.utc).isoformat(),
                "source_sha256": source_fingerprint(), "roster": roster,
                "roster_sha256": hashlib.sha256(json.dumps(roster, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
                "scope": "Exploratory limited-context assistant run through HTTP; no OS-enforced solver/evaluator isolation.",
                "certified_benchmark_model_score": False, "solver_received_author_context": False,
                "solver_instruction": "Only public HTTP episode/tools; no source, graders, seeds, private files or evaluator helpers.",
                "status": "running", "deadline_seconds": args.seconds}
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    servers, endpoints = [], []
    for row in roster:
        task = make_task(row["family"], row["seed"], row["split"], row["difficulty"], row["twin"])
        server = create_server(Session(task, max_seconds=args.seconds), port=0,
                               token=(token := secrets.token_urlsafe(32)), output_dir=args.out / row["label"])
        servers.append(server)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        endpoints.append({"label": row["label"], "url": f"http://127.0.0.1:{server.server_port}", "token": token})
    print(json.dumps({"endpoints": endpoints}), flush=True)
    deadline = time.monotonic() + args.seconds
    try:
        while time.monotonic() < deadline and not all(server.session.closed for server in servers):
            time.sleep(0.2)
    finally:
        for server in servers:
            with server._session_lock:
                if not server.session.closed:
                    server.session.finish_failure("pilot_host_deadline")
                server._persist_closed()
            server.shutdown()
            server.server_close()
        manifest["status"] = "completed"
        manifest["finished_utc"] = datetime.now(timezone.utc).isoformat()
        manifest["source_stable_during_run"] = manifest["source_sha256"] == source_fingerprint()
        manifest["results"] = [{"label": row["label"], **server.session.result} for row, server in zip(roster, servers)]
        (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        print(json.dumps({"completed": len(servers), "successes": sum(r["success"] for r in manifest["results"])}), flush=True)


if __name__ == "__main__":
    main()
