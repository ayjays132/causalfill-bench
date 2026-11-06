import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest

from causalfill.logic_kernel import statement_digest
from causalfill.verify_proof import main, verify_statement_proof


class OfflineVerifierTests(unittest.TestCase):
    def setUp(self):
        # F=(p OR q) AND (NOT p OR q), hence q; no task or solver imports.
        self.statement = {"nvars": 2, "clauses": [[1, 2], [-1, 2]], "goal": 2}
        self.digest = statement_digest(self.statement["clauses"], 2, 2)
        self.statement["statement_sha256"] = self.digest
        self.fill = {"statement_sha256": self.digest,
                     "proof_steps": [[0, 1, 1], [3, 2, 2]],
                     "consistency_model": [False, True]}

    def test_independent_certificate(self):
        result = verify_statement_proof(self.statement, self.fill, self.digest)
        self.assertTrue(result["success"])
        self.assertEqual(result["checked_steps"], 2)

    def test_external_digest_prevents_substituted_theorem(self):
        altered = copy.deepcopy(self.statement)
        altered["clauses"].append([2])
        altered["statement_sha256"] = statement_digest(altered["clauses"], 2, 2)
        fill = dict(self.fill, statement_sha256=altered["statement_sha256"])
        result = verify_statement_proof(altered, fill, self.digest)
        self.assertFalse(result["success"])
        self.assertFalse(result["statement_bound"])

    def test_every_obligation_required(self):
        for field, value in [("statement_sha256", "0" * 64),
                             ("consistency_model", [False, False]),
                             ("proof_steps", [[0, 1, 2]])]:
            with self.subTest(field=field):
                self.assertFalse(verify_statement_proof(
                    self.statement, dict(self.fill, **{field: value}), self.digest)["success"])

    def test_duplicate_json_field_rejected_by_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            statement = Path(directory) / "statement.json"
            fill = Path(directory) / "fill.json"
            statement.write_text(json.dumps(self.statement))
            fill.write_text('{"proof_steps":[],"proof_steps":[]}')
            with contextlib.redirect_stdout(io.StringIO()) as output:
                status = main([str(statement), str(fill), "--expected-sha256", self.digest])
            self.assertEqual(status, 1)
            self.assertIn("duplicate JSON field", output.getvalue())

    def test_cli_actual_success(self):
        with tempfile.TemporaryDirectory() as directory:
            statement = Path(directory) / "statement.json"
            fill = Path(directory) / "fill.json"
            statement.write_text(json.dumps(self.statement))
            fill.write_text(json.dumps(self.fill))
            with contextlib.redirect_stdout(io.StringIO()) as output:
                status = main([str(statement), str(fill), "--expected-sha256", self.digest])
            self.assertEqual(status, 0)
            self.assertTrue(json.loads(output.getvalue())["success"])
