"""Adaptive solver. Uses only own copies of public contracts and responses.

This stage prepares the final fill after safely committing one action. Final
submissions are sent separately, exactly once, after inspecting these outputs.
"""
import json
from concurrent.futures import ThreadPoolExecutor
from client import WORK, call
from planner import Planner

def records(i):
    return [json.loads(line) for line in (WORK/f'pilot-{i}-observations.jsonl').read_text().splitlines()]

def prepare(i):
    p=Planner(i)
    q_index={q['id']:j for j,q in enumerate(p.experiments)}
    q_by_id={q['id']:q for q in p.experiments}
    actions={a['id']:a for a in p.actions}
    used=ones=spent=0
    observations={}
    committed=None
    trace=[]
    for r in records(i):
        output=r['output']
        if r['tool'].startswith('probe_'):
            q=r['tool'][6:]
            assert output['experiment']==q and output['outcome'] in (0,1)
            assert q not in observations and committed is None
            observations[q]=output['outcome']
            used|=1<<q_index[q]
            ones|=output['outcome']<<q_index[q]
            spent+=q_by_id[q]['cost']
        elif r['tool'].startswith('commit_'):
            assert committed is None and output['committed'] is True
            committed=output['action']
            spent+=actions[committed]['cost']
        elif r['tool']=='submit':
            raise RuntimeError('Episode already submitted; refusing any further operations')
    root=p.solve()
    assert root[0]<=p.contract['operational_budget']
    while committed is None:
        compatible=p.compatible(used,ones)
        assert compatible, 'The observed state is impossible under the public corruption limit'
        value,kind,choice=p.solve(used,ones)
        assert spent+value<=p.contract['operational_budget']
        entry={'observations':dict(observations),'compatible_worlds':compatible,'spent_operational_cost':spent,'guaranteed_remaining_cost':value,'next_kind':kind,'next_choice':choice}
        trace.append(entry)
        if kind=='probe':
            assert choice not in observations
            output=call(i,'probe_'+choice)
            assert output['experiment']==choice and output['outcome'] in (0,1)
            observations[choice]=output['outcome']
            used|=1<<q_index[choice]
            ones|=output['outcome']<<q_index[choice]
            spent+=q_by_id[choice]['cost']
        elif kind=='action':
            assert set(compatible)<=set(actions[choice]['success_worlds'])
            output=call(i,'commit_'+choice)
            assert output['committed'] is True and output['action']==choice
            committed=choice
            spent+=actions[choice]['cost']
        else:
            raise RuntimeError('No safe continuation exists')
    compatible=p.compatible(used,ones)
    assert compatible and set(compatible)<=set(actions[committed]['success_worlds'])
    assert spent<=p.contract['operational_budget']
    exclusions=[]
    for world in p.worlds:
        if world not in actions[committed]['success_worlds']:
            conflicts=[q for q,outcome in observations.items() if q_by_id[q]['responses'][world]!=outcome]
            assert len(conflicts)>=p.k+1
            exclusions.append({'world':world,'conflicts':conflicts})
    all_records=records(i)
    fill={'problem_sha256':p.contract['problem_sha256'],'action':committed,'exclusions':exclusions}
    submission={'fill':fill,'confidence':1.0,'abstain':False,'evidence':[r['output']['event_id'] for r in all_records if 'event_id' in r['output']]}
    prepared={'episode':i,'episode_id':json.loads((WORK/f'pilot-{i}-public.json').read_text())['episode_id'],'observations':observations,'compatible_worlds':compatible,'action':committed,'operational_cost':spent,'operational_budget':p.contract['operational_budget'],'setup_read_cost':1,'public_cost_used':all_records[-1]['output']['cost_used'],'minimax_initial_operational_cost':root[0],'submission':submission,'trace':trace}
    (WORK/f'pilot-{i}-prepared.json').write_text(json.dumps(prepared,indent=2))
    return {key:value for key,value in prepared.items() if key not in ('submission','trace')} | {'exclusions':exclusions}

if __name__=='__main__':
    with ThreadPoolExecutor(max_workers=6) as pool:
        summaries=list(pool.map(prepare,range(1,7)))
    (WORK/'prepared-summary.json').write_text(json.dumps(summaries,indent=2))
    for summary in summaries:
        print(json.dumps(summary))
