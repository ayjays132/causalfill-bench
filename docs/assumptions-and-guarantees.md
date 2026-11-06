# Assumptions, proof obligations and guarantees

This document answers a stronger question than "did some tests pass?": what follows logically from each accepted certificate, under which explicit assumptions? It also states what remains in the trusted computing base.

## 1. Affine operator certificate

Assume both the intended operator and submitted operator are affine maps over the same finite field, with the stated dimension. Let their difference be d(x)=A x+b. If d(0)=0, then b=0. If d(e_j)=0 for every standard basis vector e_j, every column of A is zero. Hence d(x)=0 for every vector x.

The latent verifier checks those points exactly modulo101. The candidate grammar enforces affine sparse rows, and the planted construction is separately implemented. Therefore a passing basis certificate establishes equivalence throughout the declared field-vector domain, not merely agreement on sampled vectors. It does not establish equivalence for nonlinear programs, other arithmetic, physical sensor noise or arbitrary model internals.

The sparse reference's moment construction is established algebra, not a new theorem. Each vector query returns n field values. Computational cost and information received must be accounted for separately from the count of queries.

## 2. Propositional entailment certificate

The independent resolution checker accepts premises and indexed proof steps. If a Boolean valuation satisfies clauses C and D, where C contains x and D contains not-x, it satisfies their resolvent: if x is false, the remaining part of C must hold; if x is true, the remaining part of D must hold. Each accepted step therefore preserves logical consequence. By induction, deriving the empty clause establishes that the submitted premise set is unsatisfiable.

For a task with fixed premises F and signed goal g, the checker receives F together with not-g. An accepted refutation establishes F entails g. The task additionally requires a concrete satisfying assignment for F. That witness prevents receiving credit from inconsistent premises, where every conclusion would follow vacuously. The statement digest binds the exact variable domain, premises and signed goal; the agent cannot substitute an easier theorem.

The checker computes every resolvent. Proofs contain only earlier-clause references and a pivot, so an agent cannot introduce an unproved assertion or an admitted axiom. A syntactically valid derivation that does not derive the empty clause does not pass. Resource bounds protect the verifier and are part of the task contract.

The optional `formal/` project now formalizes these finite propositional semantics in Lean 4.35.0. Its kernel-checked theorems establish resolution soundness, indexed-checker acceptance implying unsatisfiability, refutation implying signed-goal entailment, model-checker soundness, and the conjunction of premise satisfiability with entailment. Two complete exported release certificates (865 and 6,018 steps) each produce that nonvacuous theorem. Their actual Lean definitions were serialized back to JSON and compared with all original clauses, goal, Boolean model and proof triples; source and input hashes were also checked. Axiom inspection reports only the declared standard Lean axioms `propext`, `Classical.choice` and `Quot.sound`, or a subset. No custom axiom, `sorry` or `native_decide` is used.

This proves the specified Lean mathematical objects and the Lean checker theorem. It does not establish generic implementation equivalence between the Python and Lean programs. Python JSON parsing, integer/resource bounds, artifact translation, build tools, statement provenance, and the link to any intended real-world interpretation remain outside that theorem. Exact instance round-trips reduce a concrete statement-binding risk but are not a proof of the exporter for every possible input. The underlying resolution rule is classical mathematics, not a new logical foundation. See [Formal assurance](formal-assurance.md) for the full trust boundary and reproducible commands.

## 3. Indistinguishability and abstention

Suppose two hidden worlds have identical public descriptions and return identical observations for every permitted action sequence, but require different final fills. A deterministic agent observes the same history and must return the same answer in both. It cannot be correct in both worlds. For a uniform random choice between two worlds and no other information, a randomized agent's expected exact-answer accuracy is at most one half.

The ambiguity controls construct that pair and exhaustively check the finite observation interface. This is a certificate of missing information under the stated interface, not evidence that all hard problems are unanswerable. The appropriate abstention score remains separate from capability success.

## 4. Finite adaptive identification

Let S be the surviving set of possible worlds. An allowed binary experiment q partitions it into S0 and S1. If only one world survives, the required remaining number of experiments is zero. Otherwise the exact minimax depth is:

`D(S) = 1 + min_q max(D(S0), D(S1))`, over informative allowed experiments.

The recurrence has two directions. Any successful strategy must start with some allowed q and handle its worse branch, which establishes a lower bound. Choosing a minimizing q and recursively following optimal subtrees provides a strategy attaining the bound. Subsets strictly shrink, so the finite recurrence terminates.

The diagnosis track supplies checkable certificates covering the reachable subproblems and their possible experiment partitions. An independent verifier validates the recurrence and a separate tree checker validates coverage of every candidate world. These establish optimal worst-case query depth within that explicit finite table. They do not establish computational hardness for language models, optimal reasoning time, or general scientific discovery ability.

The simpler counting bound is `D(S) >= ceil(log2 |S|)` when every experiment has two possible outputs and all worlds must be distinguished. It can be loose because not every balanced partition is an allowed experiment. The exact recurrence can be stricter.

Finally, a diagnosis submission must cite actually observed experiments that eliminate every competing world. Guessing the hidden world without sufficient distinguishing evidence does not pass the proof-carrying task, even if the guess happens to match.

## 5. Sufficient workflow certification

