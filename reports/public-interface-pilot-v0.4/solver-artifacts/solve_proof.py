import json,time
from pathlib import Path
W=Path('/workspace/scratch/addf9cb6769c/pilot_solver_work')
log=[json.loads(s) for s in (W/'public_log_6.jsonl').read_text().splitlines()]
statement=json.loads(next(x['response']['content'] for x in log if x['tool']=='read_file' and x['arguments']['path']=='/formal/statement.json'))
original=[frozenset(c) for c in statement['clauses']]+[frozenset([-statement['goal']])]
clauses=list(original); ninitial=len(original); proof=[]
known={c:i for i,c in enumerate(clauses)}
stats={'nodes':0,'leaves':0,'max_depth':0}
def resolve(a,b,p):
 ca,cb=clauses[a],clauses[b]
 if p in ca and -p in cb: r=(ca-{p})|(cb-{-p})
 elif -p in ca and p in cb: r=(ca-{-p})|(cb-{p})
 else: raise AssertionError(('invalid pivot',a,b,p))
 assert not any(-x in r for x in r)
 if r in known: return known[r]
 idx=len(clauses); clauses.append(r); proof.append([a,b,p]); known[r]=idx
 return idx
def false_clause(idx,assignment):
 return all(assignment.get(abs(lit))==(lit<0) for lit in clauses[idx])
def strip_units(idx,units):
 for lit,reason in reversed(units):
  if -lit in clauses[idx]: idx=resolve(idx,reason,abs(lit))
 return idx
large=[i for i,c in enumerate(original) if len(c)>3]
def search(incoming,depth=0):
 stats['nodes']+=1; stats['max_depth']=max(stats['max_depth'],depth)
 assignment=dict(incoming); units=[]
 while True:
  changed=False; residual=[]
  for i,c in enumerate(original):
   if any(assignment.get(abs(lit))==(lit>0) for lit in c): continue
   available=[lit for lit in c if abs(lit) not in assignment]
   if not available:
    stats['leaves']+=1
    idx=strip_units(i,units); assert false_clause(idx,incoming)
    return idx
   if len(available)==1:
    lit=available[0]; assignment[abs(lit)]=lit>0; units.append((lit,i)); changed=True
   else: residual.append((i,available))
  if not changed: break
 if not residual: raise RuntimeError('SAT under negated goal')
 choices=[(len(av),i,av) for i,av in residual if i in large]
 if not choices: choices=[(len(av),i,av) for i,av in residual]
 _,_,av=min(choices,key=lambda t:(t[0],t[1]))
 lit=min(av,key=lambda l:abs(l)); var=abs(lit)
 a1=dict(assignment); a1[var]=lit>0
 left=search(a1,depth+1)
 assert false_clause(left,a1)
 if -lit not in clauses[left]:
  idx=strip_units(left,units); assert false_clause(idx,incoming); return idx
 a2=dict(assignment); a2[var]=lit<0
 right=search(a2,depth+1)
 assert false_clause(right,a2)
 if lit not in clauses[right]: idx=right
 else: idx=resolve(left,right,var)
 idx=strip_units(idx,units); assert false_clause(idx,incoming)
 return idx
start=time.monotonic(); final=search({}); elapsed=time.monotonic()-start
assert not clauses[final]
print('Search complete',stats,'raw steps',len(proof),'seconds',elapsed,flush=True)
# Keep exactly the ancestor sub-DAG needed for the empty clause and renumber.
needed=set()
def mark(idx):
 if idx<ninitial or idx in needed:return
 needed.add(idx)
 a,b,p=proof[idx-ninitial]; mark(a);mark(b)
mark(final)
remap={i:i for i in range(ninitial)}; compact=[]
for idx in sorted(needed):
 a,b,p=proof[idx-ninitial]
 remap[idx]=ninitial+len(compact);compact.append([remap[a],remap[b],p])
# Independently replay the compact proof from the immutable public clauses.
replay=[set(c) for c in original]
for k,(a,b,p) in enumerate(compact):
 assert 0<=a<len(replay) and 0<=b<len(replay) and 1<=p<=statement['nvars']
 ca,cb=replay[a],replay[b]
 if p in ca and -p in cb:r=(ca-{p})|(cb-{-p})
 else:
  assert -p in ca and p in cb
  r=(ca-{-p})|(cb-{p})
 replay.append(r)
assert not replay[-1]
model=[False]*statement['nvars']
assert all(any(model[abs(l)-1]==(l>0) for l in c) for c in statement['clauses'])
fill={'statement_sha256':statement['statement_sha256'],'proof_steps':compact,'consistency_model':model}
body={'tool':'submit','arguments':{'fill':fill,'confidence':0.99,'abstain':False,'evidence':['e0001','e0002']}}
size=len(json.dumps(body).encode());literals=sum(map(len,replay))
print('Certificate',len(compact),'steps;',literals,'literal entries;',size,'request bytes; final empty:',not replay[-1],'; original consistency model verified',flush=True)
(W/'proof_solution.json').write_text(json.dumps(fill,separators=(',',':')))
(W/'proof_stats.json').write_text(json.dumps({'stats':stats,'raw_steps':len(proof),'compact_steps':len(compact),'literal_entries':literals,'request_bytes':size,'seconds':elapsed},indent=2))
assert len(compact)<=12000 and literals<=500000 and size<128*1024
