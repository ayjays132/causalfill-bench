#!/usr/bin/env python3
"""Translate a release statement and fill into locally checked Lean theorems.

This script is an untrusted data translator, not part of Lean's logical kernel.
Every emitted resolvent is checked by a separate Lean ``by decide`` proof.
It imports no CausalFill evaluator, generator, or search implementation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re


def integer(value: object, low: int, high: int, label: str) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{label}: expected integer in [{low}, {high}]")
    return value


def literal(value: int) -> str:
    return f"{'pos' if value > 0 else 'neg'} {abs(value)}"


def clause(values: list[int]) -> str:
    return "[" + ", ".join(map(literal, values)) + "]"


def deduplicate(values: list[int]) -> list[int]:
    # Match the Lean function: retain the last occurrence, in original order.
    return [value for index, value in enumerate(values) if value not in values[index + 1 :]]


def load_and_validate(statement_path: Path, fill_path: Path) -> tuple[dict, dict, list[list[int]], str]:
    statement = json.loads(statement_path.read_text())
    fill = json.loads(fill_path.read_text())
    if type(statement) is not dict or type(fill) is not dict:
        raise ValueError("statement and fill must be JSON objects")
    nvars = integer(statement.get("nvars"), 1, 200, "nvars")
    goal = integer(statement.get("goal"), -nvars, nvars, "goal")
    if goal == 0:
        raise ValueError("goal must be nonzero")
    premises = statement.get("clauses")
    if type(premises) is not list or len(premises) > 2000:
        raise ValueError("clauses must be a list of at most 2000 clauses")
    if len(premises) + 1 > 2000:
        raise ValueError("adding the negated goal exceeds the initial-clause limit")
    for number, current in enumerate(premises):
        if type(current) is not list or len(current) > 2 * nvars:
            raise ValueError(f"clause {number}: expected a bounded JSON list")
        for value in current:
            integer(value, -nvars, nvars, f"clause {number} literal")
            if value == 0:
                raise ValueError("literals must be nonzero")
    canonical = [sorted(set(current)) for current in premises]
    payload = {"schema": "causalfill.propositional-statement.v1", "nvars": nvars,
               "clauses": canonical, "goal": goal}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                      allow_nan=False).encode()).hexdigest()
    for owner in (statement, fill):
        if owner.get("statement_sha256") != digest:
            raise ValueError("statement content commitment is absent or does not match")
    assignment = fill.get("consistency_model")
    if (type(assignment) is not list or len(assignment) != nvars
            or any(type(value) is not bool for value in assignment)):
        raise ValueError("consistency_model must be a total Boolean assignment")
    steps = fill.get("proof_steps")
    if type(steps) is not list or len(steps) > 12000:
        raise ValueError("proof_steps must be a list of at most 12000 triples")
    known = [list(current) for current in premises] + [[-goal]]
    entries = sum(len(set(current)) for current in known)
    if entries > 500000:
        raise ValueError("initial literal-storage limit exceeded")
    for number, step in enumerate(steps):
        if type(step) is not list or len(step) != 3:
            raise ValueError(f"step {number}: expected a triple")
        left_index = integer(step[0], 0, len(known) - 1, f"step {number} left")
        right_index = integer(step[1], 0, len(known) - 1, f"step {number} right")
        pivot = integer(step[2], 1, nvars, f"step {number} pivot")
        left, right = known[left_index], known[right_index]
        if pivot in left and -pivot in right:
            left_pivot, right_pivot = pivot, -pivot
        elif -pivot in left and pivot in right:
            left_pivot, right_pivot = -pivot, pivot
        else:
            raise ValueError(f"step {number}: parents lack opposite pivot literals")
        result = deduplicate([value for value in left if value != left_pivot]
                             + [value for value in right if value != right_pivot])
        entries += len(result)
        if entries > 500000:
            raise ValueError("derived literal-storage limit exceeded")
        known.append(result)
    if (steps and known[-1]) or (not steps and [] not in known):
        raise ValueError("certificate does not end in the required empty clause")
    return statement, fill, known, digest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--statement", required=True, type=Path)
    parser.add_argument("--fill", required=True, type=Path)
    parser.add_argument("--name", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Z][A-Za-z0-9_]*", args.name):
        raise ValueError("name must be a simple Lean namespace starting with an uppercase letter")
    statement, fill, known, digest = load_and_validate(args.statement, args.fill)
    premise_count = len(statement["clauses"])
    initial_count = premise_count + 1
    statement_sha = hashlib.sha256(args.statement.read_bytes()).hexdigest()
    fill_sha = hashlib.sha256(args.fill.read_bytes()).hexdigest()
    formal_dir = Path(__file__).resolve().parent
    roundtrip_relative = args.output.resolve().relative_to(formal_dir).with_suffix(".roundtrip.json")
    lines = [
        "-- Generated by formal/export_certificate.py; every local inference is kernel checked.",
        f"-- statement file SHA-256: {statement_sha}",
        f"-- fill file SHA-256: {fill_sha}",
        f"-- canonical statement commitment: {digest}",
        "import CausalFill.Resolution",
        "set_option maxRecDepth 100000",
        "set_option maxHeartbeats 0",
        f"namespace CausalFill.Exported.{args.name}",
        "",
    ]
    for index in range(initial_count):
        lines.append(f"def clause{index} : Clause := {clause(known[index])}")
    lines.extend([
        "def premises : CNF := [" + ", ".join(f"clause{i}" for i in range(premise_count)) + "]",
        f"def goal : Literal := {literal(statement['goal'])}",
        f"def variableCount : Nat := {statement['nvars']}",
        "def extended : CNF := premises ++ [[goal.complement]]",
        "def assignment : List Bool := [" + ", ".join(str(value).lower() for value in fill["consistency_model"]) + "]",
        "theorem modelAccepted : checkModel (assignmentValuation assignment) premises = true := by decide",
        "",
    ])
    for index in range(initial_count):
        lines.extend([
            f"theorem derived{index} : Derivable extended clause{index} :=",
            "  Derivable.premise (by decide)",
        ])
    for offset, (left, right, pivot) in enumerate(fill["proof_steps"]):
        index = initial_count + offset
        lines.extend([
            f"def clause{index} : Clause := {clause(known[index])}",
            f"theorem derived{index} : Derivable extended clause{index} :=",
            f"  Derivable.resolution (pivot := {pivot}) derived{left} derived{right} (by decide)",
        ])
    final_index = len(known) - 1 if fill["proof_steps"] else known.index([])
    lines.extend([
        "",
        "theorem emptyDerived : Derivable (premises ++ [[goal.complement]]) [] :=",
        f"  derived{final_index}",
        "theorem certifiedNonvacuous : NonvacuousEntailment premises goal :=",
        "  checked_derivation_nonvacuous modelAccepted emptyDerived",
        "#print axioms certifiedNonvacuous",
        "",
        "-- This independent runtime evaluation also exercises the full indexed checker.",
        "def steps : List Step := [",
    ])
    lines.append(",\n".join(f"  ⟨{left}, {right}, {pivot}⟩" for left, right, pivot in fill["proof_steps"]))
    lines.extend([
        "]",
        "def signedLiteral (value : Literal) : Int :=",
        "  if value.positive then Int.ofNat value.var else -(Int.ofNat value.var)",
        "def jsonArray (items : List String) : String :=",
        '  "[" ++ String.intercalate "," items ++ "]"',
        "def roundtripJSON : String :=",
        '  "{\\\"nvars\\\":" ++ toString variableCount ++',
        '  ",\\\"clauses\\\":" ++ jsonArray (premises.map (fun values => jsonArray (values.map (fun value => toString (signedLiteral value))))) ++',
        '  ",\\\"goal\\\":" ++ toString (signedLiteral goal) ++',
        '  ",\\\"consistency_model\\\":" ++ jsonArray (assignment.map (fun value => if value then "true" else "false")) ++',
        '  ",\\\"proof_steps\\\":" ++ jsonArray (steps.map (fun step => jsonArray [toString step.left, toString step.right, toString step.pivot])) ++ "}\\n"',
        "#eval do",
        "  unless refutes extended steps do",
        '    throw (IO.userError "full indexed Lean checker rejected the certificate")',
        "  IO.FS.writeFile " + json.dumps(roundtrip_relative.as_posix()) + " roundtripJSON",
        f'  IO.println "{args.name}: kernel theorem + indexed runtime checker accepted {len(fill["proof_steps"])} steps"',
        f"end CausalFill.Exported.{args.name}",
        "",
    ])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines))
    manifest = {
        "schema": "causalfill.lean-export.v1",
        "namespace": f"CausalFill.Exported.{args.name}",
        "source_statement": args.statement.as_posix(),
        "source_fill": args.fill.as_posix(),
        "source_statement_file_sha256": statement_sha,
        "source_fill_file_sha256": fill_sha,
        "canonical_statement_sha256": digest,
        "lean_source_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
        "nvars": statement["nvars"],
        "premises": premise_count,
        "proof_steps": len(fill["proof_steps"]),
        "proof_mode": "kernel-checked local resolution equations; no native_decide",
        "roundtrip_file": roundtrip_relative.as_posix(),
        "correspondence_note": "JSON translation and Python normalization correspondence are not Lean-proved",
    }
    manifest_path = args.output.with_suffix(".manifest.json")
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"lean_source": str(args.output), "manifest": str(manifest_path),
                      "proof_steps": len(fill["proof_steps"])}))


if __name__ == "__main__":
    main()
