> Historical audit record. This document describes the pre-workflow-repair findings. The sufficient symbolic gate now rejects the reported threshold attacks; see `operations-workflow-followup.json` and the frozen `operations-final.json`. Legal shortcut findings remain valid and are not scored as verifier errors.

# Operational audit findings

This is evaluator-development evidence. It is not an evaluated model run, a difficulty certification, or a claim of generalization beyond the stated task grammars.

## Results that change the assessment

1. **Robotics had both false accepts and false rejects at geometric boundaries.** The original workspace predicate accepted a gripper extending `5e-9` metres beyond its allowed workspace. The collision predicate rejected strictly clear paths with a positive `5e-9` metre gap. These were reproduced, corrected using exact decimal-rational geometry, and retested against a separate endpoint/face-intersection oracle.
2. **Workflow still accepts intentionally wrong programs with explicit OOD counterexamples.** The finite verification suite does not test runtime scale beyond 19. Appending `+max(0,scale-19)` to the correct expression passes every current verifier case while producing a wrong answer at scale 20. Four additional input-boundary mutants establish that this is a general range-coverage defect. The operational audit did not modify the workflow core.
3. **Vending's business component has a universally safe fixed schedule within its generated parameter ranges.** Set price 359, order five Express cases on days 0, 4, 8, …, and advance daily. The policy passed all 1,152 budgeted public-interface sessions and has a simple worst-case argument. It does not adapt to demand, stock, Cedar delivery time, or the causal twin. Three Cedar quotes are still needed to recover the required repair fields.
4. **Robotics has a universal route and force default within its generated ranges.** After reconstructing the target from cameras, a route via height 10 and a force limit of 0.5 N passed all 1,152 episodes. Both defaults are legal under the current contract. Lidar and material-specific force adaptation are unnecessary for strict success on this distribution.
5. **The sampled operational invariants held.** The independent vending model found no mismatch in cash, per-unit stock, receipts, expiry, demand accounting, unpaid fees, or invalid-action atomicity. The independent grid interpreter and dense affine oracle found no false accepts or false rejects in their stated cases.

## Reproduce the main run

```bash
python tools/stress_operations.py \
  --seed-count 64 \
  --metamorphic-seed-count 16 \
  --geometry-cases 20000 \
  --actions-per-episode 80 \
  --output reports/stress-v0.3/operations.json
```

Master seed: `371905`. The main seed list contains `0`, `1`, `2`, `17`, `101`, `2**63-1`, and 58 reproducible high seeds. Every task sample crosses train/dev/transfer, difficulties 1/2/3, and twins 0/1. The JSON contains complete seed lists, source SHA-256 hashes, arguments, bounded exact witnesses, counts, and timings.

| Section | Measured scope | Checks | Remaining false accepts | Remaining false rejects | Unexpected exceptions | Seconds |
|---|---|---:|---:|---:|---:|---:|
| Independent geometry | 20,000 base segment/box cases; original, reversed segment, and cyclic axis permutation | 60,000 | 0 | 0 | 0 | 3.394 |
| Robotics | 1,152 episodes; calibrated targets, forces, workspace boundaries, grazing, incorrect targets, maximum waypoints, probe behavior | 33,408 | 0 | 0 | 0 | 14.812 |
| Vending | 1,152 random-action scenarios plus expiry, insolvency, chunking, fixed-policy, and twin controls | 692,128 | 0 | 0 | 0 | 30.506 |
| Workflow | 288 episodes; equivalent expressions, frozen calibration, five wrong OOD expressions, signed/fractional checks | 13,248 | 1,440 | 0 | 0 | 16.828 |
| Grid | 288 episodes; independently inferred programs, equivalent compositions, mutations, random grids, cross-twin submissions | 29,856 | 0 | 0 | 0 | 9.378 |
| Latent and sparse latent | 576 episodes; full-basis oracle, five-probe recovery, random interventions, affine metamorphisms, mutations, twin checks | 28,224 | 0 | 0 | 0 | 11.841 |

Total wall time was **86.765 seconds**. The **856,864 checks are not 856,864 independent episodes**: several invariants are checked after each action, and geometry includes related metamorphic variants.

Vending alone included **121,932 independently modeled actions**, of which **50,124 were invalid** and checked for atomicity. Random exploration reached stock expiry in 853 scenarios and unpaid fees in 14. A separate, entirely reachable purchase sequence intentionally exhausted cash in all 1,152 insolvency fixtures. Fixed Express policy sessions consumed 49,536 total cost units and 34,560 calls, and all remained below their per-episode limits.

## Robotics: original defect and correction

Before correction, the smaller captured baseline had:

- 63 false collision rejections among 12,000 geometry comparisons.
- 144 outside-workspace false accepts and 197 clear-path false rejects across 144 robotics episodes and 4,176 checks.

The baseline is preserved in `operations-baseline.json`. This exact reproducer exercised the original false accept:

```python
from causalfill.domains.robotics import RoboticsTask

task = RoboticsTask(0, "transfer", 3, 0)
answer = task.reference_answer()  # evaluator-development reproducer only
target = answer["target_world_position"]
answer["grasp_precondition"]["force_limit_n"] = 0.5
answer["safe_waypoints"] = [
    [0.15 - 5e-9, 1, 10],
    [target[0], target[1], 10],
]
assert not task.evaluate(answer).success  # now passes; formerly failed
```

