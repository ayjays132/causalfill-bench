# Formal evaluator stress audit — v0.3

This is author/auditor testing of evaluator integrity. It contains no model-solver trial, leaderboard result, or proof of global correctness.

**Result:** 633,087 checks; 0 false accepts; 0 false rejects; 0 failed invariants; 0 unexpected exceptions.

Fixed seed: `2026110103`. Runtime: 11.956 seconds. Source stable during the run: `True`. Profile: `full`.

## Measured checks

| Section | Checks | Expected accepts | Expected rejects | False accepts | False rejects | Invariant failures | Exceptions |
|---|---:|---:|---:|---:|---:|---:|---:|
| resolution_exhaustive | 515,550 | 120,295 | 154,665 | 0 | 0 | 0 | 0 |
| model_truth_tables | 50,422 | 30,188 | 20,234 | 0 | 0 | 0 | 0 |
| proof_alternatives_and_forgeries | 5,920 | 1,120 | 4,480 | 0 | 0 | 0 | 0 |
| satisfiable_multistep_semantics | 4,997 | 1,000 | 2,997 | 0 | 0 | 0 | 0 |
| proof_nonvacuity_and_nonentailment | 16 | 0 | 16 | 0 | 0 | 0 | 0 |
| generated_proof_statement_semantics | 224 | 0 | 0 | 0 | 0 | 0 | 0 |
| statement_commitment_metamorphisms | 1,200 | 0 | 0 | 0 | 0 | 0 | 0 |
| diagnosis_complete_policy_oracle | 3,240 | 1,975 | 0 | 0 | 0 | 0 | 0 |
| diagnosis_bound_and_strategy_forgeries | 29,011 | 1,353 | 27,658 | 0 | 0 | 0 | 0 |
| diagnosis_observed_eliminations | 22,102 | 5,675 | 13,341 | 0 | 0 | 0 | 0 |
| generated_diagnosis_operational_checks | 216 | 108 | 0 | 0 | 0 | 0 | 0 |
| formal_malformed_and_resource_bounds | 188 | 19 | 161 | 0 | 0 | 0 | 0 |
| audit_reproducibility | 1 | 0 | 0 | 0 | 0 | 0 | 0 |

Counts include acceptance decisions and separately labeled semantic/integrity invariants. They are test assertions, not independent sampled episodes or intelligence measurements. Expected-accept counts for exception-contract tests mean the expected rejection behavior was observed.

## Independent oracles and coverage

### resolution_exhaustive

```json
{
  "accepted_inferences": 120295,
  "assignment_implications_represented": 1878926,
  "assignments_satisfying_both_parents": 1741446,
  "clause_pair_pivot_cases": 274960,
  "oracle": "Complete Boolean truth tables compressed into bit masks; no proof-search oracle.",
  "variables": [
    1,
    2,
    3,
    4
  ]
}
```

### model_truth_tables

```json
{
  "complete_cnf_scope": "All 0-, 1-, and ordered 2-clause formulas over 1..3 variables, including tautologies and duplicates.",
  "model_calls": 50422,
  "random_formulas": 2000
}
```

### proof_alternatives_and_forgeries

```json
{
  "construction": "All assignment blockers, randomly relabeled and signed, paired into a resolution tree.",
  "independent_statements": 160,
  "input_variables": "1..7 plus the signed goal",
  "randomized_internal_step_corruptions": 1920,
  "uses_production_proof_search": false
}
```

### satisfiable_multistep_semantics

```json
{
  "complete_valuations": 65364,
  "constructed_steps": 31894,
  "oracle": "Final clause truth implication under every Boolean valuation, with at least one known premise model.",
  "satisfiable_formulas": 1000,
  "variables": "1..8"
}
```

### proof_nonvacuity_and_nonentailment

```json
{
  "cases": [
    "explicit inconsistent units",
    "existing empty premise",
    "empty satisfiable nonentailing premises",
    "satisfiable disjunction not entailing goal"
  ],
  "complete_consistency_assignments_per_statement": 4,
  "statements": 4
}
```

### generated_proof_statement_semantics

```json
{
  "complete_valuations": 366592,
  "seeds": [
    0,
    1,
    2,
    3,
    4,
    5,
    6,
    7
  ],
  "statements": 112,
  "transfer_difficulties_excluded_from_truth_enumeration": [
    2,
    3
  ]
}
```

### statement_commitment_metamorphisms

