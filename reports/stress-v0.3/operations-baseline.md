# Operational stress audit

Evaluator-development checks; no model-performance or certified-difficulty claim.

Master seed: `371905`. Total wall time: 11.328 seconds.

| Section | Checks | False accepts | False rejects | Oracle mismatches | Unexpected exceptions | Seconds |
|---|---:|---:|---:|---:|---:|---:|
| geometry | 12000 | 0 | 63 | 0 | 0 | 0.318 |
| robotics | 4176 | 144 | 197 | 0 | 0 | 1.403 |
| workflow | 6624 | 720 | 0 | 0 | 0 | 9.601 |

## geometry

Exact decimal-rational oracle tests segment endpoints and all six box faces; the implementation under test uses its own predicate.

Counters:

```json
{
  "check:exact_segment_geometry": 12000,
  "checks": 12000,
  "expected_accepts": 11628,
  "expected_rejects": 372,
  "passed_checks": 11937,
  "segment_comparisons": 12000,
  "verdict_checks": 12000
}
```

Failure counts:

```json
{
  "false_reject": 63,
  "false_reject:exact_segment_geometry": 63
}
```

The JSON report contains bounded examples and exact witnesses for each failure label.


## robotics

Targets are reconstructed by independent exact Gaussian calibration from camera observations. All route verdicts use the independent face-intersection oracle.

A fixed z=10 detour and fixed 0.5 N force is a legal shortcut control; successes are not classified as verifier false accepts.

Counters:

```json
{
  "check:closed_gripper": 144,
  "check:constant_route_force": 144,
  "check:defensive_lidar_copy": 144,
  "check:direct_route": 144,
  "check:force_boundary": 1008,
  "check:incorrect_target": 432,
  "check:maximum_valid_waypoints": 144,
  "check:obstacle_grazing": 864,
  "check:probe_geometry_only": 432,
  "check:workspace_boundary": 720,
  "checks": 4176,
  "constant_route_force_successes": 144,
  "direct_successes_twin_0": 0,
  "direct_successes_twin_1": 72,
  "episodes": 144,
  "expected_accepts": 1709,
  "expected_rejects": 1891,
  "passed_checks": 3835,
  "verdict_checks": 3600
}
```

Failure counts:

```json
{
  "false_accept": 144,
  "false_accept:workspace_boundary": 144,
  "false_reject": 197,
  "false_reject:obstacle_grazing": 197
}
```

The JSON report contains bounded examples and exact witnesses for each failure label.


## workflow

Acceptance is compared with explicit well-formed OOD witnesses, not merely disagreement with a reference string. The finite verifier cannot certify every unbounded input of its min/max DSL.

Counters:

```json
{
  "check:equivalent_workflow_expression": 720,
  "check:frozen_calibration_rejected": 144,
  "check:independent_fractional_signed_ood": 4320,
  "check:workflow_attack_witness_differs": 720,
  "check:workflow_ood_range_attack": 720,
  "checks": 6624,
  "episodes": 144,
  "expected_accepts": 720,
  "expected_rejects": 864,
  "passed_checks": 5904,
  "verdict_checks": 1584
}
```

Failure counts:

```json
{
  "false_accept": 720,
  "false_accept:workflow_ood_range_attack": 720
}
```

The JSON report contains bounded examples and exact witnesses for each failure label.

## Scope and interpretation

The source hashes, command arguments, actual seed lists, and bounded failure examples are in the adjacent JSON. Source files were not treated as a solver interface. Geometry checks cover sampled and targeted cases, not a formal proof of all possible JSON numeric inputs. Grid checks are finite and affine certificates are complete only inside the declared affine hypothesis class. Legal constant controls are reported as task-distribution shortcuts, not as false successes. Workflow threshold mutants test the stated unbounded new-input contract beyond the finite verifier suite.
