# Decision sufficiency under bounded observation uncertainty

Version 0.5 adds an exact finite audit of the question: **which observation is
worth buying before committing to an action?** Full hidden-state identification
is a different objective and can require more information than successful action.

## Explicit model

There is a finite set of initially possible worlds W. The true world stays fixed.
Each terminal action a has an integer cost and a set G(a) of worlds where it
succeeds. Each experiment q has positive integer cost and a nonempty support
O(q,w) of possible observations in each world. Supports may overlap. Experiments
are available once; after an observation the controller retains every compatible
world. No probability, independent-noise assumption, or sample-average guarantee
is inserted. Each per-world support table admits every cross-experiment
combination of supported readings; it does not encode joint restrictions
between sensors. This is robust finite uncertainty, not Bayesian estimation.

Let B be the current compatible-world set and R the remaining experiments. A
terminal action is admissible for guaranteed success exactly when B is a subset
of G(a). An observation z changes B to `{w in B : z in O(q,w)}`. The exact value
is the smallest of (i) the cost of any admissible terminal action and (ii) each
query cost plus its worst nonempty observation-branch value. A branch with no
guaranteed completion has value infinity, serialized as JSON null. Each query
removes itself from R, so recursion terminates even if a blurred observation
leaves B unchanged. Zero-cost successful actions permit immediate stopping.

For the identification objective, stopping costs zero and requires a singleton
belief. Always state whether terminal-action costs are included before comparing
the two objectives. The bundled demonstrations assign zero terminal costs so
their reported differences are exclusively observation cost.

## Checkable evidence

`causalfill/decision_sufficiency.py` contains a bitmask optimizer, a separate
set-based certificate checker, and a fixed-world policy replay. A certificate
binds the trusted normalized problem with SHA-256, names the objective, and
provides all subproblems needed for every legal alternative, not only the chosen
policy. A zero-cost successful terminal action is the explicit exception:
nonnegative costs already prove its optimality, so positive-cost queries may
be pruned. The checker rejects missing alternatives, forged values, duplicate
states, Boolean aliases, incorrect roots, and unsupported schema fields.

Each checked equality establishes a lower bound by considering every candidate
and an upper bound through a selected attaining action. The replay separately
checks every allowed outcome on the selected policy in each fixed world. These
are finite Python guarantees. They are not Lean proofs and do not prove that
a camera's actual noise lies inside a declared support. Resource caps return
an explicit error rather than an invented optimality result.

## Six useful controls

| Fixture | Decision sensing cost | Full identification cost | Interpretation |
|---|---:|---:|---|
| Decision | 1 | 4 | The lane is relevant; dry/wet identity is irrelevant to a slow action. |
| Robust | 0 | 4 | A common bypass makes further sensing unnecessary. |
| Ambiguous | No guaranteed solution | No guaranteed solution | Blur overlaps both lanes and can persist. |
| Noisy but resolvable | 2 | 5 | An alternative side view has multiple but lane-disjoint outcomes. |
| Conditional probes | 3 | 3 | A cheap selector chooses one of two expensive probes; best fixed sensing costs 4. |
| Action despite ambiguity | 1 | No guaranteed identification | Every possible reading supports a successful action although two worlds always remain compatible. |

The final fixture has worlds `left_only`, `shared`, `right_only`. Left succeeds
in the first two and right in the last two. The sensor returns L in the first,
R in the last, and either in the shared world. After either reading a successful
action is available; exact world identity is still ambiguous. This also shows
why "can share an action" is not generally an equivalence relation: the first
and middle worlds share an action, as do the middle and last, while the first
and last do not. The implementation retains the actual action-success sets
rather than incorrectly merging transitive clusters.

The adaptive fixture's fixed comparison chooses its entire sensor subset in
advance, then may use all returned observations to choose a terminal action.
It is not an artificially weak policy that must ignore sensor feedback.

## Stress and reproducibility

```bash
python -m unittest tests.test_decision_sufficiency -v
python tools/stress_decision_v05.py --cases 256 \
  --output private-runs/decision-stress-v05.json
```

The stress harness includes random finite support tables, exact fixed-subset
enumeration, cost scaling, representation reordering, reduced-noise monotonicity,
robust-action bounds, certificate forgery controls and selected-policy replay.
New seeds and assertions are correlated engineering cases, not independent
mechanisms or intelligence scores. The separate audit harness adds exhaustive
tiny adaptive-policy enumeration when listed in the release evidence.

## Relationship to rendered robotics

The renderer and robot task provide executable pixels and consequences. This
module provides an exact audit for a separately declared finite abstraction.
Passing both does not by itself establish that every pixel, noisy history,
camera pose, or physical action refines that abstraction. Keep those claims
separate. In particular, a damaging contact probe cannot be treated as a free
static observation: its state change belongs in a sequential transition model.
The existing finite belief-game machinery supports such finite transitions;
connecting a future physical simulator requires an explicit conformance study.

The underlying principles are established in partially observed planning and
active perception. The engineering contribution here is a transparent test
contract and independently inspectable evidence, not a claim of a new planning
algorithm or of being first to distinguish perception from action utility.
