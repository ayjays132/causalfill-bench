"""Exact finite minimax search derived solely from the public binary tables.

A state is a pair (observed-probe mask, observed-one mask). A world remains
possible exactly when it disagrees with at most k distinct observed probes.
Terminal choices must succeed in every possible world. Probe choices minimize
probe cost plus the worst remaining cost over nonempty legal response branches.
"""
import json
from functools import lru_cache
from client import WORK

class Planner:
    def __init__(self, episode_number):
        self.number=episode_number
        self.contract=json.loads(json.loads((WORK/f'pilot-{episode_number}-formal-response.json').read_text())['content'])
        self.problem=self.contract['problem']
        self.worlds=tuple(self.problem['worlds'])
        self.experiments=self.problem['experiments']
        self.actions=self.problem['actions']
        self.k=self.problem['max_corruptions']
        self.codes=tuple(sum(q['responses'][w]<<j for j,q in enumerate(self.experiments)) for w in self.worlds)
        self.action_masks=tuple(sum(1<<j for j,w in enumerate(self.worlds) if w in a['success_worlds']) for a in self.actions)
        self.full_world_mask=(1<<len(self.worlds))-1
        self.full_probe_mask=(1<<len(self.experiments))-1
        self.memo={}

    @lru_cache(None)
    def possible(self,used,ones):
        return sum(1<<j for j,code in enumerate(self.codes) if ((code^ones)&used).bit_count()<=self.k)

    @lru_cache(None)
    def solve(self,used=0,ones=0):
        possible=self.possible(used,ones)
        if not possible:
            return (0, 'impossible', None)
        best=(float('inf'), 'unresolved', None)
        for a,mask in zip(self.actions,self.action_masks):
            if possible & ~mask == 0 and a['cost'] < best[0]:
                best=(a['cost'],'action',a['id'])
        for j,q in enumerate(self.experiments):
            bit=1<<j
            if used&bit or q['cost']>=best[0]:
                continue
            branches=[]
            for response in (0,1):
                next_ones=ones|(response<<j)
                if self.possible(used|bit,next_ones):
                    branches.append(self.solve(used|bit,next_ones)[0])
            worst=q['cost']+max(branches)
            if worst<best[0]:
                best=(worst,'probe',q['id'])
        return best

    def compatible(self,used,ones):
        possible=self.possible(used,ones)
        return [w for j,w in enumerate(self.worlds) if possible&(1<<j)]

if __name__=='__main__':
    results=[]
    for i in range(1,7):
        p=Planner(i)
        best=p.solve()
        result={'episode':i,'minimax_operational_cost':best[0], 'root_choice':best[1:], 'operational_budget':p.contract['operational_budget'], 'cumulative_cached_states':p.solve.cache_info().currsize}
        results.append(result)
        print(json.dumps(result),flush=True)
    (WORK/'planning-summary.json').write_text(json.dumps(results,indent=2))
