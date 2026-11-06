# Lean assurance artifact

This project uses the pinned official **Lean 4.35.0** toolchain and `Std`.
It has no Mathlib dependency and does not invoke proof search in the Python
benchmark. The original resolution contract is in `CausalFill/Resolution.lean`;
v0.4 adds finite information and strategy guarantees, concrete procurement
profiles, and kernel-checked statement bindings.

The first commands below reproduce the original resolution artifact. The
complete v0.4 source, binding, stress, and export-replay sequence is given later
in this file. A default `lake build` alone does not check that entire sequence.

From this directory, with the pinned `lean` and `lake` on `PATH`:

```sh
lake build
lake env lean CausalFill/Audit.lean
lake env lean CausalFill/ReleaseModel.lean
lake env lean CausalFill/ReleaseReference.lean
```

The release modules prove every local inference using kernel reduction with
`by decide`, assemble a proof of the empty clause, and prove satisfiable
entailment using a separately checked model. They also run the full indexed
checker and emit JSON round trips of the actual Lean data. The round trips and
source hashes support independent comparison with the original release JSON;
the JSON translator itself is not formally verified.

To regenerate the release sources, run from the repository root:

```sh
python formal/export_certificate.py --statement reports/certificates/model-statement.json --fill reports/certificates/model-fill.json --name ReleaseModel --output formal/CausalFill/ReleaseModel.lean
python formal/export_certificate.py --statement reports/certificates/reference-statement.json --fill reports/certificates/reference-fill.json --name ReleaseReference --output formal/CausalFill/ReleaseReference.lean
```

See [`../docs/formal-assurance.md`](../docs/formal-assurance.md) for theorem
scope, source correspondence, trusted assumptions, and recorded verification.

For a recorded verification run that also enforces the exact standard-axiom
whitelist and compares all actual Lean round-trip fields with the release
JSON, run:

```sh
python verify.py
```

Alternatively, supply an unpacked official toolchain explicitly with
`python verify.py --toolchain /path/to/lean-4.35.0-linux`. Logs and exact source
hashes are saved in `verification/`. The permitted axiom set is `propext`,
`Classical.choice`, and `Quot.sound`; any other reported axiom fails the gate.

## v0.4 information and adaptive strategy assurance

`CausalFill/Information.lean` proves observation-necessity, finite success-count
bounds, lower bounds for every finite strategy, and ranked attaining-strategy
soundness. `CausalFill/FiniteArena.lean` connects executable finite checks to
those generic theorems. Four concrete adaptive-procurement arenas include an
exact budget of 8 and three information-restricted impossibility results. Their
theorems also check nonempty action branches and terminating goal shape.

The new gate is separate from the original verification record:

```sh
python verify_information.py --toolchain /path/to/lean-4.35.0-linux \
  --arena-manifest CausalFill/ReleaseAdaptiveMarket.manifest.json \
  --arena-manifest CausalFill/ReleaseNoObserveMarket.manifest.json \
  --arena-manifest CausalFill/ReleaseOpenLoopMarket.manifest.json \
  --arena-manifest CausalFill/ReleaseOpenLoopNoObserveMarket.manifest.json
```

