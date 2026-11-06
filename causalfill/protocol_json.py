"""Shared bounded JSON contract for the HTTP and stdio transports."""
from __future__ import annotations

import json
import math
from typing import Any


MAX_BODY_BYTES = 128 * 1024
MAX_JSON_DEPTH = 32
MAX_JSON_NODES = 65536
MAX_STRING_LENGTH = 16384
MAX_OBJECT_KEYS = 256


def _strict_json(raw: bytes) -> Any:
    """Parse bounded UTF-8 JSON without duplicate keys or nonfinite numbers."""
    if not isinstance(raw, (bytes, bytearray)) or len(raw) > MAX_BODY_BYTES:
        raise ValueError("JSON request byte limit")
    text = raw.decode("utf-8", errors="strict")
    depth, in_string, escaped = 0, False, False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
            if depth > MAX_JSON_DEPTH:
                raise ValueError("JSON nesting limit")
        elif char in "]}":
            depth -= 1

    def parse_int(value: str) -> int:
        if len(value.lstrip("-")) > 256:
            raise ValueError("integer size limit")
        return int(value)

    def parse_float(value: str) -> float:
        number = float(value)
        if not math.isfinite(number):
            raise ValueError("nonfinite JSON number")
        return number

    def reject_constant(value: str) -> None:
        raise ValueError("nonstandard JSON constant")

    def object_pairs(pairs: list[tuple[str, Any]]) -> dict:
        if len(pairs) > MAX_OBJECT_KEYS:
            raise ValueError("object size limit")
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    value = json.loads(text, parse_int=parse_int, parse_float=parse_float,
                       parse_constant=reject_constant, object_pairs_hook=object_pairs)
    pending, nodes = [value], 0
    while pending:
        current = pending.pop()
        nodes += 1
        if nodes > MAX_JSON_NODES:
            raise ValueError("JSON node limit")
        if isinstance(current, str) and len(current) > MAX_STRING_LENGTH:
            raise ValueError("JSON string limit")
        if isinstance(current, dict):
            pending.extend(current.keys())
            pending.extend(current.values())
        elif isinstance(current, list):
            pending.extend(current)
    return value


