# Public evaluator protocol

## Purpose and isolation boundary

The HTTP server exposes one evaluator-owned episode through public observations and budgeted tools. The agent receives a task description and tool responses. The evaluator retains the generator seed, task object, hidden state, final grader, trusted result, and trace files.

This is a standard-library **development server**, not a hardened multi-tenant service, an operating-system sandbox, or a complete model-evaluation platform. A separate Python process on the same host does not prevent an agent with filesystem or process access from reading evaluator state. For credible evaluation, place the evaluator and its output directory in a separate container or VM that is inaccessible to the agent, expose only this authenticated interface, and restrict the agent's other network and filesystem capabilities. Do not mount the benchmark source, evaluator outputs, seed file, or reference answers into the agent's environment.

The server defaults to loopback. It does not provide TLS, identity management, rate limiting against unauthenticated callers, or an external immutable audit log. Bind it to an untrusted network only behind independently configured deployment controls. These requirements are deployment work; they are not claimed as implemented by this package.

## Python entry points

```python
from pathlib import Path
import secrets
from causalfill.domains.words import WordsTask
from causalfill.session import Session
from causalfill.server import create_server, serve

session = Session(WordsTask(seed=41, split="dev", difficulty=2))
token = secrets.token_urlsafe(32)

# Blocking server. Pass the token to the agent through a separate local channel.
serve(session, host="127.0.0.1", port=8787,
      token=token, output_dir=Path("private-evaluator-results"))
```

Exact signatures:

```python
create_server(session: Session, host: str = "127.0.0.1", port: int = 8787,
              *, token: str, output_dir: Path) -> EvaluatorHTTPServer
serve(session: Session, host: str = "127.0.0.1", port: int = 8787,
      *, token: str, output_dir: Path) -> None
```

`create_server` returns a `ThreadingHTTPServer` subclass. Its caller owns `serve_forever()`, `shutdown()`, and `server_close()`. Port `0` selects an ephemeral port for integration tests. `serve` runs until interrupted; it records an unfinished episode as failed when stopping. Neither function prints credentials or request bodies. The supplied token must contain 24–256 printable ASCII characters without whitespace. Generate it randomly; length validation does not establish entropy.

## Authentication

Every supported request requires exactly one header:

```http
Authorization: Bearer <privately supplied token>
```

Unauthorized requests receive HTTP 401 and do not consume the episode's action budget. The token is compared using constant-time comparison. Authentication headers are not included in evaluator traces or written to stderr.

## Endpoints

| Method and path | Request | Response |
|---|---|---|
| `GET /v1/episode` | No body | Public task description, file names, domain tools, common tools, budgets, random episode ID, and `episode_closed` |
| `POST /v1/tool` | JSON object with exactly `tool` and `arguments` | The public response from `Session.call`, including event ID and cost when applicable |

No endpoint returns final grades, reference answers, seeds, task internals, arbitrary host files, source code, or a reset operation. Query strings, fragments, unknown routes, and unsupported methods are rejected. File tools access only the task's declared virtual file map; passing `/etc/passwd` or a relative path does not open that host file.

Example request body:

```json
{
  "tool": "read_file",
  "arguments": {"path": "/skill/routing.txt"}
}
```

Example final submission:

```json
{
  "tool": "submit",
  "arguments": {
    "fill": {"gate_word": "any", "required_state": "true"},
    "confidence": 0.85,
    "abstain": false,
    "evidence": ["e0001", "e0002"]
  }
}
```

The exact fill keys depend on the episode. A well-formed final submission closes the episode immediately. Its HTTP response acknowledges acceptance and closure, **not correctness**. All later tool calls receive `episode_closed`. The server serializes all episode mutations under one lock, so concurrent final submissions have exactly one accepted winner.

For abstention, set `abstain` to `true` and `fill` to `{}`. Confidence concerns the correctness of the submitted decision; abstention does not imply confidence must be zero. Evidence IDs must refer to previously observed events. These IDs establish that the event occurred; they do not prove that an argument logically follows from it.

## Input bounds and errors

POST requests require `Content-Type: application/json` and one valid `Content-Length` no greater than **131,072 bytes**. Chunked transfer encoding is unsupported. The body must be UTF-8 JSON. Duplicate object keys, NaN/infinity, numbers that overflow to infinity, nesting deeper than 32, more than 65,536 JSON nodes, strings over 16,384 characters, objects over 256 keys, and integers over 256 decimal digits are rejected. Domain validators impose additional, tighter limits. The node budget admits the thousands of compact proof-step triples in the formal track while retaining the same byte bound.

Authenticated malformed HTTP or JSON requests are recorded as sanitized `__protocol_error__` actions and consume core budget. Raw malformed bodies are omitted from traces. Unknown or invalid domain tool calls are handled by the core. Transport-level failures before authentication are outside the episode ledger. Requests use a five-second socket timeout; the episode has its own separately declared deadline.

Error responses are bounded JSON with generic messages. They do not expose exception tracebacks or filesystem paths. The server sends `Cache-Control: no-store` and closes each connection after its response. Common HTTP status codes are 400 for invalid JSON/envelopes, 401 for authentication failure, 404 for unknown routes, 405 for unsupported methods, 411 for a missing or invalid length, 413 for oversized bodies, 415 for the wrong content type, and 500 for an evaluator-side failure. A syntactically valid tool call can receive HTTP 200 with a domain `error` object; inspect the body.

## JSON-lines transport

`python -m causalfill stdio ...` exposes the same public episode and tool envelope over standard input/output. It reads raw bytes and applies the same strict JSON decoder and structural limits as HTTP, including duplicate-key rejection and the 131,072-byte cap. The byte cap applies to UTF-8 bytes, not Unicode character count. Other malformed requests are charged through the core invalid-call path; an oversized line terminates the episode as `request_too_large`. HTTP authentication and headers do not apply to this local transport. A caller must isolate the process and its private files just as for an HTTP evaluator.

## Trusted output files

After closure, the evaluator writes these files to its private output directory:

- `<episode_id>.result.json`: trusted evaluator result and metrics.
- `<episode_id>.trace.json`: tool arguments, public responses, costs, and hash-chain events.
- `<episode_id>.complete.json`: filenames and SHA-256 hashes, committed last as the completion indicator.

Individual files are replaced atomically. The completion manifest indicates both final result and trace were written. It is not a digital signature or external attestation. A hash chain detects inconsistencies only relative to a trusted hash or trusted evaluator; someone who controls the entire artifact can rewrite and rehash it. Keep the output directory inaccessible to evaluated agents.

The supplied integration tests bind a real loopback socket and exercise authorization, virtual-file isolation, grade withholding, final-submission races, malformed JSON, nonfinite values, deep structures, content-length limits, and trusted output persistence. Passing those tests establishes these specific behaviors. It does not establish adversarial deployment security or frontier-model performance.
