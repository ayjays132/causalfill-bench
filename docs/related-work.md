# Related work and the proposed contribution

The original research review was checked on 2026-11-01 for CausalFill-Bench 0.3.0.
The v0.4 additions below and the Axiom, OpenAI mathematics, GPT-Red, Vending-Bench 2
and Lean 4.35.0 primary sources were rechecked on 2026-11-04. This does not claim
that every older link was rechecked on the later date. This release contains original tasks and code.
References describe methodological influences; they do not indicate affiliation,
official benchmark membership, reproduced results, or copied implementations.

## Positioning

Code infilling, skill evaluation, tool composition, interactive inference,
long-horizon simulations, proof checking and exact query learning all have
substantial prior art. The research hypothesis
for CausalFill-Bench is narrower: **causally selected omissions, permitted active
evidence gathering, and an executable downstream outcome can be evaluated
together, with checkable evidence and explicitly typed paired changes.** This
combination is a proposed evaluation design, not a demonstrated breakthrough.

| Prior work | Relevant mechanism | What this prototype does and does not establish |
| --- | --- | --- |
| [HumanEval Infilling](https://github.com/openai/human-eval-infilling) | Executable code completion with missing spans, accompanying the Fill-in-the-Middle paper. | Masking code is established prior art; our contribution cannot be the existence of holes. |
| [ARC-AGI-2](https://github.com/arcprize/ARC-AGI-2) | Example-based rule induction, exact outputs, public and private evaluation tiers. | Original rule tasks can test some related operations. They are not official ARC tasks or a substitute for human calibration. |
| [ARC-AGI-3](https://arcprize.org/arc-agi/3) | Interactive exploration, goal acquisition, learning across steps, and action efficiency relative to human baselines. | Paid observations and action logs adopt a general experimental principle. This prototype has no ARC human-efficiency baseline. |
| [Vending-Bench 2](https://andonlabs.com/evals/vending-bench-2) | Persistent simulated business operations over a year, delayed consequences, supplier problems, and final cash scoring. | The included small deterministic vending simulator is original. It is not Vending-Bench, a port, a year-long study, or a reproduction of published model scores. |
| [OSWorld](https://github.com/xlang-ai/OSWorld) | Real desktop tasks and execution-based evaluation. | Virtual files and typed tools are a controlled simulation. They do not establish real operating-system or GUI competence. |
| [SWE-bench](https://github.com/SWE-bench/SWE-bench) | Repository repair evaluated through execution. | Tests should accept behaviorally equivalent repairs. A restricted task language does not establish arbitrary repository repair ability. |
| [Terminal-Bench 4.0](https://www.tbench.ai/news/terminal-bench-4-0) | Resource calibration, versioned environments, verifier fixes, and removal of saturated or compromised tasks. | Freeze environment versions and record budgets. Different resource limits must not be silently compared. |
| [Inspect AI](https://github.com/UKGovernmentBEIS/inspect_ai) and [Harbor](https://github.com/harbor-framework/harbor) | Evaluation orchestration, traces, and isolated agent environments. | These are potential integration targets. A custom JSON protocol alone is not an implemented integration with them. |
| [SkillsBench v1.1](https://www.skillsbench.ai/blogs/skillsbench-1-1), [repository](https://github.com/benchflow-ai/skillsbench) | Paired with/without-skills evaluation, skill composition and deterministic verifiers. | Skill composition and skill-conditioned task success are established. Paired conditions are necessary to measure the marginal value of a skill. |
| [Skill-Use](https://arxiv.org/abs/2608.04828), [repository](https://github.com/JinyiHan99/Skill-Use-Bench) | Skill discovery under progressive disclosure; trigger, compliance and boundary metrics. | Finding and obeying skills are not new benchmark concepts. Our task should identify the additional construct it measures. |
| [SkillForgeBench](https://arxiv.org/abs/2610.14918) | Skill-grounded task synthesis and fine-grained completion/process requirements. | Building tasks from skills and checking every requirement are prior art. |
| [ToolComp](https://labs.scale.com/leaderboard/tool_use_chat) | Dependent compositional tool calls with verified answers and process supervision. | Multi-step tool composition alone cannot support a novelty claim. |
| [Axiom: Proof of Concept](https://axiommath.ai/research/proof-of-concept/) | Generates proof artifacts and accepts them through Lean/Mathlib checking; separates the generative search from verification. | This motivates evidence-carrying completion. Our finite propositional development and two exported Lean proofs do not reproduce Axiom Prover or its research mathematics; the Python interface remains outside the Lean theorem. |
| [VERINA](https://github.com/sunblaze-ucb/verina), [authors' project](https://verina.io/) | Evaluates code, formal specification and proof generation, separately and in combination, using Lean tasks. | A benchmark that requests a proof as well as executable correctness is established prior art. Our proof track fixes the statement and uses a narrower finite propositional calculus. |
| [miniF2F](https://github.com/openai/miniF2F), [paper](https://arxiv.org/abs/2109.00110) | Cross-system formal mathematics benchmarks with fixed theorem statements and held-out evaluation problems. | Completing a formal proof of a fixed statement is established. Our generated clause families are not Olympiad mathematics or a replacement for miniF2F. |
| [Angluin: Queries and Concept Learning](https://doi.org/10.1007/BF00116828), [Learning Regular Sets from Queries and Counterexamples](https://doi.org/10.1016/0890-5401(87)90052-6) | Studies learning through chosen queries and exact identification, including the distinctions between query types. | Choosing an informative experiment is a classical idea. Our finite explicit response table is a restricted identification setting, not an implementation or extension of every exact-learning result. |
| [Bshouty and Haddad-Zaknoon: Adaptive Exact Learning of Decision Trees from Membership Queries](https://proceedings.mlr.press/v98/bshouty19a.html) | Studies query complexity of adaptive exact learning. | The diagnosis track's independently checked minimax cap is a finite-table property; it is not a new general query-complexity theorem. |
| [POMDP belief-state planning](https://www.pomdp.org/tutorial/pomdp-background.html), [finite-horizon solving](https://www.pomdp.org/tutorial/pomdp-solving.html) | Reduces partial observability to planning over information states and conditional policies. | Belief-state planning and minimax recursion are established. Our finite robust set-of-worlds objective is not the usual stochastic expected-reward objective. |
| [Lean 4.35.0 release](https://lean-lang.org/doc/reference/latest/releases/v4.35.0/), [foreign-function interface](https://lean-lang.org/doc/reference/latest/Run-Time-Code/Foreign-Function-Interface/) | Provides independent proof checkers, export checking and documented embedding support. | We used the official runtime and directly replayed exports in six configurations. This is not a claim that Lake's paranoid build sandbox ran. |

## Proof-carrying completion is a verification contract

Axiom's published workflow makes a generated mathematical artifact acceptable
through a separate proof checker. VERINA and miniF2F already evaluate formal
reasoning and verification tasks. CausalFill's proof track follows the general
principle of checking an artifact against an immutable claim. It fixes premises
F and signed goal g using a SHA-256 content digest, requires a resolution
refutation of F together with not-g, and also requires a satisfying assignment
for F. The last condition rejects vacuous conclusions from inconsistent premises.

Resolution itself is classical: J. A. Robinson, *A Machine-Oriented Logic Based
on the Resolution Principle*, JACM 1965, [primary paper](https://doi.org/10.1145/321250.321253).
The code computes each resolvent from earlier parent clauses and permits no
agent-provided axiom. This narrows the verifier's trusted surface; it does not
formally prove the Python verifier correct. Version 0.3 adds an optional Lean
soundness development and two complete exported proof artifacts, actually checked
with the official Lean 4.35.0 kernel. The toolchain is separately installed, not
bundled. No Axiom model, VERINA task, miniF2F proof, or OpenAI mathematical result
is imported. See [Formal assurance](formal-assurance.md) for exact scope.

## Diagnosis is a bounded exact-identification problem

Exact query learning predates modern language-model agents. The new diagnosis
configuration has an explicit finite hypothesis table, noiseless binary queries,
and a known guarantee that the actual world is one listed row. Its independent
checker validates every relevant minimax recurrence alternative, while a separate
tree checker supplies an attaining strategy. These give an exact worst-case
query bound for that table. They do not establish optimal model computation or
general scientific-discovery ability.

The answer must include observed elimination witnesses covering every other
world. That contract prevents lucky guesses from receiving identification
credit. Its evidence requirements, finite scope and runtime accounting must be
stated when comparing it with broader active-learning or robotics evaluations.

## What would make a scientific claim stronger?

### The v0.4 contribution being tested

The new engineering combination is a masked procedure with irreversible actions,
an explicit information budget, a finite certificate of what observations and
cost can suffice, actual runtime conformance evidence, and formal statement
binding. Neither partial observability, active experiments, Bellman recurrences,
weighted set cover nor proof checking is new by itself. The exact bounds in this
release are small finite model properties. Their usefulness as a new evaluation
construct still needs independent task authors, controlled comparisons and
external reproduction. Six successful assistant pilot episodes do not establish
frontier hardness or incremental measurement value.

### Experimental evidence still needed

Compare matched complete-skill, random-mask, causal-mask, no-tool, and active-tool
conditions. Keep task instance, token budget, time budget and available evidence
comparable. Test after a controlled intervention, not only on another numerical
instance. Report end-to-end success, recovery, task outcome, process constraints,
observation cost and calibration separately before proposing an aggregate score.

Confirm identifiability: there must be enough permitted evidence to recover the
answer, or the task must explicitly support an insufficient-evidence response.
Hiding an arbitrary secret does not establish difficult reasoning. A reference
controller proves constructive solvability for tested instances, not human ease,
frontier-model difficulty, or model improvement.

Group held-out tests by rule or workflow structure. Random seeds from one task
generator are correlated variants. Confidence intervals treating those seeds as
independent research problems will overstate evidence. A public generator and
public examples are development infrastructure, not a secure private test set.

## Execution and contamination boundaries

[Terminal-Bench's integrity policy](https://www.tbench.ai/news/leaderboard-integrity-update)
documents solution-retrieval reward hacking and leaked test files. The agent
should receive only its public task and permitted observations. Private state,
seeds, answer constructors and graders belong to the evaluator. Record full tool
trajectories and exact task/agent versions. An instruction not to inspect private
files is not a filesystem isolation boundary. A public local development harness
must not be presented as tamper-proof remote evaluation.

External web research during benchmark authoring is distinct from scored-agent
network access. A future real-tool track must state whether web access is allowed,
how source solutions are excluded, and which traces were checked for leakage.

## Skill-source provenance and licensing

The [OpenAI skills catalog](https://github.com/openai/skills) currently marks itself
deprecated and points to [OpenAI Plugins](https://github.com/openai/plugins) for
current examples. Old catalog skills have individual LICENSE.txt files. Do not
treat every GitHub skill as carrying the same reuse permission.

Verified repository licenses at research time: ARC-AGI-2, OSWorld, Harbor,
SkillsBench and VERINA use Apache-2.0; Inspect AI, the SWE-bench harness, HumanEval Infilling,
and the [ARC-AGI-3 benchmarking harness](https://github.com/arcprize/arc-agi-3-benchmarking)
use MIT. miniF2F documents system-specific licenses, including MIT for its
Metamath content and Apache for Lean content; check the specific material before
reuse. These observations are not permission to republish arbitrary underlying
datasets, external artifacts, or every dependent skill. No official reusable
Vending-Bench 2 code license was verified. The simulator here is independently
implemented from general principles and public methodological descriptions.

Pin imported skills by commit and content hash, record their individual licenses,
inspect scripts before execution, and separate the evaluated skill corpus from
the benchmark author's tooling. Popularity is not evidence of skill quality.
SkillsBench's own contribution workflow requires human-authored prompts and
oracle solutions; this AI-assisted prototype does not claim to meet that rule or
to be a SkillsBench submission.
