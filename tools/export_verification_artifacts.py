"""Export small independently checkable artifacts from the recorded demo runs."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from causalfill.decision_certificates import (build_decision_certificate, extract_decision_tree,
    verify_decision_certificate, verify_decision_tree)
from causalfill.proof_search import solve_statement
from causalfill.verify_proof import verify_statement_proof

OUT = ROOT / "reports/certificates"
OUT.mkdir(parents=True, exist_ok=True)


def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def extract(events, path):
    statement = next(json.loads(e["response"]["content"]) for e in events
                     if e["tool"] == "read_file" and e["arguments"]["path"] == path)
    fill = next(e["arguments"]["fill"] for e in events if e["tool"] == "submit")
    return statement, fill


demo = json.loads((ROOT / "reports/proof-example.json").read_text())
statement, fill = extract(demo["trace"], "/formal/statement.json")
save("reference-statement.json", statement)
save("reference-fill.json", fill)
save("reference-verification.json", verify_statement_proof(statement, fill, statement["statement_sha256"]))

trial_path = next((ROOT / "reports/exploratory-trial/proof").glob("*.trace.json"))
events = json.loads(trial_path.read_text())
statement, fill = extract(events, "/formal/statement.json")
save("model-statement.json", statement)
save("model-fill.json", fill)
verified = verify_statement_proof(statement, fill, statement["statement_sha256"])
reference = solve_statement(statement)
reference_verified = verify_statement_proof(statement, reference, statement["statement_sha256"])
assert verified["success"] and reference_verified["success"]
save("model-verification.json", verified)
save("same-statement-comparison.json", {
    "model_steps": len(fill["proof_steps"]),
    "reference_steps": len(reference["proof_steps"]),
    "reference_verified": reference_verified,
    "scope": "One exploratory proof; certificate length is not a general model capability score."
})

diagnosis = json.loads((ROOT / "reports/diagnosis-example.json").read_text())
contract, elimination = extract(diagnosis["trace"], "/formal/diagnosis.json")
table = contract["responses"]
certificate = build_decision_certificate(table)
tree = extract_decision_tree(table, certificate)
bound = verify_decision_certificate(table, certificate)
strategy = verify_decision_tree(table, tree)
assert bound["valid"] and strategy["valid"] and bound["optimal_depth"] == strategy["depth"]
save("diagnosis-table.json", table)
save("diagnosis-bound-certificate.json", certificate)
save("diagnosis-strategy.json", tree)
save("diagnosis-elimination-fill.json", elimination)
save("diagnosis-verification.json", {"exact_bound": bound, "strategy": strategy})

constrained = json.loads((ROOT / "reports/diagnosis-constrained-example.json").read_text())
contract, _ = extract(constrained["trace"], "/formal/diagnosis.json")
constrained_table = contract["responses"]
constrained_certificate = build_decision_certificate(constrained_table)
constrained_tree = extract_decision_tree(constrained_table, constrained_certificate)
constrained_bound = verify_decision_certificate(constrained_table, constrained_certificate)
constrained_strategy = verify_decision_tree(constrained_table, constrained_tree)
assert constrained_bound["valid"] and constrained_strategy["valid"]
assert constrained_bound["optimal_depth"] == constrained_strategy["depth"] == 6
for suffix, value in [("table", constrained_table), ("bound-certificate", constrained_certificate),
                      ("strategy", constrained_tree),
                      ("verification", {"exact_bound": constrained_bound, "strategy": constrained_strategy})]:
    save("diagnosis-constrained-" + suffix + ".json", value)

print(json.dumps({"proof": verified, "same_statement_reference_steps": len(reference["proof_steps"]),
                  "diagnosis": bound, "files": len(list(OUT.glob("*.json")))}, indent=2))
