"""Reproducible development runs and trusted evaluator result storage."""
from __future__ import annotations

import json
import platform
import hashlib
from pathlib import Path
from datetime import datetime, timezone

from . import __version__
from .policies import evidence_reference
from .registry import make_task
from .session import Session,verify_trace
from .types import digest,canonical


def source_fingerprint():
    root=Path(__file__).resolve().parent
    h=hashlib.sha256()
    for path in sorted(root.rglob("*.py")):
        h.update(path.relative_to(root).as_posix().encode()+b"\0"+path.read_bytes()+b"\0")
    return h.hexdigest()


def write_json(path,value):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+".tmp")
    temporary.write_text(json.dumps(value,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    temporary.replace(path)


def run_episode(kind,seed,split,difficulty,twin=0,policy="evidence",skill=True,tools=True,mask_strategy="causal"):
    task=make_task(kind,seed,split,difficulty,twin,mask_strategy)
    session=Session(task,skill=skill,tools_enabled=tools)
    try:
        if policy=="evidence":
            fill,abstain=evidence_reference(session.public(),session.call)
        elif policy=="oracle":
            for name,args in task.reference_actions():
                response=session.call(name,args)
                if "error" in response: raise ValueError(response["error"])
            fill,abstain=(task.reference_answer(),False) if task.answerable else ({},True)
        elif policy=="blind": fill,abstain={},False
        elif policy=="abstain": fill,abstain={},True
        else: raise ValueError("unknown policy")
        session.call("submit",{"fill":fill,"confidence":1.0 if policy!="blind" else 0.0,
            "abstain":abstain,"evidence":[x["event_id"] for x in session.trace][-200:]})
    except (ValueError,RuntimeError) as exc:
        session.finish_failure("policy_error: "+str(exc)[:240])
    if session.result is None: session.finish_failure("no_valid_submission")
    record={**session.result,"policy":policy,"kind":kind,"seed":seed,"twin":twin,
        "pair_id":digest([kind,seed,split,difficulty,policy,skill,tools,mask_strategy])[:20],
        "mask_strategy":mask_strategy,
        "config_id":digest([__version__,policy,skill,tools,mask_strategy])[:16],
        "trace_integrity":verify_trace(session.trace),
        "canonical_request_bytes":sum(len(canonical(x["arguments"]).encode()) for x in session.trace),
        "canonical_response_bytes":sum(len(canonical(x["response"]).encode()) for x in session.trace)}
    return record,session.trace,session.public()


def run_suite(output,families,splits,difficulties,seeds,policies=("evidence",),twins=True,
              skill=True,tools=True,mask_strategy="causal",save_traces=True):
    from .metrics import summarize
    output=Path(output)
    if output.exists() and any(output.iterdir()):
        raise ValueError("output directory must be new or empty; do not overwrite an evaluation")
    output.mkdir(parents=True,exist_ok=True)
    records=[]
    for policy in policies:
        for kind in families:
            for split in splits:
                for difficulty in difficulties:
                    for seed in seeds:
                        for twin in (0,1) if twins else (0,):
                            rec,trace,public=run_episode(kind,seed,split,difficulty,twin,policy,skill,tools,mask_strategy)
                            records.append(rec)
                            if save_traces:
                                write_json(output/"traces"/(rec["episode_id"]+".json"),
                                    {"public":public,"events":trace})
    records_path=output/"records.jsonl"
    with records_path.open("w",encoding="utf-8") as f:
        for rec in records: f.write(json.dumps(rec,sort_keys=True,allow_nan=False)+"\n")
    manifest={"benchmark":"CausalFill-Bench","version":__version__,"status":"development-only",
        "created_utc":datetime.now(timezone.utc).isoformat(),"python":platform.python_version(),
        "platform":platform.platform(),"families":list(families),"splits":list(splits),
        "difficulties":list(difficulties),"seeds":list(seeds),"policies":list(policies),"twins":twins,
        "skill":skill,"tools":tools,"mask_strategy":mask_strategy,"records":len(records),
        "records_sha256":digest(records),"source_sha256":source_fingerprint(),
        "note":"Scripted controls; not frontier-model scores. Seeds are evaluator-only metadata."}
    write_json(output/"manifest.json",manifest)
    summary=summarize(records)
    write_json(output/"summary.json",summary)
    return manifest,summary
