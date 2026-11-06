# From controlled pixels to decision-relevant embodied reasoning

This is a research agenda, not a report of completed learned-model or physical
experiments. Completed v0.5 results are in `v0.5-results.md`; the executable
contracts are in `visual-perception.md`, `robotics-vision.md`, and
`decision-sufficiency.md`. The release implements the first bounded steps of
the earlier robotics roadmap and makes the next claims falsifiable.

## 1. The unit of progress is a better decision

An observation has value relative to an action, a task, and a resource limit.
Accurate reconstruction can be unnecessary, insufficient, or too expensive.
The benchmark should preserve all three possibilities.

Let B be the worlds still compatible with the observation history, and let G(a)
be the worlds where action a meets the task requirements. A guaranteed terminal
decision is possible when B is a subset of at least one G(a). Unique state
identification is sufficient in many finite tasks, but it is not necessary.
Different successful-action sets can overlap without forming an equivalence
relation. The v0.5 action-ambiguity fixture provides an explicit small example.

There are three distinct ways to make a decision possible:

1. **Observe:** refine B until one action succeeds in every remaining world.
2. **Intervene:** change the world so a common subsequent action becomes valid.
3. **Choose a robust alternative:** accept extra execution time or other cost in
   exchange for succeeding across the original uncertainty.

The rendered robot task contains all three. Gate pixels select a route; contact
both measures and changes friction; a slow detour can meet the relaxed task
without identifying either hidden component. The conditionable and resistant
surface profiles prevent the intervention alternative from being universally
successful. This is deliberate experimental design, not a newly established
law of robot contact.

Classical partially observed planning already supplies the conceptual
framework. The intended contribution is a checkable experimental contract that
separates these mechanisms and records where they succeed or fail. See the
primary sources in `../configs/research-provenance-v0.5.json`.

## 2. An image-to-action claim has several separate obligations

| Layer | What must be established | What an error looks like |
|---|---|---|
| Observation integrity | Delivered pixels contain the intended sensor data and no privileged annotation. | A seed, answer label, or scene coordinate leaks through metadata. |
| Sensor support | The asserted image/noise/calibration conditions include the actual observation. | A partial object is treated as a complete disc, or a real error exceeds the declared bound. |
| State abstraction | The compatible state set contains the true state. | An overly narrow point estimate eliminates the actual gate or contact regime. |
| Action precondition | The chosen action succeeds for every state retained when a guarantee is claimed. | A clearance margin ignores object size, control error, or surface wear. |
| Execution correspondence | The simulator/robot implements the transition assumed by the controller. | A camera move consumes time or a probe changes contact, but the planner treats it as free. |
| Evaluation integrity | The score checks the intended task and retains failure evidence. | A post-failure correct label earns completion, or a valid robust alternative is rejected. |

An exact policy certificate cannot repair a false sensor-support assumption.
Likewise, an accurate pixel detector does not establish safe execution. In v0.5,
the independent finite calibration audit establishes a bounded property of the
declared visual renderer, while the noisy decision certificate checks a
separately supplied finite support model. A general refinement proof joining
these layers has not been implemented.

For a future geometric abstraction, use explicit conservative inequalities.
For example, a route can require an opening half-width greater than robot
radius plus the sum of pose, calibration, and tracking error bounds. Every term
needs a declared unit and justification. A pose acceptance tolerance in a
benchmark score is not automatically a valid control-error bound.

## 3. Design a study that can falsify the proposed advantage

Freeze the evaluator, controller prompts, model versions, inference budgets,
available observations, and all resource accounting before evaluating the
study set. The supplied protocol JSON is a starting point for preregistration;
this release does not claim a preregistered model experiment.

Compare a useful family of policies, including a strong fixed-sensing baseline
whose final action can use every observation it purchased. A policy is not
"fixed" merely because it ignores information. Permit known public task
parameters to influence a controller's plan before sensing. Report when an
apparent adaptive advantage disappears against an efficient fixed sequence.

The v0.5 robot controls intentionally expose this distinction. Its policy named
`adaptive` selects sensing based on the public deadline and selects a handling
mode from the contact reading. The minimal fixed sequence is sufficient for
both deadlines. Consequently the robot comparison is not a proof that sensing
contingent on hidden observations is superior. A separate exact finite fixture
does establish a worst-case cost of 3 for contingent queries versus 4 for every
fixed sensor subset within its declared action/observation model.

Recommended study hypotheses are narrow enough to fail:

| Hypothesis | Main endpoint | A result that defeats the claim |
|---|---|---|
| Selecting a useful view improves decisions. | Complete-pair success at a common observation/inference cap. | A prompt-only or efficient fixed-view control matches the active controller. |
| The controller uses the recovered component. | Behavior under paired image swaps with fixed original world labels. | Its actions remain unchanged, or it succeeds by an unrelated shortcut. |
| Uncertainty improves execution choices. | Completion, collision/slip counts, and coverage together. | Better calibration scores do not improve decisions at comparable coverage. |
| The controller values intervention. | Success/cost on conditionable versus resistant contacts. | It always probes, always conditions, or ignores the action's state change. |
| The representation transfers. | Outcomes on independently authored held-out mechanisms. | Gains occur only on new seeds of the same small generator. |

