#!/usr/bin/env python3
"""Reproducible noisy-decision certificate stress; scripted engineering checks."""
from __future__ import annotations
import argparse
import copy
import hashlib
import itertools
import json
from pathlib import Path
import random
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from causalfill.decision_sufficiency import (SCHEMA, build_certificate, demo_problem,
    replay_certificate, verify_certificate)
from causalfill.runner import source_fingerprint, write_json


def fixed_queries_oracle(model, objective="action"):
    """Enumerate subsets and raw observation tuples, without Bellman recursion.

    Sensing is fixed in advance, but the final action can depend on all observed
    values. This is a stronger comparison than a single fixed terminal action.
    """
    worlds, qs = model["worlds"], model["experiments"]
    best = None
    for bits in itertools.product((False, True), repeat=len(qs)):
        chosen = [q for bit, q in zip(bits, qs) if bit]
        alphabets = [sorted({o for row in q["supports"].values() for o in row}) for q in chosen]
        worst = 0
        possible = True
        for observations in itertools.product(*alphabets):
            belief = {w for w in worlds if all(o in q["supports"][w] for q, o in zip(chosen, observations))}
            if not belief:
                continue
            if objective == "identification":
                if len(belief) != 1:
                    possible = False
                    break
            else:
                choices = [a["cost"] for a in model["actions"] if belief <= set(a["success_worlds"])]
                if not choices:
                    possible = False
                    break
                worst = max(worst, min(choices))
        if possible:
            cost = sum(q["cost"] for q in chosen) + worst
            if best is None or cost < best:
                best = cost
    return best


