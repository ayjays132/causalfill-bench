#!/usr/bin/env python3
"""Independent, deterministic evaluator audit; never a scored solver run.

Run from any directory with Python 3.10+; no third-party package is required::

    python tools/stress_formal.py --output reports/stress-v0.3/formal-results.json

The resolution oracle is exhaustive Boolean truth semantics.  The diagnosis
oracle enumerates *complete policies* and simulates response rows through them;
it does not reimplement the production minimax/Bellman recurrence.  Constructed
proofs do not use ``proof_search``.  Both valid alternatives and invalid attacks
are tested, so a reject-everything checker cannot pass this audit.

This is finite executable testing, not a formal proof of Python, SHA256,
the parser, arbitrary formulas, or arbitrary experimental environments.
"""
from __future__ import annotations

import argparse
import copy
from collections import Counter
from datetime import datetime, timezone
import hashlib
import itertools
import json
from pathlib import Path
import platform
import random
import sys
import time
from typing import Any, Callable
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from causalfill.decision_certificates import (  # noqa: E402
    build_decision_certificate, elimination_certificate, extract_decision_tree,
    table_digest, verify_decision_certificate, verify_decision_tree,
)
from causalfill.domains.diagnosis import DiagnosisTask  # noqa: E402
from causalfill.domains.proof import ProofTask  # noqa: E402
from causalfill.logic_kernel import (  # noqa: E402
    MAX_INITIAL_CLAUSES, MAX_LITERAL_ENTRIES, MAX_PROOF_STEPS,
    statement_digest, verify_model, verify_resolution,
)

SEED = 2026110103
SOURCE_FILES = (
    "causalfill/logic_kernel.py", "causalfill/decision_certificates.py",
    "causalfill/domains/proof.py", "causalfill/domains/diagnosis.py",
    "causalfill/types.py", "tools/stress_formal.py",
)


class Audit:
    """Count verdicts separately from semantic/integrity assertions."""

    def __init__(self) -> None:
        self.sections: dict[str, Counter] = {}
        self.failures: list[dict] = []
        self.transcript = hashlib.sha256()
        self.measurements: dict[str, Any] = {}

    def _record(self, section: str, kind: str, expected: bool, actual: bool,
                case: Any, detail: Any = None) -> None:
        counts = self.sections.setdefault(section, Counter())
        counts["checks"] += 1
        counts[kind + "_checks"] += 1
        if kind == "acceptance":
            counts["expected_accepts" if expected else "expected_rejects"] += 1
            counts["observed_accepts" if actual else "observed_rejects"] += 1
        if expected != actual:
            key = ("false_accepts" if actual else "false_rejects") if kind == "acceptance" else "invariant_failures"
            counts[key] += 1
            if len(self.failures) < 100:
                self.failures.append({"section": section, "kind": key, "case": case,
                                      "expected": expected, "actual": actual, "detail": detail})
        event = [section, kind, expected, actual, case]
        self.transcript.update(json.dumps(event, separators=(",", ":"), sort_keys=True).encode())
        self.transcript.update(b"\n")

    def expect(self, section: str, expected: bool, function: Callable[[], Any],
               case: Any, selector: Callable[[Any], bool] = bool) -> Any:
        try:
            result = function()
            self._record(section, "acceptance", expected, bool(selector(result)), case,
                         repr(result)[:500])
            return result
        except Exception as exc:  # Audit exceptions are findings, not crashes.
            counts = self.sections.setdefault(section, Counter())
            counts["checks"] += 1
            counts["acceptance_checks"] += 1
            counts["expected_accepts" if expected else "expected_rejects"] += 1
            counts["exceptions"] += 1
            record = {"section": section, "kind": "exception", "case": case,
                      "exception": type(exc).__name__, "detail": str(exc)[:500]}
            if len(self.failures) < 100:
                self.failures.append(record)
            self.transcript.update(json.dumps(record, sort_keys=True).encode())
            return None

    def invariant(self, section: str, condition: bool, case: Any, detail: Any = None) -> None:
        self._record(section, "invariant", True, bool(condition), case, detail)

    def raises(self, section: str, function: Callable[[], Any], case: Any,
               exception_type: type[Exception] = ValueError) -> None:
        def rejected() -> bool:
            try:
                function()
            except exception_type:
                return True
            return False
        self.expect(section, True, rejected, case)

    def report(self) -> dict:
        keys = ("checks", "acceptance_checks", "invariant_checks", "expected_accepts",
                "expected_rejects", "observed_accepts", "observed_rejects",
                "false_accepts", "false_rejects", "invariant_failures", "exceptions")
        sections = {section: {key: counter[key] for key in keys}
                    for section, counter in self.sections.items()}
        totals = {key: sum(values[key] for values in sections.values()) for key in keys}
        return {"sections": sections, "totals": totals, "failures": self.failures,
                "failure_examples_cap": 100, "measurements": self.measurements,
                "deterministic_transcript_sha256": self.transcript.hexdigest()}


def satisfies(clauses: list, assignment: tuple | list) -> bool:
    """Literal-by-literal Boolean semantics; independent of kernel normalization."""
    for clause in clauses:
        satisfied = False
        for literal in clause:
            value = assignment[abs(literal) - 1]
            if literal < 0:
                value = not value
            if value:
                satisfied = True
                break
        if not satisfied:
            return False
    return True


def clause_truth_mask(clause: list | tuple, assignments: list[tuple]) -> int:
    return sum(1 << i for i, values in enumerate(assignments) if satisfies([clause], values))


def exhaustive_resolution(audit: Audit, max_variables: int = 4) -> None:
    """Every signed-literal subset, including empty/tautological clauses."""
    scope = "resolution_exhaustive"
    candidates = accepted = model_implications = represented_valuations = 0
    for nvars in range(1, max_variables + 1):
        literals = tuple(range(-nvars, 0)) + tuple(range(1, nvars + 1))
        clauses = [[literal for bit, literal in enumerate(literals) if mask & (1 << bit)]
                   for mask in range(1 << len(literals))]
        assignments = list(itertools.product((False, True), repeat=nvars))
        truths = [clause_truth_mask(clause, assignments) for clause in clauses]
        lookup = {tuple(clause): truth for clause, truth in zip(clauses, truths)}
        for ai, left in enumerate(clauses):
            for bi, right in enumerate(clauses):
                for pivot in range(1, nvars + 1):
                    opposite = (pivot in left and -pivot in right) or (-pivot in left and pivot in right)
                    result = audit.expect(scope, opposite,
                        lambda: verify_resolution([left, right], [[0, 1, pivot]], nvars),
                        [nvars, ai, bi, pivot], lambda x: x["valid"])
                    candidates += 1
                    if result and result["valid"]:
                        accepted += 1
                        canonical = tuple(result["final_clause"])
                        truth = lookup.get(canonical, -1)
                        premise_models = truths[ai] & truths[bi]
                        audit.invariant(scope, truth != -1 and premise_models & ~truth == 0,
                                        ["truth", nvars, ai, bi, pivot], result)
                        audit.invariant(scope, result["derived_empty"] == (canonical == ()),
                                        ["empty", nvars, ai, bi, pivot], result)
                        model_implications += premise_models.bit_count()
                        represented_valuations += len(assignments)
    audit.measurements[scope] = {
        "variables": list(range(1, max_variables + 1)), "clause_pair_pivot_cases": candidates,
        "accepted_inferences": accepted, "assignment_implications_represented": represented_valuations,
        "assignments_satisfying_both_parents": model_implications,
        "oracle": "Complete Boolean truth tables compressed into bit masks; no proof-search oracle.",
    }


