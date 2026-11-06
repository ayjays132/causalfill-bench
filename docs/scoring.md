# Scoring and uncertainty — v0.5.0

`causalfill.metrics.summarize(records, bootstrap_seed=0, n_bootstrap=1000)` accepts
evaluator result dictionaries, including the fields emitted by `Session`. It
returns JSON-compatible data. It does not execute agents or reinterpret a
reference controller as a model result.

## Headline: macro family success on answerable tasks

For each family, divide successful answerable episodes by all answerable episodes.
An abstention on an answerable task remains a failure in this denominator. Take
the unweighted mean of those family rates. A family containing only unanswerable
episodes is not included in the capability average.

This gives each represented family equal weight, regardless of how many seeds it
has. It does not automatically make a small synthetic family representative of a
real-world capability. Family definitions and task counts must be published.

Version 0.5.0 has fourteen task configurations across nine conceptual domains:
`words`/`ambiguity`, `latent`/`latent_sparse`, `robotics`/`robotics_barrier`/`robotics_vision`, and
`vending`/`vending_adaptive`
each share a conceptual domain. The analyzer uses the actual `family` labels
in records, so base and challenge configurations retain separate weights.
The unanswerable `ambiguity` control is excluded from the capability mean.
An average with nine conceptual-domain weights requires an explicit
pre-registered remapping. Headlines across versions are not directly comparable
when the task roster, semantics or weighting differ.

Correctly abstaining on an impossible task never raises the capability headline.
Report that behavior through the separate unanswerable correct-abstention metric.
There is no aggregate combining capability, safety, cost, and abstention.

| Metric | Numerator and denominator |
| --- | --- |
| `solvable_success_rate` | Successful answerable episodes / all answerable episodes. This is the episode-weighted micro rate, distinct from the headline. |
| `unanswerable_correct_abstention_rate` | Abstentions on unanswerable episodes / all unanswerable episodes. |
| `coverage` | Non-abstained episodes / all episodes. |
| `answered_accuracy` | Strictly successful episodes / all non-abstained episodes. An answered unanswerable task counts as wrong. |
| `solvable_coverage` | Non-abstained answerable episodes / all answerable episodes. |
| `solvable_answered_accuracy` | Successful answerable episodes / non-abstained answerable episodes. |
| `decision_accuracy` | Correct answers or correct unanswerable abstentions / all episodes. It is a separate decision diagnostic, not the capability headline. |
| `invalid_call_episode_rate` | Episodes with at least one invalid call / episodes recording invalid-call counts. |

`metric_means` reports tool cost, tool calls, wall time, recovery, outcome, safety,
invalid calls, and decision Brier score separately. Each entry has `mean` and `n`.
Missing optional fields are excluded from that metric and never assumed to be
zero. Undefined ratios and unavailable intervals are `null`.

The decision Brier score is the `Session` value `(confidence - decision_correct)^2`.
Here confidence refers to the correctness of the overall answer-or-abstain
decision. Lower is better. If both confidence and Brier are supplied, the analyzer
checks consistency. It does not treat confidence as a calibrated probability
merely because it appears in a result record.

## Certificate tracks and strict success

The `proof` task succeeds only if the exact fixed statement digest matches, a
valid resolution refutation proves its signed conclusion, and the supplied
Boolean model satisfies the original premises. Proof length, a valid incomplete
prefix, a matching digest, or a plausible explanation cannot substitute for
these combined obligations. Evaluator diagnostics expose statement binding,
refutation validity, premise consistency and checked step count separately.

The `diagnosis` task succeeds only if the chosen world is correct and consistent
with actual observations, every competing world has a valid observed elimination
witness, and the independent experiment cap was respected. A lucky guess with
insufficient evidence fails. Recovery reports the fraction of competitors with
valid elimination witnesses; that partial quantity is not strict task success.

Its query cap is the independently checked minimum worst-case adaptive depth for
the supplied finite noiseless table. A particular world can be identified in
fewer queries than this worst-case cap. The cap says nothing about the CPU time,
tokens or other computation needed to find a strategy. Keep these costs distinct.