Neither a generated-image total nor a large assertion count is a model
capability endpoint. The release's current numbers are engineering controls.

## 4. Preserve the causal comparison

Paired scenes should change the specified decision-relevant parameter while
holding nuisance variables fixed. Check the complete public payload, including
compressed bytes, dimensions, hashes, tool availability, costs, and timing
semantics. A visually identical image can still differ in metadata or
compression if the generator writes hidden information.

Use interventions at distinct layers and state what they test:

- Blank valid images test whether the delivered visual path is necessary for
  the chosen controller under that contract.
- Swapping twin images tests whether plausible evidence about another world
  changes the recovered answer and action when original labels remain fixed.
- An occluded view tests identifiability from that specific observation. It
  does not show that every permitted sensor is uninformative.
- Corrupting a fiducial tests the calibration path and the controller's response
  to insufficient support. A refusal to act is not task completion; report
  coverage alongside failure avoidance.
- A wrong contact interval, with true wear retained, separates dependence on
  the reading from dependence on the physical conditioning action.
- Legal detours and contact alternatives test whether the evaluator rewards
  successful behavior or accidentally requires one preferred solution.

Keep clean and intervention runs paired at the episode level. Do not tune a
model or choose its best policy from the final evaluation outcomes. Engineering
repairs remain appropriate during author development, but preserve the earlier
failure, version the change, and rerun the relevant final gates.

## 5. Extend realism through explicit contracts

The next simulator should expose sensor observations and action feedback while
retaining privileged state in the evaluator. ManiSkill's documented distinction
between state and sensor observation modes provides a useful interface model;
using that interface would still require an actual integration and experiment.

Start with a small transport or insertion task whose failure modes can be
identified. Add perspective/depth cameras, varied lighting and materials,
geometric occlusion, calibration drift, tracking error, and contact dynamics
one layer at a time. Keep the mechanism roster, parameter support, and units
explicit. A single jump from colored discs to unconstrained household scenes
would make failures difficult to explain.

The crucial simulator audit is conformance: whenever the abstraction licenses
an action, does the simulator meet its promised outcome across the tested
states and disturbances? Save the violating state and observation when it
does not. Classify failures as perception support, abstraction, planning,
actuation, or scorer errors. Expanding the uncertainty set can improve soundness
while making more actions unavailable; measure that success/coverage tradeoff.

Destructive probes require a sequential model. The latent state should include
surface wear, elapsed time, remaining resources, payload status, and any
irreversible damage. Observation and transition probabilities or bounded
supports must refer to the post-action state when appropriate. Repeating a
correlated reading does not create independent evidence, and repeated probing
may change what is being measured.

Controlled physical trials become useful after those contracts work in the
simulator. A laboratory protocol should measure sensor and actuator errors,
define termination/intervention criteria, and record recovery after unexpected
outcomes. Bench completion, simulator completion, and physical completion are
separate evidence levels. No physical trial is included in v0.5.

## 6. Count the right resources and statistical units

Report tool cost, observation count, delivered bytes, simulated time, inference
tokens/time, and physical energy separately. A vector sensor or image is a
high-bandwidth observation even if the interface calls it one query. The
100-dimensional finite-field track's five probes return 500 residues. A
240x240 RGB image contains 172,800 uncompressed channel bytes; the robot's
192x192 RGB image contains 110,592. Neither query is equivalent to a scalar bit.

Score strict completion and complete-pair completion. Also report per-component
recovery where it is actually graded, task outcome, collisions/slips/stalls,
deadline violations, observation cost, coverage, and calibration of stated
confidence. A single blended number can conceal conservative failure or unsafe
success. In the current operational robot family, the generic recovery field
mirrors delivery; it is not a separate estimate-accuracy score.

For a future empirical model study, episodes from the same generator mechanism
are correlated. Resample or aggregate at the mechanism/scene-family level when
estimating transfer uncertainty, and report the number of distinct mechanisms.
With zero observed failures in n genuinely independent trials, the one-sided
95% binomial upper bound is 1-0.05**(1/n); applying that calculation to dependent
pixels, repeated seeds, or syntactic assertions would misstate the evidence.
No such confidence claim is attached to the current engineering stress counts.

## 7. What would justify a stronger research claim?

A persuasive advance would combine a verified observation contract, strong
baseline policies, real learned-agent results, and an outcome/cost improvement
that survives independently authored mechanisms. A robotics-transfer claim
would additionally require simulator correspondence and physical evidence.
An exact finite result can be valuable before those stages, provided its model
and quantifiers are stated precisely.

The intended long-term object is a decision-relevant representation: one that
supports predicting which actions will meet a task and deciding which
experiments or interventions are worth their costs. Dimensionality alone is
not evidence for that property. A future high-dimensional latent track would
need explicit physical variables, units, observation maps, intervention maps,
and downstream outcome tests. The present algebraic 100D track provides none
of those mappings by itself.

The release therefore makes an ambitious question executable in a bounded
setting: **does an agent obtain or create enough information for a successful
action, while paying for what it observes and accounting for what it changes?**
The next result must answer that question with measured controllers and
independent mechanisms, not just a larger generator.
