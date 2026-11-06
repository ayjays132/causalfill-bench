"""Solver-owned wrapper using only the authorized public mailbox adapter."""
import importlib.util
import json
from pathlib import Path
import time
BASE = Path('/workspace/scratch/addf9cb6769c/signal-public-mailbox')
WORK = BASE / 'solver-work'
spec = importlib.util.spec_from_file_location('public_mailbox', BASE / 'mailbox_client.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

def episode(i):
    value = module.PublicMailbox(BASE / f'pilot-{i}').episode()
    (WORK / f'pilot-{i}-public.json').write_text(json.dumps(value, indent=2))
    return value

def call(i, tool, arguments=None):
    arguments = {} if arguments is None else arguments
    start = time.monotonic()
    value = module.PublicMailbox(BASE / f'pilot-{i}').call(tool, arguments)
    record = {'tool': tool, 'arguments': arguments, 'output': value, 'elapsed_seconds': time.monotonic() - start}
    with (WORK / f'pilot-{i}-observations.jsonl').open('a') as f:
        f.write(json.dumps(record, allow_nan=False) + '\n')
    return value
