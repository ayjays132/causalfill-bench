# Prospective calibration and transfer plan

This is a **proposed next experiment**, written after the v0.5.1 development
pilot. It is not a preregistration of that pilot and does not describe a study
already performed. The six-case exploratory assistant result was 6/6 strict
successes. A harder benchmark requires measured failure under fair conditions,
not more variables, a more impressive title, or an impossible task.

## Freeze the scientific claim before another model run

The first claim to test is narrow: maintaining the shared corruption budget
improves justified decisions under a constrained sensing-and-action budget.
Separate it from natural-image recognition, tool discovery, long-term memory,
formal proof search, and physical safety. A joint end-to-end score can be added
only when the individual stages remain measurable.

Freeze the source, generators, contracts, model identifiers, prompts/skills,
sampling settings, planning wall-time limits, token budgets, observation/action
costs, hardware, scoring and exclusion rules. Publish a commitment before any
held-out solver run. Keep public solved examples and source out of the solver
environment for a closed-book protocol; explicitly disclose them for an
open-source protocol. Different protocols need separate results.

Use an isolated container or VM with no evaluator filesystem/process access.
The current pilot's solver-instruction boundary is useful for development but
does not satisfy that release criterion. Network transport must pass a
cross-process connectivity smoke check before task timing begins. Start each
episode timer when the solver actually receives it; the current pilot's
Session wall times include host setup and waiting and are not inference times.

## Task generation that cannot win by being impossible

1. Generate a finite contract and compute a checked optimum plus an attaining
   policy. Reject uncertified answerable tasks. Route intentional impossibility
   to a separately scored abstention pool with an explicit certificate.
2. Measure a fixed development solver's regret, strict failure, and resource
   use. An adversary can search for high regret only within the solvable pool.
3. Save the failures and minimize them to identify the actual missing skill.
   Do not keep a case merely because a malformed parser or confusing wording
   causes a failure.
4. Freeze selected mechanism families before testing new model versions.
   Hold out mechanisms created by separate authors, not only random seeds,
   sensor labels, bit polarities or larger instances of the same code.
5. Validate solvability with an independent checker and human attempts. Human
   difficulty and accessibility must be measured; expert intuition is not a
   human baseline.

This combines established adversarial environment-design ideas with this
module's finite solvability gate. It is not a new adversarial-training theorem.
The relevant prior art and differing assumptions are in
[the research document](robust-research.md).

## Comparison matrix

| Comparison | Hold fixed | Measure separately |
|---|---|---|
| Global fault accounting vs a noiseless assumption | Public contract, worlds, faults and tool costs | Actual outcome, justified outcome, false confidence, calls |
| Action sufficiency vs exact identification | Success sets and corruption model | Required evidence, total cost, remaining feasible worlds |
| Adaptive sensing vs a fixed probe schedule | Available probes, task budget and terminal goals | Worst-case cost and realized cost; do not equate these |
| Learned agent vs exact reference | Episode contract and observation budget | Strict success, planning time, memory, token count, actual resource bill |
| Skill guide present vs absent | Task-specific contract and tools | Incremental benefit of the guide; avoid hiding task definitions |
| Symbolic observations vs extracted image observations | Latent scenes and action rules | Perception error, model mismatch, policy error, execution error |
| In-model faults vs cap violations | Generator family, probe catalogue and action set | Robustness within assumptions and graceful failure outside them |

Use budget curves around the certified optimum: exact optimum, one unit below,
and selected slack levels. Below-optimum guaranteed success is impossible by
the finite contract; those trials test abstention/claim calibration and should
not be pooled as ordinary answerable failures. Randomized strategies require
a separate probabilistic objective; the current robust optimum is a guaranteed
worst-case objective.

## Reporting and statistical units

Keep three units separate: configurations, independently authored mechanisms,
and sampled episodes. Repeated seeds and causal twins are correlated. Report
family-level and mechanism-level results, exact denominators, all attempts,
resource distributions and an uncertainty method suited to those clusters.
Do not sum proof-checker executions, assertions, paths or pixels into a score.

Report strict success and actual selected-world outcome separately. An action
that happens to work can still be unjustified. Give coverage and abstention
quality, including the impossible pool, and confidence calibration. Capture
token/cost metadata from the model adapter rather than inferring it from
elapsed Session time. Predefine stopping rules and disclose model-development
reuse of any cases.

The current scripted evidence reference solves the released answerable matrix.
The current assistant pilot also solves its six cases. Consequently, neither
large test counts nor the bounded-fault extension currently demonstrate a
frontier capability gap. A follow-on paper should report that result plainly
and investigate mechanism holdouts, computation limits and harder interactions.

## A robotics transfer experiment that could answer a real question

Start with the existing rendered robotics family. Construct a finite set of
pose/contact hypotheses and justified action regions. The perception adapter
should emit observed predicates with documented calibration, not silently
convert confidence scores into a deterministic corruption cap. Faults from
occlusion, lighting, lens contamination, timing and contact disturbance may be
correlated or persistent, so their relationship to the cap must be measured.

First compare clean, declared in-model fault, and deliberately out-of-model
episodes in simulation. Hold policy cost accounting fixed and preserve enough
budget for the terminal manipulation. Ask whether the agent maintains multiple
viable explanations and chooses a robust action when full identification is
unnecessary. Include successful contact-conditioning/bypass strategies when
the task permits them; do not invalidate them just because they use fewer
observations than an intended reference.

Only after those stages should a separately specified robot experiment test
the same causal question. Measure observation extraction, dynamics mismatch,
actuator behavior and task success independently. The current symbolic proof
does not establish that real sensors obey a cap, that a real scene is one of
the enumerated worlds, or that the robot's physical action has the declared
success set. Those are empirical obligations for any transfer claim.

## Publication readiness

The current code, source-bound verification, traces, theorem statements,
negative controls, research positioning, attribution and original branding are
ready for review. A scientifically stronger benchmark claim still needs an
independent mechanism holdout, multiple model runs with complete settings,
human validation, real isolation and external replication. A new mathematical
or robotics breakthrough would require a new result and appropriate evidence,
not a benchmark branding milestone.
