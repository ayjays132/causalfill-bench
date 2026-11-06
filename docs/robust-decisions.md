# Decisions under a shared corruption budget

`causalfill.robust_decisions` checks finite decision problems in which a fixed
hidden world determines every truthful binary reading, but an adversary can flip
at most `max_corruptions` of the readings requested during an episode. The
corruption allowance belongs to the **whole transcript**. It is not a separate
allowance for each sensor, and it is not a probability of sensor failure.

The module computes the exact minimum worst-case cost of obtaining enough
evidence and taking a successful terminal action. A separate objective computes
the cost of identifying the exact world. These objectives can differ sharply:
several possible worlds may share a successful action.

This is an author/evaluator component for bounded public models. Its exactness
does not establish the accuracy of a physical sensor table, a fault bound in a
robot, a stochastic noise distribution, or a trained agent's performance. It adds
no Lean theorem or proof of equivalence between a runtime and its model.

## Public problem

```json
{
  "schema": "causalfill.robust-decision.v1",
  "worlds": ["left", "right"],
  "max_corruptions": 1,
  "actions": [
    {"id": "go_left", "cost": 2, "success_worlds": ["left"]},
    {"id": "go_right", "cost": 2, "success_worlds": ["right"]}
  ],
  "experiments": [
    {"id": "sensor_a", "cost": 1, "responses": {"left": 0, "right": 1}},
    {"id": "sensor_b", "cost": 1, "responses": {"left": 0, "right": 1}},
    {"id": "sensor_c", "cost": 1, "responses": {"left": 0, "right": 1}}
  ]
}
```

Each experiment can be requested **once**. Repeated measurements must be listed
as distinct experiments, so their availability and total cost are explicit.
Truthful readings are deterministic integers `0` or `1`. Query costs are positive
integers; terminal action costs are nonnegative integers. Success sets may
overlap, may be empty, or may contain every world. An empty action list is valid
and permits identification-only problems.

In this example, three queries are sufficient in the worst case to tolerate one
flipped reading. A policy can stop after two equal readings. Its worst-case action
cost is `3 + 2 = 5`, whereas its identification cost is `3`. Two available readings
cannot guarantee either exclusive action under one possible flip.

Unlike the earlier `decision_sufficiency` support model, the robust model retains
information about how much of the corruption allowance each candidate world
would have consumed. Giving every sensor independent support `{0, 1}` would lose
that information and would allow arbitrarily many inconsistent readings.

## Belief state and the fixed-world assumption

For the observed transcript `[(q_1, y_1), ..., (q_t, y_t)]`, define

\[
m_w = \sum_{i=1}^{t} \mathbf{1}[r(q_i,w) \ne y_i].
\]

`m_w` is the minimum number of flips needed to explain the transcript in world
`w`. A world remains possible exactly when `m_w <= k`. A single disagreement
therefore cannot eliminate a world when `k = 1`. Discarding such a world would
make the evaluation depend on an unjustified assumption that an early reading
was truthful.

The finite state stores the discrepancy vector, clipped at `k + 1`, together with
the set of unrequested experiments. Clipping is sound because an excluded world
cannot re-enter the possible-world set: later observations never reduce its
discrepancy count. `evidence_state` also returns the full, unclipped counts and the
observed conflicting experiment IDs for inspection.

Although the optimizer considers the worst feasible observation at each step,
it does not permit the hidden world to change. Every feasible complete path has
at least one fixed listed world whose total discrepancy count is at most `k`.
The separate policy verifier checks this directly by selecting each world first
and then enumerating permitted flip choices along its requested queries.

An empty possible-world set indicates a transcript outside the published model
and fault bound. It is never accepted as vacuous evidence that every action is
safe.

## What the exact certificate establishes

Let `S` be the nonempty possible-world set and `R` the remaining experiments. A
terminal action is permitted when its success set contains all of `S`. For the
action objective, its terminal value is its published cost. For identification,
the terminal value is zero only when `S` has one world.

For each available query `q`, the alternative value is its cost plus the maximum
value of its feasible observation children. A query cannot guarantee success if
any feasible child has no successful continuation. The state value is the minimum
over valid terminal choices and all query alternatives. If there is no valid
alternative, the value is JSON `null`, meaning that guaranteed completion is
impossible under these assumptions.

The optimizer and checker use separate implementations:

