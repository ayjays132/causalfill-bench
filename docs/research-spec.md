# Research specification

## Status and intended claim

CausalFill-Bench 0.5.0 is an AI-assisted, original implementation of a benchmark hypothesis: missing components that matter to a task can provide a common evaluation unit for tool selection, reconstruction, executable completion, and checkable evidence. The prototype supports generated tasks, bounded interactions, typed completions and independent verification. Version 0.5.0 adds actual raster observations, calibrated visual recovery, costed stateful robot controls, image/contact interventions, and exact finite decision-sufficiency certificates with overlapping observation supports. It preserves earlier procurement, resolution, Lean, workflow and barrier work with their original provenance. Current controls establish implementation properties; they do not establish frontier difficulty, learned training benefit or physical robot transfer.

The proposed question is narrower than general intelligence: **When a procedure lacks information that matters to its outcome, can an agent find adequate evidence, recover a valid completion and make the procedure work within a declared budget?**

The project should be compared with code infilling, SkillsBench, ARC, Vending-Bench, active perception, sparse system identification, formal proof benchmarks and exact query learning. Their primary sources are in [Related work](related-work.md). A missing logical proof is an obligation in a formal specification, and a hidden diagnosis is a state-identification problem; neither must be relabeled as a physical causal mechanism to fit this protocol.

## Task definition

An episode contains an environment E, a procedure or specification P, a mask M, a public observation interface O, an action set A, an observation/action budget B and an independent evaluator V. A missing component may be a word, expression, rule, coefficient, state variable, action precondition, proof or diagnosis. The agent produces a typed completion C and, where required, an actual trajectory tau and a certificate K.

Success is V(E, C, tau, K)=1. Surface similarity to an original string is insufficient. Multiple implementations, paths or proofs pass when they satisfy the declared contract. The candidate and intended property are represented separately: a sparse matrix is compared with an independently constructed affine operator; a robot path is checked against geometric and handling constraints; proof steps are checked against a fixed statement; and diagnosis witnesses must refer to real observations.

The agent sees virtual files and permitted observations, not the evaluator object. Final grades do not return through the agent API. One accepted submission closes the episode. Invalid tool calls consume budget; malformed protocol calls and termination are recorded. Tools are deterministic for a fixed planted episode, except that no timing guarantees are made.

## Nine conceptual domains, fourteen task configurations

1. **Words:** reconstruct literal Boolean-routing instructions. Recoverability comes from chosen experiments; all possible Boolean inputs are verified. A dependency graph ranks masks by downstream influence. Causal and random masking match the number of declared one-word components. This is slot-level matching, not exact model-token matching.
2. **Code workflow:** fill a ledger expression in a restricted arithmetic language. Files supply the operational specification; visible examples aid debugging. Strict acceptance requires a sufficient symbolic equivalence and bounded-totality certificate over the declared integer input box subject to the explicit task constraints (`reserve <= ceiling` in transfer), plus behavioral tests. Unsupported proof forms return `not_certified`. No candidate Python is executed.
3. **Grid program:** infer a bounded compositional transformation from demonstrations and active experiments. Grids and tasks are original. The small known grammar supports a constructive identification experiment. New transfer primitives are explained in the public DSL; this is not a claim of pure composition-only learning.
4. **Vending:** the original configuration repairs five procurement fields and operates a mutable business through 16, 20 or 24 simulated days. The separate `vending_adaptive` challenge repairs four terms and serves hidden demand over two, three or four irreversible rounds. A complete finite candidate-world model allows exact minimum worst-case operational costs and observation-necessity checks. Both configurations enforce cash, stock and service constraints; they have different semantics and should be reported separately.
5. **Robotics:** infer a target's world coordinates from numeric orthographic projections with known fiducials and unknown affine camera calibration. Choose a route that avoids expanded obstacles and respects gripper bounds and force limits. The barrier profile adds two individually feasible hidden scenes whose union blocks a separating plane, certifying that no one continuous path solves both. Those two configurations remain symbolic geometric simulators. The added `robotics_vision` configuration uses actual PNG observations, a calibrated affine gate view, contact probes that change friction, and irreversible simulated delivery with separate time and energy limits. It is a finite 2D abstraction rather than full contact dynamics or physical control.
6. **Mathematical state:** recover an affine operator over GF(101), at 8, 32 or 100 dimensions. The control allows coordinate probing. The sparse challenge allows only nine cost units and at most two nonzero entries per row. Five vector probes are sufficient by a classical moment-based construction.
7. **Proof:** complete a resolution certificate for a fixed propositional conclusion and supply a consistency witness for its premises. The exact statement is bound by SHA-256. The splits use implication chains, XOR ladders and pigeonhole constructions. Search is separate from a bounded checker that computes every resolvent; no new axiom or unchecked clause can be inserted.
8. **Diagnosis:** identify one current world from a finite binary experiment table. An independently checked minimax recurrence and a separate attaining decision tree certify the optimal worst-case query budget. The final completion must include an actually observed experiment excluding each competing world. A correct world ID without sufficient observed evidence fails.

