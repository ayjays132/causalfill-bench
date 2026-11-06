#!/usr/bin/env python3
"""Compile the formal artifact, enforce the axiom whitelist, and compare round trips."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time


FORMAL = Path(__file__).resolve().parent
REPOSITORY = FORMAL.parent
ALLOWED_AXIOMS = {"propext", "Classical.choice", "Quot.sound"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect_axioms(output: str, expected_count: int) -> dict[str, list[str]]:
    rows = re.findall(r"'([^']+)' depends on axioms: \[([^\]]*)\]", output)
    if len(rows) != expected_count:
        raise RuntimeError(f"expected {expected_count} axiom audit rows; got {len(rows)}")
    results = {}
    for theorem, content in rows:
        names = {part.strip() for part in content.split(",") if part.strip()}
        if names - ALLOWED_AXIOMS:
            raise RuntimeError(f"unapproved axioms for {theorem}: {sorted(names - ALLOWED_AXIOMS)}")
        results[theorem] = sorted(names)
    return results


def compare_roundtrip(name: str, stem: str) -> dict:
    source = FORMAL / "CausalFill" / f"{name}.lean"
    manifest = json.loads(source.with_suffix(".manifest.json").read_text())
    statement_path = REPOSITORY / f"reports/certificates/{stem}-statement.json"
    fill_path = REPOSITORY / f"reports/certificates/{stem}-fill.json"
    statement = json.loads(statement_path.read_text())
    fill = json.loads(fill_path.read_text())
    roundtrip_path = FORMAL / manifest["roundtrip_file"]
    roundtrip = json.loads(roundtrip_path.read_text())
    for key in ("nvars", "clauses", "goal"):
        if roundtrip[key] != statement[key]:
            raise RuntimeError(f"{name}: actual Lean {key} differs from source statement")
    for key in ("consistency_model", "proof_steps"):
        if roundtrip[key] != fill[key]:
            raise RuntimeError(f"{name}: actual Lean {key} differs from source fill")
    for key, path in (
        ("source_statement_file_sha256", statement_path),
        ("source_fill_file_sha256", fill_path),
        ("lean_source_sha256", source),
    ):
        if manifest[key] != sha256(path):
            raise RuntimeError(f"{name}: recorded {key} no longer matches")
    payload = {
        "schema": "causalfill.propositional-statement.v1",
        "nvars": roundtrip["nvars"],
        "clauses": [sorted(set(values)) for values in roundtrip["clauses"]],
        "goal": roundtrip["goal"],
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                      allow_nan=False).encode()).hexdigest()
    if not digest == manifest["canonical_statement_sha256"] == statement["statement_sha256"] == fill["statement_sha256"]:
        raise RuntimeError(f"{name}: canonical statement commitments differ")
    return {"exact_roundtrip": True, "canonical_statement_sha256": digest,
            "roundtrip_sha256": sha256(roundtrip_path),
            "proof_steps": len(roundtrip["proof_steps"]),
            "input_and_generated_source_hashes_match": True}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--toolchain", type=Path, help="directory containing official bin/lean and bin/lake")
    parser.add_argument("--output", type=Path, default=FORMAL / "verification")
    args = parser.parse_args()
    output_dir = args.output.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    if args.toolchain:
        toolchain = args.toolchain.resolve()
        lean = str(toolchain / "bin/lean")
        lake = str(toolchain / "bin/lake")
        env.update(LEAN_SYSROOT=str(toolchain), LAKE_HOME=str(toolchain), LEAN=lean)
        env["PATH"] = str(toolchain / "bin") + os.pathsep + env.get("PATH", "")
    else:
        lean, lake = "lean", "lake"
    report = {"schema": "causalfill.lean-verification.v1", "status": "running",
              "started_at_utc": datetime.now(timezone.utc).isoformat(),
              "allowed_axioms": sorted(ALLOWED_AXIOMS), "commands": [], "axioms": {}, "certificates": {},
              "source_sha256": {path.relative_to(FORMAL).as_posix(): sha256(path)
                                for path in [FORMAL / "lean-toolchain", FORMAL / "lakefile.lean",
                                             FORMAL / "CausalFill.lean", FORMAL / "export_certificate.py",
                                             FORMAL / "verify.py", *sorted((FORMAL / "CausalFill").glob("*.lean"))]}}

    def run(name: str, command: list[str]) -> str:
        started = time.monotonic()
        result = subprocess.run(command, cwd=FORMAL, env=env, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        (output_dir / f"{name}.log").write_text(result.stdout)
        report["commands"].append({"name": name, "command": command, "exit_code": result.returncode,
                                   "elapsed_seconds": round(time.monotonic() - started, 3)})
        print(f"{name}: exit {result.returncode}", flush=True)
        if result.returncode:
            raise RuntimeError(f"{name} failed; see {output_dir / (name + '.log')}")
        if "declaration uses `sorry`" in result.stdout:
            raise RuntimeError(f"{name} reported an admitted declaration")
        return result.stdout

    try:
        report["lean_version"] = run("version", [lean, "--version"]).strip()
        if "version 4.35.0" not in report["lean_version"]:
            raise RuntimeError("verification requires the pinned Lean 4.35.0 toolchain")
        run("build", [lake, "build"])
        audit = run("axioms", [lake, "env", "lean", "CausalFill/Audit.lean"])
        report["axioms"].update(inspect_axioms(audit, expected_count=15))
        for name, stem in (("ReleaseModel", "model"), ("ReleaseReference", "reference")):
            compiled = run(stem, [lake, "env", "lean", f"CausalFill/{name}.lean"])
            report["axioms"].update(inspect_axioms(compiled, expected_count=1))
            report["certificates"][stem] = compare_roundtrip(name, stem)
        report["status"] = "passed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = str(error)
        raise
    finally:
        report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        (output_dir / "results.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
