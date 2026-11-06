# Independently checkable examples

These are public development artifacts, not hidden evaluation tasks. The proof is the final submitted artifact from the exploratory single-agent trial. Its 865 inference steps and consistency witness passed the private evaluator and the standalone checker. The scripted search produced 6,073 steps for the same statement; this comparison is about certificate size on one theorem, not general model superiority.

## Verify the proof

From the repository root:

```bash
python -m causalfill.verify_proof reports/certificates/model-statement.json reports/certificates/model-fill.json --expected-sha256 0b2fbd2916a4bf10d536aada3c30467b8713b59ca0592f5a6e8e044b6fda9298
```

The expected digest is the commitment to the fixed statement from the recorded evaluator. For a new evaluation, obtain it from that trusted evaluator, not from the solver. A digest is a content commitment, not a digital signature. The checker imports no task or proof-search implementation.

## Verify the experiment bound

`diagnosis-table.json` is the complete finite noiseless experiment-response table. `diagnosis-bound-certificate.json` includes all relevant alternatives in the exact minimax recurrence. `diagnosis-strategy.json` separately witnesses an attainable five-query worst-case policy. This is a 32-world, 10-experiment example with 541 certified states. The elimination fill must be interpreted together with the recorded actual observations in `reports/diagnosis-example.json`.

```python
import json
from pathlib import Path
from causalfill.decision_certificates import verify_decision_certificate, verify_decision_tree
p = Path("reports/certificates")
read = lambda name: json.loads((p / name).read_text())
table = read("diagnosis-table.json")
print(verify_decision_certificate(table, read("diagnosis-bound-certificate.json")))
print(verify_decision_tree(table, read("diagnosis-strategy.json")))
```

The `diagnosis-constrained-*` example has 32 worlds and ten experiments but requires six worst-case queries, despite the five-bit counting lower bound. Its 1,448-state certificate checks the restriction imposed by the actual experiment set. The accompanying strategy independently attains six.

Both checkers implement finite mathematical contracts in Python. They are not Lean formalizations or evidence of a new mathematical theorem. Rebuild these exports with `python tools/export_verification_artifacts.py`.
