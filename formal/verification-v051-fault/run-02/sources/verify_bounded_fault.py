#!/usr/bin/env python3
"""Check the bounded-fault claims, expected statements, and exported proof terms.

Run against the pinned official Lean 4.35.0 toolchain. The optional embedding
backend uses the unchanged public C ABI host with trust level zero and an
explicit system root. All builds, source snapshots, mutations, and logs stay in
a fresh output directory; earlier release artifacts are never modified.

This gate checks mathematical declarations. It does not prove Python-to-Lean
refinement, the optimizer's exact cost, runtime isolation, or physical sensing.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time


FORMAL = Path(__file__).resolve().parent
ALLOWED_AXIOMS = {"propext", "Classical.choice", "Quot.sound"}
ARCHIVE_SHA256 = "7289597a44543246c9227b8cae501767e095ce17f6d448b95fc4a8dc97268f6d"
ROOT_SUFFIXES = (
    "mismatches_append", "mismatches_step", "realizes_iff_mismatches",
    "feasible_iff_realizes_within", "capped_update_exact", "capped_live_iff",
    "capped_state_step", "true_world_preserved", "excluded_stays_excluded",
    "badReadings_length", "witness_count_le_mismatches", "exclusion_witness_sound",
    "witnesses_certify_action", "safe_action_sound",
)
ROOTS = ["CausalFill.BoundedFault." + name for name in ROOT_SUFFIXES]
TARGET = "CausalFill.BoundedFault.safe_action_sound"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def axiom_inventory(output: str, expected: set[str]) -> dict[str, list[str]]:
    rows = re.findall(
        r"^'([^']+)' (?:depends on axioms: \[([^\]]*)\]|(does not depend on any axioms))$",
        output, re.MULTILINE,
    )
    if len(rows) != len(expected) or {row[0] for row in rows} != expected:
        raise ValueError("axiom inventory names or count differ from the trusted inventory")
    result = {}
    for name, contents, _ in rows:
        axioms = {item.strip() for item in contents.split(",") if item.strip()}
        if axioms - ALLOWED_AXIOMS:
            raise ValueError(f"unapproved axioms for {name}: {sorted(axioms - ALLOWED_AXIOMS)}")
        result[name] = sorted(axioms)
    return result


def export_inventory(rows: list[dict]) -> dict:
    names, declarations, axioms, unsafe = {0: ""}, {}, [], []
    for row in rows:
        if "in" in row:
            part = row.get("str", row.get("num"))
            suffix = str(part.get("str", part.get("i")))
            names[row["in"]] = ".".join(filter(None, (names[part["pre"]], suffix)))
        for kind in ("def", "thm", "axiom", "opaque"):
            if kind not in row:
                continue
            declaration = row[kind]
            name = names[declaration["name"]]
            if name in declarations:
                raise ValueError(f"duplicate exported declaration: {name}")
            declarations[name] = kind
            if kind == "axiom":
                axioms.append(name)
            if declaration.get("isUnsafe", False):
                unsafe.append(name)
    return {
        "names": names, "axioms": sorted(axioms), "unsafe": sorted(unsafe),
        "declarations": declarations, "records": len(rows),
    }


def audit_export(info: dict) -> None:
    if info["unsafe"] or set(info["axioms"]) - ALLOWED_AXIOMS:
        raise ValueError("unsafe declaration or unapproved axiom in export")
    if any(info["declarations"].get(root) != "thm" for root in ROOTS):
        raise ValueError("a required export root is missing or is not a theorem")


def weaken_leaf_statement(source: str, name: str) -> str:
    """Replace a leaf theorem's conclusion/proof by True, keeping its name/args."""
    pattern = re.compile(r"^theorem " + re.escape(name) + r"\b.*?(?=^\S|\Z)", re.M | re.S)
    matches = list(pattern.finditer(source))
    if len(matches) != 1:
        raise ValueError(f"expected one theorem block for mutation: {name}")
    match = matches[0]
    header = match.group().split(":=", 1)[0]
    colon = header.rfind(" :")
    if colon < 0:
        raise ValueError("could not find the theorem conclusion")
    replacement = header[:colon] + " : True := by\n  trivial\n\n"
    return source[:match.start()] + replacement + source[match.end():]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--toolchain", type=Path, required=True)
    parser.add_argument("--toolchain-archive", type=Path)
    parser.add_argument("--backend", choices=("cli", "embedding"), default="cli")
    parser.add_argument("--output", type=Path, default=FORMAL / "verification-v051-fault")
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    output, toolchain = args.output.resolve(), args.toolchain.resolve()
    if output.exists():
        parser.error("output directory must be fresh")
    if args.timeout < 10:
        parser.error("timeout must be at least ten seconds")
    output.mkdir(parents=True)
    sources, build = output / "sources", output / "build"
    (build / "CausalFill").mkdir(parents=True)
    report = {
        "schema": "causalfill.bounded-fault-verification.v1", "status": "running",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "backend": args.backend, "trust_level": 0, "elaboration_async": False,
        "allowed_axioms": sorted(ALLOWED_AXIOMS), "required_roots": ROOTS,
        "commands": [], "axioms": {}, "negative_controls": {},
        "statement_bindings": {}, "kernel_replay": {}, "source_sha256": {},
        "limitations": [
            "Claims concern a fixed world, a truthful binary table, and a single global flip cap.",
            "Runtime one-use query IDs must correspond to distinct accepted transcript occurrences; that representation refinement is not proved here.",
            "The optimizer's Bellman costs, Python/runtime equivalence, physical sensing, and model performance are outside these theorem statements.",
            "Six checker configurations include Lean's checker, its hardened variant, and four bundled external implementations; they are not six wholly independent stacks.",
            "Checkers run directly on a data export; this does not assert that Lake's full paranoid build sandbox ran.",
        ],
    }

    def save() -> None:
        (output / "results.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")

    def run(name: str, command: list[str], *, cwd: Path = sources,
            search: Path = build, success: bool = True, log: Path | None = None) -> str:
        environment = os.environ.copy()
        environment["LEAN_PATH"] = str(search)
        environment["PATH"] = str(toolchain / "bin") + os.pathsep + environment.get("PATH", "")
        destination = log or output / (name + ".log")
        started = time.monotonic()
        with destination.open("w") as target:
            try:
                process = subprocess.run(command, cwd=cwd, env=environment,
                                         text=True, stdout=target, stderr=subprocess.STDOUT,
                                         check=False, timeout=args.timeout)
                code = process.returncode
            except subprocess.TimeoutExpired:
                target.write("\nVERIFIER COMMAND TIMEOUT\n")
                code = None
        text = destination.read_text()
        report["commands"].append({
            "name": name, "command": command, "cwd": str(cwd),
            "lean_path": str(search), "exit_code": code, "expected_success": success,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "log": destination.relative_to(output).as_posix(),
            "log_sha256": sha256(destination),
        })
        save()
        print(f"{name}: exit {code}", flush=True)
        if code is None or code < 0 or (code == 0) != success:
            raise RuntimeError(f"{name}: unexpected verdict; inspect {destination}")
        if success and "declaration uses `sorry`" in text:
            raise RuntimeError(f"{name}: an admitted declaration was reported")
        return text

    def compile_source(name: str, module: str, relative: str, *, source_root: Path = sources,
                       search: Path = build, write_olean: bool = True,
                       success: bool = True, log: Path | None = None) -> str:
        destination = search / (module.replace(".", "/") + ".olean")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if args.backend == "embedding":
            command = [str(host), str(toolchain), module, relative]
            if write_olean:
                command.append(str(destination))
        else:
            command = [str(toolchain / "bin" / "lean"), "--trust=0", "-DElab.async=false"]
            if write_olean:
                command += ["-o", str(destination)]
            command.append(relative)
        return run(name, command, cwd=source_root, search=search,
                   success=success, log=log)

    try:
        tracked = [
            Path(__file__).resolve(), FORMAL / "CausalFill/BoundedFault.lean",
            FORMAL / "BoundedFaultAudit.lean", FORMAL / "BoundedFaultExport.lean",
            FORMAL / "bounded-fault-roots.json", FORMAL / "lean-toolchain",
            FORMAL / "embedding/lean_frontend.c", FORMAL / "embedding/Smoke.lean",
        ]
        for path in tracked:
            relative = path.relative_to(FORMAL)
            destination = sources / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
            report["source_sha256"][relative.as_posix()] = sha256(path)
        if json.loads((sources / "bounded-fault-roots.json").read_text()) != ROOTS:
            raise ValueError("root manifest differs from verifier's fixed inventory")
        audit_text = (sources / "BoundedFaultAudit.lean").read_text()
        printed = re.findall(r"^#print axioms (\S+)$", audit_text, re.M)
        if printed != ROOTS:
            raise ValueError("audit source differs from the fixed root inventory")
        if len(re.findall(r"^example\b", audit_text, re.M)) != len(ROOTS):
            raise ValueError("expected one explicit type binding per theorem root")
        header = toolchain / "include/lean/version.h"
        version = re.search(r'#define LEAN_VERSION_STRING "([^"]+)"', header.read_text())
        if version is None or version[1] != "4.35.0":
            raise ValueError("official Lean 4.35.0 headers are required")
        report["toolchain_version"] = version[1]
        report["toolchain_files_sha256"] = {
            "include/lean/version.h": sha256(header),
            "lib/lean/libleanshared.so": sha256(toolchain / "lib/lean/libleanshared.so"),
        }
        if args.toolchain_archive:
            if sha256(args.toolchain_archive) != ARCHIVE_SHA256:
                raise ValueError("toolchain archive does not match the pinned official hash")
            report["verified_toolchain_archive_sha256"] = ARCHIVE_SHA256
        if args.backend == "embedding":
            host = output / "lean_frontend"
            run("build-host", [
                "cc", "-std=c11", "-D_POSIX_C_SOURCE=200809L", "-Wall", "-Wextra", "-Werror",
                "-I", str(toolchain / "include"), str(sources / "embedding/lean_frontend.c"),
                "-L", str(toolchain / "lib/lean"), "-Wl,-rpath," + str(toolchain / "lib/lean"),
                "-lleanshared", "-o", str(host),
            ])
            report["embedding_host_sha256"] = sha256(host)
        smoke = compile_source("smoke", "EmbeddingSmoke", "embedding/Smoke.lean")
        if '"4.35.0"' not in smoke:
            raise ValueError("loaded Lean runtime did not report version 4.35.0")
        report["smoke_axioms"] = axiom_inventory(smoke, {"embedding_smoke"})

        compile_source("bounded-fault", "CausalFill.BoundedFault", "CausalFill/BoundedFault.lean")
        audited = compile_source("audit", "BoundedFaultAudit", "BoundedFaultAudit.lean")
        report["axioms"] = axiom_inventory(audited, set(ROOTS))
        report["statement_bindings"]["all_root_types_checked"] = True

        controls = output / "controls"
        controls.mkdir()
        prefix = "import CausalFill.BoundedFault\nopen CausalFill.BoundedFault\n"
        positive = prefix + """
def fixtureTruth : Unit → Unit → Bool := fun _ _ => false
example : Feasible fixtureTruth 1 [((), true)] () := by unfold Feasible; decide
example : ¬ Feasible fixtureTruth 0 [((), true)] () := by unfold Feasible; decide
example : ¬ ([((), true), ((), true)] : List (Reading Unit)).Sublist
    (badReadings fixtureTruth () [((), true)]) := by decide
example : capped 1 3 = 2 := by decide
example : capped 1 (capped 1 3 + 0) = 2 := by decide
"""
        (controls / "PositiveBoundaries.lean").write_text(positive)
        compile_source("positive-boundaries", "PositiveBoundaries", "PositiveBoundaries.lean",
                       source_root=controls, write_olean=False)
        bad_sources = {
            "FalseTheorem": prefix + "example : False := by exact True.intro\n",
            "DuplicateOccurrence": prefix + """
def fixtureTruth : Unit → Unit → Bool := fun _ _ => false
example : ([((), true), ((), true)] : List (Reading Unit)).Sublist
    (badReadings fixtureTruth () [((), true)]) := by decide
""",
            "InsufficientContradictions": prefix + """
def fixtureTruth : Unit → Unit → Bool := fun _ _ => false
example : ¬ Feasible fixtureTruth 1 [((), true)] () := by unfold Feasible; decide
""",
            "DebtResurrection": prefix + "example : capped 1 (capped 1 3 + 0) ≤ 1 := by decide\n",
            "PerQueryReset": prefix + """
def fixtureTruth : Unit → Unit → Bool := fun _ _ => false
example : Feasible fixtureTruth 1 [((), true), ((), true)] () := by unfold Feasible; decide
""",
        }
        for module, text in bad_sources.items():
            (controls / (module + ".lean")).write_text(text)
            rejected = compile_source("negative-" + module, module, module + ".lean",
                                      source_root=controls, write_olean=False, success=False)
            diagnostic = ("type mismatch" in rejected.lower() if module == "FalseTheorem"
                          else "decide" in rejected and "false" in rejected.lower())
            if not diagnostic:
                raise RuntimeError(f"{module}: rejection did not have the intended diagnostic")
            report["negative_controls"][module] = {
                "rejected": True, "intended_diagnostic": True,
                "source_sha256": sha256(controls / (module + ".lean")),
            }

        axiom_source = prefix + """
axiom CausalFill.BoundedFault.UnapprovedAssumption : False
theorem CausalFill.BoundedFault.UnapprovedClaim : False :=
  CausalFill.BoundedFault.UnapprovedAssumption
#print axioms CausalFill.BoundedFault.UnapprovedClaim
"""
        (controls / "AxiomInjection.lean").write_text(axiom_source)
        axiom_output = compile_source("axiom-injection", "AxiomInjection", "AxiomInjection.lean",
                                      source_root=controls, write_olean=False)
        try:
            axiom_inventory(axiom_output, {"CausalFill.BoundedFault.UnapprovedClaim"})
        except ValueError as error:
            if "unapproved axioms" not in str(error):
                raise
            report["negative_controls"]["custom_axiom_inventory"] = {
                "compiled": True, "whitelist_rejected": True, "diagnostic": str(error),
            }
        else:
            raise RuntimeError("custom axiom was not rejected by the whitelist")

        original = (sources / "CausalFill/BoundedFault.lean").read_text()
        for leaf in ("capped_live_iff", "safe_action_sound"):
            mutant_sources = controls / ("weakened-" + leaf) / "sources"
            mutant_build = controls / ("weakened-" + leaf) / "build"
            (mutant_sources / "CausalFill").mkdir(parents=True)
            (mutant_build / "CausalFill").mkdir(parents=True)
            mutant = mutant_sources / "CausalFill/BoundedFault.lean"
            mutant.write_text(weaken_leaf_statement(original, leaf))
            shutil.copy2(sources / "BoundedFaultAudit.lean", mutant_sources / "BoundedFaultAudit.lean")
            compile_source("weakened-" + leaf, "CausalFill.BoundedFault", "CausalFill/BoundedFault.lean",
                           source_root=mutant_sources, search=mutant_build)
            rejected = compile_source("binding-rejects-" + leaf, "BoundedFaultAudit", "BoundedFaultAudit.lean",
                                      source_root=mutant_sources, search=mutant_build,
                                      write_olean=False, success=False)
            if "type mismatch" not in rejected.lower() or leaf not in rejected:
                raise RuntimeError(f"{leaf}: wrong-statement audit lacked its expected type diagnostic")
            report["statement_bindings"][leaf] = {
                "weakened_statement_compiles": True, "unchanged_expected_type_audit_rejects": True,
                "mutation": "retain name and parameters; replace conclusion/proof by True",
                "mutant_source_sha256": sha256(mutant),
                "unchanged_audit_sha256": sha256(mutant_sources / "BoundedFaultAudit.lean"),
            }

        export = output / "bounded-fault.ndjson"
        compile_source("export", "BoundedFaultExport", "BoundedFaultExport.lean",
                       write_olean=False, log=export)
        rows = [json.loads(line) for line in export.read_text().splitlines()]
        info = export_inventory(rows)
        audit_export(info)
        report["export"] = {
            "sha256": sha256(export), "bytes": export.stat().st_size, "metadata": rows[0],
            "records": info["records"], "axioms": info["axioms"],
            "unsafe_declarations": info["unsafe"],
            "declaration_count": len(info["declarations"]),
            "selected_declarations": {name: kind for name, kind in sorted(info["declarations"].items())
                                      if name.startswith("CausalFill.BoundedFault.")},
        }
        omitted = dict(info, declarations={key: value for key, value in info["declarations"].items()
                                          if key != ROOTS[-1]})
        try:
            audit_export(omitted)
        except ValueError:
            report["negative_controls"]["omitted_required_export_root"] = {"rejected": True}
        else:
            raise RuntimeError("omitted export root was accepted")

        target_row = next(index for index, row in enumerate(rows)
                          if "thm" in row and info["names"][row["thm"]["name"]] == TARGET)
        sort_zero = next(row["ie"] for row in rows if row.get("sort") == 0 and "ie" in row)
        corrupted = list(rows)
        corrupted[target_row] = {"thm": dict(rows[target_row]["thm"], value=sort_zero)}
        bad_export = output / "corrupted-proof.ndjson"
        bad_export.write_text("".join(json.dumps(row, separators=(",", ":")) + "\n" for row in corrupted))
        specs = {
            "lean_default": ("leanchecker", ["--from-export"]),
            "lean_hardened": ("leanchecker-paranoid", ["--from-export"]),
            "lean4lean": ("lean4lean", ["--import"]),
            "nanoda": ("nanoda_bin", []), "con_ron": ("con-ron", []),
            "con_leche": ("con-leche", []),
        }
        kernel_directory = output / "kernels"
        kernel_directory.mkdir()

        def replay(checker: str, variant: str, path: Path) -> dict:
            binary, flags = specs[checker]
            argument = path
            if checker == "nanoda":
                argument = kernel_directory / (checker + "-" + variant + ".json")
                argument.write_text(json.dumps({
                    "use_stdin": False, "export_file_path": str(path),
                    "permitted_axioms": sorted(ALLOWED_AXIOMS), "unpermitted_axiom_hard_error": True,
                    "num_threads": 2, "nat_extension": True, "string_extension": True,
                }, indent=2) + "\n")
            command = [str(toolchain / "bin" / binary), *flags, str(argument)]
            started = time.monotonic()
            try:
                completed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                           text=True, check=False, timeout=args.timeout)
                code, log = completed.returncode, completed.stdout
            except subprocess.TimeoutExpired as error:
                code, log = None, "CHECKER TIMEOUT\n" + str(error.stdout or "")
            log_path = kernel_directory / (checker + "-" + variant + ".log")
            log_path.write_text(log)
            type_diagnostic = ("assertion failed: self.def_eq(u, v)" in log if checker == "nanoda"
                               else "type mismatch" in log.lower() and TARGET in log)
            return {
                "checker": checker, "variant": variant, "command": command, "exit_code": code,
                "seconds": round(time.monotonic() - started, 3), "binary_sha256": sha256(Path(command[0])),
                "input_sha256": sha256(path), "log": log_path.relative_to(output).as_posix(),
                "log_sha256": sha256(log_path),
                "intended_type_failure": type_diagnostic if variant == "corrupted" else None,
                "expected_verdict_met": code == 0 if variant == "valid" else
                    code is not None and code > 0 and type_diagnostic,
            }

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(replay, checker, variant, path)
                       for checker in specs for variant, path in (("valid", export), ("corrupted", bad_export))]
            verdicts = [future.result() for future in futures]
        report["kernel_replay"] = {
            "commands": verdicts, "proof_mutation_target": TARGET,
            "proof_mutation": "replace target proof term by closed Sort 0",
            "corrupted_export_sha256": sha256(bad_export),
            "valid_acceptances": sum(item["expected_verdict_met"] for item in verdicts if item["variant"] == "valid"),
            "intended_corruption_rejections": sum(item["expected_verdict_met"] for item in verdicts if item["variant"] == "corrupted"),
        }
        if not all(item["expected_verdict_met"] for item in verdicts):
            raise RuntimeError("one or more exported-proof checker controls failed")
        for relative, expected in report["source_sha256"].items():
            if sha256(FORMAL / relative) != expected or sha256(sources / relative) != expected:
                raise RuntimeError("verification source changed during run: " + relative)
        report["status"] = "passed"
        return 0
    except Exception as error:
        report["status"] = "failed"
        report["error"] = str(error)
        raise
    finally:
        report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        save()


if __name__ == "__main__":
    raise SystemExit(main())
