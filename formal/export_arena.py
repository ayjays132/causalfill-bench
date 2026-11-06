#!/usr/bin/env python3
"""Translate a validated complete finite-belief arena into a Lean statement.

This translator is untrusted. Lean proves the checks over the emitted arena;
verify_information.py compares JSON read back from the actual Lean definitions.
The Python game-to-belief projection is not formally verified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys


FORMAL = Path(__file__).resolve().parent
REPOSITORY = FORMAL.parent
sys.path.insert(0, str(REPOSITORY))

from causalfill.belief_certificates import expand_game_certificate


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def semantic_projection(arena: dict) -> dict:
    """Exactly the fields represented by FiniteArena and its Lean JSON encoder."""
    return {
        "size": len(arena["nodes"]),
        "root": arena["root"],
        "nodes": [
            {
                "goal": node["goal"],
                "rank": node["rank"],
                "value": node["value"],
                "choices": [
                    {key: choice[key] for key in ("action", "cost", "children")}
                    for choice in node["choices"]
                ],
            }
            for node in arena["nodes"]
        ],
    }


def lean_string(value: str) -> str:
    # JSON's non-ASCII strings and ordinary escapes agree with Lean string syntax.
    # Reject controls needing JSON's unsupported \uXXXX spelling.
    if any(ord(c) < 32 and c not in "\n\r\t" for c in value):
        raise ValueError("Lean exporter rejects control characters in action identifiers")
    return json.dumps(value, ensure_ascii=False)


def emit_arena(game_path: Path, certificate_path: Path, name: str, output: Path) -> dict:
    if not re.fullmatch(r"[A-Z][A-Za-z0-9_]*", name):
        raise ValueError("name must be a Lean module component beginning with a capital")
    game_path, certificate_path, output = (
        game_path.resolve(), certificate_path.resolve(), output.resolve()
    )
    game = json.loads(game_path.read_text())
    certificate = json.loads(certificate_path.read_text())
    expanded = expand_game_certificate(game, certificate)
    semantic = semantic_projection(expanded)
    size, root = semantic["size"], semantic["root"]
    if not size:
        raise ValueError("cannot export an empty arena")
    try:
        game_relative = game_path.relative_to(REPOSITORY).as_posix()
        certificate_relative = certificate_path.relative_to(REPOSITORY).as_posix()
        source_relative = output.relative_to(FORMAL).as_posix()
    except ValueError as exc:
        raise ValueError("export inputs must be inside repository and output inside formal") from exc
    roundtrip = output.with_suffix(".roundtrip.json").relative_to(FORMAL).as_posix()
    lines = [
        "import CausalFill.ArenaJSON",
        "",
        "/-! Generated finite arena. The emitter is untrusted; every check below is",
        "kernel reduction. Semantic JSON is emitted from the actual Lean data. -/",
        "set_option maxRecDepth 200000",
        "set_option maxHeartbeats 0",
        "",
        f"namespace CausalFill.Exported.{name}",
        "open CausalFill.Information",
        "",
    ]
    for index, node in enumerate(semantic["nodes"]):
        value = "none" if node["value"] is None else f"some {node['value']}"
        choices = []
        for choice in node["choices"]:
            children = ", ".join(f"⟨{child}, by decide⟩" for child in choice["children"])
            choices.append(
                "{ action := " + lean_string(choice["action"]) +
                f", cost := {choice['cost']}, children := [{children}] }}"
            )
        lines.extend([
            f"def node{index} : ArenaNode {size} where",
            f"  goal := {str(node['goal']).lower()}",
            f"  rank := {node['rank']}",
            f"  value := {value}",
            "  choices := [" + ", ".join(choices) + "]",
            "",
        ])
    lines.extend([
        f"def arena : FiniteArena {size} where",
        "  nodes := ⟨#[" + ", ".join(f"node{i}" for i in range(size)) + "], by decide⟩",
        f"  root := ⟨{root}, by decide⟩",
        "",
        "theorem shapeChecked : arena.checkShape = true := by decide",
        "theorem lowerChecked : arena.checkLower = true := by decide",
        "theorem upperChecked : arena.checkUpper = true := by decide",
        "",
    ])
    root_value = semantic["nodes"][root]["value"]
    if root_value is None:
        outcome_theorem = "unwinnable"
        lines.extend([
            "theorem unwinnable : ∀ budget, ¬ CanWin arena.game arena.root budget :=",
            "  FiniteArena.unwinnable_of_check lowerChecked (by decide)",
            "theorem certifiedProfile : arena.checkShape = true ∧",
            "    (∀ budget, ¬ CanWin arena.game arena.root budget) :=",
            "  ⟨shapeChecked, unwinnable⟩",
        ])
    else:
        outcome_theorem = "exactBudget"
        lines.extend([
            f"theorem exactBudget : CanWin arena.game arena.root {root_value} ∧",
            f"    (∀ budget, CanWin arena.game arena.root budget → {root_value} ≤ budget) :=",
            "  FiniteArena.exact_budget_of_checks lowerChecked upperChecked (by decide)",
            "theorem certifiedProfile : arena.checkShape = true ∧",
            f"    (CanWin arena.game arena.root {root_value} ∧",
            f"      (∀ budget, CanWin arena.game arena.root budget → {root_value} ≤ budget)) :=",
            "  ⟨shapeChecked, exactBudget⟩",
        ])
    lines.extend([
        "#print axioms certifiedProfile",
        "#eval do",
        "  unless arena.checkShape && arena.checkLower && arena.checkUpper do",
        '    throw (IO.userError "finite arena runtime checker rejected certificate")',
        f"  IO.FS.writeFile {lean_string(roundtrip)} (arena.semanticJSON.compress ++ \"\\n\")",
        f"  IO.println {lean_string(name + ': finite arena kernel theorem and roundtrip accepted')}",
        f"end CausalFill.Exported.{name}",
        "",
    ])
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines))
    manifest = {
        "schema": "causalfill.lean-arena-export.v1",
        "name": name,
        "source_game": game_relative,
        "source_certificate": certificate_relative,
        "lean_source": source_relative,
        "roundtrip_file": roundtrip,
        "source_game_file_sha256": sha256(game_path),
        "source_certificate_file_sha256": sha256(certificate_path),
        "lean_source_sha256": sha256(output),
        "semantic_arena_sha256": hashlib.sha256(
            json.dumps(semantic, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "game_sha256": expanded["game_sha256"],
        "certificate_sha256": expanded["certificate_sha256"],
        "mode": expanded["mode"],
        "node_count": size,
        "root": root,
        "root_value": root_value,
        "theorem": f"CausalFill.Exported.{name}.certifiedProfile",
        "outcome_theorem": f"CausalFill.Exported.{name}.{outcome_theorem}",
        "formal_scope": "complete emitted AND/OR arena and finite-strategy worst-case action cost",
        "unformalized_boundary": "Python game validation and game-to-belief-arena projection",
        "metadata_not_in_lean_semantics": ["belief", "failure_cut", "selected_action", "observations"],
    }
    output.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", type=Path, required=True)
    parser.add_argument("--certificate", type=Path, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(emit_arena(args.game, args.certificate, args.name, args.output), indent=2))


if __name__ == "__main__":
    main()
