import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from causalfill.metrics import summarize
from causalfill.protocol_json import MAX_BODY_BYTES, _strict_json


class TransportRegressionTests(unittest.TestCase):
    def stdio(self, first):
        final = json.dumps({"tool": "submit", "arguments": {
            "fill": {}, "confidence": 0.5, "abstain": True, "evidence": []}}).encode()
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, "-m", "causalfill", "stdio", "--output", directory],
                input=first + b"\n" + final + b"\n", cwd=Path(__file__).resolve().parents[1],
                capture_output=True, timeout=10, check=True)
            record = json.loads(next(Path(directory).glob("*.result.json")).read_text())
            return [json.loads(line) for line in result.stdout.splitlines()], record

    def test_duplicate_json_fields_do_not_change_transport_meaning(self):
        lines, result = self.stdio(b'{"tool":"submit","tool":"list_files","arguments":{}}')
        self.assertIn("error", lines[1])
        self.assertNotIn("files", lines[1])
        self.assertEqual(result["invalid_calls"], 1)

    def test_nested_duplicate_fields_rejected(self):
        lines, result = self.stdio(b'{"tool":"read_file","arguments":{"path":"/x","path":"/y"}}')
        self.assertIn("error", lines[1])
        self.assertEqual(result["invalid_calls"], 1)

    def test_stdio_nesting_matches_http_limit(self):
        raw = b'{"tool":"unknown","arguments":{"x":' + b'['*33 + b'0' + b']'*33 + b'}}'
        lines, result = self.stdio(raw)
        self.assertIn("error", lines[1])
        self.assertEqual(result["invalid_calls"], 1)

    def test_request_limit_counts_utf8_bytes(self):
        raw = json.dumps({"tool": "unknown", "arguments": {"x": "\U0001f680"*33000}}, ensure_ascii=False).encode()
        self.assertGreater(len(raw), MAX_BODY_BYTES)
        lines, result = self.stdio(raw)
        self.assertEqual(len(lines), 1)
        self.assertEqual(result["verdict"]["details"]["failure"], "request_too_large")

    def test_parser_itself_rejects_oversized_bytes(self):
        with self.assertRaises(ValueError):
            _strict_json(b' ' * (MAX_BODY_BYTES + 1))

    def test_finite_positive_metric_mean_cannot_overflow(self):
        record = {"family": "fixture", "structural_signature": "fixture:a", "answerable": True,
                  "success": False, "abstained": False, "tool_cost": 1e308}
        result = summarize([record, record], n_bootstrap=1)
        mean = result["groups"][0]["aggregate"]["metric_means"]["tool_cost"]
        self.assertEqual(mean, {"mean": 1e308, "n": 2})

    def test_subnormal_metric_mean_is_not_lost_before_summing(self):
        record = {"family": "fixture", "structural_signature": "fixture:a", "answerable": True,
                  "success": False, "abstained": False, "tool_cost": 5e-324}
        result = summarize([record, record], n_bootstrap=1)
        mean = result["groups"][0]["aggregate"]["metric_means"]["tool_cost"]["mean"]
        self.assertEqual(mean, 5e-324)
