# Finite evolving-state games and exact cost certificates

The v0.4 core checks a specific claim: **within a bounded, explicitly listed,
deterministic, partially observed game, this is the minimum worst-case total
action cost that guarantees success from every possible initial state**. It
checks both an attaining policy and the lower bound against every available
alternative. `null` means that no policy in the declared class guarantees
success. It does not mean zero success probability or zero expected reward.

The environment can change after an action. A procurement order can spend cash,
commit inventory, and make a later observation too late to prevent failure.
This extends the earlier static diagnosis table to finite contingent planning.
The algorithms are classical belief-space planning and AND/OR dynamic
programming; the contribution here is their explicit, independently checked
benchmark contract and connection to the operational task.

## What is public during a scored episode

The schema, algorithms, restrictions, and tests are published. A scored solver
receives the task's compact public contract and actual tool feedback. The
evaluator's compiled transition table, reference certificates, selected hidden
world, task object, and generation seeds are not episode tools or solver
inputs. The solver may independently reason from the public hypotheses or
build its own model. Publishing a complete development example for certificate
inspection does not authorize access to evaluator artifacts in a live run.

These utilities are author/evaluator tools. Their explicit input contains all
possible model states but never a field identifying which state is currently
real. The strategy format branches only on observation strings; it has no
hidden-world selector.

## Exact semantics

An adversary selects one initial state before the first action. Every state and
action then has at most one successor. There are no stochastic transitions or
numerical prior probabilities. The initial list is a possibility set, and a
guarantee quantifies over its entire contents.

A state has a nonnegative integer rank. Live states have positive rank;
terminal success and failure states have rank zero and no outgoing edges.
Every transition strictly reduces rank. This bounds action sequences and rules
out cycles without a heuristic depth cutoff. Every action costs a strictly
positive integer. Costs are fixed per action, public, and independent of the
hidden world. They measure the declared benchmark action budget. Economic
spending, final cash, elapsed market days, wall-clock time, and token use are
separate quantities; any of these that matter for success must be encoded in
the task state and outcome.

After an action, the policy receives the successor state's observation token.
The token must include every piece of public feedback relevant to the claimed
model. Equal tokens must expose the same live/terminal status and the same
available action set. Terminal success and failure may share a token: the
episode can be over while its correctness remains evaluator-private. All
initial states must have the same token, so the initial list represents actual
uncertainty before any action. A live state may have no available actions; it
then cannot guarantee success.

The four policy classes have different meanings:

| Mode | Allowed actions | Feedback used to select the next action |
| --- | --- | --- |
| `adaptive` | All declared actions | All modeled observation tokens |
| `no_observe` | Actions with `kind="act"` | All modeled operational feedback |
| `open_loop` | All declared actions | None; one fixed action sequence |
| `open_loop_no_observe` | Actions with `kind="act"` | None; one fixed action sequence |

`no_observe` removes actions explicitly tagged as paid experiments. It still
allows adaptation to delivery receipts, past demand, and other feedback from
ordinary operation. It is therefore not a no-feedback baseline. `open_loop`
forbids dependence on every observation, including information returned by
ordinary actions. Allowing an observation action in that mode is deliberate:
the policy can pay for it, but cannot use its result to change its script.

In an ignored-feedback mode, some worlds may reach success before others. A
successful world is absorbing and incurs no further execution cost; the common
script can continue in the remaining live worlds. A common action must be
available in every live world. The last live world pays the entire common
prefix, so the scalar sum-of-action-costs recurrence equals the worst-case
execution cost. A failure in any possible world makes guaranteed success
impossible. In the adaptive modes, observation consistency prevents a live
world from sharing an information set with a terminal one.

## Bounded JSON statement

`causalfill/belief_games.py` validates the strict `finite-belief-game-v1`
statement. Unknown fields, duplicate transitions, undeclared action IDs,
Boolean aliases for integers, floating-point costs, and invalid Unicode are
rejected. List order identifies state indices and is part of the canonical
SHA-256 binding.

| Object | Required fields |
| --- | --- |
| Game | `schema_version`, `actions`, `states`, `initial` |
| Action | `id`, `cost`, `kind` (`observe` or `act`) |
| State | `rank`, `observation`, `outcome` (`live`, `success`, or `failure`), `transitions` |
| Transition | `action` (declared ID), `next` (state index) |

