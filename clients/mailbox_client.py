"""Public-data-only client for the shared-host development pilot mailbox.

The directory must contain public.json and numbered request/response files.
This adapter contains no evaluator imports, seeds, grades, or task solutions.
It is a development transport, not an operating-system security boundary.
"""
from __future__ import annotations
import json
from pathlib import Path
import time


class PublicMailbox:
    def __init__(self, directory):
        self.directory = Path(directory)

    def episode(self):
        return json.loads((self.directory / "public.json").read_text())

    def call(self, tool, arguments, timeout=40):
        numbers = [int(path.stem.split("-")[1]) for path in self.directory.glob("request-*.json")]
        number = max(numbers, default=0) + 1
        request = self.directory / f"request-{number:04d}.json"
        temporary = request.with_suffix(".tmp")
        temporary.write_text(json.dumps({"tool": tool, "arguments": arguments}, allow_nan=False))
        temporary.replace(request)
        response = self.directory / f"response-{number:04d}.json"
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if response.exists():
                return json.loads(response.read_text())
            time.sleep(0.05)
        raise TimeoutError("public mailbox response deadline exceeded")