def model_semantics(audit: Audit, rng: random.Random, random_cases: int = 2000) -> None:
    scope = "model_truth_tables"
    calls = 0
    for nvars in (1, 2, 3):
        literals = tuple(range(-nvars, 0)) + tuple(range(1, nvars + 1))
        clauses = [[literal for bit, literal in enumerate(literals) if mask & (1 << bit)]
                   for mask in range(1 << (2 * nvars))]
        assignments = list(itertools.product((False, True), repeat=nvars))
        formulas = [[]] + [[clause] for clause in clauses]
        formulas.extend([left, right] for left in clauses for right in clauses)
        for fi, formula in enumerate(formulas):
            for vi, values in enumerate(assignments):
                audit.expect(scope, satisfies(formula, values),
                             lambda: verify_model(formula, list(values), nvars), [nvars, fi, vi])
                calls += 1
    for case in range(random_cases):
        nvars = rng.randint(1, 10)
        formula = []
        for _ in range(rng.randint(0, 24)):
            clause = [rng.choice((-1, 1)) * rng.randint(1, nvars)
                      for _ in range(rng.randint(0, 2 * nvars))]
            formula.append(clause)
        for sample in range(8):
            values = [bool(rng.randrange(2)) for _ in range(nvars)]
            audit.expect(scope, satisfies(formula, values),
                         lambda: verify_model(formula, values, nvars), ["random", case, sample])
            calls += 1
    audit.measurements[scope] = {"complete_cnf_scope": "All 0-, 1-, and ordered 2-clause formulas over 1..3 variables, including tautologies and duplicates.",
                                "random_formulas": random_cases, "model_calls": calls}


def blocker_statement(ninputs: int, rng: random.Random) -> tuple[dict, dict]:
    """Construct a refutation tree directly from all Boolean assignment blockers.

    Each blocker excludes exactly one input valuation.  Their conjunction is
    false by exhaustive coverage.  Gating every blocker by g yields F |= g and
    is consistent whenever g holds.  Pairwise merging drops one distinguishing
    literal until only g remains.  No production search or generator is used.
    """
    nvars = ninputs + 1
    labels = list(range(1, nvars + 1))
    rng.shuffle(labels)
    signs = [rng.choice((-1, 1)) for _ in range(nvars)]
    goal = labels[-1] * signs[-1]
    premises = []
    group = []
    for assignment in itertools.product((False, True), repeat=ninputs):
        literals = [labels[i] * signs[i] * (-1 if value else 1)
                    for i, value in enumerate(assignment)] + [goal]
        rng.shuffle(literals)
        group.append(len(premises))
        premises.append(literals)
    steps = []
    next_index = len(premises) + 1  # Negated goal is one additional premise.
    for position in range(ninputs - 1, -1, -1):
        following = []
        for pair in range(0, len(group), 2):
            a, b = group[pair:pair + 2]
            if rng.randrange(2):
                a, b = b, a
            steps.append([a, b, labels[position]])
            following.append(next_index)
            next_index += 1
        group = following
    steps.append([group[0], len(premises), abs(goal)])
    model = [bool(rng.randrange(2)) for _ in range(nvars)]
    model[abs(goal) - 1] = goal > 0
    statement = {"nvars": nvars, "clauses": premises, "goal": goal,
                 "statement_sha256": statement_digest(premises, nvars, goal)}
    fill = {"statement_sha256": statement["statement_sha256"],
            "proof_steps": steps, "consistency_model": model}
    return statement, fill


def proof_task_for_statement(statement: dict) -> ProofTask:
    """Exercise the real domain evaluator with an independently made statement."""
    task = ProofTask.__new__(ProofTask)
    task.nvars = statement["nvars"]
    task.clauses = statement["clauses"]
    task.goal = statement["goal"]
    task.statement = statement
    task.twin_kind = "audit_synthetic"
    return task


def swap_and_duplicate_steps(fill: dict, initial_count: int, rng: random.Random) -> dict:
    result = copy.deepcopy(fill)
    original = result["proof_steps"]
    remap: dict[int, int] = {}
    steps = []
    for i, (a, b, pivot) in enumerate(original):
        a, b = remap.get(a, a), remap.get(b, b)
        if rng.randrange(2):
            a, b = b, a
        # Redundant sound steps are permitted by the public proof contract.
        if rng.randrange(3) == 0:
            steps.append([a, b, pivot])
        remap[initial_count + i] = initial_count + len(steps)
        steps.append([a, b, pivot])
    result["proof_steps"] = steps
    return result