The mean `safety` field is a domain-defined diagnostic. In proof and diagnosis it
does not establish operational or physical safety. Certificate correctness does
not establish that the Python checker itself has been formally verified. See
[Assumptions and guarantees](assumptions-and-guarantees.md).

### Sequential operational cost

The `vending_adaptive` task separates strict realized success from the certified
minimum worst-case operational action cost. Success checks service, cash, horizon
completion and recovered terms. It does not require a named sensor or an exact
reference history. Direct assays, forecasts and inference from prior observations
can all be valid strategies when they meet the contract.

The finite-game cost includes calibration, sampling, ordering and settlement.
It excludes setup reads, static quotes and final term reconstruction. Report the
complete Session cost alongside that operational cost. A realized trajectory's
cost compared with a worst-case optimum is a descriptive efficiency comparison,
not a pointwise regret guarantee. Do not merge it into binary success.

An impossible guarantee in `no_observe`, `open_loop` or their intersection means
there is no policy in that class that succeeds in every listed world. It does
not mean every such policy fails on every individual world. `no_observe` removes
explicit experiment actions but retains operational feedback; only `open_loop`
forbids conditioning on all observations. See [Finite games](finite-belief-games.md).

## Keep configurations separate

### Pixel and rendered-robot outcome semantics

`visual` strict success requires pose within the declared coordinate tolerance,
the exact relational object count, and a correct dispatch label. Its outcome
field scores dispatch-rule correctness; no mutable routing action is executed.
In `robotics_vision`, success requires actual irreversible simulated delivery
before a true completion claim. Its generic recovery and outcome fields both
mirror delivery, and do not separately grade a numeric pose/friction estimate.
The safety diagnostic records absence of collision/slip; a stall or late detour
can still fail completion. Report those failure categories separately.

Tool cost, sensing cost, simulated time, energy, wear, capture count, and delivered
PNG bytes remain distinct. The dedicated robot control report stratifies public
deadline/contact profiles and sensor interventions. Relaxed reference episodes
that skip sensing are unexposed controls when interpreting an image or probe
ablation. Sensor corruption does not erase the physical state change of a probe.

The finite decision-sufficiency audit is separate from episode capability
scores. Its action and identification costs have comparable meanings only under
explicit terminal-cost conventions. The supplied comparison fixtures have zero
terminal costs. See [Decision sufficiency](decision-sufficiency.md).

Groups use the complete identity:

```text
policy + config_id + model + harness + condition
```

`model_id` and `harness_id` are accepted aliases if their primary fields are absent.
Conflicting aliases are rejected. The entire `condition` object is compared,
including with/without-skill and tools-enabled settings. There is no top-level
score pooled across groups. Missing policy/configuration names are marked
`unspecified` and flagged. The analyzer cannot discover unrecorded configuration
differences; assign a distinct `config_id` to each model, harness, prompt, budget,
or tool setup that should not be pooled.

Family results and episode counts remain visible. For comparisons across splits,
difficulty settings, or resource budgets, place the chosen condition in the
`condition` object or use different configuration IDs. The analyzer does not
silently turn mixed experimental settings into a controlled comparison.

## Structural-cluster bootstrap

Seeds generated from the same template are correlated. The resampling unit is
the task's `structural_signature`, within each family. A sampled cluster repeats
all answerable records in that cluster, including both twins if present. The
implementation uses cluster success/count sufficient statistics, which is
equivalent to repeating those records; it never resamples individual seeds.

Each family resamples its own number of clusters with replacement. The headline
draw takes the equal-weight mean of the resampled family rates. The 2.5th and
97.5th percentiles form the reported descriptive 95% interval. The supplied seed
and group identity make resampling deterministic; adding another group does not
change an existing group's random draws.

Fewer than two clusters yields no interval. In addition, the macro interval is
withheld if any participating family has fewer than two clusters: holding that
family fixed would hide its unmeasured structural uncertainty. Other families can
still have their own intervals. The report discloses the total cluster count,
counts per family, singleton families, and why an interval is unavailable.

