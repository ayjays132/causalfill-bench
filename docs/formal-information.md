# Information necessity and finite strategy guarantees

The v0.4 addition gives machine-checked statements about **which information a
successful completion must distinguish** and **the minimum worst-case action
budget of a declared finite planning arena**. It does not infer benchmark
novelty, model intelligence, or physical robot competence from a proof checker
pass.

The generic statements are in
[`Information.lean`](../formal/CausalFill/Information.lean), with executable
finite checks in [`FiniteArena.lean`](../formal/CausalFill/FiniteArena.lean).
They use Lean 4.35.0 and `Std`; there is no Mathlib dependency, custom axiom,
`sorry`, or `native_decide`. The original resolution proofs are preserved.

## 1. What an observation must distinguish

Let a world be a possible hidden state, an observation be everything available
to a deterministic policy at a decision, and a completion be its output. If
two worlds give the same observation, the policy must give the same completion.
If those worlds have disjoint sets of successful completions, that common
completion cannot succeed in both worlds.

The module proves this for arbitrary types, with no assumption about words,
grids, economics, or robots:

- `equal_observation_equal_choice` states policy congruence.
- `incompatible_same_observation` rules out joint success under identical
  observations and incompatible completion requirements.
- `guaranteed_pair_requires_distinguishing_observations` gives the converse
  requirement for a policy that succeeds in both worlds.
- `observation_class_success_le_one` counts successes in any finite list of
  mutually incompatible worlds sharing an observation.

The more general `observation_class_capacity_bound` permits overlapping
successful-completion sets. For a finite observation class \(C\), a finite list
of legal completions \(A\), and policy \(\pi\), it proves the counting bound

\[
 \#\{w\in C:\operatorname{success}(w,\pi(o(w)))\}
 \leq \max_{a\in A}\#\{w\in C:\operatorname{success}(w,a)\},
\]

provided every listed world has the same observation and the selected output
belongs to \(A\). The right side is computed by `completionCapacity`; it is not
a guessed difficulty score. If all successful-completion sets are pairwise
disjoint, the bound is one success. Dividing the count by a nonzero number of
distinct uniformly sampled worlds gives the corresponding accuracy bound.
The Lean statement is a counting theorem, not a formal development of
probability measures or randomized policies.

An observation can represent a complete transcript, so these statements also
apply to final outputs after tool use when transcript equivalence has been
established. They do not themselves prove that two interactive executions have
equivalent transcripts. The next component models that sequential issue.

## 2. The sequential model

An arena node is a belief state. Each available action has a nonnegative natural
cost and a list of possible observation-successor nodes. Choosing an action is
an existential choice: the strategy can choose one available alternative.
Handling its possible observations is universal: every successor must succeed.
Costs accumulate along a single realized trajectory, not across mutually
exclusive observation branches.

`CanWin game state budget` is an inductively defined **finite successful
strategy**. A goal node succeeds immediately. Otherwise, a strategy picks a
listed action of cost \(c\), reserves a remaining budget \(r\), proves that all
its possible successor nodes can win within \(r\), and requires \(c+r\leq B\).
There is no hidden solver, Python callback, or runtime reward function inside
this proposition.

The value domain is `Option Nat`: `some n` is a finite budget and `none` is
infinity/unwinnability. In particular, `none` never means zero cost.

### Lower certificate: all alternative actions matter

For a proposed node value \(V\), `ValidLower` requires goal values to be zero
and checks every available alternative:

\[
 V(s)\leq c(a)+\max_{t\in\operatorname{children}(s,a)} V(t).
\]

`lower_certificate_sound` proves that any finite successful strategy at budget
\(B\) has a finite proposed value no greater than \(B\). The proof is by
induction over the successful strategy. It applies to every allowed strategy,
including one that chooses different actions from the submitted policy.
`infinite_value_unwinnable` follows: a checked infinite value rules out finite
guaranteed success at every budget in that arena.

Checking only a selected policy would not prove this lower bound. Every
alternative action must be represented in the arena and tested by the lower
certificate. Completeness of the arena relative to a simulator is a separate
correspondence obligation described below.