def generated_problem(seed):
    rng = random.Random(seed)
    worlds = [f"w{i}" for i in range(rng.randint(2, 7))]
    actions = [{"id": f"a{j}", "cost": rng.randint(0, 5),
                "success_worlds": [w for w in worlds if rng.random() < .55]}
               for j in range(rng.randint(2, 6))]
    qs = []
    for qi in range(rng.randint(1, 4)):
        alphabet = [f"z{k}" for k in range(rng.randint(2, 3))]
        supports = {}
        for w in worlds:
            supports[w] = sorted(rng.sample(alphabet, rng.randint(1, min(2, len(alphabet)))))
        qs.append({"id": f"q{qi}", "cost": rng.randint(1, 5), "supports": supports})
    return {"schema": SCHEMA, "worlds": worlds, "actions": actions, "experiments": qs}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=int, default=256)
    parser.add_argument("--seed-start", type=int, default=42000)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if not 1 <= args.cases <= 10000 or args.output.exists():
        parser.error("cases must be 1..10000 and output must not exist")
    started = time.monotonic()
    counts = {"models": 0, "certificates": 0, "certificate_states": 0,
              "fixed_query_comparisons": 0, "supported_policy_leaves": 0,
              "metamorphic_comparisons": 0, "forged_certificates_rejected": 0}
    failures, rows = [], []

    def require(condition, label, case):
        if not condition:
            failures.append({"case": case, "label": label})

    for seed in range(args.seed_start, args.seed_start + args.cases):
        model = generated_problem(seed)
        counts["models"] += 1
        for objective in ("action", "identification"):
            cert = build_certificate(model, objective)
            checked = verify_certificate(model, cert)
            counts["certificates"] += 1
            counts["certificate_states"] += len(cert["nodes"])
            require(checked["valid"], "valid certificate rejected", seed)
            if cert["value"] is not None:
                replay = replay_certificate(model, cert)
                require(replay["valid"], "attaining policy replay", seed)
                counts["supported_policy_leaves"] += replay.get("supported_policy_leaves", 0)
            fixed = fixed_queries_oracle(model, objective)
            require(fixed is None or (cert["value"] is not None and cert["value"] <= fixed),
                    "adaptive no worse than fixed sensing", seed)
            require((fixed is None) == (cert["value"] is None),
                    "finite static-support feasibility agrees with full fixed sensing", seed)
            counts["fixed_query_comparisons"] += 1
            rows.append({"seed": seed, "objective": objective, "adaptive_cost": cert["value"],
                         "fixed_sensing_cost": fixed, "states": len(cert["nodes"])})
            scaled = copy.deepcopy(model)
            for entry in scaled["actions"] + scaled["experiments"]:
                entry["cost"] *= 3
            expected = None if cert["value"] is None else 3 * cert["value"]
            require(build_certificate(scaled, objective)["value"] == expected, "cost scaling", seed)
            counts["metamorphic_comparisons"] += 1
            reordered = copy.deepcopy(model)
            for key in ("worlds", "actions", "experiments"):
                reordered[key].reverse()
            require(build_certificate(reordered, objective)["value"] == cert["value"], "ordering invariance", seed)
            counts["metamorphic_comparisons"] += 1
            precise = copy.deepcopy(model)
            for q in precise["experiments"]:
                q["supports"] = {w: obs[:1] for w, obs in q["supports"].items()}
            pv = build_certificate(precise, objective)["value"]
            require(cert["value"] is None or (pv is not None and pv <= cert["value"]),
                    "reducing uncertainty cannot worsen robust optimum", seed)
            counts["metamorphic_comparisons"] += 1
            for mutation in ("digest", "value", "root", "missing", "duplicate", "boolean"):
                forged = copy.deepcopy(cert)
                if mutation == "digest": forged["problem_sha256"] = "f" * 64
                elif mutation == "value": forged["value"] = 0 if cert["value"] != 0 else 1
                elif mutation == "root": forged["root"][0] = 0
                elif mutation == "missing": forged["nodes"].pop()
                elif mutation == "duplicate": forged["nodes"].append(copy.deepcopy(forged["nodes"][0]))
                elif mutation == "boolean": forged["nodes"][0][0] = True
                rejected = not verify_certificate(model, forged)["valid"]
                require(rejected, "forgery accepted: " + mutation, seed)
                counts["forged_certificates_rejected"] += int(rejected)
        robust = copy.deepcopy(model)
        robust["actions"].append({"id": "guaranteed_bypass", "cost": 2, "success_worlds": model["worlds"]})
        require(build_certificate(robust)["value"] <= 2, "robust alternative upper bound", seed)
        counts["metamorphic_comparisons"] += 1

    examples = {}
    example_dir = args.output.parent / "decision-certificates"
    example_dir.mkdir(parents=True, exist_ok=True)
    for name in ("decision", "robust", "ambiguous", "noisy_resolvable", "adaptive", "action_ambiguity"):
        model = demo_problem(name)
        examples[name] = {}
        for objective in ("action", "identification"):
            cert = build_certificate(model, objective)
            checked = verify_certificate(model, cert)
            examples[name][objective] = {"adaptive_cost": cert["value"],
                "fixed_sensing_cost": fixed_queries_oracle(model, objective), "check": checked,
                "replay": replay_certificate(model, cert) if cert["value"] is not None else None}
            write_json(example_dir / f"{name}-{objective}.json", {"problem": model, "certificate": cert})
    report = {"schema": "causalfill.decision-stress.v05", "passed": not failures,
        "counts": counts, "failures": failures, "examples": examples,
        "records": rows, "elapsed_seconds": round(time.monotonic()-started, 3),
        "source_fingerprint": source_fingerprint(),
        "command": " ".join(sys.argv),
        "scope": "Finite correlated engineering checks; scripted models, not LLM episodes or physical experiments.",
        "limits": ["A known finite support table is assumed; calibration validity is not inferred.",
                   "Experiments are non-destructive and usable once; no contact-dynamics refinement is proved.",
                   "Independent fixed-subset enumeration is not independent adaptive policy enumeration."]}
    write_json(args.output, report)
    print(json.dumps({k: report[k] for k in ("passed", "counts", "failures", "elapsed_seconds")}, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
