"""Evaluator commands. A scored agent should see only HTTP/stdio, not this package."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from .registry import factories, make_task
from .runner import run_episode,run_suite,write_json
from .session import Session,verify_trace
from .protocol_json import MAX_BODY_BYTES, _strict_json


def task_options(p):
    p.add_argument("--family",choices=list(factories()),default="words")
    p.add_argument("--seed",type=int,default=0)
    p.add_argument("--split",choices=("train","dev","transfer"),default="dev")
    p.add_argument("--difficulty",type=int,choices=(1,2,3),default=2)
    p.add_argument("--twin",type=int,choices=(0,1),default=0)
    p.add_argument("--mask-strategy",choices=("causal","random"),default="causal")
    p.add_argument("--no-skill",action="store_true")
    p.add_argument("--no-tools",action="store_true")


def main(argv=None):
    parser=argparse.ArgumentParser(description="CausalFill-Bench research prototype; scripted controls are not AI scores.")
    sub=parser.add_subparsers(dest="command",required=True)
    sub.add_parser("list",help="list task families")
    demo=sub.add_parser("demo",help="run a scripted development control")
    task_options(demo)
    demo.add_argument("--policy",choices=("evidence","oracle","blind","abstain"),default="evidence")
    demo.add_argument("--output",type=Path)
    suite=sub.add_parser("suite",help="run paired development cases and store traces/metrics")
    suite.add_argument("--output",type=Path,required=True)
    suite.add_argument("--families",nargs="+",choices=list(factories()),default=list(factories()))
    suite.add_argument("--splits",nargs="+",choices=("train","dev","transfer"),default=["dev"])
    suite.add_argument("--difficulties",nargs="+",type=int,choices=(1,2,3),default=[2])
    suite.add_argument("--count",type=int,default=3,help="number of evaluator seeds per cell")
    suite.add_argument("--seed-start",type=int,default=0)
    suite.add_argument("--policies",nargs="+",choices=("evidence","oracle","blind","abstain"),default=["evidence"])
    suite.add_argument("--no-twins",action="store_true")
    suite.add_argument("--no-skill",action="store_true")
    suite.add_argument("--no-tools",action="store_true")
    suite.add_argument("--no-traces",action="store_true")
    suite.add_argument("--mask-strategy",choices=("causal","random"),default="causal")
    server=sub.add_parser("serve",help="serve one episode; keep host and results isolated from agent")
    task_options(server)
    server.add_argument("--host",default="127.0.0.1")
    server.add_argument("--port",type=int,default=8787)
    server.add_argument("--output",type=Path,default=Path("private-runs/server"))
    stdio=sub.add_parser("stdio",help="JSON-lines public tool interface; result saved separately")
    task_options(stdio)
    stdio.add_argument("--output",type=Path,default=Path("private-runs/stdio"))
    verify=sub.add_parser("verify-trace",help="check hash chain consistency, not authenticity")
    verify.add_argument("path",type=Path)
    score=sub.add_parser("summarize",help="summarize trusted evaluator records")
    score.add_argument("path",type=Path)
    args=parser.parse_args(argv)
    try:
        if args.command=="list":
            print(json.dumps({"families":list(factories()),"status":"research prototype"},indent=2));return
        if args.command=="demo":
            rec,trace,public=run_episode(args.family,args.seed,args.split,args.difficulty,args.twin,args.policy,
                not args.no_skill,not args.no_tools,args.mask_strategy)
            if args.output: write_json(args.output,{"result":rec,"public":public,"trace":trace})
            print(json.dumps(rec,indent=2));return
        if args.command=="suite":
            if not 1<=args.count<=10000: raise ValueError("count must be 1..10000")
            manifest,summary=run_suite(args.output,args.families,args.splits,args.difficulties,
                list(range(args.seed_start,args.seed_start+args.count)),args.policies,not args.no_twins,
                not args.no_skill,not args.no_tools,args.mask_strategy,not args.no_traces)
            print(json.dumps({"manifest":manifest,"summary":summary},indent=2));return
        if args.command=="verify-trace":
            obj=json.loads(args.path.read_text())
            events=obj.get("events",obj.get("trace",[])) if isinstance(obj,dict) else obj
            passed=bool(events) and verify_trace(events)
            print(json.dumps({"hash_chain_consistent":passed,"authenticated":False}))
            if not passed: raise SystemExit(1)
            return
        if args.command=="summarize":
            from .metrics import summarize
            rows=[json.loads(x) for x in args.path.read_text().splitlines() if x.strip()]
            print(json.dumps(summarize(rows),indent=2));return
        task=make_task(args.family,args.seed,args.split,args.difficulty,args.twin,args.mask_strategy)
        session=Session(task,skill=not args.no_skill,tools_enabled=not args.no_tools)
        if args.command=="serve":
            from .server import serve
            token=os.environ.get("CFB_TOKEN","")
            if len(token)<24: raise ValueError("set CFB_TOKEN to a random secret of at least 24 characters")
            print(f"Evaluator listening on {args.host}:{args.port}; final results saved privately.",file=sys.stderr)
            serve(session,args.host,args.port,token=token,output_dir=args.output)
        else:
            print(json.dumps({"episode":session.public()}),flush=True)
            while not session.closed:
                line=sys.stdin.buffer.readline(MAX_BODY_BYTES+1)
                if not line: session.finish_failure("agent_disconnected");break
                if len(line)>MAX_BODY_BYTES:
                    session.finish_failure("request_too_large");break
                try:
                    request=_strict_json(line)
                    if not isinstance(request,dict) or set(request)!={"tool","arguments"}:
                        raise ValueError("request needs tool and arguments")
                    result=session.call(request["tool"],request["arguments"])
                except (ValueError,TypeError,RecursionError):
                    result=session.call(None,{})
                print(json.dumps(result,allow_nan=False),flush=True)
            write_json(args.output/(session.id+".result.json"),session.result)
            write_json(args.output/(session.id+".trace.json"),session.trace)
    except (ValueError,OSError) as exc:
        parser.exit(2,f"error: {exc}\n")


if __name__=="__main__": main()
