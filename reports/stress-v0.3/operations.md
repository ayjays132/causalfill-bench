# Operational stress audit

Evaluator-development checks; no model-performance or certified-difficulty claim.

Master seed: `371905`. Total wall time: 86.765 seconds.

| Section | Checks | False accepts | False rejects | Oracle mismatches | Unexpected exceptions | Seconds |
|---|---:|---:|---:|---:|---:|---:|
| geometry | 60000 | 0 | 0 | 0 | 0 | 3.394 |
| robotics | 33408 | 0 | 0 | 0 | 0 | 14.812 |
| vending | 692128 | 0 | 0 | 0 | 0 | 30.506 |
| workflow | 13248 | 1440 | 0 | 0 | 0 | 16.828 |
| grid | 29856 | 0 | 0 | 0 | 0 | 9.378 |
| latent | 28224 | 0 | 0 | 0 | 0 | 11.841 |

## geometry

Exact decimal-rational oracle tests segment endpoints and all six box faces; the implementation under test uses its own predicate.

Counters:

```json
{
  "check:exact_segment_geometry": 60000,
  "checks": 60000,
  "expected_accepts": 58839,
  "expected_rejects": 1161,
  "passed_checks": 60000,
  "segment_comparisons": 60000,
  "verdict_checks": 60000
}
```


## robotics

Targets are reconstructed by independent exact Gaussian calibration from camera observations. All route verdicts use the independent face-intersection oracle.

A fixed z=10 detour and fixed 0.5 N force is a legal shortcut control; successes are not classified as verifier false accepts.

Counters:

```json
{
  "check:closed_gripper": 1152,
  "check:constant_route_force": 1152,
  "check:defensive_lidar_copy": 1152,
  "check:direct_route": 1152,
  "check:force_boundary": 8064,
  "check:incorrect_target": 3456,
  "check:maximum_valid_waypoints": 1152,
  "check:obstacle_grazing": 6912,
  "check:probe_geometry_only": 3456,
  "check:workspace_boundary": 5760,
  "checks": 33408,
  "constant_route_force_successes": 1152,
  "direct_successes_twin_0": 0,
  "direct_successes_twin_1": 576,
  "episodes": 1152,
  "expected_accepts": 13629,
  "expected_rejects": 15171,
  "passed_checks": 33408,
  "verdict_checks": 28800
}
```


## vending

Independent unit inventory oracle uses three public quotes, public forecast and initial constants; hidden noise is copied once only as evaluator-side exogenous scenario data.

The fixed Express controller sets price 359 and orders five cases on days 0,4,8,...; it receives three Cedar quotes solely to fill the required coefficients and one initial status for the horizon. It runs through the budgeted Session interface. It is a scripted shortcut control, not a model result.

Counters:

