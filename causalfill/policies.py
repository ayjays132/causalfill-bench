"""Task-aware scripted controls that see only a public task and a tool callback.

These are deliberately strong constructive references, NOT general-purpose AI
models. Importing a solver helper does not give it a Task or private state.
"""
from __future__ import annotations

import itertools
import json
import re

from .domains.grid import diagnostic_grid, infer_program
from .domains.latent import basis_probe_plan, recover_affine_operator
from .domains.robotics import solve_from_observations
from .domains.words import gate
from .vending_policy import solve_vending


def evidence_reference(public, call):
    def use(name,args):
        result=call(name,args)
        if "error" in result: raise ValueError(result["error"])
        return result

    def read(path):
        return use("read_file",{"path":path})["content"]

    family=public["family"]
    if family=="words":
        grammar=json.loads(read("/docs/grammar.json"))
        text=read("/skill/routing.txt")
        if "/docs/sensor-notice.txt" in public["files"]:
            notice=read("/docs/sensor-notice.txt")
            if "never the route name" in notice:
                return {},True
        n=grammar["input_count"]
        observations=[]
        for bits in itertools.product((False,True),repeat=n):
            bits=list(bits)
            observations.append((bits,use("experiment",{"inputs":bits})["route"]))
        match=re.fullmatch(r"IF (.+)\(inputs\) == (.+) THEN send (.+) ELSE send HOLD.\nComment: (.+).",text)
        if match is None: raise ValueError("unknown routing template")
        names=("gate_word","required_state","route_word","comment_word")
        known={k:v for k,v in zip(names,match.groups()) if not v.startswith("<MASK:")}
        for g,r,route in itertools.product(grammar["gate_words"],("true","false"),grammar["route_vocabulary"]):
            config=dict(gate_word=g,required_state=r,route_word=route,comment_word=grammar["comment_word"])
            if any(config[k]!=v for k,v in known.items()): continue
            if all((route if gate(g,bits)==(r=="true") else "HOLD")==out for bits,out in observations):
                return {k:config[k] for k in public["slots"]},False
        raise ValueError("observations inconsistent with public grammar")
    if family=="workflow":
        text=read("/docs/current.txt")
        answer="balance-amount*scale-fee"
        if "lower bound" in text: answer=f"max({answer},reserve)"
        if "upper bound" in text: answer=f"min({answer},ceiling)"
        use("run_candidate",{"expression":answer})
        return {"expression":answer},False
    if family=="grid":
        text=read("/docs/grid-dsl.txt")
        match=re.search(r"This episode uses the (train|dev|transfer) grammar",text)
        if not match: raise ValueError("missing grammar")
        g=diagnostic_grid()
        out=use("transform",{"grid":g})["output"]
        return {"program":infer_program(match.group(1),[{"input":g,"output":out}])},False
    if family in ("robotics", "robotics_barrier"):
        world=json.loads(read("/scene/workspace.json"))
        cameras=[use("camera",{"view":v}) for v in ("xy","xz","yz")]
        lidar=use("lidar",{})
        if family=="robotics_barrier":
            from .domains.robotics_barrier import solve_robotics_barrier_from_observations
            return solve_robotics_barrier_from_observations(world,cameras,lidar),False
        return solve_from_observations(world,cameras,lidar),False
    if family in ("latent","latent_sparse"):
        template=json.loads(read("/workspace/operator.masked.json"))
        n,p=template["dimension"],template["modulus"]
        if family=="latent_sparse":
            from .domains.latent import sparse_probe_plan,recover_sparse_operator
            plan=sparse_probe_plan(n)
            obs=[use("probe",{"vector":v})["output"] for v in plan]
            return recover_sparse_operator(obs,n,p),False
        obs=[use("probe",{"vector":v})["output"] for v in basis_probe_plan(n)]
        return recover_affine_operator(obs,n,p),False
    if family=="vending": return solve_vending(public,use),False
    if family=="vending_adaptive":
        from .domains.vending_adaptive import solve_vending_adaptive
        return solve_vending_adaptive(public,use)
    if family=="proof":
        from .proof_search import solve_proof
        return solve_proof(public,use),False
    if family=="diagnosis":
        from .decision_certificates import solve_diagnosis
        return solve_diagnosis(public,use),False
    if family=="visual":
        from .domains.visual import solve_visual
        return solve_visual(public,use),False
    if family=="robotics_vision":
        from .robotics_vision_policy import solve_robotics_vision
        return solve_robotics_vision(public,use),False
    if family=="robust_sensing":
        from .domains.robust_sensing import solve_robust_sensing
        return solve_robust_sensing(public,use),False
    raise ValueError("no reference for family")

