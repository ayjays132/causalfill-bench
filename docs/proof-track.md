# Proof-carrying completion track

## What is checked

`ProofTask` asks an agent to fill a missing proof behind a fixed controller output statement. The assumptions are a finite conjunction of propositional clauses `F`, and the conclusion is a signed literal `goal`. A successful submission contains all three:

1. The exact published statement digest.
2. A resolution refutation of `F AND NOT goal`.
3. A concrete Boolean assignment satisfying the original `F`.

The first condition prevents changing the statement. The second establishes entailment in the declared propositional calculus. The third establishes that the assumptions are consistent. A proof from contradictory assumptions cannot satisfy the third condition. These obligations are independently visible in the evaluator's result.

The default evaluator checks a finite certificate in Python. Version 0.3 also provides a separate Lean soundness development and two complete kernel-checked exported artifacts. This is not a new mathematical theorem or evidence of Axiom-level research capability. The intended engineering standard is to make correctness depend on an inspectable artifact and a separate checker rather than the model's confidence or explanation.

## Public inputs and completion

Read `/formal/statement.json` for `nvars`, `clauses`, `goal` and `statement_sha256`. A literal `v` means variable `v`; `-v` means its negation. Each clause is an OR of its literals, while the entire list is an AND of clauses. Clause order is significant for proof indices and the statement digest. The empty clause is false.

The initial proof clauses are all original `F` clauses followed by exactly one clause `[-goal]`. Every subsequent proof step is a compact triple `[a, b, p]`: take earlier clauses `a` and `b`, resolve their opposite occurrences of variable `p`, and append the computed resolvent. The agent never gets to supply an invented derived clause. Indices are zero-based, and parents must already exist. The last derived clause must be empty. Every supplied step must be valid, and the final clause must be empty; an invalid suffix is rejected even after a valid refutation.

The final fill is:

```json
{
  "statement_sha256": "the exact public digest",
  "proof_steps": [[0, 5, 2], [1, 6, 3]],
  "consistency_model": [true, false, true]
}
```

The illustrated values are format examples, not a valid proof for a shipped task. The model has exactly `nvars` booleans, one for each variable in index order. Integers such as `0` and `1` are not accepted in place of booleans.

`check_prefix` checks at most 256 proposed steps at a time and supplies no missing steps or solution. Its feedback concerns only the candidate derivation against public premises. A final certificate may contain up to 12,000 steps subject to the kernel's 500,000 literal-entry storage bound and the protocol's 128 KiB request limit.

## Separate search and verification

`logic_kernel.py` is a small verifier with no dependency on a generator or search procedure. It normalizes and bounds inputs, computes each resolvent directly from its parents, checks model truth values, and binds the immutable statement. It has no `eval`, executable proof language, admitted-axiom mechanism, arbitrary import, or model-judgment call.

`proof_search.py` is an untrusted constructive reference. It uses Davis-Putnam variable elimination, subsumption and pruning of unused proof-DAG nodes. Any of its outputs can fail verification; its own success flag is never trusted. `solve_proof(public, call)` obtains the formal statement through the public `read_file` tool and returns a certificate without access to a Task object or private state.

The verifier and proof search were written independently. Tests establish accepted-resolution-step soundness against a separately enumerated Boolean semantics on small clauses, verify all supported task classes, reject forged premises and forward references, and ensure an incomplete proof or false consistency witness cannot pass. The Python implementation itself has not been formally verified in Lean or another foundational proof assistant. Its runtime, parser, logic code and immutable task statement remain part of the trusted computing base.

## Original generated statements

Start with an unsatisfiable clause set `G`. Introduce a fresh signed output variable `goal` and append it to every clause: each assumption becomes `C OR goal` for `C` in `G`. The resulting assumptions are satisfiable when `goal` is true. If `goal` were false, all clauses of `G` would need to hold, which is impossible. Thus `F` entails `goal` nonvacuously.

The underlying contradictions are established finite logic constructions, not new discoveries:

| Split | Structure | Scale |
|---|---|---|
| train | A forced implication chain with an opposite terminal condition | 6, 9 or 12 chain variables before the output variable |
| dev | A Boolean XOR ladder, fixed inputs and an opposite final parity | 4, 5 or 6 input variables plus ladder variables |
| transfer | Distinct resource requests exceeding available slots, encoded as pigeonhole clauses | 4 into 3, 5 into 4, or 7 into 6 |

The largest standard case has 43 variables including the output and 238 original premises. Variables and signs are relabeled per instance. The proof must remain valid for the actual published clause encoding. These structural changes do not establish an unseen mathematical-domain distribution; all generators are public.

Counterfactual pairs change one signed output-polarity parameter and all its occurrences. They are explicitly labeled `twin_kind="theorem_polarity"`. The non-goal constraints remain fixed. This is a specification-binding intervention, not a physical causal intervention, and should be reported separately from sensor or supply-delay twins.

## What a passing result means

Under the stated finite propositional semantics and the correctness of the executed kernel, the submitted certificate proves the exact conclusion from consistent assumptions. This is stronger than testing a few sample assignments or accepting persuasive prose. It does not establish a novel theorem, bound a model's general intelligence, or demonstrate that the case is hard for a frontier model. A strong agent can legitimately use its own SAT/proof-search program to construct the certificate.

The original development reference generated and independently checked 40 relabeled 7-into-6 cases (20 seeds, both theorem-polarity twins). All passed. The shortest retained certificate had 4,881 resolution steps; the largest serialized standard JSON submission envelope was 110,445 bytes and contained 6,454 steps, below the 128 KiB limit. The matrix took approximately 44.6 seconds in the development environment. These are constructive reference checks, not LLM results or a worst-case bound across every possible seed.

Raw proof length or CPU time is not a model difficulty score. Comparative claims still require controlled real-model trials, isolation, exact versions and independent replication.

## Research grounding

Propositional resolution and refutation are classical methods. See J. A. Robinson, *A Machine-Oriented Logic Based on the Resolution Principle*, JACM 12(1), 1965: [primary paper](https://web.stanford.edu/class/linguist289/robinson65.pdf).

Axiom's [Proof of Concept](https://axiommath.ai/research/proof-of-concept/) describes generating mathematical proof artifacts and accepting them through Lean/Mathlib verification. That is an inspiration for separating candidate generation from checking; this project does not reproduce AxiomProver or its research results. Our optional Lean artifacts have the exact foundational scope documented in [Formal assurance](formal-assurance.md), while generic Python/Lean implementation equivalence remains unproved.