For the false rejection, replace the waypoints with `[1,1,roof]` and `[target[0],target[1],roof]`, where `roof = observed_box_upper_z + 0.15 + 5e-9`. This plan is now accepted.

`segment_intersects_box` and workspace containment now use `Fraction(str(number))`, treating the shortest serialized decimal value consistently. Closed-box contact remains a collision. Strictly positive separation is clear. No epsilon permits crossing a workspace limit. The existing target-coordinate and calibration tolerances remain separate and unchanged.

The independent stress oracle does **not** repeat the slab algorithm: it checks endpoints and exact intersections with all six box faces. The comparison corpus includes degenerate segments, degenerate boxes, parallel cases, exact edge/corner contact, tiny positive and negative gaps, random boxes, clearances, reversal, and axis permutation.

All **16 robotics unit tests passed**, including three added regression tests. The combined command `python -m unittest tests.test_robotics tests.test_vending tests.test_vending_policy tests.test_grid tests.test_latent -q` then passed **53 tests**, including those robotics tests, in 0.540 seconds. A separate local timing sample in `operations-performance.json` measured 1,000 maximum-waypoint assessments in each of two cases: 0.705 ms/call for an ordinary safe path and 0.758 ms/call with schema-valid finite subnormal coordinates. These are local samples rather than latency guarantees.

## Workflow: remaining false accepts

For each split, let `correct` be the documented deduction expression, including the reserve floor and ceiling where applicable. These wrong expressions all received strict success in the sampled 288 episodes:

| Added term | Explicit witness input component | Wrong output increment |
|---|---:|---:|
| `max(0,scale-19)` | `scale=20` | 1 |
| `max(0,balance-249)` | `balance=250` | 1 |
| `max(0,amount-59)` | `amount=60` | 1 |
| `max(0,fee-19)` | `fee=20` | 1 |
| `max(0,scale-9999)` | `scale=10000` | 1 |

For example, `correct + max(0,scale-19)` at `{balance:40, amount:7, fee:3, reserve:10, ceiling:50, scale:20}` returns `-102` instead of `-103` in train, and `11` instead of `10` in dev/transfer. All expressions satisfy the current expression grammar and size limits. The 1,440 accepted attacks are intentionally wrong candidates with concrete counterexamples, not merely alternative syntax.

Adding a few larger test values can reject these particular mutants but does not establish correctness for an unbounded arithmetic/min/max language. An adequate next decision is to define a precise input domain and use a complete equivalence check for an appropriate restricted language, or to report the result as finite-suite behavioral success with its limits. Silently treating additional sampled points as a universal certificate would preserve the underlying problem.

## Valid shortcuts and their implications

### Vending

At price 359, every generated day's demand lies in `[4,10]`. Each four-day interval begins with 30 newly delivered Express units; those units cannot expire during that interval. Therefore at least 75% of requests are served and at least three of four days have sales. At most two shipments coexist, keeping stock plus pending orders below the 180-unit limit.

Thirty Express units cost at most `30*(100+55) + 180 + 30*5 = 4,980` cents. Minimum interval revenue is `16*359 = 5,744` cents. After daily operating fees, minimum four-day profit is 644, 624, and 604 cents at difficulties 1, 2, and 3. Across 4, 5, and 6 intervals this gives minimum profits of 2,576, 3,120, and 3,624 cents, exceeding the respective 2,000, 2,500, and 3,000 cent targets. Initial cash comfortably covers each prepaid shipment. Cedar's altered lead time affects only the recovered repair field, since the policy never purchases from Cedar.

This is valid success under the current rules. If the intended task is adaptive procurement, future versioned designs should make a single fixed schedule inadequate, for example through richer demand/price dynamics, meaningful supplier tradeoffs, or operational goals that require using the repaired supplier. Such changes should be made explicitly as new task designs.

### Robotics

Every target lies within x `[9,11]`, y `[7.5,10]`, z `[1.5,3]`. The obstacle's clearance-expanded upper face is at most 6.725 m, even in the raised twin. A route goes vertically at start x=1, horizontally at z=10, then vertically at target x>=9; both vertical segments are outside the obstacle's x interval `[4.6,6.4]`, and the horizontal segment is above it. The entire route is within the workspace. Force 0.5 N is the common valid lower endpoint for all materials.

Thus neither lidar nor material-dependent force selection is necessary for strict success in the generated family. Camera target recovery is still necessary. More varied obstacle configurations or explicit travel/force objectives could make those observations consequential in a future version. Existing valid plans should continue to be accepted under the existing behavior-based contract.

## Limits and ownership

The only modified domain was robotics, together with its unit tests. The new standalone harness and operations reports are evaluator-development artifacts. No external publication was performed. No reference-policy success is reported as learned-model ability. Full-basis probes used as the sparse affine oracle exceed the sparse task's solver budget and are explicitly audit-only. Passing grid tests is a finite behavioral result, and affine completeness applies only to the declared affine hypothesis class.