A 95% bootstrap interval is not a 95% reliability guarantee. With only two or
three templates it may be unstable, and it says nothing about tasks outside the
sampled design. All-pass/all-fail data can produce a degenerate interval; that is
not evidence of zero risk on unseen tasks. Adding thousands of seeds to one
template does not increase the number of independent structural clusters.

## Paired variants and intervention kinds

Records may include `pair_id` and integer `twin` equal to 0 or 1. Pairing occurs
only within one group and a matching family, split, difficulty, structural
signature, `twin_kind`, and pair ID. A complete pair has exactly one record on
each side. Missing legacy `twin_kind` values are preserved as `unspecified`;
malformed supplied values are rejected rather than silently reclassified.

For complete pairs where both tasks are answerable, report the fraction where
both succeed. Incomplete pairs never enter this denominator and their count is
explicit. Duplicate sides are excluded and flagged instead of selecting the
best or latest run. Repeated stochastic runs must have distinct pair IDs.

Pairs with one unanswerable task and pairs with two unanswerable tasks have
separate joint decision-accuracy summaries. They do not inflate paired capability
success. Records without pairing metadata, partially specified metadata, and
duplicate pairs have separate exclusion counts.

Each group includes `paired_by_twin_kind`, using the same pairing summary for
each recorded kind:

| Kind | Meaning of joint success |
| --- | --- |
| `causal_parameter` | Both variants succeed after the task's declared controlled parameter change. |
| `wall_y_translation` | Both feasible barrier scenes are solved despite having no common valid route; hidden geometry must influence guaranteed pair success. |
| `theorem_polarity` | Both signed statement variants receive a bound proof and a consistency witness. |
| `diagnostic_state` | Both current worlds are identified with sufficient observed elimination evidence. |
| `demand_trajectory` | Both hidden demand sequences are served within the operational and completion contract. |
| `target_horizontal_translation` | Pose, relational count and dispatch are correct in both pixel scenes under fixed nuisance variables. |
| `gate_lane` | Both rendered gate variants lead to successful simulated delivery. |
| `surface_friction` | Both initial contact regimes permit successful handling, including valid conditioning alternatives. |
| `unspecified` | Legacy metadata does not establish which interpretation applies. |

The overall `paired` section is a descriptive summary across the configured
roster. Use the per-kind and per-task results to interpret it; do not label that
mixed total a physical causal-reasoning score. Joint success is not itself an
estimate of a change's causal effect on performance or proof of the agent's
internal reasoning. Separate episodes reset state, so they also do not measure
online adaptation within one continuous run.

## Return schema

```json
{
  "schema_version": "causalfill.metrics.v1",
  "record_count": 12,
  "group_count": 1,
  "groups": [{
    "group_id": "stable identity hash",
    "identity": {"policy": "name", "config_id": "version", "model": null, "harness": null, "condition": {}},
    "headline": {"name": "macro_family_solvable_success", "value": 0.5, "answerable_families": 2, "ci95": null},
    "aggregate": {"episodes": 12, "solvable_success_rate": 0.5, "metric_means": {}},
    "per_family": {"family-name": {"episodes": 6, "solvable_success_rate": 0.5}},
    "paired": {"solvable_complete_pairs": 6, "joint_solvable_success_rate": 0.5, "incomplete_pairs_excluded": 0},
    "paired_by_twin_kind": {"causal_parameter": {"solvable_complete_pairs": 6, "joint_solvable_success_rate": 0.5}},
    "uncertainty": {"cluster_count": 2, "clusters_per_family": {}, "macro_family_success_ci95": null, "ci_unavailable_reason": "at_least_one_family_has_fewer_than_two_structure_clusters"},
    "notes": []
  }],
  "methodology": {"no_pooled_configuration_score": true, "no_composite_score": true}
}
```

This abbreviated example illustrates keys, not a measured benchmark result.
`aggregate` and every `per_family` entry contain the complete metric set. The
`uncertainty.per_family` entries include each family's cluster count and interval.
`paired` also contains complete, duplicate, unpaired and malformed-metadata
counts, plus mixed-answerability and both-unanswerable summaries.
`paired_by_twin_kind` has that same schema for each observed intervention kind.
