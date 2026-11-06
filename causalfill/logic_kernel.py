"""A bounded, standalone checker for finite propositional certificates.

The trusted logic is the usual binary resolution rule. A clause is a disjunction
of signed, one-based variable indices; a CNF is a conjunction of clauses. Proof
steps contain only [left_index, right_index, positive_pivot]. They cannot add
premises or provide a claimed resolvent. The checker computes each resolvent.

This module imports neither task generators nor proof search. Its checks are
ordinary Python computation, not a Lean formalization or a new logical axiom.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

MAX_VARIABLES = 200
MAX_INITIAL_CLAUSES = 2000
MAX_PROOF_STEPS = 12000
MAX_LITERAL_ENTRIES = 500000
STATEMENT_SCHEMA = "causalfill.propositional-statement.v1"


def _integer(value: Any, low: int, high: int, label: str) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{label} must be an integer in [{low}, {high}]")
    return value


def normalize_cnf(clauses: Any, nvars: int) -> list[tuple[int, ...]]:
    """Validate and canonicalize clauses without changing clause indices.

    The outer container must be a list. Each clause may be a list or tuple;
    repeated literals are removed, and literals are numerically sorted.
    Duplicate clauses and their order are preserved. Empty and tautological
    clauses are permitted: they have their ordinary propositional meanings.
    Raw clause length is bounded by 2*nvars, even when duplicates are present.
    """
    _integer(nvars, 1, MAX_VARIABLES, "nvars")
    if type(clauses) is not list or len(clauses) > MAX_INITIAL_CLAUSES:
        raise ValueError(f"clauses must be a list of at most {MAX_INITIAL_CLAUSES} clauses")
    normalized = []
    entries = 0
    for clause in clauses:
        if type(clause) not in (list, tuple) or len(clause) > 2*nvars:
            raise ValueError("each clause must be a bounded list or tuple of literals")
        for literal in clause:
            if type(literal) is not int or literal == 0 or abs(literal) > nvars:
                raise ValueError("literals must be nonzero integers with absolute value <= nvars")
        current = tuple(sorted(set(clause)))
        entries += len(current)
        if entries > MAX_LITERAL_ENTRIES:
            raise ValueError("CNF exceeds literal-storage limit")
        normalized.append(current)
    return normalized


def verify_resolution(
    clauses: Any, steps: Any, nvars: int, max_steps: int = MAX_PROOF_STEPS
) -> dict[str, Any]:
    """Check a complete supplied derivation; never search for a proof.

    ``valid`` means every supplied step is a well-formed resolution inference.
    ``derived_empty`` additionally means the last derived clause is empty. A
    valid non-refuting derivation is therefore not a proof of contradiction.
    With no steps, an existing empty premise is sufficient to report a
    contradiction. A task proving entailment should separately require a model
    of its original, un-negated premises to prevent vacuous entailment.

    Invalid input returns ``valid=False`` and a bounded diagnostic. No malformed
    certificate is partially accepted, even if its valid prefix reached empty.
    """
    checked = 0
    final: tuple[int, ...] = ()
    try:
        _integer(max_steps, 0, MAX_PROOF_STEPS, "max_steps")
        known = normalize_cnf(clauses, nvars)
        if type(steps) is not list or len(steps) > max_steps:
            raise ValueError(f"steps must be a list of at most {max_steps} triples")
        literal_entries = sum(map(len, known))
        if known:
            final = known[-1]
        for number, step in enumerate(steps):
            if type(step) not in (list, tuple) or len(step) != 3:
                raise ValueError(f"step {number}: expected a triple")
            left_index, right_index, pivot = step
            # Every parent must already exist. A zero-sized pool admits no refs.
            if (type(left_index) is not int or type(right_index) is not int or
                    not 0 <= left_index < len(known) or
                    not 0 <= right_index < len(known)):
                raise ValueError(f"step {number}: parent is not an earlier clause")
            _integer(pivot, 1, nvars, f"step {number} pivot")
            left, right = set(known[left_index]), set(known[right_index])
            if pivot in left and -pivot in right:
                # Remove only the selected occurrence from EACH parent. Removing
                # both signs after union would be unsound for tautological clauses.
                resolvent = (left - {pivot}) | (right - {-pivot})
            elif -pivot in left and pivot in right:
                resolvent = (left - {-pivot}) | (right - {pivot})
            else:
                raise ValueError(f"step {number}: parents lack opposite pivot literals")
            final = tuple(sorted(resolvent))
            literal_entries += len(final)
            if literal_entries > MAX_LITERAL_ENTRIES:
                raise ValueError("proof exceeds literal-storage limit")
            known.append(final)
            checked += 1
        # This special case describes a contradiction already in the premises,
        # not a license to invent an empty clause in the proof.
        initial_empty = not steps and any(not clause for clause in known)
        if initial_empty:
            final = ()
        return {
            "valid": True,
            "derived_empty": bool(initial_empty or (steps and not final)),
            "checked_steps": checked,
            "final_clause": list(final),
            "error": None,
        }
    except (ValueError, TypeError, OverflowError) as exc:
        return {
            "valid": False,
            "derived_empty": False,
            "checked_steps": checked,
            "final_clause": list(final),
            "error": str(exc)[:240],
        }


def verify_model(clauses: Any, assignment: Any, nvars: int) -> bool:
    """Check a total Boolean model of the stated CNF; malformed input fails."""
    try:
        known = normalize_cnf(clauses, nvars)
        if (type(assignment) is not list or len(assignment) != nvars or
                any(type(value) is not bool for value in assignment)):
            return False
        return all(any(assignment[abs(literal)-1] == (literal > 0)
                       for literal in clause) for clause in known)
    except (ValueError, TypeError, OverflowError):
        return False


def statement_digest(clauses: Any, nvars: int, goal: int) -> str:
    """Commit to the canonical premises, variable domain and signed goal.

    Clause ordering is retained because proof indices refer to that ordering.
    This is a content commitment, not a digital signature or proof of truth.
    """
    normalized = normalize_cnf(clauses, nvars)
    if type(goal) is not int or goal == 0 or abs(goal) > nvars:
        raise ValueError("goal must be a nonzero literal within the variable domain")
    payload = {"schema": STATEMENT_SCHEMA, "nvars": nvars,
               "clauses": normalized, "goal": goal}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                         allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
