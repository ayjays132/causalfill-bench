# Changelog

## 0.5.2 — 2026-11-06

This release improves evaluator correctness, inspection, visual documentation and package completeness. It introduces no new model-performance claim.

### Corrected

- Signal Repair computes actual outcome and robust action justification from the action actually committed and the observations available at that point. A malformed certificate, wrong digest, incorrect action name, abstention, timeout or disconnect no longer erases an executed outcome.
- No committed Signal Repair action now reports zero outcome and zero action-justification diagnostic, with an explicit `action_committed: false` field. This does not describe a physical safety event.
- Equivalent train/difficulty-1 and dev/difficulty-1 Signal Repair mechanisms share the same structural signature. Label permutations and split names do not create independent mechanisms.
- Restored the 131 original verification logs and three C frontend source files omitted from the published v0.5.1 tree. Their bytes match the supplied release archive.
- Updated the scoring documentation from the older fourteen-configuration roster to the current fifteen configurations, including sensor-corruption twins.

### Added

- `python -m causalfill review RUN --output REVIEW.html [--verify-traces]`: a self-contained evaluator review with configuration separation, per-task bars, episode filters, pagination, full record details, manifest binding and optional trace verification.
- `python -m causalfill --version`.
- Explicit `scoring_version: causalfill.scoring.v2` in Session records and suite manifests. Summary schema `causalfill.metrics.v2` adds that version to grouping identity; historical unversioned records use `legacy-unspecified`.
- Regression checks for scoring failure paths, grouping, review data binding and inert rendering of record text.
- A deterministic release inventory, checkout/archive validation and a dedicated release-integrity CI workflow.
- A coordinated SVG identity for v0.5.2: desktop/mobile heroes, social artwork, fifteen configuration icons, explanatory feature diagrams, a browsable gallery and reproducible asset manifests.
- Quickstart, feature guide, review guide, migration notes and release reproduction instructions.

### Preserved and scoped

The task roster and public tool contract remain compatible. Historical reports, traces and formal verification artifacts retain their original provenance. No fresh Lean compilation or independent frontier-model evaluation is represented by the new Python release checks. See [measured results](docs/v0.5.2-results.md).

## 0.5.1 — preserved release

Introduced Signal Repair (`robust_sensing`), a global bounded sensor-corruption model, exact finite probe-plus-action cost certificates, observed exclusion witnesses and fourteen generic Lean roots. See the original [release results](docs/v0.5.1-results.md).

## Earlier releases

The preserved [v0.5 results](docs/v0.5-results.md) cover controlled perception and rendered robotics. [v0.4 results](docs/v0.4-results.md) cover adaptive procurement and finite-game verification. These are historical source-bound records, not reruns on v0.5.2.
