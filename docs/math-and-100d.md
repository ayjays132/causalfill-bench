# Mathematics, verification, and the meaning of 100 dimensions

## What is implemented

`LatentTask` is an exact, symbolic system-identification task over the prime
field GF(101). Difficulty 1 has 8 coordinates, difficulty 2 has 32, and
difficulty 3 has 100. An agent sees a masked operator template and can query
its output on bounded vectors of canonical integer residues. The final fill
is an offset vector and a sparse matrix representing an affine map:

\[
f(x) = Ax + b \pmod{101}.
\]

The candidate is data, not executable Python. Booleans, floats, noncanonical
residues, duplicate columns, oversized rows, and unknown submission keys are
rejected. Zero terms and row-term reordering are permitted because they can
describe the same behavior. Empty rows represent zero linear contributions.

The hidden verifier has two components. First, it checks the zero vector and
every standard basis vector. Because the submission language and task grammar
are both affine, agreement on these inputs proves equality on the entire
finite input space. Second, it checks twelve independently generated dense
interventions. These are additional behavioral checks, not a substitute for
the complete affine certificate. The target is evaluated directly from the
planted structural construction; the candidate uses a separate sparse
interpreter. Verification does not compare answer strings or require the
planted row ordering.

Recovery is the proportion of entire output rows recovered exactly. Counting
correct scalar matrix entries would inflate scores because the planted maps
contain many zeros. Success requires the complete certificate and all held-out
interventions to pass. The exact certificate is valid only for this explicit
affine hypothesis class; it is not a general proof checker.

## Actual structural split

| Split | Planted transform | Structural change |
| --- | --- | --- |
| `train` | `y[i] = d[i] * x[i] + b[i]` | Independent affine coordinates. |
| `dev` | `y[i] = d[i] * x[pi(i)] + b[i]` | Unknown coordinate permutation composed with affine scaling. |
| `transfer` | `y[i] = d[i] * x[pi(i)] + c[i] * x[pi((i+1) mod n)] + b[i]` | Adds cyclic coupling after the permutation. |

All arithmetic is modulo 101. Planted coefficients are nonzero. The dev
permutation is forced to differ from the identity. The transfer map has two
distinct input coordinates per row; invertibility is not assumed or needed
for identifying the forward map. These are genuinely different structural
classes, but only three authored grammars. Holding out transfer compositions
does not establish broad out-of-distribution generalization.

A counterfactual twin changes exactly one primary coefficient to a different
nonzero residue. Offsets, permutation, other coefficients, public artifacts,
and evaluator interventions stay fixed. Reusing the first episode's answer
therefore fails the twin unless the changed relationship is recovered.

## Solvability and known easy solution

The domain deliberately documents a complete observation plan: query `f(0)`
and then `f(e_j)` for all coordinates. The offset is `f(0)` and column `j` is
`f(e_j) - f(0)`. This requires `n + 1` probes. Probe cost is one; the task has
`n + 8` total cost units and `n + 12` calls. The seven remaining cost units can
cover document inspection. Its implementation helper,
`recover_affine_operator`, receives public observations and does not receive a
task, seed, coefficients, or hidden verifier state.

`reference_answer()` obtains the same observations through the domain's
`query` method. It is an engineering solvability witness. Direct method calls
do not pay the external runner's budget, so a measured solver must issue the
probes through the runner and account for every call. The reference is not a
blind model evaluation and must never appear in a model leaderboard.

This is an intentionally solvable control family for exact reasoning, tool
discipline, and counterfactual sensitivity. A hundred dimensions alone do not
make it a hard frontier-model problem. An efficient general solver is supplied.
Potential future restrictions on probe budgets need an identifiability proof;
reducing observations until multiple maps fit is not a legitimate way to
manufacture difficulty. This implementation does not simulate 100 spatial
dimensions, render robot camera images, or demonstrate real robot transfer.

## Additional challenge: sparse recovery with five informative interventions

`SparseLatentTask` keeps the same exact affine construction and complete
verifier but limits the entire episode to nine cost units at every dimension.
It publicly states that each output row contains at most two nonzero terms.
The public manual gives the grammar and constraints, without a solving
derivation. The control's coordinate-by-coordinate observation plan exceeds
the budget at 32 and 100 dimensions. In the 8-dimensional case it consumes
all nine cost units, so this level is a light control rather than an enforced
scarcity challenge when the solver already knows the schema.