### Upper certificate: attainment and termination

`ValidUpper` requires each finite non-goal node to have an action whose cost
plus worst child value attains the stated value. Every child of that action
must have a strictly smaller natural-number rank. `upper_certificate_sound`
uses strong induction on rank to construct a finite winning strategy. The
rank condition prevents a circular collection of alleged winning values from
being accepted as an actual finite strategy.

`certified_exact_budget` combines the two directions: the stated budget is
achievable and no smaller budget can guarantee success. It proves an optimum
for worst-case modeled action cost. It says nothing about expected return,
wall-clock time, token cost, or the difficulty of discovering the strategy.

### Finite executable checks

`FiniteArena` represents every node with an in-bounds `Fin size` index. Its
`checkLower` and `checkUpper` enumerate all nodes and the appropriate action and
successor lists. The module proves that a true check yields the generic
certificate premises; the generated releases prove these Boolean checks by
kernel reduction with `by decide`.

The separate `checkShape` rules out empty successor lists and requires goal
nodes to terminate. Without this representational condition, the general
inductive semantics would treat an action with no possible observations as a
vacuously successful branch. Every concrete `certifiedProfile` theorem includes
the shape check as a conjunction, so the exported theorem does not leave that
condition implicit.

## 3. Concrete adaptive procurement profile

The release fixture is generated by `VendingAdaptiveTask(17, "train", 1)`: two
stages, four possible demand worlds, 448 raw states, and 732 transition edges.
The source game is
[`train2stage4world-game.json`](../artifacts/v04/finite-games/train2stage4world-game.json).
Its canonical game digest is
`6a6c388ea485a25d2510554ae48a2c44fcd8578424c1b860717be46be0feba89`.

Four separately projected arenas have concrete kernel-checked profiles:

| Mode | Reachable belief nodes | Formal root result |
| --- | ---: | --- |
| `adaptive` | 326 | Exact guaranteed-success budget: 8 |
| `no_observe` | 63 | No finite guaranteed-success strategy |
| `open_loop` | 40 | No finite guaranteed-success strategy |
| `open_loop_no_observe` | 10 | No finite guaranteed-success strategy |

`no_observe` excludes actions classified as explicit observations while still
allowing feedback from operational actions. `open_loop` ignores all observations
and requires a fixed action script. These restrictions are distinct. Their
combination is also evaluated explicitly. The adaptive arena contains 495
available alternatives across its reachable belief nodes, not merely the
actions along one winning trajectory.

The main theorem in each generated module is
`CausalFill.Exported.<Module>.certifiedProfile`, for modules
`ReleaseAdaptiveMarket`, `ReleaseNoObserveMarket`, `ReleaseOpenLoopMarket`, and
`ReleaseOpenLoopNoObserveMarket`. Each theorem includes `checkShape = true` and
the exact-budget or impossibility statement. Eight is measured in the
declaration's charged action-cost units; cash balance and service failures are
separate parts of the state and goal definition.

These results establish that information and adaptation are necessary for
universal success **in these declared finite arenas**. They are not measurements
of a language model, a claim that all vending simulations require adaptation,
or a theorem about a physical supply chain.

## 4. Source correspondence and trusted boundaries

[`export_arena.py`](../formal/export_arena.py) is an untrusted translator. It
validates the submitted Python certificate, asks the independent verifier to
reconstruct the complete reachable arena, then writes a finite Lean statement.
The generated theorem checks that statement.

[`ArenaJSON.lean`](../formal/CausalFill/ArenaJSON.lean) serializes the **actual Lean
definitions** back to JSON. The verification gate compares the actual root,
node count, node goals, ranks, proposed values, action identifiers, action costs,
and every action's complete child-index list against a freshly reconstructed
Python arena. It also checks source file hashes, canonical game/certificate
commitments, and the semantic arena digest. It separately checks that the mode,
node count, root, and root value in the manifest match the independently checked
arena. During review, a copied manifest with an altered mode label was accepted;
that metadata defect was fixed and all four corresponding mutation cases were
rejected on retest. The original fixture was unchanged.