The explicit bounds are 8,192 states, 32 action IDs, 32 possible initial states,
65,536 transitions, rank 64, and action costs from 1 through 1,000. Observation
tokens are at most 4,096 characters. Canonical game encoding is at most 8 MiB.
Certificates have at most 20,000 belief nodes and a 16 MiB encoding. Attaining
strategies have at most 2,049 nodes, and any finite guaranteed cost is at most
64,000. The state cap accommodates the measured 8,192-state maximum of the
current four-stage development procurement compiler without removing legal
supplier or experiment alternatives.

These are accepted-input limits, not a guarantee of a particular OS memory
limit or deadline. A valid raw game can still exceed the reachable-belief cap;
the producer then raises an error rather than reporting an optimum. Since
deterministic transitions cannot increase the number of possibilities, a
reachable belief contains at most 32 state IDs.

## Optimizer, lower bound, and attaining strategy

A belief is the set of current states compatible with a public action and
observation history. Adaptive modes partition successor states by their exact
observation strings. Ignored-feedback modes merge all successors into one
set. Restrictions determine the available actions before this operation.

For belief \(B\), let \(B_{a,o}\) be a nonempty successor information set after
action \(a\) and possible observation \(o\). The extended value domain is the
nonnegative integers plus infinity (`null` in JSON). The recurrence is:

\[
V(B)=
\begin{cases}
0 & \text{if every state in }B\text{ is successful},\\
\infty & \text{if any state in }B\text{ has failed},\\
\min_a\left(c(a)+\max_o V(B_{a,o})\right)&\text{otherwise}.
\end{cases}
\]

The minimum of an empty set is infinity. An action with any infinite child is
infinite. The policy must succeed for every observation that the current
possibilities can actually produce, but does not need branches for impossible
observations.

The rank of a belief is the maximum rank of its states. Every nonterminal
successor information set has strictly smaller rank, including an ignored-
feedback set containing previously successful worlds. This gives induction
over a finite DAG:

1. A successful belief needs no more actions, while a failed world cannot be
   repaired within the model.
2. Every permitted policy must choose some available first action. Its
   worst-case remaining cost is at least the greatest lower bound over that
   action's possible observation branches. Checking **all** first actions
   proves the lower bound at the current belief.
3. An action attaining the minimum, followed by an attaining child policy on
   each possible observation, achieves that bound. Induction constructs the
   upper-bound witness.

This covers all finite, observation-history-dependent policies in the declared
class, not only policies generated by the optimizer. Two histories with the
same belief have the same feasible continuation problem because transitions,
costs, and goal status depend on the modeled state. A belief policy suffices to
attain the optimum. Randomization cannot improve a success guarantee that must
hold for every possible initial world and every realized random choice.

`build_game_certificate` uses memoized bit-set beliefs. It records the value
and one attaining action for every belief reachable through **any legal
alternative**, including alternatives not selected by its proposed policy.
Goal and failure beliefs stop exploration. Lexicographic tie-breaking in the
producer is just a reproducibility choice; an alternative action with the
same exact value is accepted by the checker.

`verify_game_certificate` reconstructs transitions using its own tuple/set
implementation. It does not call the producer's optimizer or bit-set update.
It checks every allowed action and nonempty observation branch, the full
Bellman equality, the attaining action, the initial uncertainty set, and the
game hash. It rejects missing alternative children, duplicate beliefs,
unreachable extra beliefs, wrong bounds, false impossibility claims, and
cross-mode certificates. Shared strict schema parsing remains trusted Python
code.

`extract_game_strategy` constructs an observation-only policy DAG from a valid
finite certificate. `verify_game_strategy` then replays that policy separately
from every initial world in the raw parsed transition model, without the
Bellman recurrence or either belief update implementation. It checks legal
actions, policy restrictions, exact branch coverage, terminal success, horizon,
and per-world costs. A strategy can pass this replay even if it is suboptimal:
the strategy checker proves an upper bound, while the complete value
certificate is what proves optimality.

## API example

