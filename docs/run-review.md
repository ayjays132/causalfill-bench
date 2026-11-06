# Offline run review

The v0.5.2 review turns stored evaluator records into one self-contained HTML page. Its purpose is to make the route from summary score to individual evidence inspectable.

```bash
python -m causalfill review reports/v052/suite \
  --output private-runs/release-review.html --verify-traces
```

The first argument may be a suite directory or an explicit `records.jsonl` path. The output must be a new `.html` or `.htm` file. Open it locally in a browser.

## What the page shows

**Run configuration.** The selector separates policy, configuration ID, model, harness, scoring version and the complete condition object. The page recomputes summaries using the same `causalfill.metrics.summarize` function as the CLI. It never publishes a single score pooled across these groups.

**Strict success.** The headline averages answerable-task success rates equally across represented family labels. The all-unanswerable ambiguity configuration does not increase that score. Correct ambiguity abstention has its own count.

**Actual outcome.** This card is the mean of the task-defined `outcome` values in the selected group, with the number of recorded values disclosed. It is a diagnostic across the group's recorded episodes. Different task configurations define outcome differently; inspect per-task records before comparing mechanisms.

**Joint twin success.** A pair counts only when both required sides are present and answerable. Joint success means both pass. Interpretation depends on `twin_kind`: changing a proof's polarity, a simulated gate lane and a sensor fault set are different interventions.

**Resource use.** Mean tool cost uses the benchmark's synthetic units. The table exposes per-episode tool calls and invalid calls. Tokens, dollars, host CPU and physical energy are not inferred from this number.

**Episode explorer.** Filter by task configuration, split and result, or search the serialized record. “Outcome without strict success” isolates episodes where an outcome diagnostic is positive but strict acceptance failed. Pagination keeps the interface usable for large runs. “Details” shows the full private result, including the failure explanation and the task's verdict diagnostics.

The table filters leave the selected configuration's headline unchanged. This avoids presenting a success-only or failure-only subset as the original run's score. For a separately scored subset, create a documented analysis with explicit conditions and use the metrics API.

## Integrity checks

When `manifest.json` is present beside the records, the builder verifies the count and canonical records digest. If a scoring version is present in the manifest, every record must match it. A mismatch stops generation. A standalone records file can be reviewed without a manifest, but the page states that provenance was not bound.

With `--verify-traces`, every record needs a unique, safe episode ID and a corresponding regular file in `traces/`. The builder validates each event hash chain, the final hash against the record, and the public episode ID against that same record. Missing or mismatched evidence stops generation. It does not silently downgrade a requested verification to “unchecked.”

Without the flag, the page labels trace verification as not performed. A stored `trace_integrity: true` field is not represented as a fresh check.

## Security and interpretation

The HTML contains no remote scripts, assets, analytics or network calls. Record strings enter the document as escaped JSON and DOM text; they are not interpreted as markup. A content-security policy permits only the embedded review code and local styling. The builder rejects duplicate JSON keys and nonfinite values rather than choosing an ambiguous interpretation.

The file contains evaluator data, potentially including seeds, hidden outcomes and failure details. Keep it out of a scored solver's environment. If publishing a review later, treat that as disclosure of its included records.

A digest or hash chain detects inconsistency relative to a supplied binding. It does not prove authorship, external custody, provider identity, independent task design, solver isolation or correctness of the evaluator implementation. This review also does not replay the episodes or run the Lean kernel.