Runtime JSON alone cannot authenticate arbitrary exporter code: a malicious
exporter could write a forged JSON literal. The stronger binding gate,
[`verify_arena_binding.py`](../formal/verify_arena_binding.py), closes this specific
gap by rendering a second literal Lean arena through a separate code path. It
does not import the original emitter or share its string, node, or semantic-data
renderer. It then asks the kernel to prove **equality of the actual imported
`FiniteArena` to the independently rendered expected arena**, including the
entire node vector and root. This equality is proved by reflexivity after
definition reduction, not by trusting a runtime JSON file.

Each new `CausalFill.Binding.<Module>.boundProfile` theorem contains that full
equality and the original shape/exactness/impossibility result transported to
the expected arena. All four concrete bindings have been checked. Their report
records the expected semantic-data digest, exact Lean source, original source
and manifest hashes, fully audited metadata, command, and axiom inventory. The
Python raw-game-to-belief reconstruction is still trusted; equality to its
literal result does not prove that reconstruction algorithm correct.

Four projection metadata fields are deliberately outside the Lean strategy
semantics: raw-state membership lists (`belief`), `failure_cut`, observation
labels, and the submitted `selected_action`. The formal upper result establishes
existence of an attaining strategy in the arena. Independently, the Python
policy verifier checks the submitted selected actions and replays that concrete
strategy from every possible raw initial state. The certificate recurrence
checker and the policy replay do not call the optimizer to decide acceptance.

The following are still not proved in Lean:

- JSON parsing, canonical hashing, and the Python certificate checker;
- refinement from the raw game to the belief arena, including completeness of
  actions and correctness of grouping successors by public observation;
- refinement from the mutable economic runtime to the raw finite game;
- correspondence from simulated sensors, costs, or success predicates to a
  physical system;
- solver isolation or freedom from evaluator leakage.

Round trips, independent implementations, exhaustive replay, and mutation
controls test these boundaries. They do not turn them into formal equivalence
proofs. Omitting an action can change an optimum while leaving a theorem about
the smaller arena valid; this is why both complete projection checks and exact
source correspondence are required.

The concrete statement correspondence is now stronger than the runtime round
trip: a deliberately altered arena that emits matching forged JSON still fails
the kernel equality test. The equality ensures that a successful binding uses
the complete expected action and successor lists produced by the independent
Python projection.

## 5. Reproduce the kernel checks

The new gate is separate from the original v0.3 verification record. With the
official pinned Lean 4.35.0 toolchain unpacked at `$LEAN_TOOLCHAIN_DIR`:

```sh
python formal/verify_information.py \
  --toolchain "$LEAN_TOOLCHAIN_DIR" \
  --arena-manifest formal/CausalFill/ReleaseAdaptiveMarket.manifest.json \
  --arena-manifest formal/CausalFill/ReleaseNoObserveMarket.manifest.json \
  --arena-manifest formal/CausalFill/ReleaseOpenLoopMarket.manifest.json \
  --arena-manifest formal/CausalFill/ReleaseOpenLoopNoObserveMarket.manifest.json
```