```python
from causalfill.belief_games import build_game_certificate
from causalfill.belief_certificates import (
    extract_game_strategy,
    verify_game_certificate,
    verify_game_strategy,
)

# `game` is an evaluator-authored explicit statement, not a live task object.
certificate = build_game_certificate(game, mode="adaptive")
bound = verify_game_certificate(game, certificate)
assert bound["valid"]

if bound["winning"]:
    policy = extract_game_strategy(game, certificate)
    replay = verify_game_strategy(game, policy)
    assert replay["valid"]
    assert replay["worst_case_cost"] == bound["optimal_cost"]

fixed_certificate = build_game_certificate(game, mode="open_loop")
fixed_bound = verify_game_certificate(game, fixed_certificate)
# An infinite fixed bound says no one fixed script wins in every initial world.
```

Neither infinity in a restricted mode nor a large optimal cost establishes
human or model difficulty. A trained solver can exploit regularities in the
contract; empirical performance needs separate, properly isolated evaluation.

## Operational and formal trust boundaries

The exact result is conditional on the transition model. Runtime conformance
must establish that every relevant action, debit, observation, irreversible
outcome, and available-action restriction matches actual execution. An
unmodeled free observation can invalidate a lower bound. A hidden-state-
dependent invalid-action error can be an experiment even if the error was
intended as an implementation detail. Missing transitions mean unavailable
actions, not secretly permitted error probes. Status, quote, file, and ledger
reads can be omitted as stuttering actions only when they add no hidden
information or useful state change; their real budget charges still need
separate accounting. Reference-model optimal cost is not automatically the
entire episode cost of setup, term recovery, file completion, and submission.

`expand_game_certificate` exports a checked `finite-belief-arena-v1` DAG for
formal tooling. Each node records its belief, rank, goal/failure-cut status,
value, selected action, and **all** choices with their costs and child IDs.
Children have lower rank and lower indices. The export binds the raw game and
certificate hashes. A theorem about this AND/OR arena can establish the generic
lower/upper bound argument or a concrete arena result. It does not, by itself,
prove that Python constructed the right arena, that JSON parsing is sound, or
that the arena equals an external simulator. Preserving the raw game,
certificate, export, and exact round-trip comparison makes those boundaries
reviewable rather than removing them.

This core does not solve arbitrary cyclic POMDPs, estimate expected reward,
certify Bayesian optimality, prove a probability of fixed-script success, or
formally verify the Python interpreter. It certifies the finite robust problem
defined above. A future probability/cost Pareto extension would require explicit
probability semantics and a separately checked attainable frontier.

## Recorded verification

`tests/test_belief_games.py` contains semantic, corruption, schema, and
independence checks. It exercises fresh information after irreversible actions,
the distinction between no experiments and no feedback, a robust valid action
that needs no experiment, alternative optimal actions, suboptimal valid
strategies, early successful worlds in fixed scripts, and malformed policy or
bound submissions.

The numerical oracle enumerates every complete three-decision binary-feedback
policy assignment for small randomly generated layered games and simulates the
raw transition lists. It shares neither the Bellman recurrence nor a production
belief update. Assignments for unreachable histories are still counted, so the
count is of **syntactic policies**, not distinct realized behaviors or
independent tasks.

The recorded 256-game run checks all four policy classes: 1,024 exact optimum
comparisons across 601,600 complete syntactic policies, with no discrepancies.
It replays 916 attaining policies and checks 108 unsolvable game/mode pairs.
The report records the seed, per-mode counts, source hashes, transcript hash,
and elapsed time at
`reports/stress-v0.4/belief-games-independent-audit.json`. These are internal
AI-assisted implementation tests, not external replication or measured
language-model scores.

Reproduce the local checks with:

```bash
python -m unittest tests.test_belief_games -v
python -m tests.test_belief_games \
  --audit-output reports/stress-v0.4/belief-games-independent-audit.json \
  --games 256
```

## Planning literature

The use of information sets and contingent actions follows established work.
For belief-state planning under incomplete information, see Bonet and Geffner,
[Planning with Incomplete Information as Heuristic Search in Belief Space](https://cdn.aaai.org/AIPS/2000/AIPS00-006.pdf)
(AIPS 2000). For the wider stochastic partially observed setting and its
distinction from this finite deterministic robust special case, see Kaelbling,
Littman, and Cassandra,
[Planning and Acting in Partially Observable Stochastic Domains](https://www.cassandra.org/arc/papers/aij98.pdf)
(Artificial Intelligence, 1998). These sources motivate the planning framework;
the correctness and scope of this implementation must be assessed from its own
contracts, checkers, and evidence.
