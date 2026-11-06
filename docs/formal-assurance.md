# Formal assurance for the propositional certificate track

The `formal/` directory contains a standalone Lean 4 project for the ordinary
propositional resolution rule used by `causalfill/logic_kernel.py`. Its scope
is deliberately limited: prove soundness of a typed executable checker and
of finite resolution derivations, then use a separately verified model to
establish satisfiable entailment. This is an application of established
propositional logic, not a claim of new mathematics.

## The formal contract

A literal has a natural-number variable and a Boolean polarity. A valuation
assigns a Boolean to every natural-number variable. A clause holds when at
least one member literal holds; a CNF holds when every member clause holds.
An empty clause therefore never holds. A tautological clause has its usual
meaning; the implementation does not discard or special-case it.

The executable resolution operation checks for opposite pivot signs, chooses
the positive-left orientation first when both orientations are available,
removes only the selected sign from each individual parent, and unions the
remaining literals. Its union uses a proved membership-preserving duplicate
removal operation. It does not remove both pivot signs from the combined
parents, which would be unsound for tautological parents.

| Declaration | What Lean proves |
| --- | --- |
| `mem_deduplicate` and `sameClause_holds` | Removing duplicates and any other membership-preserving representation change preserve clause semantics. |
| `mem_mergeResolvent` | A literal belongs to the result exactly when it belongs to one parent and is not that parent's selected pivot literal. |
| `resolve_sound` | Every successful resolution result holds under every valuation satisfying both parents. |
| `derivable_sound` | Every finite derivation built from premises and the executable resolution rule is entailed by its premises. |
| `derive_sound` | Successful execution of every supplied indexed step preserves satisfaction of the complete clause pool. |
| `refutes_unsatisfiable` | Acceptance by the executable refutation checker implies that no valuation satisfies its premises. |
| `refutation_entails` | An accepted refutation of `F ++ [[complement goal]]` entails the goal from `F`. |
| `satisfiable_refutation_nonvacuous` | If `F` is satisfiable and the extended CNF is refuted, then `F` is satisfiable and entails the goal. |
| `checkModel_sound` and `checked_nonvacuous` | A computed Boolean model check supplies the satisfiability witness needed for the preceding conclusion. |
| `checked_derivation_nonvacuous` | The same conclusion follows from a kernel-checked derivation of the empty clause and a checked model. |

`NonvacuousEntailment F goal` means exactly
`Satisfiable F ∧ Entails F goal`. The satisfiability conjunct prevents a
contradictory original premise set from counting as a substantive proof of an
arbitrary goal. No proof-search completeness claim is made.

## Indexed certificate behavior

`Step` contains only a left index, right index, and pivot variable. `lookup`
uses zero-based indices and fails when a parent does not yet exist.
`executeStep` computes the result itself. `derive` appends one computed clause
per successful step and checks the complete supplied list.

`refutes` accepts an existing empty premise when there are no steps. When
there are steps, it requires the last computed clause to be empty. A malformed
suffix causes failure even if an earlier prefix derived the empty clause.
The Lean examples cover both pivot orientations, empty inputs, an existing
empty premise, self-resolution of a tautology, duplicate literals, missing
pivots, forward references, invalid suffixes, and a nonempty final clause.
They also prove nonvacuous conclusions for positive and negative goals.

## Relationship to the Python implementation

The theorem is about the Lean definitions. It is not a formal verification of
Python execution or of JSON parsing. The intended correspondence is explicit:

| Python representation or operation | Lean representation or operation |
| --- | --- |
| Nonzero signed literal `k` | `pos k` for `k > 0`; `neg abs(k)` for `k < 0`. Variable numbers remain one-based. |
| Boolean assignment entry `assignment[k - 1]` | `assignmentValuation assignment k`. |
| Ordered list of initial clauses | An ordered `CNF` list; initial clause indices are unchanged. |
| Triple `[left_index, right_index, positive_pivot]` | `Step` with the same three natural numbers. |
| Python clause `sorted(set(clause))` | A clause with the same literal membership. The exporter preserves the original initial-clause order and multiplicity, while Lean removes duplicate literals from derived clauses. |
| `(left - {pivot}) \| (right - {-pivot})` | `mergeResolvent left right (pos pivot) (neg pivot)`. The reverse orientation is treated correspondingly. |
| Python first-orientation priority | The first branch of `resolve`. |
| Appending one computed resolvent | Appending one computed clause in `derive`. |
| `derived_empty` after successful checking | `refutes = true`, including the no-step existing-empty special case. |

Clause order inside a clause is not logically relevant; order in the outer
CNF is relevant to parent indices and is preserved. `mem_mergeResolvent`
establishes the exact set-membership equation that connects the two
resolution representations. `sameClause_holds` establishes semantic
invariance whenever two representations have the same members. The claim
that Python's actual `set`, `sorted`, integer checks, and JSON implementation
realize that correspondence is not a Lean theorem in this artifact.

The typed Lean checker accepts a broader syntactic domain than the Python
public API: it does not enforce the Python variable, clause, step, or storage
bounds, and natural-number variable zero exists in its internal type. The
exporter validates the release JSON's nonzero one-based domain, integer types,
triple shapes, earlier-parent references, and resource limits before writing
Lean source. The absence of those resource limits in the logical theorem
does not grant the Python API permission to ignore its own limits.

The finite assignment is extended with `false` at variable zero and beyond
its supplied entries, providing a total mathematical valuation. Release
input validation ensures that every relevant variable is in `1..nvars` and
that the supplied assignment has exactly `nvars` Boolean entries.

## Release-certificate proof construction

