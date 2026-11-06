import json
from pathlib import Path
from fractions import Fraction as Q
from public_client import call
W=Path('/workspace/scratch/addf9cb6769c/pilot_solver_work')
log=[json.loads(s) for s in (W/'public_log_4.jsonl').read_text().splitlines()]
workspace=json.loads(next(x['response']['content'] for x in log if x['tool']=='read_file' and x['arguments']['path']=='/scene/workspace.json'))
target_id=workspace['target_id']; coords={}; material=None
for entry in log:
 if entry['tool']!='camera': continue
 r=entry['response']; target=next((o for o in r['objects'] if o['id']==target_id),None)
 if target is None: continue
 origin,u,v=r['fiducials']; ax,bx=r['projection_axes']
 b=list(map(lambda x:Q(str(x)),origin['image']))
 a00=(Q(str(u['image'][0]))-b[0])/Q(str(u['world'][ax]))
 a10=(Q(str(u['image'][1]))-b[1])/Q(str(u['world'][ax]))
 a01=(Q(str(v['image'][0]))-b[0])/Q(str(v['world'][bx]))
 a11=(Q(str(v['image'][1]))-b[1])/Q(str(v['world'][bx]))
 t0=Q(str(target['image'][0]))-b[0]; t1=Q(str(target['image'][1]))-b[1]
 det=a00*a11-a01*a10
 values=[(a11*t0-a01*t1)/det,(-a10*t0+a00*t1)/det]
 for axis,value in zip([ax,bx],values):
  assert axis not in coords or coords[axis]==value
  coords[axis]=value
 material=target['material']
 print('Calibrated view',r['view'],'axes',[ax,bx],'coordinates',list(map(str,values)))
assert len(coords)==3 and material=='steel'
fill={'target_world_position':[float(coords[i]) for i in range(3)],'safe_waypoints':[[7,1,1]],'grasp_precondition':{'gripper':'open','force_limit_n':1.0}}
(W/'geometry_solution.json').write_text(json.dumps(fill,indent=2))
print('Recovered fill',json.dumps(fill))
call(4,'probe_path',{k:fill[k] for k in ['target_world_position','safe_waypoints']})
