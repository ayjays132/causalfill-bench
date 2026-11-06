#!/usr/bin/env python3
"""Negative controls for the actual released finite arena and correspondence gate."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from verify_information import compare_arena, inspect_axioms

FORMAL = Path(__file__).resolve().parent


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--toolchain", type=Path, required=True)
    parser.add_argument("--compiler-host", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=FORMAL / "verification-v04-stress")
    args = parser.parse_args()
    output = args.output.resolve()
    sources = output / "sources"
    sources.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["LEAN_PATH"] = str(FORMAL / ".lake" / "build" / "lib" / "lean")
    manifest_path = FORMAL / "CausalFill" / "ReleaseAdaptiveMarket.manifest.json"
    manifest = json.loads(manifest_path.read_text())
    original = json.loads((FORMAL / manifest["roundtrip_file"]).read_text())
    root, value, size = original["root"], manifest["root_value"], manifest["node_count"]
    assert value > 0
    mutations = [
        ("RaisedLower", f"value := some {value + 1}", "checkLower"),
        ("LoweredUpper", f"value := some {value - 1}", "checkUpper"),
        ("NondecreasingRank", "rank := 0", "checkUpper"),
        ("EmptySuccessors", 'choices := [{ action := "empty", cost := 0, children := [] }]', "checkShape"),
    ]
    report = {
        "schema": "causalfill.formal-information-stress.v1",
        "status": "running", "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_profile": manifest["theorem"], "source_profile_sha256": manifest["lean_source_sha256"],
        "script_sha256": sha256(Path(__file__).resolve()),
        "controls": [],
    }
    try:
        for name, change, check in mutations:
            source = sources / f"{name}.lean"
            source.write_text(
                "import CausalFill.ReleaseAdaptiveMarket\n"
                "set_option maxRecDepth 200000\nset_option maxHeartbeats 0\n"
                "open CausalFill.Information\n"
                "open CausalFill.Exported.ReleaseAdaptiveMarket\n"
                f"def changed : FiniteArena {size} := {{ arena with\n"
                "  nodes := arena.nodes.set arena.root.val\n"
                f"    {{ arena.nodes.get arena.root with {change} }} arena.root.isLt }}\n"
                f"example : changed.{check} = true := by decide\n"
            )
            command = [str(args.compiler_host.resolve()), str(args.toolchain.resolve()),
                       "CausalFill.Mutations." + name, source.relative_to(FORMAL).as_posix()]
            start = time.monotonic()
            result = subprocess.run(command, cwd=FORMAL, env=env, text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
            (output / f"{name}.log").write_text(result.stdout)
            rejected = result.returncode != 0 and "Tactic `decide` proved that the proposition" in result.stdout and "is false" in result.stdout
            report["controls"].append({
                "name": name, "kind": "kernel_rejects_false_concrete_check",
                "passed": rejected, "command": command, "exit_code": result.returncode,
                "elapsed_seconds": round(time.monotonic() - start, 3),
                "source": source.relative_to(FORMAL).as_posix(), "source_sha256": sha256(source),
                "log_sha256": hashlib.sha256(result.stdout.encode()).hexdigest(),
            })
            print(f"{name}: {'rejected as false' if rejected else 'FAILED'}", flush=True)
            if not rejected:
                raise RuntimeError(f"{name}: expected a kernel reduction failure, see diagnostic log")

        for name, change in (
            ("OmittedAlternative", lambda x: x["nodes"][root]["choices"].pop()),
            ("ReroutedSuccessor", lambda x: x["nodes"][root]["choices"][0]["children"].__setitem__(0, root)),
        ):
            altered = deepcopy(original)
            change(altered)
            actual_path = sources / f"{name}.roundtrip.json"
            actual_path.write_text(json.dumps(altered))
            modified_manifest = dict(manifest, roundtrip_file=actual_path.relative_to(FORMAL).as_posix())
            changed_manifest = sources / f"{name}.manifest.json"
            changed_manifest.write_text(json.dumps(modified_manifest))
            rejected = False
            try:
                compare_arena(changed_manifest)
            except RuntimeError as error:
                rejected = "actual Lean arena differs from independent projection" in str(error)
            report["controls"].append({
                "name": name, "kind": "roundtrip_comparator_rejects_statement_change", "passed": rejected,
                "altered_data": actual_path.relative_to(FORMAL).as_posix(), "altered_data_sha256": sha256(actual_path),
            })
            print(f"{name}: {'rejected by correspondence check' if rejected else 'FAILED'}", flush=True)
            if not rejected:
                raise RuntimeError(f"{name}: semantic statement change was accepted")

        # A forged runtime JSON file can look correct while the imported mathematical
        # object is different. The new equality gate must reject that statement.
        source = sources / "ForgedRoundtrip.lean"
        forged_path = sources / "ForgedRoundtrip.roundtrip.json"
        forged_text = json.dumps(original, sort_keys=True, separators=(",", ":"))
        source.write_text(
            "import CausalFill.BindingReleaseAdaptiveMarket\n"
            "set_option maxRecDepth 200000\nset_option maxHeartbeats 0\n"
            "open CausalFill.Information\n"
            "open CausalFill.Exported.ReleaseAdaptiveMarket\n"
            f"def forgedArena : FiniteArena {size} := {{ arena with\n"
            "  nodes := arena.nodes.set arena.root.val\n"
            f"    {{ arena.nodes.get arena.root with value := some {value + 1} }} arena.root.isLt }}\n"
            f"#eval IO.FS.writeFile {json.dumps(forged_path.relative_to(FORMAL).as_posix())} {json.dumps(forged_text)}\n"
            "example : forgedArena = CausalFill.Binding.ReleaseAdaptiveMarket.expectedArena := by rfl\n"
        )
        command = [str(args.compiler_host.resolve()), str(args.toolchain.resolve()),
                   "CausalFill.Mutations.ForgedRoundtrip", source.relative_to(FORMAL).as_posix()]
        start = time.monotonic()
        result = subprocess.run(command, cwd=FORMAL, env=env, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        (output / "ForgedRoundtrip.log").write_text(result.stdout)
        equality_rejected = result.returncode != 0 and "Tactic `rfl` failed" in result.stdout
        forged_json_matches = forged_path.exists() and json.loads(forged_path.read_text()) == original
        report["controls"].append({
            "name": "ForgedRoundtrip", "kind": "kernel_statement_binding",
            "passed": equality_rejected and forged_json_matches,
            "kernel_correspondence_rejected": equality_rejected,
            "forged_runtime_json_matches_original": forged_json_matches,
            "command": command, "exit_code": result.returncode,
            "elapsed_seconds": round(time.monotonic() - start, 3),
            "source": source.relative_to(FORMAL).as_posix(), "source_sha256": sha256(source),
            "log_sha256": hashlib.sha256(result.stdout.encode()).hexdigest(),
        })
        print("ForgedRoundtrip: " + ("kernel rejected false equality despite matching JSON" if equality_rejected and forged_json_matches else "FAILED"), flush=True)
        if not equality_rejected or not forged_json_matches:
            raise RuntimeError("forged roundtrip negative control did not exercise the intended boundary")

        for name, content, expected in (
            ("CustomAxiom", "'a' depends on axioms: [propext, fabricated]", {"a"}),
            ("MissingAuditRoot", "'a' does not depend on any axioms", {"a", "b"}),
            ("DuplicateAuditRoot", "'a' does not depend on any axioms\n'a' does not depend on any axioms", {"a"}),
        ):
            rejected = False
            try:
                inspect_axioms(content, expected)
            except RuntimeError:
                rejected = True
            report["controls"].append({"name": name, "kind": "axiom_gate", "passed": rejected})
            if not rejected:
                raise RuntimeError(f"{name}: audit gate accepted invalid inventory")
        report["status"] = "passed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = str(error)
        raise
    finally:
        report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        (output / "results.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
