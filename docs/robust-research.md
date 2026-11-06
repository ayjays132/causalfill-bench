# Bounded-fault decisions: research, exact fixtures, and proof scope

This extension adds one missing semantic guarantee to the restored v0.5.0
release: several binary sensors share **one global bound on corrupted answers**.
The previous decision-sufficiency model permits each experiment to return any
member of its per-world support. Its own documentation correctly explains that
these independent supports cannot express a shared fault allowance. New random
seeds would not repair that distinction.

The intended outcome is an independently checkable benchmark component. The
design does not establish a new planning algorithm, a novel mathematical
problem, physical robot robustness, or measured frontier-model difficulty.
Results from the new implementation, formal gate, stress suite, and any model
evaluation must be reported separately.

## Primary sources and prior-art boundaries

The following sources motivate different parts of the design. Their findings
are not measurements of CausalFill.

1. **Osthus and Watkinson, 2008, “A simple solution to Ulam's liar game with one
   lie.”** [Official EMS paper](https://ems.press/content/serial-article-files/45347?nt=1).
   A fixed hidden object, adaptive yes/no questions, a bounded number of lies,
   and worst-case query complexity are established mathematical objects.
   CausalFill's corruption cap must be presented as an application of this
   tradition. The present finite experiment catalogue and overlapping terminal
   success sets change the benchmark contract, not that history.

2. **Javdani et al., 2014, “Near Optimal Bayesian Active Learning for Decision
   Making.”** [AISTATS/PMLR paper](https://proceedings.mlr.press/v33/javdani14.html).
   Decision-region determination permits overlapping regions and seeks enough
   evidence for a valid decision without demanding exact hypothesis recovery.
   That is the right prior-art boundary for successful action under residual
   ambiguity. The proposed worst-case, globally bounded corruption objective
   differs from the paper's Bayesian objective.

3. **Dennis et al., NeurIPS 2020, “Emergent Complexity and Zero-shot Transfer
   via Unsupervised Environment Design.”** [Primary conference paper](https://proceedings.neurips.cc/paper_files/paper/2020/hash/985e9a46e10005356bbaf194249f6856-Abstract.html).
   PAIRED uses an antagonist and a regret objective to avoid an adversary
   winning merely by choosing impossible environments. For this finite module,
   an exact feasibility and optimal-cost certificate can provide a simpler
   task-generation gate. That is an implementation choice; it is not a claim
   to have invented regret-based environment design or reproduced its learned
   transfer results.

4. **Kaelbling, Littman, and Cassandra, 1998, “Planning and acting in partially
   observable stochastic domains.”** [Author-hosted primary paper](https://people.csail.mit.edu/lpk/papers/aij98-pomdp.pdf).
   Partial observations make policies depend on the evolving information
   state, while sensing may consume resources or affect the world. The
   bounded-fault model below deliberately has a fixed world and once-only
   queries. It does not inherit a probabilistic confidence interpretation from
   POMDPs and does not yet cover destructive probes or changing physical state.

5. **ARC Prize Foundation, April 22, 2026, “ARC-AGI-3: A New Challenge for
   Frontier Agentic Intelligence.”** [Primary technical report](https://arcprize.org/media/ARC_AGI_3_Technical_Report.pdf).
   Its human validation, action-efficiency calibration, and separate held-out
   environments are useful evaluation practices. CausalFill should likewise
   separate human solvability, public-interface model runs, action costs, and
   mechanism holdouts. Historical model scores in that report are not current
   CausalFill results. Fresh seeds within one generator are not independently
   authored reasoning mechanisms.

### Current workflow references, checked November 5, 2026

**OpenAI's mathematical artifacts.** The official
[`openai/math` Lean README](https://github.com/openai/math/blob/main/lean/README.md)
directs verification to its
[Comparator challenge instructions](https://github.com/openai/math/blob/main/lean/ComparatorChallenges/README.md).
The upstream [Comparator documentation](https://github.com/leanprover/comparator)
separates agreement with the requested statement, the permitted-axiom check,
and kernel acceptance. We adopt that separation through explicit expected-type
bindings, an axiom inventory, source snapshots, and proof replay. Our type audit
has a narrower scope than Comparator's independent statement/environment
comparison. We did not run Comparator or Lake's paranoid build orchestration,
and did not reproduce or verify the repository's mathematical research results.

**Axiom's proof-of-concept workflow.** Axiom's
[February 5, 2026 case study](https://axiommath.ai/research/proof-of-concept/)
describes supplied statements and definitions, formal target construction,
intermediate lemmas, and a Lean/Mathlib proof artifact accepted by a checker.
The practice adopted here is to make the target, assumptions, proof artifact,
and actual checker result inspectable. “Axiom-level” is an aspiration for this
discipline, not a claim that this benchmark matches Axiom's system or reproduces
its research result. Failed verification attempts and repaired follow-ups are
preserved with their source snapshots.

**ARC-AGI-3 and Vending-Bench 2.** The
[ARC-AGI-3 report](https://arcprize.org/media/ARC_AGI_3_Technical_Report.pdf)
motivates evaluating information gathering through interaction and keeping
human calibration separate from solver scores. Andon Labs'
[Vending-Bench 2](https://andonlabs.com/evals/vending-bench-2), released in 2025,
evaluates sustained tool use and resource management over a simulated business
year, including unreliable or adversarial suppliers. We adopt the need to
preserve accepted observation/action histories, resource charges, and terminal
outcomes so that loss of accumulated evidence is auditable. This bounded-fault
component is a short finite diagnostic; it does not reproduce Vending-Bench's
long time horizon, economic environment, or leaderboard results. The separate
GPT-Red and 100D positioning remains in `docs/related-work.md`.

## Mathematical contract

Let `W` be a nonempty finite list of distinct world IDs. One world remains fixed
throughout an episode. Every experiment `q` has a positive integer cost and a
published deterministic truthful response `t(q,w)` in `{0,1}` for every world.
An experiment may be used at most once. At most `k` reported answer bits differ
from the truthful responses over the **entire** episode. The adversary may
choose which answers to flip after seeing earlier actions; no probabilities,
independence, or stochastic stationarity are assumed.

Each terminal action `a` has a nonnegative integer cost and an explicitly
published success set `G(a)`. Success sets may overlap. Total budget includes
the queries and the terminal action. The empty feasible-world set denotes an
unreachable observation branch under the declared model; it is not a successful
vacuous terminal action.

For a transcript `h`, define the candidate world's debt

\[
d_h(w)=\#\{(q,z)\in h:t(q,w)\ne z\}.
\]

The feasible candidates are exactly those with `d_h(w) <= k`. On reading bit
`z` from a new experiment `q`, the update is

\[
d_{h+(q,z)}(w)=d_h(w)+[t(q,w)\ne z].
\]

Counts can be saturated at `k+1`, since an excluded world never becomes feasible
again. The sufficient information state is the debt vector together with the
remaining experiment set. A set of surviving world IDs alone is insufficient.
For example, with two worlds whose truthful sensor values are always 0 and 1,
cap 1, and a first reading of 0 versus 1, both worlds survive in both histories.
Their debts are respectively `(0,1)` and `(1,0)`. A subsequent reading of 0
excludes the second world in the first history but retains both worlds in the
second. A world-set-only merge would therefore change the legal transitions.

A terminal action is justified when every surviving world is in its success
set. The optimal worst-case cost is the minimum over safe terminal costs and
query cost plus the maximum of all nonempty successor costs. Every query
removes itself from the remaining set, so this finite recursion is acyclic.
An impossibility value must remain distinct from zero cost and from a missing
certificate row. Lower-bound verification needs every legal alternative,
unless a zero-cost safe action already supplies the global lower bound of zero.

### Proof-carrying final actions

For each published world outside the selected action's success set, a solver
can cite `k+1` **distinct actual transcript occurrences** that contradict that
world. Such a world would require more errors than the shared cap permits.
The runtime fill uses distinct experiment IDs, each resolved to an accepted
pre-commit observation. Because experiments are once-only, these query IDs
identify unique transcript occurrences. The session envelope separately carries
observed event IDs. A submitted query ID must resolve to the actual recorded
query and reported bit; repeating one query ID does not create more evidence.

The generic Lean witness is a subsequence of the contradictory transcript
occurrences. This preserves occurrence identity and cannot reuse a single
occurrence. The runtime's experiment-ID representation and once-only checks
must still be checked and tested independently; they are not silently equated
with that Lean definition.

## Independent exact-cost fixtures

The following expectations were derived before receiving results from the new
optimizer. They are useful regression oracles, not claims that these small
instances are frontier-hard.

### A. Weighted complement actions

Take all `m`-bit patterns as worlds. Coordinate query `i` reveals bit `i` once,
at positive cost `c_i`. Action `a_x` succeeds on every world except pattern
`x`. Give all these terminal actions the same cost `alpha >= 0`.

For `k < m`, the exact robust optimum is

\[
\alpha+\sum_{i\text{ among the }k+1\text{ cheapest queries}}c_i.
\]

**Lower bound.** After at most `k` readings every world remains possible: even
if every observed coordinate contradicts a particular world, the required
number of errors is at most `k`. Each action fails on some remaining world, so
no safe action is available yet. Every successful path therefore pays for at
least `k+1` distinct coordinates, whose total cost is at least the stated sum,
and then pays `alpha`.

**Upper bound.** Query the `k+1` cheapest coordinates. Choose any pattern `x`
that is opposite to every reported bit on those queried coordinates. World `x`
would require `k+1` corruptions and is excluded. Action `a_x` succeeds on all
remaining worlds.

If `k >= m`, even the entire observation sequence leaves every world feasible,
so these actions cannot guarantee success. Adding a universal action of cost
`beta` changes the optimum to the minimum of `beta` and the finite expression
above; in the impossible case the universal action is the only guaranteed
option. With `beta=0`, a verifier can exercise its zero-cost stopping rule.
Adding nuisance copies of every bit pattern preserves decision cost while
making exact identity recovery impossible.

Concrete small cases:

| Coordinates | Corruption cap | Query costs | Terminal cost | Exact robust decision cost |
|---|---:|---|---:|---:|
| 2 | 0 | 2, 5 | 3 | 5 |
| 2 | 1 | 2, 5 | 3 | 10 |
| 2 | 2 | 2, 5 | 3 | impossible |
| 3 | 1 | 7, 2, 5 | 1 | 8 |
| 4 | 2 | 9, 1, 6, 3 | 2 | 12 |

### B. Two queries for action, six for identification

Let worlds be `w = 0,...,7`, interpreted as three-bit vectors. The seven
unit-cost experiments are the nonzero binary linear forms
`t(q_s,w) = parity(w & s)`, for masks `s = 1,...,7`. Let four zero-cost actions
`a_j`, `j = 0,...,3`, fail exactly on worlds satisfying `(w & 3) == j`.
Each action succeeds in six of the eight worlds. In world-bitmask notation the
four success sets are `[238, 221, 187, 119]`.

With cap 1, the **exact decision cost is 2**. Query masks 1 and 2, then choose
the action whose forbidden low-bit pattern is opposite to both reported bits.
That forbidden pattern would require two errors. One query cannot suffice,
since every world can explain any single reading with at most one flip.

The **exact identification cost is 6**. If a depth-five adaptive policy
identified all eight worlds with at most one lie, each world would require six
distinct possible length-five answer strings: no lie, or one lie at each of the
five positions. Strings belonging to different worlds must be disjoint. This
would require `8 * (5+1) = 48` strings, but only `2^5 = 32` exist. Early-stopping
policies can be padded with unused queries, so they do not evade this lower
bound. Conversely, for each nonzero three-bit difference, exactly four of the
seven nonzero masks have odd parity. The seven-bit simplex code therefore has
pairwise distance four; puncturing any one coordinate leaves distance at least three. Any six queries
therefore permit correction of one corrupted bit and identify the world.

With cap zero the same family has decision cost 1 and identification cost 3.
With cap two, full seven-query identification is impossible because codeword
distance four is at most twice the error radius. A separately written small
enumeration suggested decision cost 5 for cap two. That last numerical value
is an exploratory expectation to be checked by the new certificate machinery,
not a Lean theorem or a new closed-form result in this document.

## Stress plan and falsifiable failure modes

The exact fixtures support more than a pass-count target:

* Check the weighted family across supported `m`, `k`, uneven costs, terminal
  costs, universal actions, and nuisance copies. Compare both the optimizer and
  the separately implemented certificate checker with the analytic result.
* Replay a chosen policy for each fixed world, allowing an honest answer always
  and a flipped answer only while that world's used-fault count is below `k`.
  Replay must not reset the corruption allowance on each query.
* Preserve state pairs with identical live worlds but different debt layers.
  Check that an over-budget world cannot reappear after later honest readings.
* Mutate root values, child debts, remaining-query masks, chosen experiments,
  action success sets, claimed budgets, and required alternative branches.
  Missing rows, duplicate states, unreachable extra rows, and stale problem
  digests should have explicit rejection reasons.
* Exercise terminal witnesses with repeated query IDs, invented query IDs, an
  unqueried experiment, fewer than `k+1` contradictions, and a
  witness against a currently feasible world. A lucky successful action in the
  selected world does not replace the requested robust justification.
* Check query and action cost boundaries, exact-budget success, one-unit-below
  failure, once-only enforcement, and state/budget atomicity after rejected
  calls. Metadata should not reveal the selected world or hidden used faults.
* Apply semantics-preserving world/query/action renamings, column bit
  complements with matching reported-bit relabeling, and permutations. Check
  that adding a query cannot increase optimal cost, raising the corruption cap
  cannot decrease it, and multiplying all costs by a positive integer scales
  every finite optimum by that integer.

These tests target concrete failures: treating a noisy reading as certain,
forgetting shared error debt, merging incompatible information states, accepting
duplicate evidence, and spending the action budget on unnecessary exact
identification. They do not demonstrate general perception, physical sensor
calibration, or safety on an actual robot.

## Difficulty calibration and robotics relevance

An exact certificate supplies a solvability gate and a reference cost, not a
model difficulty score. A proposed generator should reject impossible cases
from the answerable pool, keep intentionally impossible cases in a separate
abstention pool, and require an attaining policy within the advertised budget.
An adversary can then seek large measured gaps between a fixed public solver
and the exact attainable cost, while development attacks stay separate from
the held-out evaluation pool.

Use budget curves around the certified optimum rather than one oversized
budget. Freeze generator version, solver prompt/skills, model identifier,
sampling settings, tool contracts, resource limits, and scoring rules before
evaluation. Report robust justification, actual selected-world outcome,
abstention, query cost, terminal-action cost, tokens, and elapsed time as
separate quantities. Independent structural families and human attempts are
needed before claiming broad difficulty or human calibration. Scripted
references and privileged optimizers are not model performance.

For robotics this is a controlled diagnostic of **action under bounded sensor
contradictions**: choose a grasp, route, or fixture that is valid across all
remaining hypotheses while preserving enough resources to act. Transferring
that lesson to a robot requires separate evidence that the robot's faults fit
the declared cap and truthful table, that its actions and dynamics match the
world model, and that observation extraction works. Persistent degradation,
continuous noise, moving objects, contact-dependent measurements, and probes
that alter the world need richer state models. No probability of success follows
from a deterministic corruption cap alone.

## Formal assurance boundary

The new Lean entry points are `formal/CausalFill/BoundedFault.lean`,
`formal/BoundedFaultAudit.lean`, and `formal/BoundedFaultExport.lean`; their root
inventory is separate from the unchanged earlier formal release. The intended
claims are exact mismatch accounting for honest/flip realizations, capped
updates, preservation of any true world within the global cap, permanent
exclusion, occurrence-supported exclusion witnesses, and safe actions over
overlapping success regions.

`formal/verify_bounded_fault.py` is the reproducible gate. Its saved report,
source hashes, axiom inventory, statement-binding controls, and independent
kernel results determine which checks actually ran. The theorem statements
require a fixed true world in the declared world list and an actual corruption
count within the cap. They do not prove the optimizer's Bellman result, general
Python equivalence, sensor hardware assumptions, physical execution, or frontier
model performance. A well-typed proof of a weakened statement must fail the
separate expected-statement audit; a corrupted proof term must be rejected by
the checking backends with the intended type-failure diagnostic.

The completed v0.5.1 extension gate is
[`formal/verification-v051-fault/run-02/results.json`](../formal/verification-v051-fault/run-02/results.json).
All 14 selected claims and all 14 separately written expected-type bindings
passed. The audit used only the three declared standard axioms. All six checker
configurations accepted the valid export and rejected its deliberately
corrupted proof with the intended type-failure diagnostics. Both well-typed
weakened-statement controls were rejected by the unchanged type audit. The
[assurance report](../formal/verification-v051-fault/README.md) describes the
other negative controls, reproduction command, preserved first harness failure,
and exact trust boundaries. These measured checks do not turn the separate
analytic cost arguments or the Python optimizer into Lean-verified results.