The normal backend invokes the Lean CLI at trust level zero. In the development
host used for this release, ordinary CLI startup failed while locating its own
executable path. The supported alternative is `--backend embedding`. It builds
the small, auditable [`lean_frontend.c`](../formal/embedding/lean_frontend.c) host
against the **unmodified official shared library**, initializes Lean using its
documented C ABI, calls the public `Lean.initSearchPath` with the explicit system
root, and calls `Lean.Elab.runFrontend` with trust level zero. It does not
intercept OS calls or modify access controls. This route is supported by the
[official FFI documentation](https://lean-lang.org/doc/reference/4.35.0/Run-Time-Code/Foreign-Function-Interface/)
and the bundled public API sources.

Both backends set the documented `Elab.async=false` option. The embedded host
also uses one Lean worker. This limits peak memory while checking the large
retained resolution export; it does not change the logical trust level. The
gate records the exact host source and binary hashes, build and execution
commands, toolchain library hash, Lean runtime version, theorem axiom lists,
source hashes, and JSON comparison results. `--toolchain-archive PATH` additionally
enforces the pinned official Linux archive SHA-256
`7289597a44543246c9227b8cae501767e095ce17f6d448b95fc4a8dc97268f6d`.

Twenty-one new generic theorem roots are explicitly audited, plus each concrete
profile. Every observed dependency is in `{propext, Classical.choice, Quot.sound}`;
the new generic and concrete profiles actually use only `propext` and
`Quot.sound`, with some elementary results requiring no axioms. A false theorem
is deliberately rejected as a negative kernel smoke test, and the audit gate
also rejects a synthetic custom-axiom report.

After running the source gate with `--backend embedding`, check the stronger
statement bindings using its compiled host:

```sh
python formal/verify_arena_binding.py \
  --toolchain "$LEAN_TOOLCHAIN_DIR" \
  --compiler-host formal/verification-v04/lean_frontend \
  --manifest formal/CausalFill/ReleaseAdaptiveMarket.manifest.json \
  --manifest formal/CausalFill/ReleaseNoObserveMarket.manifest.json \
  --manifest formal/CausalFill/ReleaseOpenLoopMarket.manifest.json \
  --manifest formal/CausalFill/ReleaseOpenLoopNoObserveMarket.manifest.json
```

Set `--compiler-host` to the actual `lean_frontend` path from the chosen source
gate output directory. The normal CLI can build the same generated binding
modules directly; the script records the embedded-host invocation used here.

### Recorded source, binding, and stress runs

The following reports were produced on November 4, 2026:

| Evidence | Result and scope |
| --- | --- |
| [`verification-v04-final/results.json`](../formal/verification-v04-final/results.json) | Passed all 43 source-gate theorem audits, four arena round trips, and both retained resolution exports (865 and 6,018 steps) |
| [`verification-v04-final/source-snapshot.json`](../formal/verification-v04-final/source-snapshot.json) | Pins the immutable full-gate report and preserves the exact verifier source executed before the subsequent metadata-validation fix |
| [`verification-v04-current/results.json`](../formal/verification-v04-current/results.json) | Patched gate passed 26 audits and all four arena comparisons; unchanged retained proof regressions were explicitly skipped because the preceding full run already checked them |
| [`verification-v04-binding/results.json`](../formal/verification-v04-binding/results.json) | Four complete arena equalities and transported profile theorems passed the kernel, with expected data and source hashes |
| [`verification-v04-stress/results.json`](../formal/verification-v04-stress/results.json) | All 10 formal assurance negative controls passed |
| [`formal-binding-review.json`](../reports/stress-v0.4/formal-binding-review.json) | Independent review reproduced the incorrect mode label before the fix, then rejected copied mode/count/root/value mutations while retaining the original fixture |

The full-gate source snapshot matters: the patched current script is not
misrepresented as having produced older full-regression logs. The actual
retained proof sources and their original statement/certificate commitments
matched in the full regression. An earlier concurrent attempt was terminated
by the host with exit code -9; the sequential runs above completed successfully.

The 10 formal stress controls cover a raised lower bound, an understated upper
bound, a nondecreasing strategy rank, empty action successors, omitted
alternatives, rerouted successors, custom axioms, missing audit roots, duplicate
audit roots, and an altered mathematical arena that emits forged matching JSON.
The last case directly tests why runtime output comparison alone was
insufficient: the file matched, but the stronger kernel equality was rejected.
Failed checks are required outcomes in these negative controls, not accepted
certificates or scored model attempts.

## 6. Independent kernel replay

Lean 4.35.0 adds the `lake check`/`--from-export` workflow and bundles several
independent kernels; see the
[official release notes](https://lean-lang.org/doc/reference/4.35.0/releases/v4.35.0/).
The final release export uses
[`KernelExport.lean`](../formal/KernelExport.lean) and the explicit trusted
inventory in
[`expected-export-roots.json`](../formal/expected-export-roots.json):

| Required roots | Count | Scope |
| --- | ---: | --- |
| Generic information and finite-arena theorems | 21 | Observation/counting results, lower and upper certificate soundness, and executable-check connections |
| `CausalFill.Exported.<Module>.certifiedProfile` | 4 | Concrete shape checks and exact-budget or impossibility results |
| `CausalFill.Binding.<Module>.boundProfile` | 4 | Equality of complete imported arenas to independent literal statements, with transported profile guarantees |
| **Total** | **29** | The export includes these roots and their dependency closure |

The original resolution examples are checked separately by the source-regression
gate; they are not included in this 29-root v0.4 export. A default library build
is not assumed to export or replay the generated release theorems.

### Recorded final replay

[`export-build.json`](../formal/verification-v04-kernels/export-build.json)
records successful export construction, the command, source and host hashes,
and source stability during the run. The exported NDJSON contains **6,638,404
bytes**, with SHA-256
`b53357b931ed077025a557859998af719f470cfce161447b32b17951a3ec2f07`.

[`replay/results.json`](../formal/verification-v04-kernels/replay/results.json)
records that all 29 required roots were present as theorems and that all six
configurations accepted that exact export:

| Checker configuration | Complete valid export | Corrupted exact-budget proof |
| --- | --- | --- |
| Lean default | Accepted | Rejected with the expected type-failure diagnostic |
| Lean hardened | Accepted | Rejected with the expected type-failure diagnostic |
| Lean4Lean | Accepted | Rejected with the expected type-failure diagnostic |
| Nanoda | Accepted | Rejected with the expected type-failure diagnostic |
| Con-Ron | Accepted | Rejected with the expected type-failure diagnostic |
| Con-Leche | Accepted | Rejected with the expected type-failure diagnostic |

The negative export replaces the proof term for
`CausalFill.Information.certified_exact_budget` with a closed universe
expression of the wrong type. The runner requires both a positive failure exit
and the expected diagnostic; a timeout or signal exit alone is insufficient.
Some checkers report type failures through exceptions or assertion panics. The
inventory controls also rejected a synthetic unapproved-axiom inventory and an
omitted required root. The valid export's axiom inventory was exactly
`propext` and `Quot.sound`, within the declared whitelist that also permits
`Classical.choice`.

These are six configurations, including two Lean checker variants and four
bundled external checkers, rather than six wholly independent software stacks.
They were invoked directly on the exported data. This result does not assert
that Lake's build sandbox or `lake check --paranoid` orchestration ran.

### Reproduce export and replay

First complete the source and four binding gates in section 5 using the
embedding backend. From the repository root, set `CFB_COMPILER_HOST` to the
actual host produced by that source gate; the default output path is shown
below. `LEAN_TOOLCHAIN_DIR` must be the absolute official toolchain path.
Choose fresh output names when repeating a run.

```bash
set -euo pipefail
CFB_COMPILER_HOST="$PWD/formal/verification-v04/lean_frontend"
(
  cd formal
  mkdir verification-local-kernels
  LEAN_PATH="$PWD/.lake/build/lib/lean" \
    "$CFB_COMPILER_HOST" "$LEAN_TOOLCHAIN_DIR" KernelExport KernelExport.lean \
    > verification-local-kernels/release-theorems.ndjson \
    2> verification-local-kernels/export-stderr.txt
)
python formal/check_export_kernels.py \
  --toolchain "$LEAN_TOOLCHAIN_DIR" \
  --export formal/verification-local-kernels/release-theorems.ndjson \
  --roots formal/expected-export-roots.json \
  --out formal/verification-local-kernels/replay \
  --timeout 300
```

The required `--roots` argument prevents a generic-only export from satisfying
the full release inventory. The complete sequential recipe, including retained
resolution proofs, metadata mutations, statement binding, and the ten formal
stress controls, is in [`formal/README.md`](../formal/README.md). The updated
[formal workflow](../.github/workflows/formal.yml) configures these gates for
hosted CI and retains their evidence. No hosted execution of that workflow is
claimed by the local reports above.

Source compilation, concrete statement binding, and independent kernel replay
remain separate evidence. The final replay includes the concrete profiles and
their stronger bindings, while the Python raw-game-to-belief projection and
simulator-to-statement refinement remain outside the formal claims.
