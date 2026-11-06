# Release evidence

## Current release: v0.4.0

`build-verification-v0.4.json` is the current versioned record;
`build-verification.json` is its current-release copy.
`tools/build_release_verification_v04.py` reassembles it by checking the frozen
Python source, all 3,240 control traces, source-bound stress reports, formal
artifacts and the separate public-interface pilot. It reads completed evidence;
it does not rerun the proof or stress campaigns.

| Evidence | Observed result | Artifact |
|---|---:|---|
| Unit/integration tests | 214 passed | `unittest-v0.4.txt` |
| Scripted controls | 3,240 episodes; evidence 990/990 answerable success and 90/90 correct abstention | `development-run-v0.4-final/` |
| Complete small policy enumeration | 1,024 exact optimum comparisons; 601,600 syntactic policies | `stress-v0.4/belief-games-independent-audit.json` |
| Independent analytic oracle | 240 certificates, 180 metamorphic cases, 720 rejected forgeries | `stress-v0.4/belief-analytic-final.json` |
| Runtime conformance | 83,616 states; 139,080 legal transitions; 2,951,089 correlated assertions; no failures | `stress-v0.4/adaptive-runtime-complete-responses.json` |
| Protocol/session/metrics | 101,349 checks; no failures | `stress-v0.4/protocol-final.json` |
| Lean source gates | 21 generic roots and four concrete profiles | `../formal/verification-v04-current/results.json` |
| Whole-arena kernel correspondence | Four bound profiles, one finite market fixture | `../formal/verification-v04-binding/results.json` |
| Formal negative controls | 10/10 | `../formal/verification-v04-stress/results.json` |
| Independent export replay | 29 roots; six accepts and six intended corrupted-proof rejections | `../formal/verification-v04-kernels/replay/results.json` |
| Fresh-context pilot | Six successes, one submission each | `public-interface-pilot-v0.4/manifest.json` |

The pilot used a public JSON mailbox on a shared host without enforced filesystem
isolation. It is exploratory, with no exact model snapshot or token telemetry.
Its six successes do not establish frontier difficulty. All tool traces and the
solver's public-only scripts are retained; they are not OS access attestations.
The unsuccessful HTTP connection attempts occurred before task observation and
are separate infrastructure history in `public-interface-pilot-http-unreachable-v0.4/`.

The final core fingerprint is
`02d337e217efc9e67247df537339033b83e2db935619ec6db25a1127161e5248`.
The source was frozen before final controls and the scored pilot. The runtime
report covers one replay witness per projected state and every outgoing edge,
not all possible histories. Four formal policy-mode arenas represent ONE
concrete two-round/four-world market. The Python belief projection and runtime
refinement remain outside Lean. The retained 865/6,018-step resolution regressions
passed source compilation separately from the new 29-root export.

Earlier v0.4 smoke/intermediate reports remain under their own names. The table
above and the verification manifest identify the final reports. In particular,
`adaptive-runtime-complete-responses.json` supersedes narrower runtime audits.
`formal/verification-v04-kernels/replay-negative-selection-baseline/` preserves
an overly broad negative-control selection and its strict gate failure; the
final replay uses a closed ill-typed expression and verifies the intended
rejection diagnostics. `stress-v0.4/formal-binding-review.json` records a genuine
policy-mode metadata defect, its repair and four rejected metadata mutations.

`skill-forward-v0.4/reviewer.json` is a separate fresh-context review of a planted
false open-loop claim. It rejected that claim and independently confirmed the
fixed-sequence impossibility. It is not an agent benchmark score.

See [v0.4 results](../docs/v0.4-results.md) for the mathematical cost table,
interpretation, commands and limits. Historical counts below retain their own
versions and must not be pooled into the current release's results.

## Historical release: v0.3.0

`build-verification-v0.3.json` preserves that release's verification record; the unversioned copy now points to v0.4. `tools/build_release_verification.py` reassembles that historical record when used with the v0.3 source checkout, checking its source hashes, final audit outcomes, all 2,970 stored control traces, record commitments, and Lean verification bindings. It reads completed evidence; it does not rerun Lean or the stress campaigns.