Five informative interventions suffice at every supported dimension. Probe
zero to recover the offset, then probe vectors whose coordinate `j` is
`1`, `j`, `j²`, and `j³`, respectively, modulo 101. For each output row,
subtract the offset to get moments `m0`, `m1`, `m2`, `m3`. If a row has terms
at distinct indices `j` and `k` with nonzero coefficients `a` and `b`, then

\[
m_r = a j^r + b k^r,\qquad
D=m_0m_2-m_1^2=ab(j-k)^2\ne 0.
\]

Field division gives their sum and product:

\[
s=\frac{m_0m_3-m_1m_2}{D},\qquad
p=\frac{m_1m_3-m_2^2}{D}.
\]

The indices are roots of `t² - s*t + p` among the permitted coordinates.
Recover `a = (m1 - m0*k)/(j-k)` and `b = m0-a`. A one-term row has `D=0`
and nonzero `m0`; its index is `m1/m0`. A zero row has all four moments zero.
The implementation also checks reconstruction consistency. It handles the
important cancellation case `m0=0` for a nonzero two-term row; treating that
case as an empty row would be incorrect.

The field contains all 100 possible coordinate indices as distinct residues,
so the required divisions are valid for the stated grammar. A test verifies
100-dimensional recovery through the actual session with five probes plus
one manual read, consuming six of nine cost units. The implementation exports
`sparse_probe_plan` and `recover_sparse_operator`, which use only supplied
public observations. The unchanged exact affine verifier then checks the
recovered map on a complete basis certificate and additional interventions.

This is a **classical Prony-style sparse reconstruction**, not a new theorem
or a claimed OpenAI algorithm. Related primary prior art includes Ben-Or and
Tiwari, *A deterministic algorithm for sparse multivariate polynomial
interpolation* (STOC 1988),
<https://doi.org/10.1145/62212.62241>, and finite-field interpolation research
such as Javadi and Monagan,
<https://www.cecm.sfu.ca/~monaganm/papers/mahdiSparse.pdf>.
Our narrow two-term formula is directly derived above and implemented
independently, without copying their code.

This task adds a meaningful distinction between indiscriminate coordinate
scanning and choosing informative experiments. It does not establish that
frontier models struggle with the task, that the benchmark is novel as a
whole, or that sparse symbolic recovery improves real robot vision.

## Verified OpenAI references and their limits

The sources below were inspected on 2026-11-01. These notes describe what the
authors report; this project did not independently compile or validate their
research proofs.

1. **OpenAI, “Working with academic communities to build scientific
   understanding,” October 26, 2026.** The official article describes an ETH
   refutation, Lean formalization, and independent academic examination. It
   explicitly says obtaining practical algorithmic improvements requires
   further research. The article also discusses local smoothing and Kakeya in
   all dimensions. This is a possible match to an informal “100D instead of
   3D” reference, not a confirmed identification of that phrase.
   <https://openai.com/index/building-scientific-understanding-with-academic-communities/>

2. **OpenAI mathematical research repository.** Its README describes results
   at differing verification stages and calls the manuscripts raw research
   data. Some results lack formalizations. The ETH formalization scope
   distinguishes its exact subexponential counting statement from a sharper
   bound in the accompanying manuscript. That distinction is a useful model
   for accurately reporting a verifier's scope.
   <https://github.com/openai/math>
   <https://github.com/openai/math/blob/main/lean/docs/378.md>
   <https://github.com/openai/math/blob/main/lean/ComparatorChallenges/README.md>

3. **OpenAI, “GPT-Red: Unlocking Self-Improvement for Robustness,” July 15,
   2026.** The official article describes automated attacker/defender
   self-play, explicit threat models, and held-out evaluation, including an
   Andon Labs vending-agent case study. No official method called “100D red
   teaming” was identified in this research. GPT-Red itself is an internal
   model; this project neither includes it nor claims access to its training
   system.
   <https://openai.com/index/unlocking-self-improvement-gpt-red/>

## What this benchmark takes from the research

The practical design influence is **a candidate artifact checked against an
independent, explicit specification**, with honest statements about the
scope of verification. Adversarial task generation should also have a stated
threat model and preserve solvability. Neither idea makes our prototype a
mathematical breakthrough by itself.

An ETH refutation is not a proof that P equals NP. Subexponential time is not
the same as polynomial time. No mathematical result from the referenced
repositories is imported into this implementation, and no general planning or
robotics acceleration is claimed. The latent track's complete certificate is
elementary finite-field linear algebra. Version 0.3 separately adds an optional
Lean 4.35.0 assurance project for the propositional proof track; its toolchain
was installed and executed during verification but is not a core runtime
dependency or included in the source archive.
