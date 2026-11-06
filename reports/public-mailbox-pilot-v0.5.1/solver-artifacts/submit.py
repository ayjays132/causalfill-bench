"""Verify public certificates and send exactly one final submission per episode."""
import json
from concurrent.futures import ThreadPoolExecutor
from client import WORK,call

def submit_one(i):
    prepared=json.loads((WORK/f'pilot-{i}-prepared.json').read_text())
    contract=json.loads(json.loads((WORK/f'pilot-{i}-formal-response.json').read_text())['content'])
    problem=contract['problem']
    submission=prepared['submission']
    fill=submission['fill']
    records=[json.loads(line) for line in (WORK/f'pilot-{i}-observations.jsonl').read_text().splitlines()]
    assert not any(r['tool']=='submit' for r in records)
    probes={r['output']['experiment']:r['output']['outcome'] for r in records if r['tool'].startswith('probe_')}
    commits=[r for r in records if r['tool'].startswith('commit_')]
    assert len(commits)==1 and commits[0]['output']['committed'] is True
    assert commits[0]['output']['action']==fill['action']
    commit_index=records.index(commits[0])
    assert all(not r['tool'].startswith('probe_') for r in records[commit_index+1:])
    action=next(a for a in problem['actions'] if a['id']==fill['action'])
    experiments={q['id']:q for q in problem['experiments']}
    k=problem['max_corruptions']
    compatible=[w for w in problem['worlds'] if sum(experiments[q]['responses'][w]!=r for q,r in probes.items())<=k]
    assert compatible and set(compatible)<=set(action['success_worlds'])
    excluded=set(problem['worlds'])-set(action['success_worlds'])
    assert len(fill['exclusions'])==len(excluded)
    assert {e['world'] for e in fill['exclusions']}==excluded
    for e in fill['exclusions']:
        assert len(e['conflicts'])==len(set(e['conflicts']))
        assert len(e['conflicts'])>=k+1
        assert all(q in probes and experiments[q]['responses'][e['world']]!=probes[q] for q in e['conflicts'])
    assert fill['problem_sha256']==contract['problem_sha256']
    op_cost=sum(experiments[q]['cost'] for q in probes)+action['cost']
    assert op_cost<=contract['operational_budget']
    assert set(submission['evidence'])=={r['output']['event_id'] for r in records}
    marker=WORK/f'pilot-{i}-submission-sent.json'
    with marker.open('x') as f:
        f.write(json.dumps(submission,indent=2))
    result=call(i,'submit',submission)
    (WORK/f'pilot-{i}-submission-response.json').write_text(json.dumps(result,indent=2))
    return {'episode':i,'response':result}

if __name__=='__main__':
    with ThreadPoolExecutor(max_workers=6) as pool:
        results=list(pool.map(submit_one,range(1,7)))
    (WORK/'submission-summary.json').write_text(json.dumps(results,indent=2))
    for result in results:
        print(json.dumps(result))
