import json
from functools import lru_cache
from pathlib import Path
from public_client import call
W=Path('/workspace/scratch/addf9cb6769c/pilot_solver_work')
log=[json.loads(s) for s in (W/'public_log_5.jsonl').read_text().splitlines()]
data=json.loads(next(x['response']['content'] for x in log if x['tool']=='read_file'))
rows=data['responses']; n=len(rows); m=len(rows[0])
ones=[sum((1<<w) for w in range(n) if rows[w][e]) for e in range(m)]
@lru_cache(None)
def plan(mask,depth):
 if mask.bit_count()==1: return {'world':mask.bit_length()-1}
 if depth==0 or mask.bit_count()>2**depth: return None
 options=[]
 for e in range(m):
  b=mask&ones[e]; a=mask^b
  if a and b and max(a.bit_count(),b.bit_count())<=2**(depth-1): options.append((max(a.bit_count(),b.bit_count()),e,a,b))
 for _,e,a,b in sorted(options):
  zero=plan(a,depth-1)
  if zero is None: continue
  one=plan(b,depth-1)
  if one is not None: return {'experiment':e,'0':zero,'1':one}
 return None
p=plan((1<<n)-1,5); assert p is not None
(W/'diagnosis_plan.json').write_text(json.dumps(p,indent=2))
print('Decision tree computed; root',p['experiment'],'cache',str(plan.cache_info()))
call(5,'experiment',{'id':p['experiment']})