9. **Visual perception:** use actual bounded-noise PNG pixels and three fiducials to recover a target pose, count objects west of it, and select a dispatch label. Controlled occlusion, subpixel camera changes, palette permutations and paired target interventions test the sensor-to-answer path.

`ambiguity` is a separate unanswerable control configuration of the words domain. It redacts route identity in every possible permitted observation. Two distinct route words are exhaustively shown to yield the same observation sequence. Guessing one hidden literal does not receive capability credit; correct abstention is measured separately.

`latent` and `latent_sparse` share the mathematical-state domain; `robotics`, `robotics_barrier` and `robotics_vision` share the robotics domain; `vending` and `vending_adaptive` share the vending domain. The fourteen configuration keys are `words`, `ambiguity`, `workflow`, `grid`, `vending`, `vending_adaptive`, `robotics`, `robotics_barrier`, `latent`, `latent_sparse`, `proof`, `diagnosis`, `visual` and `robotics_vision`. This conceptual grouping is distinct from the analyzer's family labels and their default weighting.

## Certificate obligations and the limits of each guarantee

The proof track fixes a variable domain, premises F and signed goal g. Its accepted fill must match that statement's SHA-256 digest, derive the empty clause by resolution from F plus the single clause not-g, and provide a Boolean model satisfying the original F. The first obligation binds the intended theorem; the second establishes entailment; the third prevents credit through inconsistent assumptions. Every supplied step must be valid; the checker rejects an invalid suffix even after a valid refuting prefix. The checker permits no admitted axiom, forward reference or agent-supplied derived clause.

The diagnosis table contains every allowed candidate world's deterministic response to every allowed experiment. Its minimax value satisfies D(S)=0 for a singleton and D(S)=1+min_q max(D(S0),D(S1)) over informative queries otherwise. The certificate checker validates all relevant alternatives, providing a lower bound as well as an attaining upper bound. Checking only one successful decision tree would establish merely an upper bound. The experiment cap is enforced independently of total file-read cost.

At submission, the selected diagnosis must agree with every observed response. Every other candidate must have a distinct elimination entry naming an experiment actually performed whose observed result contradicts that candidate. The requirements certify identification from permitted observations; an oracle guess cannot substitute for that evidence.

The Python evaluators implement these finite semantics. The optional Lean project separately proves resolution and indexed-checker soundness and nonvacuous entailment. Two complete release certificates, with 865 and 6,018 resolution steps, were checked by the Lean 4.35.0 kernel; exact exported statements, models and triples were round-tripped. This does not prove generic equivalence of Python parsing/checking and Lean, nor formalize the diagnosis or workflow checker. Python implementation, statement/table construction, resource bounds, artifact translation, and the relation to any real-world interpretation remain relevant trust boundaries. Content hashes bind artifacts to a statement; they do not authenticate a publisher or eliminate this trust.

Version 0.4 adds 21 generic Lean theorem roots for observational indistinguishability, finite observation-class capacity and ranked AND/OR strategy cost. Four profile theorems cover four policy modes of one two-round, four-world procurement fixture; four additional equality theorems bind the whole imported arenas to independently rendered expected literals. All 29 roots were exported and accepted by six checker configurations, including four external implementations. The Python raw-game-to-belief projection and the runtime-to-model correspondence remain outside those Lean theorems. Extensive conformance tests are finite engineering evidence. See [Formal information assurance](formal-information.md).

The affine basis certificate establishes universal equality within the enforced affine finite-field grammar. Proof certificates establish finite propositional entailment with satisfiable premises. Diagnosis certificates establish optimal worst-case query depth for the explicit noiseless table. Workflow acceptance adds a sufficient symbolic identity and intermediate-value bound certificate within its public integer box and explicit task constraints (`reserve <= ceiling` in transfer). Grid acceptance remains finite behavioral testing. Robotics uses exact decimal-rational workspace and segment/box predicates, with separate camera/target tolerances; barrier pair certification establishes observation necessity only in that idealized geometry. Vending outcomes hold for the realized simulation. See [Assumptions and guarantees](assumptions-and-guarantees.md), [Proof track](proof-track.md), and [Identification track](identification-track.md).

## Mask selection

