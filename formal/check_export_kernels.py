#!/usr/bin/env python3
"""Replay a Lean 4.35 NDJSON proof export with six bundled checker variants.

This is a direct checker invocation over data, not `lake check --paranoid`:
the latter's full build sandbox is unavailable on the development host.
The input theorem/axiom inventory is audited independently before replay.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time

STANDARD_AXIOMS = {"propext", "Classical.choice", "Quot.sound"}
TARGET = "CausalFill.Information.certified_exact_budget"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inventory(rows):
    names, axioms, declarations, unsafe = {0: ""}, [], {}, []
    for row in rows:
        if "in" in row:
            part = row.get("str", row.get("num"))
            suffix = str(part.get("str", part.get("i")))
            names[row["in"]] = ".".join(filter(None, (names[part["pre"]], suffix)))
        for kind in ("def", "thm", "axiom", "opaque"):
            if kind in row:
                declaration = row[kind]
                name = names[declaration["name"]]
                declarations[name] = kind
                if kind == "axiom":
                    axioms.append(name)
                if declaration.get("isUnsafe", False):
                    unsafe.append(name)
    return {"axioms": sorted(axioms), "unsafe_declarations": sorted(unsafe),
            "selected_declarations": dict(sorted((name, kind) for name, kind in declarations.items()
                                                 if name.startswith("CausalFill."))),
            "named_definition_theorem_axiom_opaque_count": len(declarations),
            "records": len(rows), "name_table": names}


def audit(info, required_roots):
    return (not info["unsafe_declarations"] and
            set(info["axioms"]) <= STANDARD_AXIOMS and
            all(info["selected_declarations"].get(root) == "thm" for root in required_roots))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--toolchain", type=Path, required=True)
    parser.add_argument("--export", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--roots", type=Path, required=True,
                        help="Trusted JSON list of every required theorem root")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    export, toolchain, output = args.export.resolve(), args.toolchain.resolve(), args.out.resolve()
    if output.exists():
        parser.error("output directory must be fresh")
    output.mkdir(parents=True)
    rows = [json.loads(line) for line in export.read_text().splitlines()]
    info = inventory(rows)
    required_roots = json.loads(args.roots.read_text())
    if (type(required_roots) is not list or not required_roots
            or any(type(root) is not str for root in required_roots)
            or len(set(required_roots)) != len(required_roots) or TARGET not in required_roots):
        raise ValueError("invalid trusted theorem-root inventory")
    if not audit(info, required_roots):
        raise ValueError("proof export axiom/unsafe/target audit failed")
    names = info.pop("name_table")
    target_index = next(i for i, row in enumerate(rows)
                        if "thm" in row and names[row["thm"]["name"]] == TARGET)
    # A closed Sort 0 has no free universe parameters. Choosing the first Sort
    # arbitrarily can test an undefined-universe error rather than this intended
    # wrong-proof-type control when export root order changes.
    sort_expression = next(row["ie"] for row in rows if row.get("sort") == 0 and "ie" in row)
    bad_rows = list(rows)
    bad_rows[target_index] = {"thm": dict(rows[target_index]["thm"], value=sort_expression)}
    bad_export = output / "corrupted-proof.ndjson"
    bad_export.write_text("".join(json.dumps(row, separators=(",", ":")) + "\n" for row in bad_rows))

    # An added unsupported axiom must fail the independent whitelist, even if
    # a general-purpose type checker allows users to state their own axioms.
    axiom_info = dict(info, axioms=info["axioms"] + ["CausalFill.UnapprovedAssumption"])
    injected_axiom_rejected = not audit(axiom_info, required_roots)
    omitted_root_info = dict(info, selected_declarations={name: kind for name, kind in
                            info["selected_declarations"].items() if name != required_roots[-1]})
    omitted_required_root_rejected = not audit(omitted_root_info, required_roots)
    specs = {
        "lean_default": ("leanchecker", ["--from-export"]),
        "lean_hardened": ("leanchecker-paranoid", ["--from-export"]),
        "lean4lean": ("lean4lean", ["--import"]),
        "nanoda": ("nanoda_bin", []),
        "con_ron": ("con-ron", []),
        "con_leche": ("con-leche", []),
    }

    def run(name, variant, path):
        binary, prefix = specs[name]
        argument = path
        if name == "nanoda":
            argument = output / f"nanoda-{variant}.json"
            argument.write_text(json.dumps({
                "use_stdin": False, "export_file_path": str(path),
                "permitted_axioms": sorted(STANDARD_AXIOMS),
                "unpermitted_axiom_hard_error": True, "num_threads": 2,
                "nat_extension": True, "string_extension": True,
            }, indent=2) + "\n")
        command = [str(toolchain / "bin" / binary), *prefix, str(argument)]
        started = time.monotonic()
        try:
            completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       text=True, timeout=args.timeout, check=False)
            exit_code, log = completed.returncode, completed.stdout
        except subprocess.TimeoutExpired as exc:
            exit_code = None
            log = "CHECKER TIMEOUT\n" + str(exc.stdout or "")
        log_path = output / f"{name}-{variant}.txt"
        log_path.write_text(log)
        diagnostic = ("assertion failed: self.def_eq(u, v)" in log if name == "nanoda"
                      else "type mismatch" in log and TARGET in log)
        return {"checker": name, "variant": variant, "command": command,
                "binary_sha256": sha(command[0]), "input_sha256": sha(path),
                "exit_code": exit_code, "seconds": time.monotonic() - started,
                "log": log_path.name, "log_sha256": sha(log_path),
                "expected_type_failure_diagnostic": diagnostic if variant == "corrupted" else None,
                "expected_verdict_met": (exit_code == 0 if variant == "valid" else
                                         exit_code is not None and exit_code > 0 and diagnostic)}

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(run, name, variant, path)
                   for name in specs for variant, path in (("valid", export), ("corrupted", bad_export))]
        commands = [future.result() for future in futures]
    result = {
        "schema": "causalfill.independent-kernel-replay.v1",
        "status": "passed" if injected_axiom_rejected and omitted_required_root_rejected
                    and all(c["expected_verdict_met"] for c in commands) else "failed",
        "finished_utc": datetime.now(timezone.utc).isoformat(), "export": str(export),
        "export_sha256": sha(export), "export_bytes": export.stat().st_size,
        "export_metadata": rows[0], "declaration_inventory": info,
        "standard_axiom_whitelist": sorted(STANDARD_AXIOMS),
        "required_theorem_roots": required_roots,
        "required_roots_sha256": sha(args.roots),
        "all_required_roots_present_as_theorems": True,
        "injected_axiom_inventory_rejected": injected_axiom_rejected,
        "omitted_required_root_rejected": omitted_required_root_rejected,
        "negative_control": {"target": TARGET, "mutation": "replace proof term by a universe expression",
                             "input_sha256": sha(bad_export)},
        "commands": commands,
        "source_sha256": {"formal/check_export_kernels.py": sha(__file__)},
        "limitations": ["Six configurations include Lean's own checker, its hardened variant, and four bundled external checkers; they are not six wholly independent software stacks.",
                        "Some external checkers use exception/panic diagnostics for type failures. A timeout or signal exit alone does not count as the expected negative-control rejection.",
                        "Invoked directly over a plain export. No claim that Lake's build sandbox or --paranoid orchestration ran on this host.",
                        "Kernel replay validates declarations in the export; Python-to-arena refinement and real robot execution are outside its statement."]}
    (output / "results.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"status": result["status"], "axioms": info["axioms"],
                      "valid_checks": sum(c["exit_code"] == 0 for c in commands if c["variant"] == "valid"),
                      "corrupted_rejections": sum(c["expected_verdict_met"] for c in commands if c["variant"] == "corrupted")}, indent=2))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
