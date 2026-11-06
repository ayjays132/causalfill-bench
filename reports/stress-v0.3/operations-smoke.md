# Operational stress audit

Evaluator-development checks; no model-performance or certified-difficulty claim.

Master seed: `371905`. Total wall time: 3.737 seconds.

| Section | Checks | False accepts | False rejects | Oracle mismatches | Unexpected exceptions | Seconds |
|---|---:|---:|---:|---:|---:|---:|
| geometry | 1200 | 0 | 0 | 0 | 0 | 0.074 |
| robotics | 1044 | 0 | 0 | 0 | 0 | 0.505 |
| vending | 6025 | 0 | 0 | 0 | 0 | 0.216 |
| grid | 3732 | 0 | 0 | 0 | 0 | 1.304 |
| latent | 3528 | 0 | 0 | 0 | 0 | 1.633 |

## geometry

Exact decimal-rational oracle tests segment endpoints and all six box faces; the implementation under test uses its own predicate.

Counters:

```json
{
  "check:exact_segment_geometry": 1200,
  "checks": 1200,
  "expected_accepts": 1017,
  "expected_rejects": 183,
  "passed_checks": 1200,
  "segment_comparisons": 1200,
  "verdict_checks": 1200
}
```


## robotics

Targets are reconstructed by independent exact Gaussian calibration from camera observations. All route verdicts use the independent face-intersection oracle.

A fixed z=10 detour and fixed 0.5 N force is a legal shortcut control; successes are not classified as verifier false accepts.

Counters:

```json
{
  "check:closed_gripper": 36,
  "check:constant_route_force": 36,
  "check:defensive_lidar_copy": 36,
  "check:direct_route": 36,
  "check:force_boundary": 252,
  "check:incorrect_target": 108,
  "check:maximum_valid_waypoints": 36,
  "check:obstacle_grazing": 216,
  "check:probe_geometry_only": 108,
  "check:workspace_boundary": 180,
  "checks": 1044,
  "constant_route_force_successes": 36,
  "direct_successes_twin_0": 0,
  "direct_successes_twin_1": 18,
  "episodes": 36,
  "expected_accepts": 425,
  "expected_rejects": 475,
  "passed_checks": 1044,
  "verdict_checks": 900
}
```


## vending

Independent unit inventory oracle uses three public quotes, public forecast and initial constants; hidden noise is copied once only as evaluator-side exogenous scenario data.

The fixed Express controller sets price 359 and orders five cases on days 0,4,8,...; it receives three Cedar quotes solely to fill the required coefficients. It is a scripted shortcut control, not a model result.

Counters:

```json
{
  "actions": 1050,
  "check:advance_chunking_equivalence": 36,
  "check:cash_conservation": 1050,
  "check:expiry_day_is_inclusive": 36,
  "check:expiry_next_day_removes_stock": 36,
  "check:fee_obligation_conservation": 1050,
  "check:fixed_controller_within_budget": 36,
  "check:independent_quote_arithmetic": 24,
  "check:invalid_world_atomicity": 295,
  "check:quote_does_not_mutate_world": 24,
  "check:stock_conservation": 1050,
  "check:unit_inventory_and_cash_oracle": 1050,
  "check:vending_action_contract": 1050,
  "check:vending_defensive_copies": 36,
  "check:vending_final_outcome": 36,
  "check:wrong_procurement_field_rejected": 180,
  "check:zero_demand_does_not_pass": 36,
  "checks": 6025,
  "expected_accepts": 756,
  "expected_rejects": 546,
  "fixed_express_episodes": 36,
  "fixed_express_successes": 36,
  "fixed_express_successes:dev:d1:t0": 2,
  "fixed_express_successes:dev:d1:t1": 2,
  "fixed_express_successes:dev:d2:t0": 2,
  "fixed_express_successes:dev:d2:t1": 2,
  "fixed_express_successes:dev:d3:t0": 2,
  "fixed_express_successes:dev:d3:t1": 2,
  "fixed_express_successes:train:d1:t0": 2,
  "fixed_express_successes:train:d1:t1": 2,
  "fixed_express_successes:train:d2:t0": 2,
  "fixed_express_successes:train:d2:t1": 2,
  "fixed_express_successes:train:d3:t0": 2,
  "fixed_express_successes:train:d3:t1": 2,
  "fixed_express_successes:transfer:d1:t0": 2,
  "fixed_express_successes:transfer:d1:t1": 2,
  "fixed_express_successes:transfer:d2:t0": 2,
  "fixed_express_successes:transfer:d2:t1": 2,
  "fixed_express_successes:transfer:d3:t0": 2,
  "fixed_express_successes:transfer:d3:t1": 2,
  "fuzz_episodes": 36,
  "invalid_actions": 295,
  "passed_checks": 6025,
  "reachable_expiry_episodes": 14,
  "reachable_unpaid_fee_episodes": 0,
  "valid_actions": 755,
  "verdict_checks": 1302
}
```


## grid

Uses an independent coordinate-index grid interpreter and evidence-filtered public grammar enumeration; no generator interpreter or reference-answer calls are used.

Counters:

```json
{
  "check:cross_twin_grid_rejected": 36,
  "check:equivalent_grid_composition": 36,
  "check:fixed_grid_default_adjudicated": 36,
  "check:grid_composition_metamorphism": 1728,
  "check:incorrect_grid_program_rejected": 96,
  "check:independent_grid_semantics": 1728,
  "check:independently_recovered_grid_program": 36,
  "check:public_observations_identify_grid_program": 36,
  "checks": 3732,
  "episodes": 36,
  "expected_accepts": 74,
  "expected_rejects": 166,
  "fixed_grid_default_successes": 2,
  "passed_checks": 3732,
  "verdict_checks": 240
}
```


## latent

Dense full-basis recovery is an evaluator-side exact oracle. For SparseLatentTask it exceeds the nine-unit solver budget and is never reported as budgeted policy success.

Counters:

```json
{
  "check:affine_addition_metamorphism": 1440,
  "check:dense_basis_certificate_accepted": 72,
  "check:dense_random_affine_interventions": 1440,
  "check:five_probe_recovery_matches_dense_oracle": 72,
  "check:latent_cross_twin_rejected": 72,
  "check:latent_mutation_rejected": 288,
  "check:latent_single_coefficient_twin": 72,
  "check:reordered_zero_augmented_matrix": 72,
  "checks": 3528,
  "episodes": 72,
  "expected_accepts": 144,
  "expected_rejects": 360,
  "passed_checks": 3528,
  "verdict_checks": 504
}
```

## Scope and interpretation

The source hashes, command arguments, actual seed lists, and bounded failure examples are in the adjacent JSON. Source files were not treated as a solver interface. Geometry checks cover sampled and targeted cases, not a formal proof of all possible JSON numeric inputs. Grid checks are finite and affine certificates are complete only inside the declared affine hypothesis class. Legal constant controls are reported as task-distribution shortcuts, not as false successes. Workflow threshold mutants test the stated unbounded new-input contract beyond the finite verifier suite.