```json
{
  "actions": 121932,
  "check:advance_chunking_equivalence": 1152,
  "check:cash_conservation": 121932,
  "check:expiry_day_is_inclusive": 1152,
  "check:expiry_next_day_removes_stock": 1152,
  "check:express_trajectory_independent_of_cedar_twin": 576,
  "check:fee_obligation_conservation": 121932,
  "check:fixed_controller_session_result": 1152,
  "check:fixed_controller_within_budget": 1152,
  "check:independent_quote_arithmetic": 6956,
  "check:invalid_world_atomicity": 50124,
  "check:quote_does_not_mutate_world": 6956,
  "check:reachable_insolvency_records_unpaid_fees": 1152,
  "check:stock_conservation": 121932,
  "check:unit_inventory_and_cash_oracle": 121932,
  "check:unpaid_fees_fail_invariant_score": 1152,
  "check:vending_action_contract": 121932,
  "check:vending_defensive_copies": 1152,
  "check:vending_final_outcome": 1152,
  "check:vending_twin_single_lead_parameter": 576,
  "check:wrong_procurement_field_rejected": 5760,
  "check:zero_demand_does_not_pass": 1152,
  "checks": 692128,
  "constructed_insolvent_episodes": 1152,
  "expected_accepts": 72048,
  "expected_rejects": 57948,
  "fixed_controller_tool_calls_total": 34560,
  "fixed_controller_tool_cost_total": 49536,
  "fixed_express_episodes": 1152,
  "fixed_express_successes": 1152,
  "fixed_express_successes:dev:d1:t0": 64,
  "fixed_express_successes:dev:d1:t1": 64,
  "fixed_express_successes:dev:d2:t0": 64,
  "fixed_express_successes:dev:d2:t1": 64,
  "fixed_express_successes:dev:d3:t0": 64,
  "fixed_express_successes:dev:d3:t1": 64,
  "fixed_express_successes:train:d1:t0": 64,
  "fixed_express_successes:train:d1:t1": 64,
  "fixed_express_successes:train:d2:t0": 64,
  "fixed_express_successes:train:d2:t1": 64,
  "fixed_express_successes:train:d3:t0": 64,
  "fixed_express_successes:train:d3:t1": 64,
  "fixed_express_successes:transfer:d1:t0": 64,
  "fixed_express_successes:transfer:d1:t1": 64,
  "fixed_express_successes:transfer:d2:t0": 64,
  "fixed_express_successes:transfer:d2:t1": 64,
  "fixed_express_successes:transfer:d3:t0": 64,
  "fixed_express_successes:transfer:d3:t1": 64,
  "fuzz_episodes": 1152,
  "invalid_actions": 50124,
  "passed_checks": 692128,
  "reachable_expiry_episodes": 853,
  "reachable_unpaid_fee_episodes": 14,
  "valid_actions": 71808,
  "verdict_checks": 129996
}
```


## workflow

Acceptance is compared with explicit well-formed OOD witnesses, not merely disagreement with a reference string. The finite verifier cannot certify every unbounded input of its min/max DSL.

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
  "passed_checks": 11808,
  "verdict_checks": 3168
}
```

Failure counts:

```json
{
  "false_accept": 1440,
  "false_accept:workflow_ood_range_attack": 1440
}
```

The JSON report contains bounded examples and exact witnesses for each failure label.


## grid

Uses an independent coordinate-index grid interpreter and evidence-filtered public grammar enumeration; no generator interpreter or reference-answer calls are used.

Counters:

```json
{
  "check:cross_twin_grid_rejected": 288,
  "check:equivalent_grid_composition": 288,
  "check:fixed_grid_default_adjudicated": 288,
  "check:grid_composition_metamorphism": 13824,
  "check:incorrect_grid_program_rejected": 768,
  "check:independent_grid_semantics": 13824,
  "check:independently_recovered_grid_program": 288,
  "check:public_observations_identify_grid_program": 288,
  "checks": 29856,
  "episodes": 288,
  "expected_accepts": 585,
  "expected_rejects": 1335,
  "fixed_grid_default_successes": 9,
  "passed_checks": 29856,
  "verdict_checks": 1920
}
```


## latent

Dense full-basis recovery is an evaluator-side exact oracle. For SparseLatentTask it exceeds the nine-unit solver budget and is never reported as budgeted policy success.

Counters:

```json
{
  "check:affine_addition_metamorphism": 11520,
  "check:dense_basis_certificate_accepted": 576,
  "check:dense_random_affine_interventions": 11520,
  "check:five_probe_recovery_matches_dense_oracle": 576,
  "check:latent_cross_twin_rejected": 576,
  "check:latent_mutation_rejected": 2304,
  "check:latent_single_coefficient_twin": 576,
  "check:reordered_zero_augmented_matrix": 576,
  "checks": 28224,
  "episodes": 576,
  "expected_accepts": 1152,
  "expected_rejects": 2880,
  "passed_checks": 28224,
  "verdict_checks": 4032
}
```

## Scope and interpretation

The source hashes, command arguments, actual seed lists, and bounded failure examples are in the adjacent JSON. Source files were not treated as a solver interface. Geometry checks cover sampled and targeted cases, not a formal proof of all possible JSON numeric inputs. Grid checks are finite and affine certificates are complete only inside the declared affine hypothesis class. Legal constant controls are reported as task-distribution shortcuts, not as false successes. Workflow threshold mutants test the stated unbounded new-input contract beyond the finite verifier suite.
