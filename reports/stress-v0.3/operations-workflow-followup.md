# Operational stress audit

Evaluator-development checks; no model-performance or certified-difficulty claim.

Master seed: `371905`. Total wall time: 18.310 seconds.

| Section | Checks | False accepts | False rejects | Oracle mismatches | Unexpected exceptions | Seconds |
|---|---:|---:|---:|---:|---:|---:|
| workflow | 13248 | 0 | 0 | 0 | 0 | 18.309 |

## workflow

Acceptance is compared with explicit well-formed OOD witnesses, not merely disagreement with a reference string. Current strict success also requires a sufficient symbolic certificate over the declared integer domain [-1000000,1000000] with positive scale 1..1000000. Signed/fractional interpreter probes outside that contract are diagnostics only. Older baseline reports capture the original finite-suite-only verifier.

Counters:

```json
{
  "check:equivalent_workflow_expression": 1440,
  "check:frozen_calibration_rejected": 288,
  "check:independent_fractional_signed_ood": 8640,
  "check:workflow_attack_witness_differs": 1440,
  "check:workflow_ood_range_attack": 1440,
  "checks": 13248,
  "episodes": 288,
  "expected_accepts": 1440,
  "expected_rejects": 1728,
  "passed_checks": 13248,
  "verdict_checks": 3168
}
```

## Scope and interpretation

The source hashes, command arguments, actual seed lists, and bounded failure examples are in the adjacent JSON. Source files were not treated as a solver interface. Geometry checks cover sampled and targeted cases, not a formal proof of all possible JSON numeric inputs. Grid checks are finite and affine certificates are complete only inside the declared affine hypothesis class. Legal constant controls are reported as task-distribution shortcuts, not as false successes. Workflow threshold mutants supply explicit new-input counterexamples; older baseline reports capture finite-suite-only acceptance, while current strict success additionally requires a symbolic certificate over the declared integer domain.
