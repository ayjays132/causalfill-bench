"""Authenticated HTTP observation boundary for one evaluator-owned episode.

This standard-library development server is not a hostile multi-tenant service
or a filesystem sandbox. Isolate the evaluator host from evaluated agents.
"""

from __future__ import annotations

import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
import tempfile
import threading
import time
from typing import Any

from .session import Session


from .protocol_json import (MAX_BODY_BYTES, MAX_JSON_DEPTH, MAX_JSON_NODES,
                            MAX_STRING_LENGTH, MAX_OBJECT_KEYS, _strict_json)


def _atomic_json(path: Path, value: Any) -> str:
    payload = (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True,
                          allow_nan=False) + "\n").encode("utf-8")
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent,
                                         prefix=f".{path.name}.", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
        temporary.replace(path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return hashlib.sha256(payload).hexdigest()


class EvaluatorHTTPServer(ThreadingHTTPServer):
    """One episode, serialized mutation, authenticated public observations only."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], session: Session, token: str, output_dir: Path):
        self.session = session
        self._authorization = ("Bearer " + token).encode("ascii")
        self._session_lock = threading.Lock()
        self._output_dir = output_dir
        self._persisted = False
        super().__init__(address, _Handler)

    def _persist_closed(self) -> None:
        """Caller holds _session_lock. Completion manifest is committed last."""
        if self._persisted or not self.session.closed or self.session.result is None:
            return
        episode_id = self.session.id
        if re.fullmatch(r"[a-f0-9]{32}", episode_id) is None:
            raise ValueError("invalid evaluator episode identifier")
        result_name = f"{episode_id}.result.json"
        trace_name = f"{episode_id}.trace.json"
        result_hash = _atomic_json(self._output_dir / result_name, self.session.result)
        trace_hash = _atomic_json(self._output_dir / trace_name, self.session.trace)
        _atomic_json(self._output_dir / f"{episode_id}.complete.json", {
            "schema_version": 1, "episode_id": episode_id,
            "result_file": result_name, "trace_file": trace_name,
            "result_sha256": result_hash, "trace_sha256": trace_hash,
        })
        self._persisted = True

    def handle_error(self, request: Any, client_address: Any) -> None:
        # Base socketserver otherwise prints arbitrary traceback context. The
        # development host must monitor its process without logging credentials.
        return


class _Handler(BaseHTTPRequestHandler):
    server: EvaluatorHTTPServer
    protocol_version = "HTTP/1.1"
    server_version = "CausalFillEvaluator"
    sys_version = ""

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(5.0)

    def log_message(self, format: str, *args: Any) -> None:
        # Never send bearer headers, request paths, bodies, or tokens to stderr.
        return

    def _send(self, status: int, payload: dict) -> None:
        data = json.dumps(payload, ensure_ascii=True, allow_nan=False,
                          separators=(",", ":")).encode("utf-8")
        self.close_connection = True
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Connection", "close")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def send_error(self, code: int, message: str | None = None, explain: str | None = None) -> None:
        # BaseHTTPRequestHandler errors are bounded JSON, without reflected text.
        self._send(code, {"error": "invalid_http_request"})

    def _authenticated(self) -> bool:
        values = self.headers.get_all("Authorization", [])
        if len(values) != 1 or len(values[0]) > 512:
            self._send(401, {"error": "unauthorized"})
            return False
        candidate = values[0].encode("utf-8", errors="strict")
        if not hmac.compare_digest(candidate, self.server._authorization):
            self._send(401, {"error": "unauthorized"})
            return False
        return True

    def _protocol_error(self, status: int, reason: str) -> None:
        """Authenticated malformed requests consume a core call; bodies are omitted."""
        try:
            with self.server._session_lock:
                event = self.server.session.call("__protocol_error__", {"reason": reason})
                self.server._persist_closed()
            payload = {"error": reason}
            for key in ("event_id", "cost_used"):
                if key in event:
                    payload[key] = event[key]
            self._send(status, payload)
        except (OSError, ValueError, TypeError):
            self._send(500, {"error": "evaluator_error"})

    def _transport_headers_valid(self) -> bool:
        if self.headers.get_all("Transfer-Encoding", []):
            self._protocol_error(400, "transfer_encoding_unsupported")
            return False
        return True

    def do_GET(self) -> None:
        if not self._authenticated() or not self._transport_headers_valid():
            return
        if self.path != "/v1/episode":
            self._protocol_error(404, "unknown_endpoint")
            return
        lengths = self.headers.get_all("Content-Length", [])
        if lengths and lengths != ["0"]:
            self._protocol_error(400, "unexpected_request_body")
            return
        try:
            with self.server._session_lock:
                session = self.server.session
                if not session.closed and time.monotonic() - session.started > session.max_seconds:
                    session.finish_failure("timeout")
                payload = session.public()
                payload["episode_closed"] = session.closed
                self.server._persist_closed()
            self._send(200, payload)
        except (OSError, ValueError, TypeError):
            self._send(500, {"error": "evaluator_error"})

    def do_POST(self) -> None:
        if not self._authenticated() or not self._transport_headers_valid():
            return
        if self.path != "/v1/tool":
            self._protocol_error(404, "unknown_endpoint")
            return
        content_types = self.headers.get_all("Content-Type", [])
        if len(content_types) != 1 or content_types[0].split(";", 1)[0].strip().lower() != "application/json":
            self._protocol_error(415, "content_type_must_be_json")
            return
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) != 1 or not lengths[0].isascii() or not lengths[0].isdigit():
            self._protocol_error(411, "valid_content_length_required")
            return
        # Avoid int() on an attacker-controlled, excessively long length token.
        if len(lengths[0]) > 6:
            self._protocol_error(413, "body_too_large")
            return
        length = int(lengths[0])
        if length > MAX_BODY_BYTES:
            self._protocol_error(413, "body_too_large")
            return
        try:
            raw = self.rfile.read(length)
            if len(raw) != length:
                self._protocol_error(400, "incomplete_request_body")
                return
            body = _strict_json(raw)
            if type(body) is not dict or set(body) != {"tool", "arguments"}:
                raise ValueError("invalid envelope")
            if type(body["tool"]) is not str or not 1 <= len(body["tool"]) <= 80:
                raise ValueError("invalid tool")
            if type(body["arguments"]) is not dict:
                raise ValueError("invalid arguments")
        except (ValueError, UnicodeError, RecursionError, OverflowError):
            self._protocol_error(400, "invalid_json_or_envelope")
            return
        except (OSError, TimeoutError):
            self._protocol_error(408, "request_body_timeout")
            return
        try:
            with self.server._session_lock:
                response = self.server.session.call(body["tool"], body["arguments"])
                self.server._persist_closed()
            self._send(200, response)
        except (OSError, ValueError, TypeError, OverflowError, RecursionError):
            self._send(500, {"error": "evaluator_error"})

    def _unsupported_method(self) -> None:
        if self._authenticated():
            self._protocol_error(405, "method_not_allowed")

    do_PUT = _unsupported_method
    do_DELETE = _unsupported_method
    do_PATCH = _unsupported_method
    do_HEAD = _unsupported_method
    do_OPTIONS = _unsupported_method
    do_CONNECT = _unsupported_method
    do_TRACE = _unsupported_method


def create_server(
    session: Session, host: str = "127.0.0.1", port: int = 8787, *,
    token: str, output_dir: Path,
) -> EvaluatorHTTPServer:
    """Construct a server; caller owns serve_forever(), shutdown(), server_close().

    ``port=0`` selects an ephemeral port for tests. The evaluator-owned output
    directory must not be mounted into the evaluated agent's environment.
    """
    if type(token) is not str or not 24 <= len(token) <= 256 or not token.isascii() or any(c.isspace() or ord(c) < 33 or ord(c) > 126 for c in token):
        raise ValueError("token must contain 24..256 printable ASCII non-whitespace characters")
    if type(host) is not str or not host or type(port) is not int or not 0 <= port <= 65535:
        raise ValueError("invalid bind address")
    destination = Path(output_dir).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    return EvaluatorHTTPServer((host, port), session, token, destination)


def serve(
    session: Session, host: str = "127.0.0.1", port: int = 8787, *,
    token: str, output_dir: Path,
) -> None:
    """Serve one episode until interrupted; persist trusted final evaluator files."""
    server = create_server(session, host, port, token=token, output_dir=output_dir)
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        with server._session_lock:
            if not session.closed:
                session.finish_failure("server_stopped")
            server._persist_closed()
        server.server_close()

