# Building and updating the v0.5.2 package

The source package contains the implementation, tests, visual assets and retained evidence. The current inventory covers every eligible file except itself. It preserves the original versioned reports and formal artifacts while excluding runtime caches, private runs, local environments, credentials and build outputs according to the published selection policy.

## Verify a downloaded package

From its extracted `causalfill-bench` directory:

```bash
python tools/release_integrity.py historical
python tools/release_integrity.py checkout
python -m unittest discover -s tests -v
python tools/build_release_verification_v052.py --check
```

The first command verifies the 134 restored v0.5.1 files against a pinned historical manifest. The checkout command checks exact inventory membership and hashes. The unit command executes current behavior. The release validator rechecks the frozen current evidence against the current sources. These checks have distinct purposes.

To validate an archive directly, without extracting it:

```bash
python tools/release_integrity.py archive ../CausalFill_Bench_v0.5.2.tar.gz
```

The archive validator rejects unsafe or duplicate paths, links, unexpected runtime files, missing entries and changed bytes. A supplied checksum still needs a trusted origin to establish authenticity.

## Reproduce current development evidence

Keep the committed `reports/v052/` record intact. Use fresh output locations for a rerun:

```bash
python tools/run_unit_gate_v052.py --output private-runs/reproduce-v052/unit-tests
python -m causalfill suite --output private-runs/reproduce-v052/suite \
  --splits train dev transfer --difficulties 1 2 3 --count 5 \
  --policies evidence blind abstain
python tools/stress_robust_v051.py --cases 256 --runtime-seeds 3 \
  --output private-runs/reproduce-v052/robust-stress
python tools/stress_robust_ablation_v051.py \
  --output private-runs/reproduce-v052/robust-ablation
python tools/audit_scoring_v052.py --output private-runs/reproduce-v052/scoring-audit
python -m causalfill review private-runs/reproduce-v052/suite \
  --output private-runs/reproduce-v052/review.html --verify-traces
```

The v0.5.1-named stress harnesses are intentionally retained and rerun against the new source version; their result objects record the actual benchmark version and core fingerprint. They are not historical results relabelled as new. Timings, random episode IDs and trace hashes can differ on a rerun. The source-bound frozen package can still be reproduced byte-for-byte from its unchanged checkout.

## Rebuild the visual system

The committed SVGs and HTML need no authoring dependencies to view. The builder uses Pillow and local DejaVu fonts; PNG rendering also uses Inkscape.

```bash
python tools/build_brand_v052.py
python tools/build_brand_v052.py --check
```

Refresh the brand manifest after modifying its bound source files or documents. See [the brand guide](brand-v052.md) for rendering commands, palette, asset scope and QA limitations.

## Freeze and package a changed release

Update version metadata before generating evidence. Freeze source and tests, run all required checks into fresh versioned directories, review the measured results, rebuild any source-bound cards, and then freeze the inventory. The release manifest must not hash the inventory or final archive; an external receipt can bind those afterward without creating a hash cycle.

```bash
python tools/build_release_verification_v052.py
python tools/release_integrity.py checkout --write-inventory
git add --all
python tools/release_integrity.py checkout --require-tracked
python tools/package_release.py \
  --output ../CausalFill_Bench_v0.5.2.tar.gz --require-tracked
python tools/release_integrity.py archive ../CausalFill_Bench_v0.5.2.tar.gz
```

The archive must be outside the source tree. The packager normalizes archive metadata and gzip time, validates the archive, and rechecks the source tree before publishing the final file. `.gitattributes` preserves exact bytes even when a Windows checkout enables `core.autocrlf`. Frozen logs under `formal/` and `reports/` are explicitly allowed by `.gitignore`.

## Apply the prepared update to GitHub

Use a clean clone of `ayjays132/causalfill-bench`. Save any unrelated local changes first. From that clone, create a review branch and extract the prepared package over it; the archive does not contain a `.git` directory.

```bash
git switch -c release/v0.5.2
tar -xzf ../CausalFill_Bench_v0.5.2.tar.gz --strip-components=1
git add --all
git diff --cached --check
python tools/release_integrity.py checkout --require-tracked
python -m unittest discover -s tests -v
git commit -m "Release v0.5.2: scoring clarity, offline review and complete evidence"
git push -u origin release/v0.5.2
```

Open a pull request from that branch to `main`. Include the measured release summary and inspect actual CI jobs. If a binary update patch accompanies the package, it is an alternative to extracting the complete archive: decompress it, run `git apply --check`, then `git apply` in the clean original v0.5.1 checkout. Do not apply both paths to the same working tree.

The new `release-integrity` workflow validates tracked file completeness, packaging rejection controls and deterministic archive creation. Existing benchmark and formal workflows retain their separate scopes. A local passing result does not establish a GitHub CI pass; a workflow that never started is not a test execution.

## Historical formal checks

The archived formal results retain their original toolchain, theorem inventory, source snapshots and logs. Fresh Lean checks require the pinned official toolchain and the commands in [the formal project](../formal/README.md). The Python release validator verifies retained artifact bindings; it does not execute Lean. Historical validators that require an old core fingerprint must run against that old source snapshot.