If the host cannot run Lean's ordinary self-locating launcher, `--backend
embedding` uses the documented C ABI and public frontend with an explicit
system root. The auditable host is `embedding/lean_frontend.c`; it loads the
unmodified official library at trust level zero. No OS interfaces or controls
are replaced. Both routes disable asynchronous elaboration; the embedded route
uses one worker to keep the large inherited proof regression within memory.
`embedding/Negative.lean` is a deliberate failing test and is not a build target.

The gate includes the original 865-step and 6,018-step resolution exports unless
`--skip-resolution-regression` is explicitly supplied. It checks 43 named axiom
inventories when all four arena profiles and both retained exports are included
(21 new generic roots, 4 profiles, 1 embedding smoke theorem, and 17 retained roots).
Its report distinguishes these source checks from independent kernel replay.

`verify_arena_binding.py` adds four stronger statement bindings. A separate
literal renderer reconstructs the expected arena and the kernel proves full
equality to the imported release's node vector and root. The resulting
`CausalFill.Binding.<Module>.boundProfile` theorem includes that equality and
the original guarantee transported to the expected arena. Runtime JSON alone
is insufficient against arbitrary forged exporter output; the binding gate
does not trust it. `stress_information.py` includes a concrete matching-JSON
forgery that still fails this kernel equality, alongside nine other controls.

See [`../docs/formal-information.md`](../docs/formal-information.md) for exact
semantics, reproduction commands, negative controls, and the unformalized
Python simulator-to-arena boundary. `KernelExport.lean` and
`check_export_kernels.py` provide a separate explicitly enumerated export and
independent replay path; their report states which roots and checkers ran.

## Complete v0.4 release reproduction

Run the following Bash commands **from the repository root**. They require
Python 3.10 or newer, Linux, a C compiler available as `cc`, and the unpacked
official Lean 4.35.0 Linux archive. Set both paths below to absolute paths:

```bash
set -euo pipefail
CFB_TOOLCHAIN_DIR=/absolute/path/to/lean-4.35.0-linux
CFB_TOOLCHAIN_ARCHIVE=/absolute/path/to/lean-4.35.0-linux.tar.zst
```

The archive is available from the
[official release](https://github.com/leanprover/lean4/releases/tag/v4.35.0).
The source gate verifies its pinned SHA-256
`7289597a44543246c9227b8cae501767e095ce17f6d448b95fc4a8dc97268f6d`.
The CI workflow includes the download and extraction commands. Run these stages
sequentially: they share compiled modules, and the retained large resolution
proof uses substantial memory. Use fresh `verification-local-*` output paths;
the replay script rejects an existing output directory.

### Source gate and retained resolution regressions

```bash
python formal/verify_information.py \
  --toolchain "$CFB_TOOLCHAIN_DIR" \
  --toolchain-archive "$CFB_TOOLCHAIN_ARCHIVE" \
  --backend embedding \
  --output formal/verification-local-source \
  --arena-manifest formal/CausalFill/ReleaseAdaptiveMarket.manifest.json \
  --arena-manifest formal/CausalFill/ReleaseNoObserveMarket.manifest.json \
  --arena-manifest formal/CausalFill/ReleaseOpenLoopMarket.manifest.json \
  --arena-manifest formal/CausalFill/ReleaseOpenLoopNoObserveMarket.manifest.json
```

This builds `formal/verification-local-source/lean_frontend`, the executable
passed explicitly to the next two gates. The default run includes both retained
resolution exports and all 43 named theorem audits; do not add
`--skip-resolution-regression` when reproducing the complete release gate.
The normal CLI backend remains available, but this complete recipe uses the
embedding backend to provide the required `--compiler-host` executable.

### Copied-manifest metadata controls

The baseline must remain valid, and changing any of these four metadata fields
must fail. Temporary copies keep the original manifest intact.

```bash
python - <<'PY'
import hashlib
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, "formal")
from verify_information import compare_arena

source = Path("formal/CausalFill/ReleaseAdaptiveMarket.manifest.json")
original_hash = hashlib.sha256(source.read_bytes()).hexdigest()
manifest = json.loads(source.read_text())
compare_arena(source)
mutations = {"mode": "open_loop", "node_count": manifest["node_count"] + 1,
             "root": manifest["root"] + 1, "root_value": manifest["root_value"] + 1}
with tempfile.TemporaryDirectory(prefix="causalfill-metadata-") as temporary:
    for field, value in mutations.items():
        copied = Path(temporary) / f"{field}.json"
        copied.write_text(json.dumps(dict(manifest, **{field: value})))
        try:
            compare_arena(copied)
        except RuntimeError as error:
            if f"manifest {field} differs from checked arena" not in str(error):
                raise
        else:
            raise RuntimeError(f"Altered manifest {field} was accepted")
if hashlib.sha256(source.read_bytes()).hexdigest() != original_hash:
    raise RuntimeError("Original manifest changed during metadata checks")
