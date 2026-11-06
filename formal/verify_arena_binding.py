#!/usr/bin/env python3
"""Kernel-bind imported release arenas to independently rendered source statements.

The original emitter and its #eval output are not trusted for correspondence.
This separate emitter reconstructs the arena through the independent Python
certificate verifier, renders literal Lean data without importing export_arena,
and asks the kernel to prove equality to the actual imported release constant.
The raw-game-to-belief projection remains a trusted Python boundary.
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

FORMAL = Path(__file__).resolve().parent
REPOSITORY = FORMAL.parent
sys.path.insert(0, str(REPOSITORY))
from causalfill.belief_certificates import expand_game_certificate

ALLOWED_AXIOMS = {"propext", "Classical.choice", "Quot.sound"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def lean_quoted(value: str) -> str:
    """Independent string renderer, intentionally not shared with export_arena."""
    escaped = []
    table = {'"': '\\"', '\\': '\\\\', '\n': '\\n', '\r': '\\r', '\t': '\\t'}
    for character in value:
        if character in table:
            escaped.append(table[character])
        elif ord(character) < 32:
            raise ValueError("unsupported control in action identifier")
        else:
            escaped.append(character)
    return '"' + ''.join(escaped) + '"'


def independently_expected(expanded: dict) -> dict:
    """Copy the semantic statement field-by-field without the original emitter."""
    nodes = []
    for item in expanded["nodes"]:
        alternatives = []
        for alternative in item["choices"]:
            alternatives.append({
                "action": alternative["action"],
                "cost": alternative["cost"],
                "children": list(alternative["children"]),
            })
        nodes.append({
            "goal": item["goal"], "rank": item["rank"],
            "value": item["value"], "choices": alternatives,
        })
    return {"size": len(nodes), "root": expanded["root"], "nodes": nodes}


def render_expected(expected: dict, name: str) -> str:
    """One inline literal array; the original emitter instead names every node."""
    size = expected["size"]
    rows = []
    for node in expected["nodes"]:
        choices = []
        for choice in node["choices"]:
            children = ', '.join(f"⟨{index}, by decide⟩" for index in choice["children"])
            choices.append(f"⟨{lean_quoted(choice['action'])}, {choice['cost']}, [{children}]⟩")
        goal = "true" if node["goal"] else "false"
        value = "none" if node["value"] is None else f"some {node['value']}"
        rows.append(f"    ⟨{goal}, {node['rank']}, {value}, [{', '.join(choices)}]⟩")
    target = f"CausalFill.Exported.{name}.arena"
    root_value = expected["nodes"][expected["root"]]["value"]
    if root_value is None:
        property_text = "(∀ budget, ¬ CanWin expectedArena.game expectedArena.root budget)"
    else:
        property_text = (
            f"(CanWin expectedArena.game expectedArena.root {root_value} ∧\n"
            f"      (∀ budget, CanWin expectedArena.game expectedArena.root budget → {root_value} ≤ budget))"
        )
    return (
        f"import CausalFill.{name}\n"
        "set_option maxRecDepth 200000\nset_option maxHeartbeats 0\n\n"
        f"namespace CausalFill.Binding.{name}\n"
        "open CausalFill.Information\n\n"
        f"def expectedArena : FiniteArena {size} :=\n"
        "  ⟨⟨#[\n" + ",\n".join(rows) + "\n  ], by rfl⟩, "
        f"⟨{expected['root']}, by decide⟩⟩\n\n"
        f"theorem arenaCorrespondence : {target} = expectedArena := by rfl\n\n"
        f"theorem boundProfile : {target} = expectedArena ∧\n"
        "    (expectedArena.checkShape = true ∧\n"
        f"      {property_text}) := by\n"
        "  constructor\n"
        "  · exact arenaCorrespondence\n"
        "  · rw [← arenaCorrespondence]\n"
        f"    exact CausalFill.Exported.{name}.certifiedProfile\n"
        "#print axioms boundProfile\n"
        f"end CausalFill.Binding.{name}\n"
    )


def verify_one(manifest_path: Path, output: Path, host: Path, toolchain: Path, env: dict) -> dict:
    manifest = json.loads(manifest_path.read_text())
    name = manifest["name"]
    if not re.fullmatch(r"[A-Z][A-Za-z0-9_]*", name):
        raise ValueError("invalid module component")
    game_path, certificate_path = (
        REPOSITORY / manifest["source_game"], REPOSITORY / manifest["source_certificate"]
    )
    expanded = expand_game_certificate(
        json.loads(game_path.read_text()), json.loads(certificate_path.read_text())
    )
    expected = independently_expected(expanded)
    audited_metadata = {
        "mode": expanded["mode"], "node_count": expected["size"], "root": expected["root"],
        "root_value": expected["nodes"][expected["root"]]["value"],
        "game_sha256": expanded["game_sha256"], "certificate_sha256": expanded["certificate_sha256"],
    }
    for key, actual in audited_metadata.items():
        if manifest[key] != actual:
            raise RuntimeError(f"{name}: manifest {key} differs from independently checked statement")
    for key, path in (
        ("source_game_file_sha256", game_path),
        ("source_certificate_file_sha256", certificate_path),
        ("lean_source_sha256", FORMAL / manifest["lean_source"]),
    ):
        if manifest[key] != sha256(path):
            raise RuntimeError(f"{name}: changed source {key}")
    expected_digest = hashlib.sha256(
        json.dumps(expected, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if manifest["semantic_arena_sha256"] != expected_digest:
        raise RuntimeError(f"{name}: semantic commitment differs from reconstructed data")
    source = FORMAL / "CausalFill" / f"Binding{name}.lean"
    source.write_text(render_expected(expected, name))
    expected_path = source.with_suffix(".expected.json")
    expected_path.write_text(json.dumps(expected, indent=2, sort_keys=True) + "\n")
    module = "CausalFill.Binding" + name
    destination = FORMAL / ".lake" / "build" / "lib" / "lean" / "CausalFill" / f"Binding{name}.olean"
    command = [str(host), str(toolchain), module, source.relative_to(FORMAL).as_posix(), str(destination)]
    start = time.monotonic()
    result = subprocess.run(command, cwd=FORMAL, env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    (output / f"{name}.log").write_text(result.stdout)
    theorem = f"CausalFill.Binding.{name}.boundProfile"
    rows = re.findall(r"^'([^']+)' depends on axioms: \[([^\]]*)\]$", result.stdout, re.MULTILINE)
    if result.returncode != 0 or len(rows) != 1 or rows[0][0] != theorem:
        raise RuntimeError(f"{name}: correspondence kernel check failed; inspect its log")
    axioms = {part.strip() for part in rows[0][1].split(",") if part.strip()}
    if axioms - ALLOWED_AXIOMS or "declaration uses `sorry`" in result.stdout:
        raise RuntimeError(f"{name}: unapproved axiom or admitted proof")
    print(f"{name}: actual imported arena equals independently rendered statement", flush=True)
    return {
        "status": "passed", "theorem": theorem,
        "correspondence_theorem": f"CausalFill.Binding.{name}.arenaCorrespondence",
        "statement_binding": "kernel-checked equality of entire FiniteArena, including nodes and root",
        "expected_semantic_sha256": expected_digest,
        "expected_data": expected_path.relative_to(FORMAL).as_posix(),
        "expected_data_file_sha256": sha256(expected_path),
        "binding_source": source.relative_to(FORMAL).as_posix(), "binding_source_sha256": sha256(source),
        "original_source": manifest["lean_source"], "original_source_sha256": manifest["lean_source_sha256"],
        "manifest": manifest_path.relative_to(FORMAL).as_posix(), "manifest_sha256": sha256(manifest_path),
        "audited_metadata": audited_metadata,
        "command": command, "exit_code": result.returncode,
        "elapsed_seconds": round(time.monotonic() - start, 3), "axioms": sorted(axioms),
        "log_sha256": hashlib.sha256(result.stdout.encode()).hexdigest(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--toolchain", type=Path, required=True)
    parser.add_argument("--compiler-host", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, default=FORMAL / "verification-v04-binding")
    args = parser.parse_args()
    output, host, toolchain = args.output.resolve(), args.compiler_host.resolve(), args.toolchain.resolve()
    output.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["LEAN_PATH"] = str(FORMAL / ".lake" / "build" / "lib" / "lean")
    dependencies = [Path(__file__).resolve(), FORMAL / "embedding" / "lean_frontend.c",
                    REPOSITORY / "causalfill" / "belief_certificates.py",
                    REPOSITORY / "causalfill" / "belief_games.py"]
    hashes = {os.path.relpath(path, FORMAL): sha256(path) for path in dependencies}
    report = {
        "schema": "causalfill.kernel-arena-binding.v1", "status": "running",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_sha256": hashes, "compiler_host_sha256": sha256(host),
        "toolchain_files_sha256": {
            "include/lean/version.h": sha256(toolchain / "include" / "lean" / "version.h"),
            "lib/lean/libleanshared.so": sha256(toolchain / "lib" / "lean" / "libleanshared.so"),
        },
        "bindings": {},
        "unformalized_boundary": "independent Python certificate verification and raw-game-to-belief projection",
        "runtime_json_required_for_binding": False,
    }
    try:
        for path in args.manifest:
            result = verify_one(path.resolve(), output, host, toolchain, env)
            report["bindings"][result["theorem"]] = result
        for relative, digest in hashes.items():
            if sha256(FORMAL / relative) != digest:
                raise RuntimeError(f"binding dependency changed during run: {relative}")
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
