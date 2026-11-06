import sys,json
from pathlib import Path
sys.path.insert(0,'/workspace/scratch/addf9cb6769c/public_pilot_mailbox_v04')
from mailbox_client import PublicMailbox
BASE='/workspace/scratch/addf9cb6769c/public_pilot_mailbox_v04'
WORK=Path('/workspace/scratch/addf9cb6769c/pilot_solver_work')
def episode(i):
    return PublicMailbox(f'{BASE}/pilot-{i}').episode()
def call(i,tool,args=None):
    answer=PublicMailbox(f'{BASE}/pilot-{i}').call(tool,args or {})
    with (WORK/f'public_log_{i}.jsonl').open('a') as f:
        f.write(json.dumps({'tool':tool,'arguments':args or {},'response':answer})+'\n')
    print(f'EPISODE {i} {tool}: '+json.dumps(answer),flush=True)
    return answer
