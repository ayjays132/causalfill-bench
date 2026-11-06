#!/usr/bin/env python3
"""Run complete discovery and save explicit source-bound completion evidence."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import platform
import sys
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from causalfill import __version__
from causalfill.runner import source_fingerprint, write_json


def checked_source_hashes():
    paths = [p for directory in ("causalfill", "tests", "tools", "clients")
             for p in (ROOT/directory).rglob("*.py") if "__pycache__" not in p.parts]
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output must not exist")
    args.output.mkdir(parents=True)
    started = time.monotonic()
    before = checked_source_hashes()
    core_before = source_fingerprint()
    suite = unittest.defaultTestLoader.discover(str(ROOT/"tests"))
    with (args.output/"unittest.log").open("w") as log:
        result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    after = checked_source_hashes()
    report = {"schema":"causalfill.unit-gate.v05", "version":__version__,
        "command":"python -m unittest discover -s tests -v (equivalent TestLoader/TextTestRunner with explicit completion record)",
        "tests":result.testsRun,"failures":len(result.failures),"errors":len(result.errors),
        "skipped":len(result.skipped),"expected_failures":len(result.expectedFailures),
        "unexpected_successes":len(result.unexpectedSuccesses),
        "source_stable":before==after,"source_fingerprint":core_before,
        "checked_source_sha256":before,"python":sys.version,"platform":platform.platform(),
        "elapsed_seconds":round(time.monotonic()-started,3),
        "passed":result.wasSuccessful() and before==after,
        "log_sha256":hashlib.sha256((args.output/"unittest.log").read_bytes()).hexdigest()}
    write_json(args.output/"result.json",report)
    print(json.dumps({k:report[k] for k in ("passed","tests","failures","errors","skipped","source_stable","elapsed_seconds")},indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
