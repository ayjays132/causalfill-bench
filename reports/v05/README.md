# v0.5 release evidence

Start with `release-verification.json` and `CausalFill_Research_Report_v0.5.0.pdf`. The current documented results are `../../docs/v0.5-results.md`; the longer research agenda is `../../docs/research-agenda-v0.5.md`.

## Final evidence

- `unit-tests/`: 268-test full discovery, log and checked-source hashes.
- `suite/`: 3,780 scripted episodes with all per-episode traces.
- `visual-qa/`: 336 exact observation PNGs, 21 sheets, automated and AI visual review.
- `robotics-qa/`: 288 Session observation PNGs, 18 sheets, automated and AI visual review. These capture-only QA sequences do not execute deliveries.
- `qa-atlas.html`: offline filtered atlas of all 624 observation files. It contains evaluator annotations and must not be given to a scored solver.
- `visual-interventions/`: 288 intact/blank/twin-swap/occlusion trials.
- `robotics-controls/`: 1,512 controller episodes and 864 sensor interventions. `records.jsonl` is unchanged by the explicit descriptive reporting refinement; `summary-initial.json` and `harness-executed.py` preserve the original summary and exact executed harness.
- `decision-stress-final.json` and `decision-certificates/`: random stress and six demonstration fixtures, each with action/identification certificates.
- `independent-vision-audit-final.json`: final combined independent-construction audit, 28,460 checks, zero failures, bound inspected source files.
- `report-qa.json`: PDF render/text checks, review scope and final report hash.

## Preserved development evidence

`legacy-baseline-*` came from a separate fresh extraction of the original v0.4 archive. `decision-stress.json`, `decision-independent-initial.json`, `independent-vision-audit-development.json`, `independent-vision-audit-final-visual.json`, `independent-calibration-support.json`, `independent-development-findings.json`, `visual-interventions-dev/`, and `unit-tests-before-report-layout/` are earlier stage records. Their source hashes and narrower scope remain intact; they are not silently promoted to final-source results. The visual-interventions development run has the expected outcomes but correctly records a concurrent-source-change failure.

An internal independent construction is not external laboratory replication. Finite certificates, measured renderer errors, scripted policy outcomes, protocol checks, actual image counts and represented-history multiplicities are distinct units. No learned-model, real-camera, rigid-body-physics or physical-robot experiment was conducted in v0.5. Historical Lean evidence belongs to earlier releases and was not rebuilt here.
