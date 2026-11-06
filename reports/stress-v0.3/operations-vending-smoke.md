# Operational stress audit

Evaluator-development checks; no model-performance or certified-difficulty claim.

Master seed: `371905`. Total wall time: 0.377 seconds.

| Section | Checks | False accepts | False rejects | Oracle mismatches | Unexpected exceptions | Seconds |
|---|---:|---:|---:|---:|---:|---:|
| vending | 9511 | 0 | 0 | 0 | 0 | 0.376 |

## vending

Independent unit inventory oracle uses three public quotes, public forecast and initial constants; hidden noise is copied once only as evaluator-side exogenous scenario data.

The fixed Express controller sets price 359 and orders five cases on days 0,4,8,...; it receives three Cedar quotes solely to fill the required coefficients and one initial status for the horizon. It runs through the budgeted Session interface. It is a scripted shortcut control, not a model result.

Counters:

```json
{
  "actions": 1685,
  "check:advance_chunking_equivalence": 36,
  "check:cash_conservation": 1685,
  "check:expiry_day_is_inclusive": 36,
  "check:expiry_next_day_removes_stock": 36,
  "check:express_trajectory_independent_of_cedar_twin": 18,
  "check:fee_obligation_conservation": 1685,
  "check:fixed_controller_session_result": 36,
  "check:fixed_controller_within_budget": 36,
  "check:independent_quote_arithmetic": 43,
  "check:invalid_world_atomicity": 424,
  "check:quote_does_not_mutate_world": 43,
  "check:reachable_insolvency_records_unpaid_fees": 36,
  "check:stock_conservation": 1685,
  "check:unit_inventory_and_cash_oracle": 1685,
  "check:unpaid_fees_fail_invariant_score": 36,
  "check:vending_action_contract": 1685,
  "check:vending_defensive_copies": 36,
  "check:vending_final_outcome": 36,
  "check:vending_twin_single_lead_parameter": 18,
  "check:wrong_procurement_field_rejected": 180,
  "check:zero_demand_does_not_pass": 36,
  "checks": 9511,
  "constructed_insolvent_episodes": 36,
  "expected_accepts": 1266,
  "expected_rejects": 671,
  "fixed_controller_tool_calls_total": 1080,
  "fixed_controller_tool_cost_total": 1548,
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
  "invalid_actions": 424,
  "passed_checks": 9511,
  "reachable_expiry_episodes": 19,
  "reachable_unpaid_fee_episodes": 1,
  "valid_actions": 1261,
  "verdict_checks": 1937
}
```

## Scope and interpretation

The source hashes, command arguments, actual seed lists, and bounded failure examples are in the adjacent JSON. Source files were not treated as a solver interface. Geometry checks cover sampled and targeted cases, not a formal proof of all possible JSON numeric inputs. Grid checks are finite and affine certificates are complete only inside the declared affine hypothesis class. Legal constant controls are reported as task-distribution shortcuts, not as false successes. Workflow threshold mutants test the stated unbounded new-input contract beyond the finite verifier suite.
