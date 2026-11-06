#!/usr/bin/env python3
"""Kernel-check v0.4 information/arena theorems and v0.3 proof regressions.

The normal CLI and the official shared-library frontend both use Lean's kernel
at trust level zero. The optional C embedding sets an explicit system root via
Lean.initSearchPath; it does not replace a syscall, alter access controls, or
change any theorem checking behavior. Independent kernel replay is a separate
gate, check_export_kernels.py, and is not inferred from this result.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

from export_arena import semantic_projection
from verify import compare_roundtrip


FORMAL = Path(__file__).resolve().parent
REPOSITORY = FORMAL.parent
sys.path.insert(0, str(REPOSITORY))
from causalfill.belief_certificates import expand_game_certificate

ALLOWED_AXIOMS = {"propext", "Classical.choice", "Quot.sound"}
OFFICIAL_ARCHIVE_SHA256 = "7289597a44543246c9227b8cae501767e095ce17f6d448b95fc4a8dc97268f6d"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def inspect_axioms(output: str, expected_names: set[str]) -> dict[str, list[str]]:
    rows = re.findall(
        r"^'([^']+)' (?:depends on axioms: \[([^\]]*)\]|(does not depend on any axioms))$",
        output, re.MULTILINE,
    )
    if len(rows) != len(expected_names) or {r[0] for r in rows} != expected_names:
        raise RuntimeError("axiom audit names/count differ from the declared theorem inventory")
    results = {}
    for theorem, content, _ in rows:
        names = {part.strip() for part in content.split(",") if part.strip()}
        if names - ALLOWED_AXIOMS:
            raise RuntimeError(f"unapproved axioms for {theorem}: {sorted(names - ALLOWED_AXIOMS)}")
        results[theorem] = sorted(names)
    return results


def expected_audit_names(source: Path) -> set[str]:
    return set(re.findall(r"^#print axioms (\S+)$", source.read_text(), re.MULTILINE))


def compare_arena(manifest_path: Path) -> dict:
    manifest = json.loads(manifest_path.read_text())
    game_path = REPOSITORY / manifest["source_game"]
    certificate_path = REPOSITORY / manifest["source_certificate"]
    source = FORMAL / manifest["lean_source"]
    for key, path in (
        ("source_game_file_sha256", game_path),
        ("source_certificate_file_sha256", certificate_path),
        ("lean_source_sha256", source),
    ):
        if sha256(path) != manifest[key]:
            raise RuntimeError(f"{manifest['name']}: stale or changed {key}")
    expanded = expand_game_certificate(
        json.loads(game_path.read_text()), json.loads(certificate_path.read_text())
    )
    semantic = semantic_projection(expanded)
    actual_metadata = {
        "mode": expanded["mode"], "node_count": semantic["size"], "root": semantic["root"],
        "root_value": semantic["nodes"][semantic["root"]]["value"],
    }
    for key, value in actual_metadata.items():
        if manifest[key] != value:
            raise RuntimeError(f"{manifest['name']}: manifest {key} differs from checked arena")
    actual_path = FORMAL / manifest["roundtrip_file"]
    actual = json.loads(actual_path.read_text())
    if semantic != actual:
        raise RuntimeError(f"{manifest['name']}: actual Lean arena differs from independent projection")
    digest = hashlib.sha256(json.dumps(actual, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if digest != manifest["semantic_arena_sha256"]:
        raise RuntimeError(f"{manifest['name']}: semantic arena commitment differs")
    if expanded["game_sha256"] != manifest["game_sha256"] or expanded["certificate_sha256"] != manifest["certificate_sha256"]:
        raise RuntimeError(f"{manifest['name']}: source canonical commitments differ")
    return {
        "exact_semantic_roundtrip": True,
        "source_hashes_match": True,
        "python_certificate_reverified": True,
        "semantic_arena_sha256": digest,
        "node_count": len(actual["nodes"]),
        "root_value": actual["nodes"][actual["root"]]["value"],
        "mode": expanded["mode"],
        "theorem": manifest["theorem"],
        "unformalized_boundary": manifest["unformalized_boundary"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--toolchain", type=Path, required=True)
    parser.add_argument("--backend", choices=("cli", "embedding"), default="cli")
    parser.add_argument("--toolchain-archive", type=Path)
    parser.add_argument("--output", type=Path, default=FORMAL / "verification-v04")
    parser.add_argument("--arena-manifest", type=Path, action="append", default=[])
    parser.add_argument("--skip-resolution-regression", action="store_true")
    args = parser.parse_args()
    toolchain, output = args.toolchain.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    build = FORMAL / ".lake" / "build" / "lib" / "lean"
    (build / "CausalFill").mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["LEAN_PATH"] = str(build)
    env["PATH"] = str(toolchain / "bin") + os.pathsep + env.get("PATH", "")
    report = {
        "schema": "causalfill.information-verification.v1", "status": "running",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "backend": args.backend, "trust_level": 0,
        "elaboration_async": False, "lean_worker_threads": 1 if args.backend == "embedding" else "CLI default",
        "allowed_axioms": sorted(ALLOWED_AXIOMS), "commands": [], "axioms": {},
        "source_sha256": {}, "arena_certificates": {}, "resolution_regression": {},
        "independent_kernel_replay": "separate gate, not asserted by this report",
        "trusted_boundary": "Lean runtime/kernel, C ABI host when selected, Python projection and roundtrip comparator",
    }
    dependency_paths = [
        Path(__file__).resolve(), FORMAL / "export_arena.py", FORMAL / "verify.py",
        REPOSITORY / "causalfill" / "belief_certificates.py",
        REPOSITORY / "causalfill" / "belief_games.py",
    ]
    dependency_hashes = {os.path.relpath(path, FORMAL): sha256(path) for path in dependency_paths}
    report["source_sha256"].update(dependency_hashes)

    def run(name: str, command: list[str], *, success: bool = True) -> str:
        started = time.monotonic()
        result = subprocess.run(command, cwd=FORMAL, env=env, text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
        (output / f"{name}.log").write_text(result.stdout)
        report["commands"].append({
            "name": name, "command": command, "exit_code": result.returncode,
            "expected_success": success, "elapsed_seconds": round(time.monotonic() - started, 3),
            "output_sha256": hashlib.sha256(result.stdout.encode()).hexdigest(),
        })
        print(f"{name}: exit {result.returncode}", flush=True)
        if success != (result.returncode == 0):
            raise RuntimeError(f"{name} unexpected exit; see {output / (name + '.log')}")
        if success and "declaration uses `sorry`" in result.stdout:
            raise RuntimeError(f"{name}: admitted declaration reported")
        return result.stdout

    def compile_module(module: str, source: Path, *, write_olean: bool = True, success: bool = True) -> str:
        relative = source.relative_to(FORMAL).as_posix()
        report["source_sha256"][relative] = sha256(source)
        destination = build / (module.replace(".", "/") + ".olean")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if args.backend == "embedding":
            command = [str(host), str(toolchain), module, relative]
            if write_olean:
                command.append(str(destination))
        else:
            command = [str(toolchain / "bin" / "lean"), "--trust=0", "-DElab.async=false"]
            if write_olean:
                command.extend(["-o", str(destination)])
            command.append(relative)
        return run(module.replace(".", "-"), command, success=success)

    try:
        header = toolchain / "include" / "lean" / "version.h"
        version = re.search(r'#define LEAN_VERSION_STRING "([^"]+)"', header.read_text())
        if version is None or version[1] != "4.35.0":
            raise RuntimeError("pinned Lean 4.35.0 toolchain headers required")
        report["toolchain_version_header"] = version[1]
        report["toolchain_files_sha256"] = {
            "include/lean/version.h": sha256(header),
            "lib/lean/libleanshared.so": sha256(toolchain / "lib" / "lean" / "libleanshared.so"),
        }
        if args.toolchain_archive:
            archive_digest = sha256(args.toolchain_archive)
            if archive_digest != OFFICIAL_ARCHIVE_SHA256:
                raise RuntimeError("archive hash differs from pinned official Linux toolchain archive")
            report["verified_toolchain_archive_sha256"] = archive_digest
        if args.backend == "embedding":
            host = output / "lean_frontend"
            host_source = FORMAL / "embedding" / "lean_frontend.c"
            report["source_sha256"]["embedding/lean_frontend.c"] = sha256(host_source)
            run("build-host", [
                "cc", "-std=c11", "-D_POSIX_C_SOURCE=200809L", "-Wall", "-Wextra", "-Werror",
                "-I", str(toolchain / "include"), str(host_source),
                "-L", str(toolchain / "lib" / "lean"),
                "-Wl,-rpath," + str(toolchain / "lib" / "lean"),
                "-lleanshared", "-o", str(host),
            ])
            report["embedding_host_sha256"] = sha256(host)
        smoke = compile_module("EmbeddingSmoke", FORMAL / "embedding" / "Smoke.lean")
        if '"4.35.0"' not in smoke:
            raise RuntimeError("running Lean library version differs from pinned version")
        report["axioms"].update(inspect_axioms(smoke, {"embedding_smoke"}))

        negative = FORMAL / "embedding" / "Negative.lean"
        rejected = compile_module("KernelNegative", negative, write_olean=False, success=False)
        if "error" not in rejected:
            raise RuntimeError("negative kernel smoke failed without a reported elaboration error")
        report["false_theorem_rejected"] = True
        try:
            inspect_axioms("'bad' depends on axioms: [admittedClaim]", {"bad"})
        except RuntimeError:
            report["custom_axiom_gate_rejected"] = True
        else:
            raise RuntimeError("custom axiom negative test was accepted")

        for name in ("Information", "FiniteArena", "ArenaJSON"):
            compile_module(f"CausalFill.{name}", FORMAL / "CausalFill" / f"{name}.lean")
        audit_source = FORMAL / "CausalFill" / "InformationAudit.lean"
        audit = compile_module("CausalFill.InformationAudit", audit_source)
        report["axioms"].update(inspect_axioms(audit, expected_audit_names(audit_source)))

        for manifest_path in args.arena_manifest:
            manifest_path = manifest_path.resolve()
            manifest = json.loads(manifest_path.read_text())
            source = FORMAL / manifest["lean_source"]
            compiled = compile_module("CausalFill." + manifest["name"], source)
            report["axioms"].update(inspect_axioms(compiled, {manifest["theorem"]}))
            report["arena_certificates"][manifest["name"]] = compare_arena(manifest_path)

        if not args.skip_resolution_regression:
            for name in ("Resolution", "Examples"):
                compile_module(f"CausalFill.{name}", FORMAL / "CausalFill" / f"{name}.lean")
            compile_module("CausalFill", FORMAL / "CausalFill.lean")
            old_audit = FORMAL / "CausalFill" / "Audit.lean"
            compiled = compile_module("CausalFill.Audit", old_audit)
            report["axioms"].update(inspect_axioms(compiled, expected_audit_names(old_audit)))
            for name, stem in (("ReleaseModel", "model"), ("ReleaseReference", "reference")):
                compiled = compile_module(f"CausalFill.{name}", FORMAL / "CausalFill" / f"{name}.lean")
                theorem = re.findall(r"^'([^']+)' depends on axioms:", compiled, re.MULTILINE)
                if len(theorem) != 1:
                    raise RuntimeError(f"{name}: expected one release theorem audit")
                report["axioms"].update(inspect_axioms(compiled, set(theorem)))
                report["resolution_regression"][stem] = compare_roundtrip(name, stem)
        for relative, expected in dependency_hashes.items():
            if sha256(FORMAL / relative) != expected:
                raise RuntimeError(f"verification dependency changed during run: {relative}")
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