| Component | Representation and check | Claim |
| --- | --- | --- |
| Optimizer | Disjoint bitmask layers for worlds requiring 0, 1, or 2 flips | Proposes a value and an attaining choice for every required state |
| Certificate checker | Integer discrepancy tuples, explicit sets of worlds, and independently constructed children | Checks every available query alternative and every feasible observation child, establishing the exact value |
| Policy verifier | Fixed world, executed query IDs, consumed flips, and explicit observed branches | Checks success and total cost for every permitted corruption history of that policy; establishes an upper bound |
| Evidence checker | Conflicting IDs from the supplied observed transcript | Checks whether one proposed action is justified by those observations |

The only shortcut in the complete alternative certificate is a valid terminal
choice with cost zero. All costs are nonnegative, so no further query can improve
that value. Every positive-value state covers every remaining query, including
queries not chosen by the attaining policy. Removing an alternative child,
changing its claimed value, or choosing a nonattaining branch invalidates the
certificate. Unreachable surplus rows also invalidate the strict format.

A policy can pass replay with a declared cost larger than the true optimum.
Replay is intentionally not an optimality test. For example, an immediate
universally safe action with cost 12 may pass replay even when a separate
certificate proves that sensing permits guaranteed completion for cost 3.

## API and artifacts

```python
from causalfill.robust_decisions import (
    build_robust_certificate,
    extract_robust_policy,
    verify_robust_certificate,
    verify_robust_policy,
)

certificate = build_robust_certificate(problem, objective="action")
checked = verify_robust_certificate(
    problem, certificate, expected_objective="action"
)
assert checked["valid"]
if certificate["value"] is not None:
    policy = extract_robust_policy(problem, certificate)
    replay = verify_robust_policy(problem, policy, expected_objective="action")
    assert replay["valid"]
```

`validate_problem(problem)` returns a fresh normalized dictionary and raises
`ValueError` for unsupported inputs. `problem_digest(problem)` computes SHA-256
over canonical JSON of that normalized model. The digest includes truthful
responses, action success sets, all costs, experiment availability, and the
corruption bound. World, action, and experiment list order is retained; action
success sets are sorted during normalization.

Both verifiers return `{valid: false, error: ...}` on rejected inputs. Both accept
an optional `expected_objective` keyword. Evaluators should supply that argument
when the requested objective is fixed outside the claimant artifact: a correct
identification certificate is not automatically the requested action-cost claim.

The certificate schema is `causalfill.robust-certificate.v1`. Its `root` is
`[[0, ..., 0], remaining_mask]`; `value` is an integer or `null`; each row in
`nodes` is:

```text
[clipped_mismatch_counts, remaining_mask, value, choice]
```

`choice` is `{kind: "query" | "act" | "identify", id: ...}`, or `null` for an
impossible state. Bit positions in `remaining_mask` follow the public experiment
list. The certificate also records `problem_sha256` and `objective`.

The extracted policy schema is `causalfill.robust-policy.v1`. It records the
problem digest, objective, root node index, cost `budget`, and a node list. A
query node has `{kind: "query", id: ..., branches: {"0": i, "1": j}}`; terminal
nodes have `{kind: "act" | "identify", id: ...}`. Only feasible observation edges
are included. The format rejects unreachable nodes or edges, unknown IDs,
repeated experiments, and reachable cycles.

Replay's `corruption_histories_checked` counts terminal histories of the actual
adaptive policy, summed over fixed worlds. It does not multiply by hypothetical
faults on queries the policy never requests. Memoization combines equivalent
continuations while preserving exact history multiplicities and cost extrema.
These counts are verifier coverage units, not independent samples, benchmark
episodes, seeds, or trained-model successes.

## Observed evidence and masked completion

The evidence API accepts records of the form:

```python
observations = [
    {"experiment": "sensor_a", "outcome": 1},
    {"experiment": "sensor_b", "outcome": 0},
    {"experiment": "sensor_c", "outcome": 0},
]
```

Here `left` remains possible with one required flip, and `right` is excluded by
the distinct contradictions `sensor_b` and `sensor_c`. A masked completion can
justify `go_left` with that two-conflict exclusion witness.

`evidence_state(problem, observations)` returns `possible_worlds`,
`mismatch_counts`, `conflicts`, `state`, `remaining_experiments`, `query_cost`, the
observation count, the corruption bound, and the problem digest.

`completion_exclusions(problem, observations, action_id)` constructs one minimal
witness for every world where the proposed action fails.
`verify_completion_evidence(problem, observations, action_id, exclusions)` checks
the proposal and, when exclusions are supplied, requires each unsafe world to
have exactly `k + 1` distinct, actually observed contradictions. Duplicate
experiments, invented observations, missing unsafe worlds, and contradictions
that agree with the purported excluded world are rejected. Worlds that share a
successful action require no exclusion witness or fabricated identification.

