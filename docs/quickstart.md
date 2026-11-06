# Quickstart — v0.5.2

Use Python 3.10 or later. The evaluator core needs no third-party runtime packages and no GPU. Run these commands from the repository root. On Windows, `py` can replace `python`.

## 1. Check the installation

```bash
python -m causalfill --version
python -m causalfill list
```

The version is `0.5.2`; the task list contains fifteen configurations. Optional installation with `python -m pip install -e .` also provides the `causalfill` command. Running the module directly does not require installation.

The release also supplies a lightweight wheel for the evaluator runtime:

```bash
python -m pip install causalfill_bench-0.5.2-py3-none-any.whl
causalfill --version
```

Use the complete source archive when you need the documentation, SVGs, tests or
historical verification evidence; these research artifacts are not bundled in
the lightweight runtime wheel.

## 2. Watch one scripted control

```bash
python -m causalfill demo --family robust_sensing \
  --split transfer --difficulty 3 --policy evidence
```

This is the task-aware scripted `evidence` reference. It obtains observations through the public tool interface, selects probes, commits an action and submits a certificate. The JSON printed at the end is an evaluator result. It is not an AI-model score.

Read `success` first for strict acceptance. Read `outcome` separately for the task's outcome diagnostic. For Signal Repair, `verdict.details.action_justified_before_commit` records whether all worlds compatible with the pre-commit evidence support the action. Tool costs are synthetic resource units; they are not token counts or dollars.

## 3. Run a small paired matrix

```bash
python -m causalfill suite --output private-runs/first-run \
  --splits transfer --difficulties 3 --count 1 \
  --policies evidence blind abstain
```

This configuration produces 90 episodes: fifteen task configurations, two twins, and three policies. `ambiguity` episodes are intentionally unanswerable controls. They are scored for appropriate abstention separately from answerable-task capability.

The output contains:

| File | Purpose |
|---|---|
| `manifest.json` | Benchmark/scoring versions, source fingerprint, seed roster, conditions and canonical record digest. |
| `records.jsonl` | One evaluator result per episode, with complete policy/configuration identity. |
| `summary.json` | Configuration-separated family, pair, abstention, resource and uncertainty summaries. |
| `traces/*.json` | Public episode description and the ordered, hash-chained tool interaction. |

Choose a fresh output directory for each run. The runner rejects a nonempty directory so evidence cannot be silently overwritten.

## 4. Open the review

```bash
python -m causalfill review private-runs/first-run \
  --output private-runs/first-run-review.html --verify-traces
```

Open `private-runs/first-run-review.html` in a browser. No web server, external font, JavaScript dependency or network connection is needed. Select a configuration, inspect task success, filter failures and open an episode's full record. The review confirms supplied manifest and trace bindings; it does not authenticate who produced the records. See [the review guide](run-review.md).

## 5. Run the implementation checks

```bash
python -m unittest discover -s tests -v
python tools/release_integrity.py checkout
```

The integrity check validates the frozen package inventory and pinned historical evidence. It will correctly report a stale inventory after local edits; regenerate it only when intentionally building a new release. The unit suite verifies behavior against the current checkout. Source-bound frozen results are listed in [the release record](v0.5.2-results.md).

## Evaluate an actual agent

Host the evaluator separately from the agent. Provide only the copied client in `clients/`, the public episode interface and an episode token. Keep source, seeds, reference policies, private records and grading state outside the agent's environment. The HTTP interface filters observations but does not itself enforce filesystem/process isolation.

Set `CFB_TOKEN` to a fresh secret of at least 24 characters using your shell or secret manager, then start an episode:

```bash
python -m causalfill serve --family robust_sensing --split transfer \
  --difficulty 3 --seed 7814 --output private-runs/model-run
```

The [protocol](protocol.md) defines tool calls and final submission. The [evaluation plan](evaluation-plan-v0.5.1.md) describes model identification, frozen conditions, independent task design, baselines and reporting. Copying the evaluator into the agent's workspace defeats that separation.

## Common issues

| Symptom | Resolution |
|---|---|
| `No module named causalfill` | Run from the extracted repository root or install it with `python -m pip install -e .`. |
| Output directory must be new or empty | Choose a new run directory. Keep old results intact. |
| Review record digest mismatch | The records differ from their manifest. Restore the matching files or keep the modified data as a separately documented analysis; do not overwrite the original manifest to disguise a change. |
| Missing trace in review | Use a run with saved traces. A suite created with `--no-traces` can be reviewed without `--verify-traces`. |
| Missing SVG/PDF authoring dependency | The core still runs. Inkscape/Pillow/ReportLab belong to optional visual/report authoring tools, not the evaluator runtime. |
| GitHub checks did not execute | Inspect the actual workflow/job status. A local passing run does not establish a successful GitHub CI execution. |