The public workflow domain contains integer ledger inputs in `[-1000000,1000000]`, scale in `[1,1000000]`, and, for the transfer clamp, the explicit constraint `reserve <= ceiling`. The symbolic checker normalizes rational polynomials and bounded min/max lattice expressions. It uses only justified identities and declared ordering assumptions. A matching normal form is sufficient for equality; failing to match is not proof of inequality.

Separately, every original AST intermediate is bounded before algebraic cancellation. The checker maintains a magnitude bound `|x| <= M` and a positive denominator divisor `denominator(x) divides D`, hence `|numerator(x)| <= M*D`. It checks the published `10**30` Fraction numerator/denominator caps throughout the original expression. Only divisors proved equal to a nonzero rational constant are supported. Syntactic and expansion limits bound the certificate computation. These obligations provide a sufficient bounded-totality argument for the declared DSL and input domain, not an operating-system memory or wall-clock guarantee.

Strict success requires this symbolic certificate and the separate behavioral suite. The implementation is Python with independent semantic/property audits; these workflow claims have not been formalized in Lean. The documented proof system is deliberately incomplete. See [Workflow certification](workflow-certification.md).

## 6. Robotics geometry and information necessity

Workspace and segment/box collision predicates interpret each finite input number through `Fraction(str(number))`. Closed obstacle contact is a collision; positive separation is clear. Camera reconstruction and target matching retain their separately declared tolerances. These exact geometric predicates concern the idealized symbolic scene, not physical actuator or sensor accuracy.

For `robotics_barrier`, start and target lie on opposite sides of a certified separating plane. Each of the paired full-height barriers leaves an individually feasible gap, but their union covers the whole plane inside the workspace. Any common continuous path must cross that plane and would intersect at least one barrier. Thus no single path solves both worlds. The public descriptions and camera data agree until an action returns geometry-dependent information. A guaranteed-success agent must obtain such information; lidar and suitable path probes are both possible sources. Under a uniform hidden choice, a policy receiving no distinguishing observations has average strict success at most one half. This is an observation-necessity argument, not a lower bound on computation after observing the scene. The finite certificate checker and constructive witnesses remain Python, not Lean-verified.

## 7. Guarantees that remain behavioral

Grid programs are checked on finite suites, not by universal equivalence proofs. Vending success establishes the simulator's accounting and operational goals for the realized episode; it is not a profitability prediction for an actual business. The stress audit's legal fixed procurement schedule shows that the original `vending` generator does not require adaptive business control. The original robotics generator also admits a high-clearance route after target recovery. Valid robust completions remain valid; the separate adaptive market and barrier profiles are scored independently.

Certificate hashes are commitments to content, not authentication. An external verifier must know which statement and evaluator it trusts. Public generator code and development seeds are not private evaluation data.

## 8. Ranked finite-game guarantees

Assume an explicit finite deterministic transition table, a complete list of
possible initial states, positive integer action costs, and a strictly decreasing
rank on every transition. States with the same current observation must agree on
terminal status and action availability. A controller remembers its own past
actions and observations. Its objective is success in every listed initial world
with minimum worst-case cumulative operational cost.

A belief is the set of states still consistent with that history. A legal action
produces one successor belief for each possible next observation. The exact value
is zero at all-success beliefs, infinity at any unavoidable-failure belief, and
otherwise the minimum over actions of action cost plus the maximum child value.
Strict rank decrease permits induction. A lower certificate must cover every
action and branch; a successful policy alone supplies only an upper bound.

The Python certificate checker reconstructs all alternatives independently of
the optimizer's bitset implementation. A separate strategy checker replays raw
transitions in every initial world. The Lean development proves the corresponding
lower-bound, impossibility, attaining-upper-bound and exactness implications for
finite ranked AND/OR arenas, including nonempty action branches and no outgoing
goal actions. Its generic observation-class result allows overlapping successful
completion sets: indistinguishable worlds need not have distinct literal answers.

Concrete Lean assurance covers four policy modes of ONE two-round, four-world
market, with 448 raw states before projection. Adaptive cost is exactly 8; the
three restricted classes cannot guarantee success. Kernel equality binds each
whole imported arena to an independently rendered expected literal, defeating a
mere JSON echo of expected data. The 29 new theorem roots passed six checker
configurations; the exported axiom inventory contains only `propext` and
`Quot.sound`. This is stronger statement binding for these fixtures, not a proof
of the generic Python projection, simulator, parser or build environment.

The larger runtime audit covers one replay witness per projected state and every
outgoing edge across 27 generated games. It compares complete responses as well
as operational state, including paid stutters and a finite invalid-action battery.
It does not enumerate every possible runtime history. In particular, real-world
equivalence requires a separate refinement argument. Operational bounds omit
setup reads, static quotes and final term reconstruction. See
[Finite games](finite-belief-games.md), [Adaptive market](vending-adaptive.md), and
[Formal information assurance](formal-information.md).

## Research context

The engineering principle of generating a proof and checking it independently is central to Axiom's published Lean/Mathlib workflow: https://axiommath.ai/research/proof-of-concept/ . The propositional inference rule has long-established prior art: J. A. Robinson, *A Machine-Oriented Logic Based on the Resolution Principle*, JACM1965, https://doi.org/10.1145/321250.321253 . Automated theorem-proving and verified-code benchmarks already exist, including miniF2F and VERINA. This project proposes a cross-domain evaluation protocol; it does not claim to invent certificates, resolution, active learning or formal verification.
