"""Deterministic public-protocol adversarial checks, including real HTTP races.

This exercises a tiny independent task, so state and grading expectations do not
reuse a benchmark domain's implementation. It is an integrity stress experiment,
not a model capability score or a hardened-service certification.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from fractions import Fraction
import hashlib
import http.client
import json
import math
from pathlib import Path
import random
import secrets
import subprocess
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from causalfill.metrics import summarize
from causalfill.runner import source_fingerprint
from causalfill.server import _strict_json, create_server
from causalfill.session import Session, verify_trace
from causalfill.types import Task, Verdict, fields, strict_int


class ProbeTask(Task):
    family = "protocol_audit"

    def __init__(self):
        super().__init__(1)
        self.private_marker = "evaluator-only-canary-7cf38c"
        self.counter = 0
        self.grade_calls = 0
        self.budget = 11
        self.max_calls = 8
        self.files = {"/public.txt": "Public fixture, no evaluator state."}
        self.tools = {"increment": {"cost": 2}, "fail": {"cost": 3}}

    def query(self, name, args):
        if name == "fail":
            raise ValueError("fixture rejects this action")
        fields(args, {"amount"})
        amount = strict_int(args["amount"], 0, 3)
        self.counter += amount
        return {"counter": self.counter}

    def evaluate(self, fill):
        self.grade_calls += 1
        fields(fill, {"counter"})
        return Verdict(type(fill["counter"]) is int and fill["counter"] == self.counter,
                       details={"private": self.private_marker})


class Audit:
    def __init__(self):
        self.counts = {}
        self.failures = []

    def check(self, category, condition, detail):
        self.counts[category] = self.counts.get(category, 0) + 1
        if not condition:
            self.failures.append({"category": category, "detail": detail})


def submission(counter=0):
    return {"fill": {"counter": counter}, "confidence": 0.5,
            "abstain": False, "evidence": []}


def parser_checks(audit, rng, cases):
    atoms = [None, True, False, 0, 17, -320, 0.125, "", "lambda", "\u03bb", "[not nesting]"]

    def value(depth=0):
        if depth == 4 or rng.random() < 0.55:
            return rng.choice(atoms)
        if rng.random() < 0.5:
            return [value(depth + 1) for _ in range(rng.randrange(5))]
        return {"k" + str(i): value(depth + 1) for i in range(rng.randrange(5))}

    for i in range(cases):
        original = value()
        raw = json.dumps(original, ensure_ascii=rng.choice((True, False)),
                         separators=(",", ":")).encode()
        audit.check("valid_json_roundtrip", _strict_json(raw) == original, i)
    malformed = [b'{"x":0,"x":1}', b'{"x":{"a":0,"a":1}}', b'{"x":NaN}',
                 b'{"x":Infinity}', b'{"x":-Infinity}', b'{"x":1e9999}',
                 b'{"x":' + b'9' * 257 + b'}', b'[' * 33 + b'0' + b']' * 33,
                 b'{"x":"' + b'a' * 16385 + b'"}', b'\xff', b'{', b'[]junk',
                 json.dumps({str(i): i for i in range(257)}).encode(),
                 b'[' + b'0,' * 65535 + b'0]']
    for i, raw in enumerate(malformed):
        try:
            _strict_json(raw)
            rejected = False
        except (ValueError, TypeError, RecursionError):
            rejected = True
        audit.check("malformed_json_rejected", rejected, i)


def session_checks(audit, rng, episodes):
    choices = [("list_files", {}), ("read_file", {"path": "/public.txt"}),
               ("read_file", {"path": "/etc/passwd"}), ("session_status", {}),
               ("increment", {"amount": 1}), ("increment", {"amount": 3}),
               ("increment", {"amount": True}), ("increment", {"amount": -1}),
               ("increment", {"amount": 10**100}), ("fail", {}), ("unknown", {}),
               (None, {}), ("list_files", []), ("submit", {}),
               ("search_files", {"text": "fixture"})]
    for episode in range(episodes):
        task = ProbeTask()
        session = Session(task)
        expected_counter = 0
        for _ in range(18):
            tool, arguments = rng.choice(choices)
            before_counter, before_cost = task.counter, session.cost
            response = session.call(tool, arguments)
            if tool == "increment" and "error" not in response:
                expected_counter += arguments["amount"]
                audit.check("mutation_requires_paid_cost", session.cost - before_cost == 2, episode)
            else:
                audit.check("rejected_action_atomicity", task.counter == before_counter, episode)
            audit.check("independent_state", task.counter == expected_counter, episode)
            audit.check("response_separation", task.private_marker not in json.dumps(response), episode)
            audit.check("trace_integrity", verify_trace(session.trace), episode)
            if session.closed:
                break
        if not session.closed:
            response = session.call("submit", submission(expected_counter))
            audit.check("correct_final_submission", response.get("accepted") is True, episode)
            audit.check("private_grade", session.result["success"], episode)
        frozen = (task.counter, session.cost, session.calls, len(session.trace), task.grade_calls)
        for tool, arguments in [("submit", submission()), ("increment", {"amount": 1})]:
            audit.check("closed_response", session.call(tool, arguments) == {"error": "episode_closed"}, episode)
            audit.check("closed_immutable", frozen == (task.counter, session.cost, session.calls,
                                                       len(session.trace), task.grade_calls), episode)
        audit.check("grade_at_most_once", task.grade_calls <= 1, episode)
        if session.trace:
            damaged = json.loads(json.dumps(session.trace))
            damaged[0]["arguments"] = {"tampered": True}
            audit.check("tamper_detected", not verify_trace(damaged), episode)


def http_request(port, token, method, path, body=None, extras=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    headers = {"Authorization": "Bearer " + token}
    if body is not None:
        headers["Content-Type"] = "application/json"
    headers.update(extras or {})
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        raw = response.read()
        return response.status, json.loads(raw)
    finally:
        connection.close()


def http_checks(audit, trials):
    for trial in range(trials):
        task = ProbeTask()
        session = Session(task)
        token = secrets.token_urlsafe(32)
        with tempfile.TemporaryDirectory() as directory:
            server = create_server(session, "127.0.0.1", 0, token=token, output_dir=directory)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            port = server.server_address[1]
            try:
                status, response = http_request(port, token + "wrong", "GET", "/v1/episode")
                audit.check("http_auth", status == 401 and session.calls == 0 and not session.trace, trial)
                status, response = http_request(port, token, "GET", "/v1/episode")
                audit.check("http_public_isolation", status == 200 and task.private_marker not in json.dumps(response)
                            and "result" not in response and "seed" not in response, trial)
                if trial % 2 == 0:
                    body = json.dumps({"tool": "submit", "arguments": submission()}).encode()
                    with ThreadPoolExecutor(max_workers=8) as pool:
                        responses = list(pool.map(lambda _: http_request(port, token, "POST", "/v1/tool", body), range(16)))
                    audit.check("http_submission_race", sum(r.get("accepted") is True for _, r in responses) == 1,
                                trial)
                    audit.check("http_single_grade", task.grade_calls == 1 and session.result["success"], trial)
                else:
                    body = json.dumps({"tool": "increment", "arguments": {"amount": 1}}).encode()
                    with ThreadPoolExecutor(max_workers=8) as pool:
                        responses = list(pool.map(lambda _: http_request(port, token, "POST", "/v1/tool", body), range(16)))
                    audit.check("http_serialized_mutation", task.counter == 5 and session.cost == 10, trial)
                    audit.check("http_budget_closes", session.closed and not session.result["success"], trial)
                for status, response in responses:
                    audit.check("http_response_separation", status == 200 and task.private_marker not in json.dumps(response)
                                and "verdict" not in response and "success" not in response, trial)
                audit.check("http_trace_integrity", verify_trace(session.trace), trial)
                completion = json.loads(next(Path(directory).glob("*.complete.json")).read_text())
                for part in ("result", "trace"):
                    payload = (Path(directory) / completion[part + "_file"]).read_bytes()
                    audit.check("http_persisted_hash", hashlib.sha256(payload).hexdigest() == completion[part + "_sha256"],
                                [trial, part])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(3)


def stdio_checks(audit):
    # Duplicate keys must not acquire a different meaning through another transport.
    invalid = [b'{"tool":"submit","tool":"list_files","arguments":{}}',
               b'{"tool":"list_files","arguments":{"x":0},"arguments":{}}']
    final = json.dumps({"tool": "submit", "arguments": {"fill": {}, "abstain": True,
                         "confidence": 0.5, "evidence": []}}).encode()
    for i, request in enumerate(invalid):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, "-m", "causalfill", "stdio", "--family", "words",
                                     "--output", directory],input=request + b"\n" + final + b"\n",
                                    cwd=ROOT,capture_output=True,timeout=15)
            lines = [json.loads(line) for line in result.stdout.splitlines()]
            audit.check("stdio_duplicate_rejection", result.returncode == 0 and len(lines) == 3
                        and "error" in lines[1] and "files" not in lines[1], i)


def metrics_checks(audit):
    def record(value):
        return {"family": "fixture", "structural_signature": "fixture:a", "answerable": True,
                "success": False, "abstained": False, "tool_cost": value}
    for i, values in enumerate([[1e308, 1e308], [1.7976931348623157e308] * 4,
                                [1e308, 1e-300], [5e-324, 5e-324], [5e-324, 0.0]]):
        try:
            report = summarize([record(v) for v in values], n_bootstrap=1)
            mean = report["groups"][0]["aggregate"]["metric_means"]["tool_cost"]["mean"]
            expected = float(sum((Fraction(v) for v in values), Fraction(0)) / len(values))
            passed = math.isfinite(mean) and mean == expected
        except (ValueError, OverflowError):
            passed = False
        audit.check("finite_metric_mean", passed, i)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=37019)
    parser.add_argument("--cases", type=int, default=20000)
    parser.add_argument("--sessions", type=int, default=2000)
    parser.add_argument("--http-trials", type=int, default=12)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    started = time.monotonic()
    audit = Audit()
    rng = random.Random(args.seed)
    parser_checks(audit, rng, args.cases)
    session_checks(audit, rng, args.sessions)
    http_checks(audit, args.http_trials)
    stdio_checks(audit)
    metrics_checks(audit)
    report = {"scope": "synthetic evaluator integrity; not model performance or hostile-service certification",
              "seed": args.seed, "source_sha256": source_fingerprint(),
              "configuration": {"parser_cases": args.cases, "sessions": args.sessions,
                                "http_trials": args.http_trials, "requests_per_race": 16},
              "checks": sum(audit.counts.values()), "counts": audit.counts,
              "failure_count": len(audit.failures), "failures": audit.failures,
              "elapsed_seconds": round(time.monotonic() - started, 3)}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "counts"}, indent=2))
    return bool(audit.failures)


if __name__ == "__main__":
    raise SystemExit(main())