The `robust_sensing` task runtime also accepts longer exclusion witnesses: at
least `k + 1` distinct observed contradictions for each unsafe world. The core
helper uses exactly `k + 1` as its canonical minimal format. Both accept the
minimal witnesses produced by `completion_exclusions` or the task's public
history-based completion helper; neither accepts repeated or unobserved IDs.

The evidence helper permits omitted witnesses for analysis; a task that requires
a filled witness must pass the submitted exclusion list explicitly. The task
must also check the submitted problem digest and must derive the observations
from its actual tool transcript. A valid evidence result does not itself execute
an action, enforce a runtime spending limit, or prove that a claimant supplied
the real observation history. Those are responsibilities of the task runtime.

## Analytic fixtures and boundary checks

The unit suite includes several families with independently derived values:

- **Repeated binary reading.** Two worlds disagree on every listed query. Three
  readings correct one possible flip; five correct two. Four cannot guarantee
  an exclusive decision when two flips are allowed. Early stopping and terminal
  action costs are checked separately.
- **Exclude one pattern.** Worlds are every `m`-bit pattern, coordinate queries
  have costs `c_i`, and action `a_x` succeeds except in pattern `x`. For `k < m`
  and equal terminal action cost `alpha`, the exact action value is `alpha` plus
  the sum of the `k + 1` cheapest coordinate costs. Before that many readings,
  every pattern remains possible. After them, the pattern opposite all observed
  bits has at least `k + 1` discrepancies and can be excluded. For `k >= m`, no
  such guaranteed decision exists. A universal action of cost `beta` changes the
  optimum to the minimum of `beta` and the sensing-based value.
- **Three-bit parity family.** Eight worlds, seven nonzero parity queries, and
  four actions that each fail on one low-two-bit class have action value 2 and
  identification value 6 under one possible flip. Two coordinate readings
  exclude the opposite low-bit class. Identification with five binary readings
  is impossible because `8 * (5 + 1) > 2**5`; six of the seven parity coordinates
  retain pairwise distance at least three. With no corruptions, the respective
  values are 1 and 3.
- **No-fault equivalence.** Random small `k = 0` models are checked against the
  existing singleton-support decision-sufficiency engine for both objectives.

The tests also check observation-only witness reconstruction, overlapping action
success, robust bypasses, certificate and policy forgery, missing alternatives,
objective confusion, malformed JSON, exact integer typing, content binding,
explicit resource exhaustion, and the independent operation of the checker and
fixed-world policy replay when optimizer functions are unavailable.

Run the owned unit suite with:

```bash
python -m unittest tests.test_robust_decisions -v
```

## Bounds, input boundary, and remaining limits

| Resource | Supported bound |
| --- | ---: |
| Listed worlds | 1–32 |
| Experiments | 0–12 |
| Terminal actions | 0–64 |
| Global corruptions | 0–2 |
| Individual integer cost | 0–1,000,000 for actions; 1–1,000,000 for queries |
| Certificate states / policy nodes | 100,000 |
| Memoized fixed-world replay states | 1,000,000 |
| Canonical problem JSON | 1 MiB |
| Certificate / policy JSON | 32 MiB |
| Strict JSON nesting depth | 32 |

These are explicit supported limits, not promises that every maximum-size model
will fit the state cap. With `q` once-only binary queries there are at most
`3**q` partial query assignments before state merging: each query is unasked,
observed zero, or observed one. Ten queries fit below the state cap on this
count; twelve need not. A state or byte cap failure produces an explicit error
and makes no optimality or complete-replay claim. It never silently substitutes a
greedy policy, partial search, or sampled adversary.

`load_robust_json` is the strict bytes-to-object parser. It rejects duplicate
object keys, nonfinite numbers, floating-point tokens, oversized integers,
invalid UTF-8, and excessive size or nesting. Object-taking APIs cannot detect
duplicate keys already discarded by a different parser. Use the strict reader
or an equivalently strict task boundary before checking an external artifact.
The checker also enforces exact fields, complete response tables, distinct IDs,
and integer fields that reject Python boolean aliases.

The trusted boundary still includes the normalizer, parser, hash implementation,
checker code, Python runtime, and the declared model itself. A digest detects
different model content; it does not authenticate who published that model.
Separate optimizer, checker, and replay representations reduce shared
implementation errors but do not remove this trusted computing base. Realistic
robotics also requires a justified hypothesis set, causal interventions, sensor
calibration, actuator checks, and evidence that the stated fault limit applies.
The finite certificates alone do not establish those properties.