def proof_domain_stress(audit: Audit, rng: random.Random, cases: int = 160) -> None:
    scope = "proof_alternatives_and_forgeries"
    for case in range(cases):
        statement, fill = blocker_statement(1 + case % 7, rng)
        task = proof_task_for_statement(statement)
        nvars = statement["nvars"]
        values = list(itertools.product((False, True), repeat=nvars))
        satisfying = [value for value in values if satisfies(statement["clauses"], value)]
        audit.invariant(scope, bool(satisfying) and all(
            value[abs(statement["goal"]) - 1] == (statement["goal"] > 0)
            for value in satisfying), [case, "nonvacuous_entailment"])
        positives = [("constructed", fill), ("redundant_swapped_steps",
                     swap_and_duplicate_steps(fill, len(statement["clauses"]) + 1, rng))]
        for _ in range(3):
            variant = copy.deepcopy(fill)
            variant["consistency_model"] = list(rng.choice(satisfying))
            positives.append(("alternative_model", variant))
        for i, (name, candidate) in enumerate(positives):
            audit.expect(scope, True, lambda: task.evaluate(candidate), [case, name, i], lambda x: x.success)
        # Reorder premises and correctly transport their indices and commitment.
        order = list(range(len(statement["clauses"])))
        rng.shuffle(order)
        reordered = copy.deepcopy(statement)
        reordered["clauses"] = [statement["clauses"][i] for i in order]
        remap = {old: new for new, old in enumerate(order)}
        reordered["statement_sha256"] = statement_digest(reordered["clauses"], nvars, reordered["goal"])
        transported = copy.deepcopy(fill)
        transported["statement_sha256"] = reordered["statement_sha256"]
        transported["proof_steps"] = [[remap.get(a, a), remap.get(b, b), pivot]
                                     for a, b, pivot in fill["proof_steps"]]
        reordered_task = proof_task_for_statement(reordered)
        audit.expect(scope, True, lambda: reordered_task.evaluate(transported),
                     [case, "premise_permutation_with_transported_indices"], lambda x: x.success)
        # Each negative changes a required assertion, not merely proof spelling.
        negatives = []
        for digest in ("0" * 64, None, True, [fill["statement_sha256"]],
                       statement_digest(statement["clauses"], nvars, -statement["goal"])):
            bad = copy.deepcopy(fill); bad["statement_sha256"] = digest
            negatives.append(("forged_statement_commitment", bad))
        bad = copy.deepcopy(fill)
        bad["consistency_model"][abs(statement["goal"]) - 1] = statement["goal"] < 0
        negatives.append(("contradicting_model", bad))
        bad = copy.deepcopy(fill); bad["consistency_model"] = [int(x) for x in bad["consistency_model"]]
        negatives.append(("integer_model", bad))
        bad = copy.deepcopy(fill); bad["proof_steps"] = bad["proof_steps"][:-1]
        negatives.append(("valid_nonrefuting_prefix", bad))
        for step in ([0, 1, 0], [0, 1, True], [10**100, 0, 1], [-1, 0, 1],
                     [0, 1, 1, []], {"axiom": []}):
            bad = copy.deepcopy(fill); bad["proof_steps"].append(step)
            negatives.append(("illegal_suffix_after_refutation", bad))
        bad = copy.deepcopy(fill); bad["clauses"] = [[]]
        negatives.append(("new_premise_field", bad))
        bad = copy.deepcopy(fill); del bad["consistency_model"]
        negatives.append(("missing_nonvacuity_witness", bad))
        for mutation in range(12):
            bad = copy.deepcopy(fill)
            position = rng.randrange(len(bad["proof_steps"]))
            if mutation % 3 == 0:
                # No clause in this construction contains both signs. A single
                # parent cannot resolve against itself on any pivot.
                bad["proof_steps"][position][1] = bad["proof_steps"][position][0]
            elif mutation % 3 == 1:
                bad["proof_steps"][position][rng.randrange(2)] = len(task.clauses) + 1 + position
            else:
                # Every nonfinal derived clause contains the same goal sign.
                position = rng.randrange(len(bad["proof_steps"]) - 1)
                bad["proof_steps"][position][2] = abs(task.goal)
            negatives.append(("randomized_internal_step_corruption", bad))
        for i, (name, candidate) in enumerate(negatives):
            audit.expect(scope, False, lambda: task.evaluate(candidate), [case, name, i], lambda x: x.success)
        before = copy.deepcopy(statement)
        arguments = {"proof_steps": fill["proof_steps"][:min(30, len(fill["proof_steps"]))]}
        saved_arguments = copy.deepcopy(arguments)
        audit.expect(scope, True, lambda: task.query("check_prefix", arguments),
                     [case, "prefix"], lambda x: x["prefix_valid"])
        audit.invariant(scope, task.statement == before and arguments == saved_arguments,
                        [case, "prefix_read_only"])
    audit.measurements[scope] = {"independent_statements": cases, "input_variables": "1..7 plus the signed goal", "construction": "All assignment blockers, randomly relabeled and signed, paired into a resolution tree.",
                                "randomized_internal_step_corruptions": 12 * cases,
                                "uses_production_proof_search": False}


def satisfiable_multistep_semantics(audit: Audit, rng: random.Random, cases: int = 1000) -> None:
    """Exercise multi-step indexing where false cannot follow from the premises.

    The derivation generator follows the advertised rule but is not the oracle:
    final entailment is checked independently on every Boolean assignment.
    This avoids the vacuous semantic test obtained by auditing only unsatisfiable
    premises, from which every conclusion follows.
    """
    scope = "satisfiable_multistep_semantics"
    derivation_steps = represented_valuations = 0
    for case in range(cases):
        nvars = rng.randint(1, 8)
        witness = [bool(rng.randrange(2)) for _ in range(nvars)]
        premises = []
        for _ in range(rng.randint(4, 16)):
            pool = list(range(-nvars, 0)) + list(range(1, nvars + 1))
            clause = rng.sample(pool, rng.randint(0, len(pool)))
            if not satisfies([clause], witness):
                variable = rng.randrange(nvars)
                literal = (variable + 1) * (1 if witness[variable] else -1)
                if literal not in clause:
                    clause.append(literal)
            premises.append(clause)
        known = copy.deepcopy(premises)
        steps = []
        for _ in range(32):
            found = False
            for _ in range(80):
                a, b, pivot = rng.randrange(len(known)), rng.randrange(len(known)), rng.randint(1, nvars)
                if pivot in known[a] and -pivot in known[b]:
                    left_removed, right_removed = pivot, -pivot
                elif -pivot in known[a] and pivot in known[b]:
                    left_removed, right_removed = -pivot, pivot
                else:
                    continue
                derived = []
                for parent, removed in ((known[a], left_removed), (known[b], right_removed)):
                    for literal in parent:
                        if literal != removed and literal not in derived:
                            derived.append(literal)
                known.append(derived)
                steps.append([a, b, pivot])
                found = True
                break
            if not found:
                break
        result = audit.expect(scope, True, lambda: verify_resolution(premises, steps, nvars),
                              [case, "well_formed_constructed_dag"], lambda x: x["valid"])
        if result and result["valid"]:
            assignments = list(itertools.product((False, True), repeat=nvars))
            final = result["final_clause"]
            semantic = all(not satisfies(premises, values) or satisfies([final], values)
                           for values in assignments)
            audit.invariant(scope, semantic and not result["derived_empty"],
                            [case, "truth_table_entailment_and_nonrefutation"])
            represented_valuations += len(assignments)
        derivation_steps += len(steps)
        if steps:
            for mutation in range(3):
                corrupt = copy.deepcopy(steps)
                position = rng.randrange(len(corrupt))
                if mutation == 0:
                    corrupt[position][rng.randrange(2)] = len(premises) + position
                elif mutation == 1:
                    corrupt[position][2] = 0
                else:
                    corrupt.insert(position, {"axiom": []})
                audit.expect(scope, False, lambda: verify_resolution(premises, corrupt, nvars),
                             [case, "internal_corruption", mutation], lambda x: x["valid"])
    audit.measurements[scope] = {"satisfiable_formulas": cases, "constructed_steps": derivation_steps,
                                "complete_valuations": represented_valuations, "variables": "1..8",
                                "oracle": "Final clause truth implication under every Boolean valuation, with at least one known premise model."}