The reusable planner receives a directed acyclic dependency graph. Each component has a declared recovery cost, mask size and consequence weight. It enumerates bounded subsets, removes those with missing evidence paths or cost above the budget, and ranks remaining subsets by the weighted union of affected descendants. Random selection uses the same admissible candidate set and optional exact declared-size constraint.

This is a conservative graph proxy. It does not prove a natural-language fact is identifiable; a task author must validate that separately. Evidence costs assume independent recovery paths and may overcount shared information. The current planner is applied to the word task. Other families have fixed, explicit omissions. A learned adversarial mask generator is future work.

Do not maximize failure without constraints. Hiding arbitrary secrets yields an impossible task, not a useful hard one. A candidate mask should pass these checks before inclusion:

- The missing component changes a downstream decision or its declared documentation requirement.
- The permitted observations identify a valid completion within budget, or the task is explicitly an uncertainty control.
- A constructive reference succeeds through the public tools.
- Incorrect plausible candidates fail meaningful tests.
- Independent review checks alternative completions and mistaken specifications.

The code's reference policies supply constructive evidence for the supported finite grammars. They do not replace human validation or independently authored reference solutions for a mature benchmark.

## Splits and interventions

Each family exposes train, dev and transfer generators. Their changes include gate arity/operator sets, clipping composition, grid operations, fee/transit structure, camera calibration class, sparse coordinate coupling, proof construction class, and experiment-table structure. These are finite structural shifts, not a claim of broad unseen-domain generalization. Publishing all three generators makes them open development distributions.

Each generated instance has a paired variant constructed from the same initial random stream. Report the kind of change explicitly:

| `twin_kind` | Change | Scope |
| --- | --- | --- |
| `causal_parameter` | A routing condition, calibration scale, recolor target, supplier lead time, obstacle height or operator coefficient | A controlled change to the declared symbolic model |
| `wall_y_translation` | The y location of a full-height wall | A geometry-observation necessity profile with individually feasible scenes |
| `theorem_polarity` | The signed proof goal and its occurrences in the premises | A specification-binding change; the non-goal clause structure is fixed |
| `diagnostic_state` | The current categorical candidate world | A different diagnosis under an unchanged table and query budget |
| `demand_trajectory` | The selected admissible demand sequence | Different operational evidence and decisions under the same public market contract |
| `target_horizontal_translation` | The target world x coordinate | Pixel-derived pose, relational count and dispatch under fixed nuisance variables |
| `gate_lane` | The open rendered lane | Route-dependent actual simulated delivery |
| `surface_friction` | Initial surface friction | Measurement-based handling or a valid contact-conditioning alternative |

The same initial random stream preserves the non-target setup. A categorical diagnostic-world change can alter several observed sensor bits; it is one selected-state change, not a claim that one physical variable changed. A theorem-polarity change is likewise not a physical causal intervention.

Twins are independent episodes with reset agent state. Joint success on both is measured. This differs from online adaptation within one continuous conversation. The workflow verifier additionally changes runtime scale within its behavioral cases. A plan valid in both twins should be accepted; different answer text is never required solely to make the pair look difficult.

## Resource accounting

Tool descriptions disclose synthetic costs. Document reads, observations, simulations and economic actions consume them. Different families intentionally use different budgets; cross-family raw costs should not be interpreted as equal computational work. Reports preserve cost and call count separately.

Suite records additionally include canonical serialized request and response byte counts. They are not actual model token counts or billed API costs. The 100D challenge's five probes each return 100 residues. It compresses the number of interventions by exploiting structure; it does not recover hundreds of unknowns from five scalar measurements.

An evaluation harness should separately record model, version, system prompt, sampling settings, retries, token usage, wall timeout, CPU/memory limits, external network access and installed skill hashes. The supplied public client is provider-neutral; no paid model API run was commissioned by this release.

## Primary score and diagnostic vector

For each answerable task family label f, compute its episode success rate S_f. The headline is the arithmetic mean of S_f across represented labels. Challenge configurations retain distinct family labels; combine them deliberately if a future leaderboard wants equal weights across the nine conceptual domains. Adding configurations changes the set being averaged, so cross-version headlines are not directly comparable unless the same task roster, semantic versions and weighting are used.

Report separately: strict success; recovery; realized outcome; operational safety; complete-pair joint success by intervention kind; coverage; answered accuracy; correct abstention on unanswerable controls; decision Brier score; cost; invalid calls; elapsed time; and artifact/trace hashes. Brier confidence refers to whether the final decision is correct, including an abstention decision, not the probability of completing a solvable task.

Certificate-specific diagnostics remain separate: proof statement binding, refutation validity, premise consistency and checked step count; diagnosis evidence coverage, used experiments and certified worst-case query depth. A partial proof's valid steps or a partial elimination list cannot substitute for strict task success. Diagnostic query optimality measures observations, not the CPU time or tokens needed to plan them.

