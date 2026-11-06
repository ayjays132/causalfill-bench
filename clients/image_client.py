#!/usr/bin/env python3
"""Public-only HTTP client that saves delivered PNGs for a vision-capable solver.

Copy this file alone to the isolated solver environment. It imports no evaluator
code. The saved image is exactly the public tool payload, never private state.
Use CFB_URL / CFB_TOKEN as with http_client.py. No credentials are printed.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import struct
import sys
import urllib.error
import urllib.request

MAX_IMAGE_BYTES = 16 * 1024 * 1024
MAX_RESPONSE_BYTES = 24 * 1024 * 1024


def materialize_images(value, output, images=None):
    """Replace inline images with verified local paths; preserve other fields."""
    images = [] if images is None else images
    if isinstance(value, dict):
        if value.get("mime_type") == "image/png" and "png_base64" in value:
            encoded = value["png_base64"]
            if type(encoded) is not str or len(encoded) > (MAX_IMAGE_BYTES * 4 // 3 + 8):
                raise ValueError("image payload exceeds limit")
            try:
                data = base64.b64decode(encoded, validate=True)
            except (ValueError, TypeError) as exc:
                raise ValueError("invalid PNG base64") from exc
            if len(data) > MAX_IMAGE_BYTES or data[:8] != b"\x89PNG\r\n\x1a\n" or len(data) < 33:
                raise ValueError("invalid or oversized PNG")
            if data[12:16] != b"IHDR" or struct.unpack(">I", data[8:12])[0] != 13:
                raise ValueError("missing PNG IHDR")
            width, height = struct.unpack(">II", data[16:24])
            if not 1 <= width <= 2048 or not 1 <= height <= 2048:
                raise ValueError("image dimensions outside bounds")
            for key, actual in (("width", width), ("height", height)):
                if type(value.get(key)) is not int or value[key] != actual:
                    raise ValueError("image dimension metadata mismatch")
            digest = hashlib.sha256(data).hexdigest()
            if value.get("sha256") != digest:
                raise ValueError("image hash mismatch")
            output.mkdir(parents=True, exist_ok=True)
            path = output / (digest + ".png")
            if path.exists():
                if path.read_bytes() != data:
                    raise ValueError("existing observation file differs")
            else:
                # Exclusive creation prevents overwriting another artifact.
                with path.open("xb") as stream:
                    stream.write(data)
            images.append(str(path.resolve()))
            return {k: v for k, v in value.items() if k != "png_base64"} | {"local_image_path": str(path.resolve())}
        return {k: materialize_images(v, output, images) for k, v in value.items()}
    if isinstance(value, list):
        return [materialize_images(v, output, images) for v in value]
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("episode", "tool"))
    parser.add_argument("--output-dir", type=Path, default=Path("observations"))
    args = parser.parse_args()
    url, token = os.environ.get("CFB_URL", ""), os.environ.get("CFB_TOKEN", "")
    if not url.startswith(("http://", "https://")) or not token:
        parser.error("set CFB_URL and CFB_TOKEN privately")
    headers = {"Authorization": "Bearer " + token}
    data = None
    route = "/v1/episode"
    if args.command == "tool":
        data = sys.stdin.buffer.read(131073)
        if len(data) > 131072:
            parser.error("request exceeds 128 KiB")
        headers["Content-Type"] = "application/json"
        route = "/v1/tool"
    request = urllib.request.Request(url.rstrip("/") + route, data=data, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read(MAX_RESPONSE_BYTES + 1)
        if len(payload) > MAX_RESPONSE_BYTES:
            raise ValueError("response exceeds client cap")
        value = json.loads(payload)
        result = materialize_images(value, args.output_dir)
        print(json.dumps(result, indent=2, allow_nan=False))
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(json.dumps({"error": "public image client failed", "kind": type(exc).__name__}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