def nonvacuity_cases(audit: Audit) -> None:
    scope = "proof_nonvacuity_and_nonentailment"
    statements = [
        ({"nvars": 2, "clauses": [[1], [-1]], "goal": 2}, [[0, 1, 1]]),
        ({"nvars": 2, "clauses": [[], [1, -1]], "goal": 2}, []),
        ({"nvars": 2, "clauses": [], "goal": 2}, []),
        ({"nvars": 2, "clauses": [[1, 2]], "goal": 2}, []),
    ]
    for index, (statement, steps) in enumerate(statements):
        statement["statement_sha256"] = statement_digest(statement["clauses"], 2, statement["goal"])
        task = proof_task_for_statement(statement)
        for values in itertools.product((False, True), repeat=2):
            fill = {"statement_sha256": statement["statement_sha256"], "proof_steps": steps,
                    "consistency_model": list(values)}
            audit.expect(scope, False, lambda: task.evaluate(fill), [index, list(values)], lambda x: x.success)
    audit.measurements[scope] = {"statements": 4, "complete_consistency_assignments_per_statement": 4,
                                "cases": ["explicit inconsistent units", "existing empty premise", "empty satisfiable nonentailing premises", "satisfiable disjunction not entailing goal"]}


def generated_statement_semantics(audit: Audit, seeds: int = 8) -> None:
    scope = "generated_proof_statement_semantics"
    total_valuations = statements = 0
    for seed in range(seeds):
        for split, difficulty in [(split, d) for split in ("train", "dev") for d in (1, 2, 3)] + [("transfer", 1)]:
            for twin in (0, 1):
                task = ProofTask(seed, split, difficulty, twin)
                models = counterexamples = 0
                for value in itertools.product((False, True), repeat=task.nvars):
                    total_valuations += 1
                    if satisfies(task.clauses, value):
                        models += 1
                        counterexamples += value[abs(task.goal) - 1] != (task.goal > 0)
                audit.invariant(scope, models > 0, [seed, split, difficulty, twin, "consistent"])
                audit.invariant(scope, counterexamples == 0,
                                [seed, split, difficulty, twin, "entails_signed_goal"], counterexamples)
                statements += 1
    audit.measurements[scope] = {"statements": statements, "complete_valuations": total_valuations,
                                "seeds": list(range(seeds)), "transfer_difficulties_excluded_from_truth_enumeration": [2, 3]}


class PolicyOracle:
    """Enumerate heap-indexed complete policies, then replay each possible world.

    A complete depth-d policy chooses one column at each of 2**d-1 internal
    positions.  A row is identified exactly when its terminal position differs
    from all other rows.  Early-stop policies can be padded without changing
    distinguishability, so this enumeration covers them.  No state depths or
    minimax recurrence are used to compute the answer.
    """

    def __init__(self, width: int, depth_limit: int) -> None:
        self.width = width
        self.rows = list(itertools.product((0, 1), repeat=width))
        self.levels = []
        self.policies_enumerated = 0
        self.world_trajectories = 0
        self.cache: dict[tuple[int, ...], tuple[int, list[tuple]]] = {}
        for depth in range(depth_limit + 1):
            level = []
            for queries in itertools.product(range(width), repeat=(1 << depth) - 1):
                leaves = []
                for row in self.rows:
                    node = 0
                    for _ in range(depth):
                        node = 2 * node + 1 + row[queries[node]]
                    leaves.append(node)
                level.append((queries, tuple(leaves)))
                self.policies_enumerated += 1
                self.world_trajectories += len(self.rows)
            self.levels.append(level)
        self.compatibility_checks = 0

    def solve(self, table: list[list[int]]) -> tuple[int, list[tuple]]:
        indices = tuple(self.rows.index(tuple(row)) for row in table)
        if indices not in self.cache:
            for depth, policies in enumerate(self.levels):
                successes = []
                for queries, leaves in policies:
                    self.compatibility_checks += 1
                    if len({leaves[i] for i in indices}) == len(indices):
                        successes.append(queries)
                if successes:
                    self.cache[indices] = (depth, successes)
                    break
            else:
                raise ValueError("oracle depth limit too small")
        return self.cache[indices]


def reachable_observation_masks(table: list[list[int]]) -> list[int]:
    """All nonempty intersections of column observations; no Bellman traversal."""
    masks = set()
    for partial_observation in itertools.product((-1, 0, 1), repeat=len(table[0])):
        worlds = [i for i, row in enumerate(table)
                  if all(value == -1 or row[q] == value for q, value in enumerate(partial_observation))]
        if worlds:
            masks.add(sum(1 << i for i in worlds))
    return sorted(masks)


def independent_certificate(table: list[list[int]], oracle: PolicyOracle) -> tuple[dict, dict]:
    nodes, choices = [], {}
    for mask in reachable_observation_masks(table):
        subtable = [row for i, row in enumerate(table) if mask & (1 << i)]
        depth, policies = oracle.solve(subtable)
        options = {policy[0] for policy in policies} if depth else {None}
        chosen = min(options) if depth else None
        nodes.append([mask, depth, chosen])
        choices[mask] = options
    # Independent digest encoding checks the table commitment at the same time.
    digest = hashlib.sha256(json.dumps(table, separators=(",", ":")).encode("ascii")).hexdigest()
    return {"schema_version": "finite-diagnosis-dp-v1", "table_sha256": digest,
            "root_mask": (1 << len(table)) - 1, "nodes": nodes}, choices


def policy_tree(table: list[list[int]], queries: tuple, max_depth: int) -> dict:
    """Prune padded/unreached branches of a full, independently enumerated policy."""
    def build(worlds: list[int], heap: int, level: int) -> dict:
        if len(worlds) == 1:
            return {"world": worlds[0]}
        if level >= max_depth:
            raise ValueError("policy does not identify every world")
        q = queries[heap]
        zero = [w for w in worlds if table[w][q] == 0]
        one = [w for w in worlds if table[w][q] == 1]
        if not zero:
            return build(one, 2 * heap + 2, level + 1)
        if not one:
            return build(zero, 2 * heap + 1, level + 1)
        return {"query": q, "zero": build(zero, 2 * heap + 1, level + 1),
                "one": build(one, 2 * heap + 2, level + 1)}
    return build(list(range(len(table))), 0, 0)


def replay_tree(table: list[list[int]], tree: dict) -> tuple[bool, int]:
    """Per-world operational semantics, separate from verifier's set traversal."""
    longest = 0
    for world, row in enumerate(table):
        node, steps = tree, 0
        while "query" in node:
            if steps > len(row):
                return False, steps
            node = node["one" if row[node["query"]] else "zero"]
            steps += 1
        if node != {"world": world}:
            return False, steps
        longest = max(longest, steps)
    return True, longest


