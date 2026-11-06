"""Offline certificate verification, without task generation or proof search.

The expected statement digest must come from the trusted evaluator or another
trusted channel. Checking a digest supplied only by a claimant cannot establish
that the claimant proved the intended theorem.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from .logic_kernel import statement_digest, verify_model, verify_resolution


def verify_statement_proof(statement, fill, expected_sha256):
    """Check entailment and non-vacuity against an externally pinned statement."""
    try:
        if (type(expected_sha256) is not str or
                re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None):
            raise ValueError("expected_sha256 must be a trusted lowercase SHA256 digest")
        if type(statement) is not dict or set(statement) != {
                "nvars", "clauses", "goal", "statement_sha256"}:
            raise ValueError("statement fields do not match the formal schema")
        if type(fill) is not dict or set(fill) != {
                "statement_sha256", "proof_steps", "consistency_model"}:
            raise ValueError("fill fields do not match the certificate schema")
        digest = statement_digest(statement["clauses"], statement["nvars"], statement["goal"])
        bound = digest == expected_sha256 == statement["statement_sha256"] == fill["statement_sha256"]
        if not bound:
            raise ValueError("statement or certificate does not match the trusted digest")
        result = verify_resolution(statement["clauses"] + [[-statement["goal"]]],
                                   fill["proof_steps"], statement["nvars"])
        consistent = verify_model(statement["clauses"], fill["consistency_model"], statement["nvars"])
        proved = bool(result["valid"] and result["derived_empty"])
        return {"success": bool(proved and consistent), "statement_bound": True,
                "conclusion_proved": proved, "premises_consistent": consistent,
                "checked_steps": result["checked_steps"], "error": result["error"],
                "scope": "finite-propositional-resolution; Python checker"}
    except (ValueError, TypeError, KeyError, OverflowError) as exc:
        return {"success": False, "statement_bound": False, "error": str(exc)[:240]}


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError("nonfinite JSON constant")


def _read_json(path):
    # This verifier reads only the two explicit user-supplied paths.
    with Path(path).open("rb") as handle:
        raw = handle.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError("certificate or statement file exceeds 1 MiB")
    return json.loads(raw, object_pairs_hook=_unique_pairs, parse_constant=_reject_constant)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("statement", help="Trusted public statement JSON")
    parser.add_argument("fill", help="Certificate fill JSON, without a tool-call envelope")
    parser.add_argument("--expected-sha256", required=True, help="Digest from a trusted channel")
    args = parser.parse_args(argv)
    try:
        result = verify_statement_proof(_read_json(args.statement), _read_json(args.fill),
                                        args.expected_sha256)
    except (OSError, ValueError, TypeError, RecursionError) as exc:
        result = {"success": False, "error": str(exc)[:240]}
    print(json.dumps(result, sort_keys=True, allow_nan=False))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