| Evidence | Final observed result | Artifact |
|---|---:|---|
| Unit and integration tests | 185 passed | `unittest-v0.3.txt` |
| Scripted control matrix | 2,970 episodes | `development-run-v0.3-final/` |
| Evidence reference, answerable episodes | 900 / 900 strict success | Final control records and summary |
| Evidence reference, unanswerable controls | 90 / 90 correct abstention | Final control records and summary |
| Blind and always-abstain capability | 0 / 900 each | Final control records and summary |
| Formal semantic/certificate stress | 633,087 checks; no failures | `stress-v0.3/formal-results.json` |
| Geometry/operations/metamorphic stress | 871,840 checks; no failures | `stress-v0.3/operations-final.json` |
| Actual transport/session/metric stress | 101,349 checks; no failures | `stress-v0.3/protocol-final.json` |
| Separate workflow Fraction oracle | 480,800 exact expression values and 411,928 original intermediate values; no false certification or bound violation | `stress-v0.3/workflow-independent-audit.json` |
| Lean assurance | Generic soundness development plus complete 865-step and 6,018-step exports passed | `../formal/verification/results.json` |

The final evaluator fingerprint is `796c1c974e1aaa4825af9fe3c444a9de646058620e7c3a3c608b497f87aebb43`. The source tree's documentation, report builders and tests have separate artifact hashes where applicable; the evaluator fingerprint covers `causalfill/**/*.py` only.

The control roster is eleven configurations, three splits, three difficulties, five seeds, two twins and three scripted policies. It is not an LLM evaluation. Check counts are correlated assertions, not independent tasks, statistical samples or solved research problems. No new model-solver trial was conducted in v0.3. The independent oracles and reviews were part of this AI-assisted build, not external laboratory or human replication.

### What the stress work changed

Exact decimal-rational predicates repaired geometry false accepts and rejects. Sufficient symbolic equality plus original-intermediate Fraction bounds repaired the workflow finite-suite blind spot. HTTP and stdio now share strict JSON and raw UTF-8 byte limits. Metric means preserve finite extremes and subnormals. A new barrier pair certificate was corrected to compare typed canonical JSON rather than conflating `1` and `true`.

The operational audit also found valid fixed strategies in the original vending and robotics generators. These remain accepted. The new `robotics_barrier` profile separately establishes the need for suitable hidden-geometry information, with individually feasible paths and no common valid route. Its final operations section checked 576 pairs / 1,152 episodes and 4,608 forged certificates.

### Historical evidence must remain separate

- `stress-v0.3/operations-baseline.json` and `protocol-baseline.json` preserve initial failures.
- `stress-v0.3/operations.json` is the larger audit before workflow certification; its 1,440 threshold false accepts are historical. `operations-workflow-followup.json` and `operations-final.json` show their rejection after repair.
- `stress-v0.3/barrier-independent-audit.json` preserves the JSON type-alias discovery and successful retest. It explicitly records that the pre-fix source hash was not captured.
- `development-run-v0.3/` and `development-run-v0.3-pre-certifier-fix/` preserve the same preliminary control snapshot. They are duplicate historical material, not additional independent runs, and are excluded from final totals. `unittest-v0.3-pre-certifier-fix.txt` records the earlier 184-test milestone.
- `build-verification-v0.2.json`, `unittest-v0.2.txt` and `development-run-v0.2/` preserve v0.2's 140 tests and 2,700 scripted episodes. Their source fingerprint belongs to that version, not v0.3.
- `development-run/` and `build-verification-v0.1.json` preserve v0.1. Do not combine releases as one evaluation.

`certificates/` contains fixed statements, submitted proofs, exact query-bound certificates, attaining strategies and offline instructions. `exploratory-trial/` contains earlier qualitative assistant trials with their provenance limitations. These are not comparative leaderboard scores. All shipped seeds and solutions are public development artifacts; an evaluated solver must not see them during an episode.
