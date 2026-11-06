import json
from pathlib import Path
import re
import tempfile
import unittest

from causalfill.review import load_run, render_review, write_review
from causalfill.runner import run_suite
from causalfill.types import digest


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def suite(self):
        path = self.root / "run"
        run_suite(path, ["words", "ambiguity"], ["dev"], [1], [0],
                  ["evidence", "blind", "abstain"])
        return path

    def test_real_suite_binds_manifest_and_all_traces_without_pooling_controls(self):
        path = self.suite()
        result = load_run(path, check_traces=True)
        self.assertEqual(result["record_count"], 12)
        self.assertEqual(result["trace_chains_checked"], 12)
        self.assertTrue(result["manifest_binding_checked"])
        self.assertEqual(result["summary"]["group_count"], 3)
        self.assertEqual(sum(map(len, result["records_by_group"].values())), 12)
        self.assertNotIn("headline", result["summary"])

    def test_record_tampering_is_rejected_by_manifest(self):
        path = self.suite()
        records_path = path / "records.jsonl"
        records = [json.loads(line) for line in records_path.read_text().splitlines()]
        records[0]["tool_cost"] += 1
        records_path.write_text("\n".join(json.dumps(row) for row in records) + "\n")
        with self.assertRaisesRegex(ValueError, "digest does not match"):
            load_run(path)

    def test_trace_chain_and_final_binding_are_both_checked(self):
        path = self.suite()
        trace_path = next((path / "traces").glob("*.json"))
        trace = json.loads(trace_path.read_text())
        trace["events"][0]["response"]["injected"] = True
        trace_path.write_text(json.dumps(trace))
        with self.assertRaisesRegex(ValueError, "trace chain or record binding failed"):
            load_run(path, check_traces=True)
        self.assertEqual(load_run(path)["trace_chains_checked"], 0)

    def test_missing_trace_fails_requested_verification(self):
        path = self.suite()
        next((path / "traces").glob("*.json")).unlink()
        with self.assertRaisesRegex(ValueError, "missing or linked trace"):
            load_run(path, check_traces=True)

    def test_intact_chain_cannot_bind_to_a_different_final_record(self):
        path = self.suite()
        records_path = path / "records.jsonl"
        records = [json.loads(line) for line in records_path.read_text().splitlines()]
        records[0]["trace_hash"] = "0" * 64
        records_path.write_text("\n".join(json.dumps(row) for row in records) + "\n")
        manifest_path = path / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["records_sha256"] = digest(records)
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "trace chain or record binding failed"):
            load_run(path, check_traces=True)

    def test_empty_run_stays_explicit_and_renders_without_a_score(self):
        path = self.root / "records.jsonl"
        path.write_text("")
        data = load_run(path)
        self.assertEqual(data["summary"]["groups"], [])
        self.assertEqual(data["record_count"], 0)
        self.assertIn("No records supplied.", render_review(data))

    def test_raw_records_allow_no_manifest_and_keep_injected_markup_inert(self):
        injected = '</script><script>window.pwned=true</script><img src=x onerror=alert(1)>'
        record = {"family": injected, "structural_signature": "one", "answerable": True,
                  "success": False, "abstained": False, "outcome": 1.0}
        path = self.root / "records.jsonl"
        path.write_text(json.dumps(record) + "\n")
        data = load_run(path)
        self.assertFalse(data["manifest_binding_checked"])
        page = render_review(data)
        self.assertNotIn(injected, page)
        self.assertIn("\\u003c/script\\u003e", page)
        payload = re.search(r'<script id="run-data" type="application/json">(.*?)</script>', page).group(1)
        self.assertEqual(json.loads(payload)["record_count"], 1)
        self.assertIn("default-src &#x27;none&#x27;", page)
        self.assertNotIn('<script src=', page)

    def test_manifest_scoring_version_cannot_relabel_records(self):
        path = self.suite()
        manifest_path = path / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["scoring_version"] = "future-version"
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "scoring version"):
            load_run(path)

    def test_duplicate_json_keys_are_rejected(self):
        path = self.root / "records.jsonl"
        path.write_text('{"family":"words","family":"ambiguity"}\n')
        with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
            load_run(path)

    def test_safe_output_does_not_overwrite_existing_evidence(self):
        path = self.suite()
        output = self.root / "review.html"
        result = write_review(path, output, check_traces=True)
        self.assertEqual(result["records"], 12)
        self.assertFalse(result["authenticated"])
        first = output.read_bytes()
        with self.assertRaisesRegex(ValueError, "new file"):
            write_review(path, output)
        self.assertEqual(output.read_bytes(), first)
        with self.assertRaisesRegex(ValueError, "html"):
            write_review(path, self.root / "manifest.json")


if __name__ == "__main__":
    unittest.main()
