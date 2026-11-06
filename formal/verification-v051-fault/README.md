# Bounded-fault formal verification, v0.5.1 extension

**Final gate: passed.** The authoritative completed report is
[`run-02/results.json`](run-02/results.json). It contains source and toolchain
hashes, exact command lines, saved diagnostics, the axiom inventory, mutations,
and checker verdicts. This is a new gate; prior formal sources, manifests, and
reports were not edited by this extension.

## What was checked

| Gate | Measured result |
|---|---|
| Pinned toolchain | Official Lean 4.35.0 Linux archive SHA-256 verified |
| Frontend | Public C ABI embedding, kernel trust level zero, sequential elaboration |
| Selected generic claims | 14 roots compiled and audited |
| Expected statements | 14 separately written explicit type bindings compiled |
| Axiom inventory | Only `propext`, `Classical.choice`, and `Quot.sound` |
| Unsafe exported declarations | None |
| Semantic wrong claims | All five rejected with their intended diagnostics |
| Injected custom axiom | Its declaration compiled; the axiom whitelist rejected the resulting claim |
| Omitted required export root | Inventory gate rejected it |
| Weakened statements | Both mutants compiled, then the unchanged expected-type audit rejected them |
| Valid export replay | Accepted by all six checker configurations |
| Deliberately corrupted proof replay | Rejected by all six with the intended type-failure diagnostics |

The six configurations are Lean's default checker, Lean's hardened checker,
Lean4Lean, Nanoda, Con Ron, and Con Leche. This includes four bundled external
implementations; the six configurations are not six wholly independent
software stacks. Nanoda reports this particular type failure through an
assertion/panic diagnostic and exit 101. The gate checks that diagnostic; an
arbitrary crash, timeout, or signal would not count as a successful control.

The valid export is `run-02/bounded-fault.ndjson`, with 99,095 records and
5,055,897 bytes. Its SHA-256 is:

```text
49fde2cfe1f847b30e12b1cd665f1de21fe865c9bc546b5f98c0b1382502169e
```

The archive hash recorded by the gate is:

```text
7289597a44543246c9227b8cae501767e095ce17f6d448b95fc4a8dc97268f6d
```

## Meaning of the claims

The mathematics has one fixed hidden world, a supplied truthful binary response
table, and a single global cap on flipped answers. The claims connect an
operational honest-or-flipped transcript to its exact mismatch count, prove
that saturated count updates preserve feasibility, preserve any actual world
whose total errors stay within the cap, and prevent excluded worlds from
returning. A supported subsequence with more than the cap's number of
contradictory occurrences excludes that world. If every remaining published
world is successful for an action, that action succeeds in any actual published
world consistent with the bounded-error transcript.

The occurrence witness is significant: a subsequence cannot use one actual
transcript occurrence twice. The generic lemmas allow repeated queries, so they
also cover transcripts broader than the runtime's once-only contract. The
runtime uses distinct one-use experiment IDs to identify accepted occurrences;
that representation and membership checking remain a separate implementation
boundary.

The five rejected wrong claims were a false proposition, duplicated occurrence
support, exclusion from too few contradictions, revival of a saturated dead
world, and failure to accumulate corruption debt over the transcript. Two
additional statement controls retained a theorem's name and parameters but
replaced its conclusion by `True`: `capped_live_iff` and `safe_action_sound`.
Both weaker sources are mathematically well typed. Their rejection by the
unchanged audit demonstrates that a theorem name alone cannot satisfy that
audit.

For the kernel control, the proof term of
`CausalFill.BoundedFault.safe_action_sound` was replaced by the closed universe
expression `Sort 0`. Its type does not match the required proposition. Each
checker had to reject that exact mismatch after accepting the valid export.

## Limits

This gate does **not** prove the Python optimizer's Bellman values, a generic
Python-to-Lean refinement, the runtime's event/query parser, physical sensor
assumptions, or physical robot execution. It also provides no evidence of model
performance or a breakthrough in mathematical research. The independent
analytic cost fixtures and Python certificate/stress reports are separate
evidence with their own scope.

The normal official CLI launcher returned `failed to locate application` on
this host. The gate therefore compiled the unchanged
`formal/embedding/lean_frontend.c` host against the official shared library. It
uses Lean's public frontend with an explicit system root and trust level zero.
No OS APIs, access controls, or proof-checking behavior were intercepted or
replaced. External replay consumed the plain exported data directly; the gate
does not claim that Lake's full paranoid build sandbox ran.

## Reproduction

From the repository root, use a **fresh** output directory:

```bash
python formal/verify_bounded_fault.py \
  --toolchain /path/to/lean-4.35.0-linux \
  --toolchain-archive /path/to/lean-4.35.0-linux.tar.zst \
  --backend embedding \
  --output formal/verification-v051-fault/reproduction \
  --timeout 300
```

On a host where the official CLI launcher locates its toolchain normally, use
`--backend cli`. The archive argument verifies the pinned download hash. The
gate also records hashes of the loaded runtime and each invoked checker.

## Preserved first attempt

`run-01` is retained rather than overwritten. Its 14 generic roots and expected
statements compiled, but a positive concrete fixture lacked an explicit unfold
of the `Feasible` definition before Lean's decidability synthesis. The harness
was repaired by adding that unfold; no theorem semantics changed. The completed
fresh run is `run-02`. Source snapshots in both directories preserve that exact
difference.