```json
{
  "cryptographic_limitation": "Tests canonicalization and changed-input commitments on this finite corpus; does not prove SHA256 collision resistance or authenticity.",
  "formulas": 300
}
```

### diagnosis_complete_policy_oracle

```json
{
  "oracle_independence": "Enumerates every complete bounded-depth query assignment and simulates every binary response row. No Bellman recurrence computes expected depths.",
  "oracles": [
    {
      "complete_policies_enumerated": 2,
      "complete_world_trajectories": 4,
      "depth_limit": 1,
      "different_subsets_evaluated": 3,
      "policy_subset_compatibility_checks": 4,
      "tables": 1,
      "width": 1
    },
    {
      "complete_policies_enumerated": 11,
      "complete_world_trajectories": 44,
      "depth_limit": 2,
      "different_subsets_evaluated": 15,
      "policy_subset_compatibility_checks": 77,
      "tables": 11,
      "width": 2
    },
    {
      "complete_policies_enumerated": 2218,
      "complete_world_trajectories": 17744,
      "depth_limit": 3,
      "different_subsets_evaluated": 255,
      "policy_subset_compatibility_checks": 227796,
      "tables": 247,
      "width": 3
    },
    {
      "complete_policies_enumerated": 16453,
      "complete_world_trajectories": 263248,
      "depth_limit": 3,
      "different_subsets_evaluated": 272,
      "policy_subset_compatibility_checks": 90576,
      "tables": 96,
      "width": 4
    }
  ],
  "table_scope": "Every subset of distinct rows with at least two worlds for widths 1, 2, 3; fixed-seed samples of 2..4 worlds for width 4."
}
```

### diagnosis_observed_eliminations

```json
{
  "state_injection": "Synthetic evaluator-only instances exercise actual query/evaluate methods; no scored or model solver runs.",
  "table_world_cases": 1330,
  "worlds_are_all_rows_of_each_audited_table": true
}
```

### generated_diagnosis_operational_checks

```json
{
  "instances": 108,
  "max_certificate_states": 1573,
  "max_depth": 6,
  "oracle_limitation": "Operational strategy replay and evidence integrity only; large-table lower bounds are not independently policy-enumerated here.",
  "seeds": [
    0,
    1,
    2,
    3,
    4,
    5
  ],
  "world_paths": 2016
}
```

### formal_malformed_and_resource_bounds

```json
{
  "bounds_exercised": {
    "certificate_states_rejected": 100001,
    "initial_clauses": 2000,
    "literal_entries": 500000,
    "proof_steps": 12000,
    "variables": 200
  },
  "malformed_scope": "JSON-like values plus NaN/Infinity, tuples where excluded, huge integers, and cyclic in-process trees; no arbitrary Python object gadget execution."
}
```

## Reproduction

```sh
python tools/stress_formal.py --output reports/stress-v0.3/formal-results.json
```

The JSON report records source hashes, interpreter/platform, exact seeds, scope, separate false-accept/false-reject/exception counters, and a deterministic transcript digest. Runtime and UTC timestamp may change on repetition; the transcript digest should remain stable for unchanged sources and the same interpreter semantics.

## Trust boundary and limitations

The truth-table checks validate the resolution axiom on every clause pair in the stated finite variable range, including tautologies and empty clauses. Induction then explains why a sequence of correctly checked resolution steps preserves entailment; the test suite does not formally verify the Python implementation of that induction or its interpreter. The model witness independently prevents vacuous entailment in the exercised proof tasks.

The exact diagnosis oracle enumerates all complete bounded-depth policies. It obtains distinguishability by simulating worlds through a policy, without evaluating the production Bellman recurrence. Only the explicitly enumerated small tables have independent exact lower-bound checks. Large generated tables receive independent operational replay and elimination-evidence checks, while their global lower bounds still rely on the finite recurrence checker.

SHA256 is a content commitment here, not a signature, identity check, or theorem. Generated families, noiseless finite tables, explicit row lists, public query columns, deterministic adaptive strategies, exact integer/Boolean parsing, the host Python runtime, and immutable evaluator-held statements are assumptions. Transport/parser integrity and scored-solver isolation are separate audits.

Mutation tests include guaranteed-invalid attacks and legitimate alternative proofs, models, optimum queries, node orders, and elimination witnesses. Passing them supplies bounded evidence of evaluator integrity; it does not establish unrestricted logical completeness, cryptographic collision resistance, frontier reasoning difficulty, or a model-performance result.

## Findings

No mismatch or unexpected exception was found within this run's stated scope. No formal evaluator core fix was required by this audit.