`formal/export_certificate.py` reads the two public JSON inputs and emits
typed Lean data. It imports no task generator, proof search code, or Python
logic kernel. For every step it proposes a concrete resulting clause and a
local theorem of the form

```lean
Derivable.resolution (pivot := p) derivedLeft derivedRight (by decide)
```

The `by decide` proof reduces and checks the local resolution equation in
Lean's kernel. An incorrect proposed result cannot be rescued by the
translator's own output. Named theorems share previous derivations, avoiding
one enormous reduction of the full indexed checker. A final empty-clause
derivation and a separately checked model produce the theorem
`certifiedNonvacuous` for the concrete exported premises and goal.

Each generated module additionally evaluates the full indexed checker. This
runtime check supplies independent operational coverage of parent indexing
and full-list processing. It is supplementary to the kernel-checked local
derivation proof; runtime evaluation is not used as an axiom of that proof.

The module then evaluates its actual Lean premises, signed goal, assignment,
and step list back to a JSON file. The corresponding manifest records exact
SHA-256 hashes of both input files, the generated Lean source, and the
canonical statement commitment. These enable an independent comparison
between the statement that Lean proves and the original release statement.
The translator and this round-trip machinery remain unverified programs;
the artifact reports that correspondence gap rather than claiming a proved
equivalence between Python and Lean.

## Trusted base and limits

The project pins `leanprover/lean4:v4.35.0`, imports `Std`, and has no external
Lean package dependencies. The proof claim relies on the pinned Lean kernel,
its standard definitions and permitted logical axioms, and the integrity of
the source and toolchain used for verification. The proof-producing tactics
must emit terms accepted by that kernel. No custom logical axiom, admitted
proof, `native_decide`, or unsafe proof escape is part of this artifact.

The actual `#print axioms` audit reports exactly `propext`,
`Classical.choice`, and `Quot.sound` for every audited resolution,
derivation, refutation, and nonvacuity theorem. `checkModel_sound` uses the
smaller set `propext` and `Quot.sound`. Both concrete release theorems use
the same permitted three-axiom set. These are the standard Lean principles
of propositional extensionality, classical choice, and quotient soundness;
they are listed explicitly rather than described as an axiom-free result.
The verification gate rejects any additional axiom, including an admitted
proof axiom or an evaluator-backed proof axiom.

The supplementary indexed-checker evaluation and round-trip file generation
also exercise Lean's evaluator/compiler, runtime, and filesystem. Their
output should be compared with the independently parsed input files. The
SHA-256 statement commitment is an integrity identifier, not a signature or
a proof of truth.

This assurance does not prove generator correctness, benchmark difficulty,
model capability, generalization, adaptive experiment optimality, tool
isolation, score calibration, or any interpretation of a real-world causal
claim. It applies to the stated finite propositional formulas.

## Recorded verification

The complete core project, its examples, the axiom audit, and both concrete
release certificates compiled successfully with Lean 4.35.0, commit
`eb6cafb7290e8bd5f2937522d8d804f58f02bafc`, using the official Linux release
toolchain. The downloaded archive was verified against SHA-256
`7289597a44543246c9227b8cae501767e095ce17f6d448b95fc4a8dc97268f6d`.

| Check | Observed result |
| --- | --- |
| `lake build` | Exit 0; the semantic proofs, executable checker, and all examples compiled. |
| `lake env lean CausalFill/Audit.lean` | Exit 0; all 15 listed generic/example theorem dependencies stayed within the explicit standard-axiom whitelist. |
| `ReleaseModel.lean` | Exit 0; 865 local resolution proofs, the consistency-model proof, and `certifiedNonvacuous` checked; the full indexed runtime checker also accepted. |
| `ReleaseReference.lean` | Exit 0; 6,018 local resolution proofs, the consistency-model proof, and `certifiedNonvacuous` checked; the full indexed runtime checker also accepted. |
| Actual Lean data round trips | Both matched all five original fields exactly: `nvars`, ordered raw `clauses`, signed `goal`, `consistency_model`, and `proof_steps`. Input and generated-source hashes also matched their manifests. |

The release conclusions are named
`CausalFill.Exported.ReleaseModel.certifiedNonvacuous` and
`CausalFill.Exported.ReleaseReference.certifiedNonvacuous`. Each applies to
238 original clauses over 43 stated variables and includes a checked
satisfiability witness. Their canonical statement commitments are:

| Release artifact | Canonical statement SHA-256 |
| --- | --- |
| Model | `0b2fbd2916a4bf10d536aada3c30467b8713b59ca0592f5a6e8e044b6fda9298` |
| Reference | `7ef0583aa6f7a0b3c26a8d8ed32ac4ff2605c3d68b534e3c2918f82e6016c77a` |

[`../formal/verification/agent-results.json`](../formal/verification/agent-results.json)
records the successful checks, source hashes, exact axiom sets, and round-trip
hashes. A complete rerun through `formal/verify.py` additionally records each
command's output and elapsed time. These are verification results for the
public certificates; they are not new solver-performance measurements or
evidence of intelligence.

## Reproduction

The exact source and verification commands are listed in
[`../formal/README.md`](../formal/README.md). Run the build first, then the axiom
audit and both release modules. The release modules require working directory
`formal/`, so their round-trip outputs are written beside their sources.

## GitHub automation

`.github/workflows/formal.yml` reproduces the formal gate on Linux using the pinned official Lean 4.35.0 archive and its SHA-256. It can run manually or on changes to formal sources and certificate inputs. The local gate was executed for this release; the GitHub-hosted workflow has not been run here. The Python core remains usable without Lean.