def diagnosis_exact_policies(audit: Audit, rng: random.Random, quick: bool = False) -> list[tuple]:
    scope = "diagnosis_complete_policy_oracle"
    tables = []
    oracle_metrics = []
    for width in (1, 2, 3, 4):
        oracle = PolicyOracle(width, min(width, 3))
        rows = [list(row) for row in oracle.rows]
        if width <= 3:
            population = [list(choice) for n in range(2, len(rows) + 1)
                          for choice in itertools.combinations(rows, n)]
            if quick and width == 3:
                population = population[::11]
        else:
            # <=4 worlds always need at most three informative binary queries.
            population = [rng.sample(rows, rng.randint(2, 4)) for _ in range(12 if quick else 96)]
        for table_index, table in enumerate(population):
            case = [width, table_index]
            expected_depth, policies = oracle.solve(table)
            independent, choices = independent_certificate(table, oracle)
            produced = build_decision_certificate(table)
            checked = audit.expect(scope, True,
                                   lambda: verify_decision_certificate(table, produced),
                                   case + ["produced_bound"], lambda x: x["valid"])
            if checked and checked["valid"]:
                audit.invariant(scope, checked["optimal_depth"] == expected_depth,
                                case + ["enumerated_optimum"], checked)
            with patch("causalfill.decision_certificates._optimize", side_effect=AssertionError("optimizer consulted")):
                audit.expect(scope, True, lambda: verify_decision_certificate(table, independent),
                             case + ["independent_certificate_without_optimizer"], lambda x: x["valid"])
            alternate = copy.deepcopy(independent)
            for node in alternate["nodes"]:
                node[2] = rng.choice(sorted(choices[node[0]], key=lambda x: -1 if x is None else x))
            rng.shuffle(alternate["nodes"])
            audit.expect(scope, True, lambda: verify_decision_certificate(table, alternate),
                         case + ["alternative_optimal_queries_and_node_order"], lambda x: x["valid"])
            trees = []
            for pi in sorted({0, len(policies) // 2, len(policies) - 1}):
                tree = policy_tree(table, policies[pi], expected_depth)
                tree_check = audit.expect(scope, True, lambda: verify_decision_tree(table, tree),
                                         case + ["enumerated_strategy", pi], lambda x: x["valid"])
                operational_ok, operational_depth = replay_tree(table, tree)
                audit.invariant(scope, operational_ok and operational_depth == expected_depth and
                                tree_check is not None and tree_check.get("depth") == operational_depth,
                                case + ["operational_strategy", pi])
                trees.append(tree)
            tables.append((table, independent, choices, expected_depth, trees[0], case))
        oracle_metrics.append({"width": width, "depth_limit": min(width, 3),
                               "tables": len(population), "complete_policies_enumerated": oracle.policies_enumerated,
                               "complete_world_trajectories": oracle.world_trajectories,
                               "policy_subset_compatibility_checks": oracle.compatibility_checks,
                               "different_subsets_evaluated": len(oracle.cache)})
    audit.measurements[scope] = {"oracles": oracle_metrics,
                                "oracle_independence": "Enumerates every complete bounded-depth query assignment and simulates every binary response row. No Bellman recurrence computes expected depths.",
                                "table_scope": "Every subset of distinct rows with at least two worlds for widths 1, 2, 3; fixed-seed samples of 2..4 worlds for width 4."}
    return tables


def diagnosis_certificate_forgeries(audit: Audit, tables: list[tuple]) -> None:
    scope = "diagnosis_bound_and_strategy_forgeries"
    for table, certificate, choices, depth, tree, case in tables:
        for index, (mask, claimed, query) in enumerate(certificate["nodes"]):
            missing = copy.deepcopy(certificate); missing["nodes"].pop(index)
            audit.expect(scope, False, lambda: verify_decision_certificate(table, missing),
                         case + ["required_state_omission", mask], lambda x: x["valid"])
            for wrong_depth in range(len(table[0]) + 1):
                if wrong_depth == claimed:
                    continue
                bad = copy.deepcopy(certificate); bad["nodes"][index][1] = wrong_depth
                audit.expect(scope, False, lambda: verify_decision_certificate(table, bad),
                             case + ["wrong_depth", mask, wrong_depth], lambda x: x["valid"])
            for alternate in [None] + list(range(len(table[0]))):
                if alternate == query:
                    continue
                bad = copy.deepcopy(certificate); bad["nodes"][index][2] = alternate
                audit.expect(scope, alternate in choices[mask], lambda: verify_decision_certificate(table, bad),
                             case + ["changed_query", mask, alternate], lambda x: x["valid"])
        alterations = []
        for key, value in (("table_sha256", "f" * 64), ("schema_version", "admit"),
                           ("root_mask", 1), ("root_mask", True), ("nodes", []),
                           ("nodes", None)):
            bad = copy.deepcopy(certificate); bad[key] = value
            alterations.append((key, bad))
        bad = copy.deepcopy(certificate); bad["nodes"].append(bad["nodes"][0])
        alterations.append(("duplicate_state", bad))
        bad = copy.deepcopy(certificate); bad["axioms"] = True
        alterations.append(("extra_axiom", bad))
        for i, (name, bad) in enumerate(alterations):
            audit.expect(scope, False, lambda: verify_decision_certificate(table, bad),
                         case + [name, i], lambda x: x["valid"])
        wrong_tree = copy.deepcopy(tree)
        leaf = wrong_tree
        while "query" in leaf:
            leaf = leaf["zero"]
        leaf["world"] = (leaf["world"] + 1) % len(table)
        audit.expect(scope, False, lambda: verify_decision_tree(table, wrong_tree),
                     case + ["wrong_leaf"], lambda x: x["valid"])
        switched = copy.deepcopy(tree); switched["zero"], switched["one"] = switched["one"], switched["zero"]
        audit.expect(scope, False, lambda: verify_decision_tree(table, switched),
                     case + ["switched_root_outcomes"], lambda x: x["valid"])
        alias = copy.deepcopy(tree); alias["one"] = alias["zero"]
        audit.expect(scope, False, lambda: verify_decision_tree(table, alias),
                     case + ["aliased_subtrees"], lambda x: x["valid"])
        cycle = {"query": 0, "one": {"world": 0}}; cycle["zero"] = cycle
        audit.expect(scope, False, lambda: verify_decision_tree(table, cycle),
                     case + ["cyclic_tree_not_json_representable"], lambda x: x["valid"])
        audit.expect(scope, False, lambda: verify_decision_tree(table, {"world": 0}),
                     case + ["guessed_leaf"], lambda x: x["valid"])


def synthetic_diagnosis(table: list, world: int, certificate: dict, budget: int) -> DiagnosisTask:
    task = DiagnosisTask.__new__(DiagnosisTask)
    task._table, task._world, task._certificate = table, world, certificate
    task.query_budget, task.query_count, task.observations = budget, 0, []
    return task


def independent_eliminations(table: list, observations: list, world: int, offset: int = 0) -> list:
    result = []
    for other, row in enumerate(table):
        if other == world:
            continue
        alternatives = [q for q, value in observations if row[q] != value]
        if not alternatives:
            raise ValueError("observations do not identify the world")
        result.append({"world": other, "experiment": alternatives[offset % len(alternatives)]})
    return result


def diagnosis_observational_forgeries(audit: Audit, tables: list[tuple]) -> None:
    scope = "diagnosis_observed_eliminations"
    worlds_tested = 0
    for table, certificate, _, budget, tree, case in tables:
        for world in range(len(table)):
            worlds_tested += 1
            label = case + [world]
            task = synthetic_diagnosis(table, world, certificate, budget)
            # The correct target without observations still has no certificate.
            lucky = {"world": world, "eliminations": [{"world": other, "experiment": 0}
                     for other in range(len(table)) if other != world]}
            audit.expect(scope, False, lambda: task.evaluate(lucky), label + ["lucky_guess"], lambda x: x.success)
            node = tree
            while "query" in node:
                query = node["query"]
                response = task.query("experiment", {"id": query})
                audit.invariant(scope, response["outcome"] == table[world][query], label + ["observation", query])
                node = node["one" if response["outcome"] else "zero"]
            for offset in (0, 1, 2):
                fill = {"world": world, "eliminations": independent_eliminations(table, task.observations, world, offset)}
                audit.expect(scope, True, lambda: task.evaluate(fill), label + ["valid_alternative_witnesses", offset], lambda x: x.success)
            negatives = []
            wrong = copy.deepcopy(fill); wrong["world"] = (world + 1) % len(table)
            negatives.append(("wrong_world", wrong))
            missing = copy.deepcopy(fill); missing["eliminations"].pop()
            negatives.append(("missing_world", missing))
            duplicate = copy.deepcopy(fill); duplicate["eliminations"].append(duplicate["eliminations"][0])
            negatives.append(("extra_duplicate_world", duplicate))
            selected = copy.deepcopy(fill); selected["eliminations"][0]["world"] = world
            negatives.append(("eliminates_selected_world", selected))
            witness = copy.deepcopy(fill); witness["eliminations"][0]["experiment"] = len(table[0])
            negatives.append(("nonexistent_query", witness))
            boolean = copy.deepcopy(fill); boolean["eliminations"][0]["experiment"] = False
            negatives.append(("boolean_query_id", boolean))
            admitted = copy.deepcopy(fill); admitted["observations"] = task.observations
            negatives.append(("inject_observations", admitted))
            if len(fill["eliminations"]) > 1:
                duplicate = copy.deepcopy(fill); duplicate["eliminations"][1] = duplicate["eliminations"][0]
                negatives.append(("duplicate_instead_of_required_world", duplicate))
            observed = dict(task.observations)
            for q in range(len(table[0])):
                if q not in observed:
                    forged = copy.deepcopy(fill); forged["eliminations"][0]["experiment"] = q
                    negatives.append(("unobserved_query", forged))
            for i, (name, bad) in enumerate(negatives):
                audit.expect(scope, False, lambda: task.evaluate(bad), label + [name, i], lambda x: x.success)
            production = elimination_certificate(table, task.observations, world)
            audit.expect(scope, True, lambda: task.evaluate({"world": world, "eliminations": production}),
                         label + ["production_helper"], lambda x: x.success)
        # Exhausting the query cap with repetitions cannot create budget.
        task = synthetic_diagnosis(table, 0, certificate, budget)
        for _ in range(budget):
            task.query("experiment", {"id": 0})
        previous = (task.query_count, copy.deepcopy(task.observations))
        audit.raises(scope, lambda: task.query("experiment", {"id": 0}), case + ["query_cap"])
        audit.invariant(scope, previous == (task.query_count, task.observations), case + ["cap_rejection_atomic"])
    audit.measurements[scope] = {"table_world_cases": worlds_tested, "worlds_are_all_rows_of_each_audited_table": True,
                                "state_injection": "Synthetic evaluator-only instances exercise actual query/evaluate methods; no scored or model solver runs."}


def generated_diagnosis_checks(audit: Audit, seeds: int = 6) -> None:
    scope = "generated_diagnosis_operational_checks"
    instances = world_paths = 0
    max_states = max_depth = 0
    for seed in range(seeds):
        for split, difficulty, twin in itertools.product(("train", "dev", "transfer"), (1, 2, 3), (0, 1)):
            task = DiagnosisTask(seed, split, difficulty, twin)
            tree = extract_decision_tree(task._table, task.decision_certificate())
            correct, replayed_depth = replay_tree(task._table, tree)
            audit.invariant(scope, correct and replayed_depth == task.query_budget,
                            [seed, split, difficulty, twin, "all_world_paths"])
            world_paths += len(task._table)
            instances += 1
            max_states = max(max_states, len(task._certificate["nodes"]))
            max_depth = max(max_depth, task.query_budget)
            node = tree
            while "query" in node:
                observation = task.query("experiment", {"id": node["query"]})
                node = node["one" if observation["outcome"] else "zero"]
            fill = {"world": node["world"], "eliminations": independent_eliminations(task._table, task.observations, node["world"])}
            audit.expect(scope, True, lambda: task.evaluate(fill), [seed, split, difficulty, twin, "independent_fill"], lambda x: x.success)
    audit.measurements[scope] = {"instances": instances, "seeds": list(range(seeds)), "world_paths": world_paths,
                                "max_certificate_states": max_states, "max_depth": max_depth,
                                "oracle_limitation": "Operational strategy replay and evidence integrity only; large-table lower bounds are not independently policy-enumerated here."}


def malformed_and_bounds(audit: Audit) -> None:
    scope = "formal_malformed_and_resource_bounds"
    bad_scalars = [None, True, False, 0, -1, "1", 1.0, float("inf"), float("nan"), [], {}, 10**200]
    for index, value in enumerate(bad_scalars):
        audit.expect(scope, False, lambda: verify_resolution([[1], [-1]], [[0, 1, value]], 1),
                     ["pivot", index], lambda x: x["valid"])
        audit.expect(scope, False, lambda: verify_resolution([[1], [-1]], [[value, 1, 1]], 1),
                     ["parent", index], lambda x: x["valid"]) if type(value) is not int or value != 0 else None
    for index, clauses in enumerate([None, {}, "F", [[[1]]], [[True]], [[1.0]], [[0]], [[2]],
                                     [[-2]], [[float("nan")]], [[1, 1, 1]], [[]] * (MAX_INITIAL_CLAUSES + 1)]):
        audit.expect(scope, False, lambda: verify_resolution(clauses, [], 1), ["cnf", index], lambda x: x["valid"])
        audit.expect(scope, False, lambda: verify_model(clauses, [True], 1), ["model_bad_cnf", index])
    for index, assignment in enumerate([None, (), [1], [0], [True, False], [], ["true"], [[True]], {"1": True}]):
        audit.expect(scope, False, lambda: verify_model([[1]], assignment, 1), ["assignment", index])
    for index, steps in enumerate([None, {}, "admit", [None], [[]], [[0, 1]], [[0, 1, 1, []]],
                                   [[True, 1, 1]], [[0, True, 1]], [[2, 1, 1]], [[0, -1, 1]],
                                   [[0, 1, 1], [2, 2, 1]]]):
        audit.expect(scope, False, lambda: verify_resolution([[1], [-1]], steps, 1), ["steps", index], lambda x: x["valid"])
    for index, nvars in enumerate([0, 201, True, None, "1", 1.0, float("nan")]):
        audit.expect(scope, False, lambda: verify_resolution([[1], [-1]], [[0, 1, 1]], nvars),
                     ["nvars", index], lambda x: x["valid"])
    audit.expect(scope, True, lambda: verify_resolution([[1], [-1]], [[0, 1, 1]] * MAX_PROOF_STEPS, 1),
                 "exact_step_cap", lambda x: x["valid"] and x["derived_empty"])
    audit.expect(scope, False, lambda: verify_resolution([[1], [-1]], [[0, 1, 1]] * (MAX_PROOF_STEPS + 1), 1),
                 "over_step_cap", lambda x: x["valid"])
    audit.expect(scope, True, lambda: verify_resolution([[]] * MAX_INITIAL_CLAUSES, [], 1),
                 "exact_initial_clause_cap", lambda x: x["valid"] and x["derived_empty"])
    literals = list(range(-200, 0)) + list(range(1, 201))
    exact = [literals] * (MAX_LITERAL_ENTRIES // len(literals))
    audit.expect(scope, True, lambda: verify_resolution(exact, [], 200), "exact_literal_cap", lambda x: x["valid"])
    audit.expect(scope, False, lambda: verify_resolution(exact + [[1]], [], 200), "over_literal_cap", lambda x: x["valid"])
    nearly = exact[:-1]
    audit.expect(scope, True, lambda: verify_resolution(nearly, [[0, 0, 1]], 200),
                 "proof_exact_literal_cap", lambda x: x["valid"])
    audit.expect(scope, False, lambda: verify_resolution(nearly, [[0, 0, 1], [0, 0, 1]], 200),
                 "proof_over_literal_cap", lambda x: x["valid"])
    table = [[0, 0], [0, 1], [1, 0], [1, 1]]
    certificate = build_decision_certificate(table)
    tree = extract_decision_tree(table, certificate)
    malformed_tables = [None, {}, [], [[0]], [[0], [0]], [[False], [True]], [[0.0], [1]],
                        [[0], [float("nan")]], [[0], [float("inf")]], [[0], [1, 0]],
                        [[0] * 13, [1] * 13], [[0]] * 33, [[[0]], [1]]]
    for index, bad in enumerate(malformed_tables):
        audit.expect(scope, False, lambda: verify_decision_certificate(bad, certificate),
                     ["table_certificate", index], lambda x: x["valid"])
        audit.expect(scope, False, lambda: verify_decision_tree(bad, tree),
                     ["table_tree", index], lambda x: x["valid"])
    for field in ("schema_version", "table_sha256", "root_mask", "nodes"):
        for index, value in enumerate([None, False, "", [], {}, 1.5, float("nan"), float("inf")]):
            bad = copy.deepcopy(certificate); bad[field] = value
            audit.expect(scope, False, lambda: verify_decision_certificate(table, bad),
                         ["certificate_field", field, index], lambda x: x["valid"])
    oversized = copy.deepcopy(certificate); oversized["nodes"] = [[1, 0, None]] * 100001
    audit.expect(scope, False, lambda: verify_decision_certificate(table, oversized),
                 "over_certificate_state_cap", lambda x: x["valid"])
    for position in range(3):
        for index, value in enumerate([True, -1, float("nan"), float("inf"), {}, [], "0", 10**200]):
            bad = copy.deepcopy(certificate); bad["nodes"][-1][position] = value
            audit.expect(scope, False, lambda: verify_decision_certificate(table, bad),
                         ["node_position", position, index], lambda x: x["valid"])
    task = synthetic_diagnosis(table, 0, certificate, 2)
    for index, args in enumerate([None, {}, {"id": True}, {"id": -1}, {"id": 2},
                                 {"id": 0, "outcome": 0}, {"id": []}, {"id": float("nan")}]):
        audit.raises(scope, lambda: task.query("experiment", args), ["bad_query", index])
        audit.invariant(scope, task.query_count == 0 and task.observations == [], ["query_atomic", index])
    for index, observations in enumerate([[], [(0, 0)], [(0, 0), (0, 1)], [(0, 1), (1, 1)],
                                          [(2, 0)], [(0, True)], [(True, 0)]]):
        audit.raises(scope, lambda: elimination_certificate(table, observations, 0), ["elimination_helper", index])
    audit.measurements[scope] = {"bounds_exercised": {"variables": 200, "initial_clauses": MAX_INITIAL_CLAUSES,
        "proof_steps": MAX_PROOF_STEPS, "literal_entries": MAX_LITERAL_ENTRIES, "certificate_states_rejected": 100001},
        "malformed_scope": "JSON-like values plus NaN/Infinity, tuples where excluded, huge integers, and cyclic in-process trees; no arbitrary Python object gadget execution."}


def digest_metamorphisms(audit: Audit, rng: random.Random, cases: int = 300) -> None:
    scope = "statement_commitment_metamorphisms"
    for case in range(cases):
        nvars = rng.randint(2, 20)
        clauses = [[1], [-1, 2]]
        for _ in range(rng.randint(0, 20)):
            clauses.append(rng.sample(list(range(-nvars, 0)) + list(range(1, nvars + 1)), rng.randint(0, nvars)))
        goal = rng.choice((-1, 1)) * rng.randint(1, nvars)
        original = statement_digest(clauses, nvars, goal)
        variant = [list(clause) for clause in clauses]
        for clause in variant:
            if clause:
                clause.append(clause[0])
            rng.shuffle(clause)
        audit.invariant(scope, statement_digest(variant, nvars, goal) == original,
                        [case, "literal_reordering_and_duplicate_invariance"])
        swapped = clauses[:]; swapped[0], swapped[1] = swapped[1], swapped[0]
        audit.invariant(scope, statement_digest(swapped, nvars, goal) != original, [case, "premise_order_bound"])
        audit.invariant(scope, statement_digest(clauses, nvars, -goal) != original, [case, "goal_sign_bound"])
        audit.invariant(scope, statement_digest(clauses, nvars + 1, goal) != original, [case, "variable_domain_bound"])
    audit.measurements[scope] = {"formulas": cases,
        "cryptographic_limitation": "Tests canonicalization and changed-input commitments on this finite corpus; does not prove SHA256 collision resistance or authenticity."}


def source_hashes() -> dict:
    return {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in SOURCE_FILES}


def markdown_report(result: dict) -> str:
    totals = result["totals"]
    lines = ["# Formal evaluator stress audit — v0.3", "",
             "This is author/auditor testing of evaluator integrity. It contains no model-solver trial, leaderboard result, or proof of global correctness.", "",
             f"**Result:** {totals['checks']:,} checks; {totals['false_accepts']:,} false accepts; {totals['false_rejects']:,} false rejects; {totals['invariant_failures']:,} failed invariants; {totals['exceptions']:,} unexpected exceptions.", "",
             f"Fixed seed: `{result['seed']}`. Runtime: {result['elapsed_seconds']:.3f} seconds. Source stable during the run: `{result['source_stable_during_run']}`. Profile: `{result['profile']}`.", "",
             "## Measured checks", "", "| Section | Checks | Expected accepts | Expected rejects | False accepts | False rejects | Invariant failures | Exceptions |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for name, values in result["sections"].items():
        lines.append("| " + name + " | " + " | ".join(f"{values[key]:,}" for key in
            ("checks", "expected_accepts", "expected_rejects", "false_accepts", "false_rejects", "invariant_failures", "exceptions")) + " |")
    lines.extend(["", "Counts include acceptance decisions and separately labeled semantic/integrity invariants. They are test assertions, not independent sampled episodes or intelligence measurements. Expected-accept counts for exception-contract tests mean the expected rejection behavior was observed.", "",
                  "## Independent oracles and coverage", ""])
    for name, measurement in result["measurements"].items():
        lines.extend([f"### {name}", "", "```json", json.dumps(measurement, indent=2, sort_keys=True), "```", ""])
    lines.extend(["## Reproduction", "", "```sh", result["reproduce_command"], "```", "",
                  "The JSON report records source hashes, interpreter/platform, exact seeds, scope, separate false-accept/false-reject/exception counters, and a deterministic transcript digest. Runtime and UTC timestamp may change on repetition; the transcript digest should remain stable for unchanged sources and the same interpreter semantics.", "",
                  "## Trust boundary and limitations", "",
                  "The truth-table checks validate the resolution axiom on every clause pair in the stated finite variable range, including tautologies and empty clauses. Induction then explains why a sequence of correctly checked resolution steps preserves entailment; the test suite does not formally verify the Python implementation of that induction or its interpreter. The model witness independently prevents vacuous entailment in the exercised proof tasks.", "",
                  "The exact diagnosis oracle enumerates all complete bounded-depth policies. It obtains distinguishability by simulating worlds through a policy, without evaluating the production Bellman recurrence. Only the explicitly enumerated small tables have independent exact lower-bound checks. Large generated tables receive independent operational replay and elimination-evidence checks, while their global lower bounds still rely on the finite recurrence checker.", "",
                  "SHA256 is a content commitment here, not a signature, identity check, or theorem. Generated families, noiseless finite tables, explicit row lists, public query columns, deterministic adaptive strategies, exact integer/Boolean parsing, the host Python runtime, and immutable evaluator-held statements are assumptions. Transport/parser integrity and scored-solver isolation are separate audits.", "",
                  "Mutation tests include guaranteed-invalid attacks and legitimate alternative proofs, models, optimum queries, node orders, and elimination witnesses. Passing them supplies bounded evidence of evaluator integrity; it does not establish unrestricted logical completeness, cryptographic collision resistance, frontier reasoning difficulty, or a model-performance result.", "",
                  "## Findings", ""])
    if result["failures"]:
        lines.extend(["```json", json.dumps(result["failures"], indent=2), "```", ""])
    else:
        lines.extend(["No mismatch or unexpected exception was found within this run's stated scope. No formal evaluator core fix was required by this audit.", ""])
    return "\n".join(lines)


def run(quick: bool = False) -> dict:
    audit = Audit()
    rng = random.Random(SEED)
    started = time.perf_counter()
    before = source_hashes()
    stages = [
        ("exhaustive resolution truth semantics", lambda: exhaustive_resolution(audit, 3 if quick else 4)),
        ("model truth semantics", lambda: model_semantics(audit, rng, 50 if quick else 2000)),
        ("independent proof alternatives and forgeries", lambda: proof_domain_stress(audit, rng, 12 if quick else 160)),
        ("satisfiable multistep derivation truth semantics", lambda: satisfiable_multistep_semantics(audit, rng, 30 if quick else 1000)),
        ("nonvacuity and nonentailment", lambda: nonvacuity_cases(audit)),
        ("generated proof statement truth tables", lambda: generated_statement_semantics(audit, 1 if quick else 8)),
        ("statement commitment metamorphisms", lambda: digest_metamorphisms(audit, rng, 20 if quick else 300)),
    ]
    for name, operation in stages:
        print(f"[formal] {name}", flush=True)
        operation()
    print("[formal] complete diagnosis policy enumeration", flush=True)
    tables = diagnosis_exact_policies(audit, rng, quick)
    for name, operation in (
        ("diagnosis bound and strategy forgeries", lambda: diagnosis_certificate_forgeries(audit, tables)),
        ("diagnosis observed elimination witnesses", lambda: diagnosis_observational_forgeries(audit, tables)),
        ("generated diagnosis world replay", lambda: generated_diagnosis_checks(audit, 1 if quick else 6)),
        ("malformed inputs and resource boundaries", lambda: malformed_and_bounds(audit)),
    ):
        print(f"[formal] {name}", flush=True)
        operation()
    after = source_hashes()
    audit.invariant("audit_reproducibility", before == after, "source_stable_during_run")
    result = audit.report()
    result.update({"schema_version": "causalfill.formal-stress.v0.3", "seed": SEED,
        "profile": "quick" if quick else "full", "run_kind": "evaluator-development-author-audit",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(time.perf_counter() - started, 6),
        "python": sys.version, "platform": platform.platform(),
        "source_sha256_before": before, "source_sha256_after": after,
        "source_stable_during_run": before == after,
        "reproduce_command": "python tools/stress_formal.py " + ("--quick " if quick else "") +
                             "--output reports/stress-v0.3/formal-results.json",
        "claims": {"finite_evaluator_stress_test": True, "formal_machine_checked_proof": False,
                   "model_solver_run": False, "global_correctness_proved": False}})
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--quick", action="store_true", help="Smaller deterministic smoke profile; not the full reported audit.")
    parser.add_argument("--output", type=Path, default=ROOT / "reports/stress-v0.3/formal-results.json")
    arguments = parser.parse_args()
    result = run(arguments.quick)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    markdown = arguments.output.with_suffix(".md")
    markdown.write_text(markdown_report(result))
    print(json.dumps({"output": str(arguments.output), "markdown": str(markdown),
                      "totals": result["totals"], "elapsed_seconds": result["elapsed_seconds"],
                      "transcript_sha256": result["deterministic_transcript_sha256"]}, sort_keys=True))
    return int(any(result["totals"][key] for key in ("false_accepts", "false_rejects", "invariant_failures", "exceptions")))


if __name__ == "__main__":
    raise SystemExit(main())
