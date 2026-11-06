# Certified experiment planning and diagnosis

## What this track establishes

`DiagnosisTask` evaluates an agent's ability to choose informative experiments and justify a recovered diagnosis from actual observations. It supplies a finite, explicit set of candidate worlds, with a binary response table for the permitted experiments. One world is current. The table contains hypotheses, not a mark identifying the correct row.

The task has 8, 16 or 32 worlds and 6, 8 or 10 experiments at difficulty 1, 2 or 3. The allowed number of experiments is the **exact minimum worst-case number of adaptive binary queries** needed to distinguish all rows of the supplied table. The task constructor verifies a complete recurrence certificate and a separate decision-tree certificate before exposing an episode.

This is a mathematically checkable resource statement about a finite noiseless experiment table. It is not a claim that a strong language model finds the task hard, that the model's computation is optimal, or that a research conjecture has been proved. Exact learning and membership-query complexity are established subjects. Relevant primary sources include [Bshouty and Haddad-Zaknoon, 2019](https://proceedings.mlr.press/v98/bshouty19a.html) and [General lower bounds on query complexity within the exact learning model](https://doi.org/10.1016/S0166-218X(99)00223-1).

## Public contract

The virtual file `/formal/diagnosis.json` contains:

- The full response table, with world IDs as row indices and experiment IDs as column indices.
- A SHA-256 digest binding the certificate to that exact table.
- The independently checked experiment budget.
- The elementary binary information lower bound, `ceil(log2(number_of_worlds))`.

The single domain tool is `experiment({"id": q})`. It returns the current world's binary response for column q and consumes one experiment. Repeating an experiment still counts. The domain enforces the experiment cap separately from the session's total cost: saving a document read cannot buy an extra experiment. Two additional cost units permit reading the table and optional manual. The final submission is free.

The private target-world index, selected strategy, and complete minimax certificate are not agent-facing files or tools. The certificate depends only on the public hypothesis table; an evaluator can export it through `decision_certificate()` for independent review. The task-aware reference can reconstruct the strategy from the public table itself.

## A completion must carry evidence

The submitted fill has exactly these fields:

```json
{
  "world": 4,
  "eliminations": [
    {"world": 0, "experiment": 2},
    {"world": 1, "experiment": 3}
  ]
}
```

The abbreviated example above is schematic; an actual answer must cover every other world exactly once. For each competing world, the cited experiment must have actually been performed, and its observed output must contradict that competitor's row. The selected world must agree with all observations. The outer session's `evidence` field uses trace event IDs separately; the elimination certificate uses experiment column IDs.

A lucky correct world guess with no elimination evidence fails. A fabricated experiment ID fails. Covering only some competitors fails. Observations must uniquely distinguish the proposed world before strict success is possible. These conditions make the completion a certificate of identification from allowed information rather than a bare oracle match.

## The exact minimax claim

Let S be the nonempty set of worlds still consistent with observed outputs. An experiment q partitions S into S0 and S1. Experiments that do not split S provide no information and can be omitted without making an optimal strategy worse.

For a singleton, D(S)=0. Otherwise:

```text
D(S) = 1 + min over informative q of max(D(S0), D(S1)).
```

The optimizer computes these depths with memoization. Its result is not trusted merely because the optimizer ran. The certificate lists each reachable candidate-set bit mask, its claimed depth, and one selected query. The independent checker validates:

1. The immutable table digest and full root state.
2. The singleton base cases.
3. Every informative query's two smaller child states, including queries the selected strategy does not use.
4. Equality of each claimed depth to the minimum over all child worst cases.
5. An optimal selected query at every non-singleton state.
6. Complete reachability, absence of duplicate states, and resource bounds.

Every child has fewer possible worlds, so induction on set cardinality establishes the recurrence. Checking **all** informative alternatives establishes a lower bound as well as a matching upper bound. Checking only the selected strategy would establish only an upper bound.

A separate set-based tree verifier traverses the selected strategy and checks that each leaf corresponds to exactly its one possible world. It independently measures the maximum root-to-leaf depth. It does not call the optimizer. Neither checker is a Lean formalization; the trust base includes the short Python checker, interpreter, hashing and table semantics. Tests include independent small-table reasoning, tampering, and validation with the optimizer disabled.

## Why the information bound alone is insufficient

Four worlds require at least two bits of information. But consider these response rows:

```text
world 0: [0, 0, 0]
world 1: [1, 0, 0]
world 2: [0, 1, 0]
world 3: [0, 0, 1]
```

Every available first query splits the worlds 1:3 rather than 2:2. In the worst case, three queries are necessary. The full recurrence certificate verifies depth 3, while the elementary binary information lower bound is only 2. A forged depth-2 certificate is rejected. This is a useful distinction between an abstract information limit and the actual observations an agent is allowed to choose.

## Structural splits and paired interpretation

- **Train:** direct latent bits plus parity sensors; an explicit easy control.
- **Dev:** randomly generated distinct binary response rows, yielding general experiment partitions.
- **Transfer:** conditional sensors with a gating variable; identifying the gate reveals which sensor group is informative.

Rows, columns and response polarities are relabeled without marking the current world. These are three finite sensor-table families. Their structural distinction is real, but public generators do not form a private generalization benchmark.

The twin changes only the current categorical world, preserving the response table, budget and certificate. This is labeled `twin_kind="diagnostic_state"`. It tests robustness across two diagnostic states. It is not a physical single-variable intervention in a robot or economy, and must not be conflated with those domains' causal interpretations.

## APIs and constructive reference

`causalfill.decision_certificates` exports:

```python
build_decision_certificate(table)
verify_decision_certificate(table, certificate)
extract_decision_tree(table, certificate)
verify_decision_tree(table, tree)
information_lower_bound(world_count)
elimination_certificate(table, observations, world)
solve_diagnosis(public, call)
```

`solve_diagnosis` receives only a public episode dictionary and the allowed tool callback. It reads the table, independently checks the advertised query budget, follows a computed optimal strategy, and returns the identified world plus observed elimination witnesses. It never receives a task object or consults the target-world index. Its result is a **task-aware scripted reference**, not a model score.

For privileged development checks, replay `task.reference_actions()` through the session before calling `task.reference_answer()`. A reference answer alone cannot manufacture evidence: the domain records only real experiment calls.

## Verification scope and limits

All responses are noiseless and deterministic, and every candidate is guaranteed to be in the finite table. There are no latent continuous states, missing candidate models or experiment costs beyond one unit each. Optimal query count ignores the potentially substantial computation required to find the optimal strategy. Worlds are capped at 32 and experiment columns at 12; production task generators use at most 10 columns. The certificate implementation rejects malformed tables, repeated rows, invalid integer types and oversized certificates.

This track supplies independently checkable finite guarantees and a stronger evidence contract. It does not establish that the whole benchmark is formally verified, axiomatically novel or empirically frontier-hard.
