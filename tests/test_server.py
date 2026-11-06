"""Real loopback integration checks for the public HTTP observation boundary."""

from concurrent.futures import ThreadPoolExecutor
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest

from causalfill.domains.words import WordsTask
from causalfill.server import MAX_BODY_BYTES, create_server
from causalfill.session import Session, verify_trace


TOKEN = "test-only-evaluator-token-64-characters-abcdefghijklmnopqrstuvwx"


class HTTPBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="causalfill-http-test-")
        self.output = Path(self.temporary.name)
        self.task = WordsTask(22, "dev", 2)
        self.session = Session(self.task)
        # Intentionally attempt the real bind. Environmental failures should be
        # reported as such, not silently converted into passing protocol tests.
        self.server = create_server(self.session, port=0, token=TOKEN, output_dir=self.output)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temporary.cleanup()

    def request(self, method, path, body=None, *, auth=TOKEN, headers=None):
        request_headers = dict(headers or {})
        if auth is not None:
            request_headers["Authorization"] = "Bearer " + auth
        if isinstance(body, dict):
            body = json.dumps(body).encode()
            request_headers.setdefault("Content-Type", "application/json")
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=3)
        try:
            connection.request(method, path, body=body, headers=request_headers)
            response = connection.getresponse()
            data = response.read()
            return response.status, json.loads(data) if data else {}, dict(response.getheaders())
        finally:
            connection.close()

    def submit_body(self):
        return {"tool": "submit", "arguments": {"fill": self.task.reference_answer(),
            "confidence": 1.0, "abstain": False, "evidence": []}}

    def test_authentication_required_without_consuming_episode_budget(self):
        for auth in (None, "wrong-token"):
            status, payload, _ = self.request("GET", "/v1/episode", auth=auth)
            self.assertEqual(status, 401)
            self.assertEqual(payload, {"error": "unauthorized"})
        self.assertEqual(self.session.cost, 0)
        self.assertEqual(self.session.trace, [])
        status, public, headers = self.request("GET", "/v1/episode")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Cache-Control"], "no-store")
        for private in ("seed", "truth", "grade", "result", "structural_signature"):
            self.assertNotIn(private, public)
        self.assertNotIn(TOKEN, json.dumps(public))

    def test_virtual_reads_cannot_read_host_files_and_no_private_endpoints(self):
        status, payload, _ = self.request("POST", "/v1/tool", {
            "tool": "read_file", "arguments": {"path": "/etc/passwd"}})
        self.assertEqual(status, 200)
        self.assertIn("error", payload)
        self.assertNotIn("root:", json.dumps(payload))
        for path in ("/v1/grade", "/v1/reset", "/v1/source", "/etc/passwd", "/v1/episode?grade=1", "/v1/episode#grade"):
            status, payload, _ = self.request("GET", path)
            self.assertEqual(status, 404)
            self.assertEqual(payload["error"], "unknown_endpoint")

    def test_tool_response_and_single_final_do_not_disclose_grades(self):
        status, response, _ = self.request("POST", "/v1/tool", self.submit_body())
        self.assertEqual(status, 200)
        self.assertTrue(response["accepted"])
        self.assertTrue(response["episode_closed"])
        for key in ("success", "recovery", "outcome", "safety", "verdict", "answerable"):
            self.assertNotIn(key, response)
        _, second, _ = self.request("POST", "/v1/tool", self.submit_body())
        self.assertEqual(second, {"error": "episode_closed"})
        result = json.loads((self.output / f"{self.session.id}.result.json").read_text())
        trace = json.loads((self.output / f"{self.session.id}.trace.json").read_text())
        complete = json.loads((self.output / f"{self.session.id}.complete.json").read_text())
        self.assertTrue(result["success"])
        self.assertTrue(verify_trace(trace))
        self.assertEqual(complete["episode_id"], self.session.id)
        self.assertNotIn(TOKEN, json.dumps([result, trace, complete]))

    def test_json_limits_nonfinite_duplicate_and_deep_values_are_rejected(self):
        invalid_bodies = [
            b'{"tool":"session_status","arguments":{"x":NaN}}',
            b'{"tool":"session_status","arguments":{"x":1e9999}}',
            b'{"tool":"session_status","tool":"read_file","arguments":{}}',
            b'{"tool":"session_status","arguments":{"x":' + b'[' * 40 + b'0' + b']' * 40 + b'}}',
            b'{"tool":"session_status","arguments":{},"unexpected":1}',
            b'\xff',
        ]
        for body in invalid_bodies:
            with self.subTest(body=body[:80]):
                status, payload, _ = self.request("POST", "/v1/tool", body,
                    headers={"Content-Type": "application/json"})
                self.assertEqual(status, 400)
                self.assertEqual(payload["error"], "invalid_json_or_envelope")
        self.assertEqual(self.session.invalid, len(invalid_bodies))
        self.assertEqual(self.session.cost, len(invalid_bodies))

    def test_size_and_content_type_are_checked_before_body_parsing(self):
        status, response, _ = self.request("POST", "/v1/tool", b"", headers={
            "Content-Type": "application/json", "Content-Length": str(MAX_BODY_BYTES + 1)})
        self.assertEqual(status, 413)
        self.assertEqual(response["error"], "body_too_large")
        status, response, _ = self.request("POST", "/v1/tool", b"{}", headers={"Content-Type": "text/plain"})
        self.assertEqual(status, 415)
        self.assertEqual(response["error"], "content_type_must_be_json")
        status, response, _ = self.request("POST", "/v1/tool", b"{}", headers={
            "Content-Type": "application/json", "Transfer-Encoding": "chunked"})
        self.assertEqual(status, 400)
        self.assertEqual(response["error"], "transfer_encoding_unsupported")

    def test_concurrent_final_submissions_have_one_winner(self):
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(self.request, "POST", "/v1/tool", self.submit_body()) for _ in range(2)]
            replies = [future.result()[1] for future in futures]
        self.assertEqual(sum(reply.get("accepted") is True for reply in replies), 1)
        self.assertEqual(sum(reply.get("error") == "episode_closed" for reply in replies), 1)
        self.assertEqual(sum(event["tool"] == "submit" for event in self.session.trace), 1)
        self.assertEqual(len(list(self.output.glob("*.complete.json"))), 1)

    def test_invalid_token_configuration_fails_before_server_creation(self):
        with self.assertRaises(ValueError):
            create_server(Session(WordsTask(1)), port=0, token="short", output_dir=self.output)


if __name__ == "__main__":
    unittest.main()

