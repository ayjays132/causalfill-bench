# Migrating from v0.5.1 to v0.5.2

## Public task interface

The registered task keys, common tool calls and final submission envelope remain compatible. Existing client scripts still use `tool` and `arguments`; `submit` still carries `fill`, `confidence`, `abstain` and `evidence`. Signal Repair's valid completion still names the public problem digest, the action actually committed and the observed exclusion witnesses.

The behavioral change affects evaluator diagnostics and aggregation. Strict rejection of an invalid certificate is preserved.

## Outcome reporting

In v0.5.1, Signal Repair parsed its entire final fill before computing actual outcome and action justification. A wrong digest or malformed certificate could therefore erase the outcome of an already executed action from the result. The same information could disappear when a committed episode ended through abstention or forced termination.

In v0.5.2 those diagnostics are computed from saved evaluator state: the action actually committed, the true world, and observations before commitment. The submitted action name cannot rewrite what happened.

| Situation | `success` | `outcome` | Signal Repair `safety` |
|---|---|---|---|
| Successful justified action, complete valid certificate, within budget | `true` | `1.0` | `1.0` |
| Same action, malformed or mismatched final certificate | `false` | `1.0` | `1.0` |
| Successful action selected without enough robust evidence | `false` | `1.0` | `0.0` |
| Actually failed action | `false` | `0.0` | Depends on recorded justification; a sound in-model justification cannot certify an actual failure. |
| No committed action | `false` | `0.0` | `0.0` |

Here `safety` means robust action justification in a finite symbolic model. It is not a physical safety rating. `action_committed` distinguishes no action from an executed failure. `certificate_valid` separately exposes complete witness validation. Other domains retain their existing failure diagnostics.

Do not relabel historical records as if they were produced with the new semantics. A new evaluation requires a fresh output directory and the exact new source fingerprint. A separately documented reconstruction from old traces is an analysis, not a new model run.

## Versioned metric grouping

New Session records and suite manifests contain:

```json
{"scoring_version": "causalfill.scoring.v2"}
```

The summary schema is now `causalfill.metrics.v2`. Group identity becomes:

```text
policy + config_id + model + harness + scoring_version + condition
```

Records without a scoring version receive the explicit identity value `legacy-unspecified`. They remain usable, but cannot silently join a current scoring group. If a downstream consumer pins the old summary schema, update it to accept the new identity field and retain group separation. There is still no top-level pooled capability score.

## Structural signatures

The train/difficulty-1 and dev/difficulty-1 Signal Repair problems both use a one-bit repetition mechanism with three unit-cost probes and one global fault. Their canonical signature is now:

```text
robust_sensing:repetition-1-bits-one-global-fault:v1
```

This prevents split-specific names from inflating the count of distinct structural clusters. Generation, costs and public behavior remain unchanged. Different seeds, labels and polarities remain correlated realizations of that mechanism. Historical summaries retain their original grouping and are not overwritten.

## Release evidence and formal scope

The restored v0.5.1 files retain their exact archive bytes. New v0.5.2 runs live in `reports/v052/`; previous versioned reports and formal snapshots remain historical. Validators that demand a v0.5.1 core fingerprint should run against the restored v0.5.1 source snapshot, not the modified v0.5.2 core.

The package integrity manifest checks file identity and completeness. It does not turn archived Lean logs into a fresh Lean build. Follow [release instructions](releasing-v052.md) and [the formal scope](formal-assurance.md) when reproducing proof checks.