print("Four metadata mutations rejected; original manifest unchanged")
PY
```

### Four mathematical statement bindings and ten formal stress controls

```bash
python formal/verify_arena_binding.py \
  --toolchain "$CFB_TOOLCHAIN_DIR" \
  --compiler-host formal/verification-local-source/lean_frontend \
  --output formal/verification-local-binding \
  --manifest formal/CausalFill/ReleaseAdaptiveMarket.manifest.json \
  --manifest formal/CausalFill/ReleaseNoObserveMarket.manifest.json \
  --manifest formal/CausalFill/ReleaseOpenLoopMarket.manifest.json \
  --manifest formal/CausalFill/ReleaseOpenLoopNoObserveMarket.manifest.json

python formal/stress_information.py \
  --toolchain "$CFB_TOOLCHAIN_DIR" \
  --compiler-host formal/verification-local-source/lean_frontend \
  --output formal/verification-local-stress
```

The binding must run before the stress gate because the forged-JSON control
imports the newly checked binding module. The gate proves equality of the entire
imported `FiniteArena`, including every node and the root, to independently
rendered literal data. Python reconstruction of that expected arena remains an
unformalized boundary.

### Export all 29 roots and replay the dependency closure

```bash
(
  cd formal
  mkdir verification-local-kernels
  LEAN_PATH="$PWD/.lake/build/lib/lean" \
    ./verification-local-source/lean_frontend \
    "$CFB_TOOLCHAIN_DIR" KernelExport KernelExport.lean \
    > verification-local-kernels/release-theorems.ndjson \
    2> verification-local-kernels/export-stderr.txt
  sha256sum KernelExport.lean expected-export-roots.json \
    verification-local-kernels/release-theorems.ndjson \
    > verification-local-kernels/export.sha256
)

python formal/check_export_kernels.py \
  --toolchain "$CFB_TOOLCHAIN_DIR" \
  --export formal/verification-local-kernels/release-theorems.ndjson \
  --roots formal/expected-export-roots.json \
  --out formal/verification-local-kernels/replay \
  --timeout 300
```

The required inventory in
[`expected-export-roots.json`](expected-export-roots.json) contains 21 generic
theorems, four `certifiedProfile` theorems, and four `boundProfile` theorems.
The original resolution examples remain in the source regression gate; they
are not part of this 29-root export. `--roots` is mandatory, and every listed
root must appear as a theorem in the exported data.

The six configurations are Lean's default checker, its hardened variant,
Lean4Lean, Nanoda, Con-Ron, and Con-Leche. They must accept the full valid export
and reject the deliberately corrupted proof. A timeout or signal exit alone
does not count as rejection: the expected type-failure diagnostic is required.
The inventory gate also rejects a synthetic unapproved axiom and an omitted
required root. These are separate checks rather than scored benchmark trials.

## CI and recorded evidence

[`.github/workflows/formal.yml`](../.github/workflows/formal.yml) runs this full
sequence using `verification-ci-*` paths. It verifies the official archive,
keeps the retained resolution regressions, checks four metadata mutations,
builds four arena bindings, runs the ten formal stress controls, exports all 29
roots, and invokes all six replay configurations. It retains generated evidence
and failure diagnostics as workflow artifacts. The workflow is configured;
the checked-in reports are local results, not an observed hosted CI execution
of this workflow.

The exact source-gate history and pre-fix source snapshot are documented in
[section 5](../docs/formal-information.md#5-reproduce-the-kernel-checks).
The final export and replay records are
[`verification-v04-kernels/export-build.json`](verification-v04-kernels/export-build.json)
and
[`verification-v04-kernels/replay/results.json`](verification-v04-kernels/replay/results.json).
[Section 6](../docs/formal-information.md#6-independent-kernel-replay) gives their
measured results. Inspect each gate's report, theorem/axiom inventory, source
hashes, exact input digests, and diagnostics before interpreting a pass.

Source compilation, mathematical statement binding, and independent replay
are distinct evidence. Six checker configurations are not six wholly
independent software stacks. Direct replay does not claim that Lake's build
sandbox or `lake check --paranoid` orchestration ran, and it does not establish
the Python simulator-to-arena refinement or model/robot performance.
