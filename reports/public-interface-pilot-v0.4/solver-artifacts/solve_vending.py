import json
from pathlib import Path
from public_client import call
W=Path('/workspace/scratch/addf9cb6769c/pilot_solver_work')
for i in [1,2,3]:
    log=[json.loads(s) for s in (W/f'public_log_{i}.jsonl').read_text().splitlines()]
    quotes=[x['response']['quote'] for x in log if x['tool']=='quote']
    q1,q2=quotes
    fill={'standard_lead_days':q1['arrival_day']-q1['order_day'],'fixed_shipping_cents':2*q1['shipping_cents']-q2['shipping_cents'],'case_shipping_cents':q2['shipping_cents']-q1['shipping_cents'],'receipt_event':'delivery'}
    samples=[x['response'] for x in log if x['tool']=='assay']
    demands=[]
    for stage in range(4):
        r=samples[0] if stage==0 and samples else call(i,'assay')
        state=json.loads(r['observation'])
        assert state['stage']==stage and state['phase']=='open' and state['sample']['kind']=='assay'
        d=state['sample']['value']; assert d in (0,1)
        demands.append(d)
        r=call(i,'order',{'product':['tea','cocoa'][d],'supplier':'standard'})
        state=json.loads(r['observation'])
        assert state['available_units']==0 and state['pending_units']==4 and state['breach'] is None
        r=call(i,'settle')
        state=json.loads(r['observation'])
        assert state['breach'] is None and state['units_sold']==4*(stage+1)
    assert state['cash_cents']>=state['cash_target_cents'] and state['stage']==4
    (W/f'vending_solution_{i}.json').write_text(json.dumps({'fill':fill,'final_state':state,'demands':demands},indent=2))
    call(i,'ledger',{'last_n':100})
    print('SOLUTION',i,json.dumps({'fill':fill,'demands':demands,'cash':state['cash_cents']}),flush=True)