Uncertainty is based on whole structural-signature clusters within each family. Repeated seeds are not independent new mechanisms. Intervals are withheld when a family has too few structural clusters. Degenerate 100% bootstrap intervals for scripted references do not prove universal reliability. See [Scoring](scoring.md).

## Proposed model experiment

Freeze a source version and pre-register hypotheses before opening final results. Use strong models from multiple providers, an open-weight baseline, and humans on a feasible subset. Fix budgets, prompts, permitted skills and retries. Record complete observable traces; do not require or publish private chain-of-thought.

Compare complete procedure, matched omission, causal omission, static-evidence, active-evidence, distractor and transfer conditions. For a genuine static-versus-active comparison, match the information initially available; the shipped `--no-tools` condition is only a prompt-only negative control. Match selected model-token length when testing token-omission effects, rather than assuming a one-word slot is one token.

Use development data to tune masks and observation budgets. Create a new independently held evaluation pool afterward. Do not repeatedly mine failures from the same final test model and then report those selected cases as an unbiased score. Select difficulty by measured performance and human solvability, not by dimensionality or output length.

## Robotics interpretation and next experiment

The new image and robot tracks make a bounded version of the original roadmap executable. They supply actual raster observations, known finite noise support, calibrated frames, occlusion, and stateful contact/action consequences. A learned controller study, perspective/depth sensing, articulation, rigid-body dynamics and physical uncertainty remain outside the implementation.

A meaningful next extension would integrate a contact-rich simulator, preserve privileged-state/sensor separation, and test whether conservative abstractions correctly license actions under new viewpoints, objects and contacts. Physical trials would test a further claim. A benchmark measures behavior; improvement requires a better learned or inference/control method and independent evaluation. See [The v0.5 research agenda](research-agenda-v0.5.md) and `configs/vision-study-v0.5.json`.

## OpenAI references: verified versus inferred

OpenAI's public `math` repository and the October 26, 2026 scientific-understanding announcement are plausible matches to the requested recent mathematics reference. The repository distinguishes proof artifacts and verification scope, which motivates independently checking the intended property here. No Lean artifact from that repository was compiled or incorporated into this benchmark, and none of its claimed mathematical results is independently verified by this project.

The October 26 announcement describes all-dimensional local smoothing/Kakeya work and an ETH result. All-dimensional mathematics is a plausible interpretation of the user's "100D rather than 3D" phrase; it is not a confirmed identification. Subexponential-time results do not imply P=NP or a practical speedup for this benchmark.

GPT-Red is an automated red-teaming research system with adversarial training and explicit threat models. We did not verify an official method named "100D red teaming" and did not integrate GPT-Red weights or internal training infrastructure. The applicable idea is constrained adversarial task generation with held-out evaluation and a solvability check.

## Shortcut audit and calibration

The v0.3 stress audit found that a fixed Express procurement schedule meets the original vending generator's operational goals, and that a fixed high-clearance path and 0.5 N grip solve the original robotics geometry after target recovery. Those valid completions remain accepted. They show that procedural length and nominal tool variety do not establish a need for adaptive control. The new barrier configuration certifies that hidden geometry must influence a guaranteed-success path, but it still has an efficient constructive solver. Necessity of an observation and computational difficulty are separate properties.

Workflow stress also exposed a finite-suite false accept: adding `max(0,scale-19)` to the correct expression preserves every sampled case while failing at scale 20. The symbolic gate now prevents that acceptance. Exact geometry removed false accept/reject cases near epsilon boundaries. Protocol stress aligned HTTP and stdio duplicate-key, structural and UTF-8 byte rules. These are measured evaluator repairs, not model-performance improvements. Full before/follow-up evidence is retained under `reports/stress-v0.3/`.

Version 0.4 now supplies a separate adaptive procurement challenge with exact
operational cost certificates, and stronger formal statement binding. Its runtime
and finite-game audits passed, while a fresh-context assistant solved all six
pilot tasks. The pilot is shared-host and exploratory; it supports accepting
alternative valid strategies but supplies no evidence of frontier hardness.
That historical measured record is [v0.4 results](v0.4-results.md). The current image/decision extension and its source-bound gates are [v0.5 results](v0.5-results.md).

## What would support a breakthrough claim

A credible strong claim needs new scientific evidence: clear separation from the closest prior art, independent task validity, reproducible failure modes missed by existing benchmarks, stable model ranking under budget controls, broad private structural generalization, and external replication. Better robotics or training outcomes require separate transfer experiments. Until those exist, use "research prototype" and state exactly what runs have been performed.
