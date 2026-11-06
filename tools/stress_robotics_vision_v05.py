#!/usr/bin/env python3
"""Matched-contract scripted robot controls and sensor-path interventions.

The evaluator may inspect truth to verify expected transitions. Controllers
receive only public data and Session responses. These are not model scores.
"""
from __future__ import annotations
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from causalfill.domains.robotics_vision import RoboticsVisionTask
from causalfill.robotics_vision_policy import solve_robotics_vision
from causalfill.runner import source_fingerprint,write_json
from causalfill.session import Session,verify_trace
from causalfill.types import canonical,digest
from causalfill.vision import encode_png,image_envelope

POLICIES = ("adaptive","fixed","fixed_minimal","query_free","robust","conditioning","conditioning_grip")


def check_ledger(trace,spec,details):
    elapsed=energy=wear=0
    for event in trace:
        name=event["tool"];args=event["arguments"];response=event["response"]
        if "error" in response:return False
        action=None
        if name=="robot_move_camera":action=spec["actions"]["move_camera"]
        elif name=="robot_capture":action=spec["actions"]["capture"]
        elif name=="robot_probe":action=spec["actions"]["probe_"+args["force"]]
        elif name=="robot_execute":
            key="detour_slow" if args["route"]=="detour" else "primary_"+args["mode"]
            action=spec["actions"][key]
        if action is not None:
            elapsed+=action["time"];energy+=action["energy"];wear+=action.get("wear",0)
            r=response["resources"]
            if (r["elapsed"],r["energy_used"],r["wear"])!=(elapsed,energy,wear):return False
    return (details["elapsed"],details["energy_used"],details["wear"])==(elapsed,energy,wear)


def run(seed,split,difficulty,twin,policy,intervention="intact"):
    task=RoboticsVisionTask(seed,split,difficulty,twin)
    spec=json.loads(task.files["/scene/robotics_vision.json"])
    contract_hash=digest({"public":task.public(),"files":task.files})
    query=task.query
    replacement=None
    if intervention=="blank":
        replacement=image_envelope(encode_png(192,192,bytes([235,239,244])*(192*192)))
    elif intervention=="paired_swap":
        replacement=RoboticsVisionTask(seed,split,difficulty,1-twin).image("inspection")
    def instrumented(name,args):
        response=query(name,args)
        if name=="robot_capture" and replacement is not None:
            response["image"]=replacement
        elif name=="robot_probe" and intervention=="probe_low_interval":
            # Deliberate in-simulator sensor fault: the physical wear still occurs.
            response["friction_interval"]=[0.1,0.13]
        return response
    task.query=instrumented
    session=Session(task)
    error=None
    try:
        fill=solve_robotics_vision(session.public(),session.call,mode=policy)
        session.call("submit",{"fill":fill,"confidence":float(fill.get("delivered",False)),
            "abstain":False,"evidence":[event["event_id"] for event in session.trace]})
    except (ValueError,RuntimeError) as exc:
        error=str(exc)
        session.finish_failure("scripted_policy_error")
        # Keep failed regressions reportable without upgrading their verdict.
        session.result["verdict"]["details"].update(task.evaluate({"delivered":False}).details)
    details=session.result["verdict"]["details"]
    row={**session.result,"seed":seed,"twin":twin,"policy":policy,
        "intervention":intervention,"public_contract_sha256":contract_hash,
        "trace_integrity":verify_trace(session.trace),
        "ledger_replay":check_ledger(session.trace,spec,details) if error is None else False,
        "policy_error":error,"profile":task.profile,"contact_profile":task.contact_profile,
        "initial_friction":task._initial_friction,"open_route":task._open_route,
        "canonical_response_bytes":sum(len(canonical(e["response"]).encode()) for e in session.trace),
        "png_bytes":sum(len(__import__('base64').b64decode(e["response"]["image"]["png_base64"]))
                        for e in session.trace if "image" in e["response"])}
    return row,session.trace,session.public()


def summarize(rows):
    pairs=defaultdict(list)
    for r in rows:pairs[(r["seed"],r["split"],r["difficulty"])].append(r)
    n=len(rows)
    details=[r["verdict"]["details"] for r in rows]
    return {"episodes":n,"successes":sum(r["success"] for r in rows),
        "complete_pairs":len(pairs),"pair_successes":sum(len(p)==2 and all(r["success"] for r in p) for p in pairs.values()),
        "collisions":sum(d["collision"] for d in details),"slips":sum(d["slip"] for d in details),
        "stalls":sum(d["stalled"] for d in details),
        "deadline_failures":sum(d["deadline_exceeded"] for d in details),
        "energy_failures":sum(d["energy_exceeded"] for d in details),
        "mean_tool_cost":sum(r["tool_cost"] for r in rows)/n,
        "mean_observation_cost":sum(d["observation_cost"] for d in details)/n,
        "mean_sensing_cost_including_camera_move":sum(d["sensing_cost"] for d in details)/n,
        "mean_simulated_time":sum(d["elapsed"] for d in details)/n,
        "mean_wear":sum(d["wear"] for d in details)/n,
        "png_bytes":sum(r["png_bytes"] for r in rows),
        "serialized_response_bytes":sum(r["canonical_response_bytes"] for r in rows)}


def expected(row):
    p=row["policy"];condition=row["intervention"]
    relaxed=row["profile"]=="relaxed"
    if condition=="intact":
        if p in ("adaptive","fixed","fixed_minimal"):return True
        if p=="robust":return relaxed
        if p=="query_free":return row["open_route"]=="upper" and row["initial_friction"]*9.81>=3
        if p=="conditioning":return relaxed or row["contact_profile"]=="conditionable"
        if p=="conditioning_grip":return max(0.1,row["initial_friction"]-0.24)<=0.45
    if condition=="blank":return relaxed
    if condition=="paired_swap":return relaxed or row["twin_kind"]=="surface_friction"
    if condition=="probe_low_interval":
        if p=="adaptive":return relaxed or max(0.1,row["initial_friction"]-0.12)<=0.45
        if p=="conditioning_grip":return max(0.1,row["initial_friction"]-0.24)<=0.45
    raise ValueError("unmodeled expected control")


def refine_summary(directory):
    """Recompute descriptive strata from existing records; execute no episodes.

    Preserve the original run summary and the exact executed harness. This is
    an explicit reporting refinement, not a rerun or a changed result.
    """
    path=directory/"summary.json"
    report=json.loads(path.read_text())
    raw=(directory/"records.jsonl").read_bytes()
    if hashlib.sha256(raw).hexdigest()!=report["records_sha256"]:
        raise ValueError("retained records changed")
    if report["source_fingerprint"]!=source_fingerprint():
        raise ValueError("core source changed since episode execution")
    initial=directory/"summary-initial.json"
    if not initial.exists():initial.write_bytes(path.read_bytes())
    records=[json.loads(line) for line in raw.decode().splitlines()]
    report["physical_ledgers_checked"]=report.pop("independent_ledgers_checked",len(records))
    report["interventions_by_profile"]={}
    report["interventions_by_contact"]={}
    for key in report["interventions"]:
        policy,condition=key.split(":")
        rows=[r for r in records if r["policy"]==policy and r["intervention"]==condition]
        report["interventions_by_profile"][key]={p:summarize([r for r in rows if r["profile"]==p]) for p in sorted({r["profile"] for r in rows})}
        report["interventions_by_contact"][key]={p:summarize([r for r in rows if r["contact_profile"]==p]) for p in sorted({r["contact_profile"] for r in rows})}
    report["policies_by_contact"]={p:{c:summarize([r for r in records if r["policy"]==p and r["intervention"]=="intact" and r["contact_profile"]==c])
        for c in ("conditionable","resistant")} for p in POLICIES}
    report["comparison_description"]=(f"Seven scripted controls each receive the same tools and cap over {report['policies']['adaptive']['episodes']} episodes. "
        "The default twelve-seed protocol covers every joint deadline/contact profile: two thirds strict and one third relaxed, with equal contact-profile counts. "
        "Tool budget: 30. Simulated deadlines: 10 strict, 26 relaxed.")
    report["action_table"]["rows"][-1][-1]="A valid action commits once; delivery requires a successful route and mode within the public resource limits."
    clarification="Relaxed reference episodes skip both sensors and are unexposed controls in the sensor interventions. Strict-profile results isolate episodes that actually receive the altered observation."
    if clarification not in report["findings"]:report["findings"].append(clarification)
    snapshot=directory/"harness-executed.py"
    report["reporting_refinement"]={"episodes_rerun":False,"raw_records_unchanged":True,
        "initial_summary_sha256":hashlib.sha256(initial.read_bytes()).hexdigest(),
        "executed_harness_sha256":hashlib.sha256(snapshot.read_bytes()).hexdigest() if snapshot.exists() else None,
        "current_report_builder_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "command":f"python tools/stress_robotics_vision_v05.py --output {directory} --summarize-existing",
        "changes":["Precise public-profile proportions and execution wording","Physical-ledger label","Deadline/contact intervention strata"]}
    write_json(path,report)
    print(json.dumps({"passed":report["passed"],"records":len(records),"raw_records_unchanged":True,"summary":str(path)},indent=2))
    return 0 if report["passed"] else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--seeds",type=int,default=12)
    parser.add_argument("--seed-start",type=int,default=60000)
    parser.add_argument("--summarize-existing",action="store_true",help="Recompute reporting strata from retained source-bound records without executing episodes.")
    args=parser.parse_args()
    if args.summarize_existing:return refine_summary(args.output)
    if args.output.exists() or args.seeds<1 or args.seeds>1000:parser.error("fresh output and 1..1000 seeds required")
    args.output.mkdir(parents=True)
    started=time.monotonic();before=source_fingerprint()
    records=[];failures=[];stored=set()
    conditions=[(p,"intact") for p in POLICIES]+[("adaptive","blank"),("adaptive","paired_swap"),
        ("adaptive","probe_low_interval"),("conditioning_grip","probe_low_interval")]
    for policy,intervention in conditions:
        for split in ("train","dev","transfer"):
            for difficulty in (1,2,3):
                for seed in range(args.seed_start,args.seed_start+args.seeds):
                    for twin in (0,1):
                        row,trace,public=run(seed,split,difficulty,twin,policy,intervention)
                        records.append(row)
                        if row["success"]!=expected(row):
                            failures.append({"kind":"unexpected_outcome","seed":seed,"split":split,
                                "difficulty":difficulty,"twin":twin,"policy":policy,"intervention":intervention})
                        if not (row["trace_integrity"] and row["ledger_replay"] and row["invalid_calls"]==0 and row["policy_error"] is None):
                            failures.append({"kind":"protocol_or_ledger","episode":row["episode_id"]})
                        key=(policy,intervention,row["profile"],row["contact_profile"],row["twin_kind"])
                        if key not in stored:
                            stored.add(key)
                            write_json(args.output/"traces"/("-".join(key)+".json"),
                                {"public":public,"record":row,"events":trace})
        print(f"robotics controls {policy}/{intervention}: completed",flush=True)
    # A shared public contract is checked across all controller/intervention runs.
    contract_hashes=defaultdict(set)
    for r in records:contract_hashes[(r["seed"],r["split"],r["difficulty"],r["twin"])].add(r["public_contract_sha256"])
    if any(len(v)!=1 for v in contract_hashes.values()):failures.append({"kind":"unmatched_contracts"})
    controls={p:summarize([r for r in records if r["policy"]==p and r["intervention"]=="intact"]) for p in POLICIES}
    by_profile={p:{profile:summarize([r for r in records if r["policy"]==p and r["intervention"]=="intact" and r["profile"]==profile])
        for profile in ("strict","relaxed") if any(r["profile"]==profile for r in records)} for p in POLICIES}
    interventions={p+":"+condition:summarize([r for r in records if r["policy"]==p and r["intervention"]==condition])
        for p,condition in conditions if condition!="intact"}
    after=source_fingerprint()
    if before!=after:failures.append({"kind":"source_changed_during_run"})
    path=args.output/"records.jsonl"
    path.write_text("".join(canonical(r)+"\n" for r in records))
    labels={"adaptive":"Budget-aware reference","fixed":"Fixed with overview","fixed_minimal":"Fixed minimal sensing",
        "query_free":"Query-free upper/roll","robust":"Robust slow detour","conditioning":"Common-mode conditioning",
        "conditioning_grip":"Firm then fixed grip"}
    table=[]
    for policy,stats in controls.items():
        table.append([labels[policy],f"{stats['successes']}/{stats['episodes']}",
            f"{stats['pair_successes']}/{stats['complete_pairs']}",
            f"{stats['mean_tool_cost']:.1f}",f"{stats['mean_observation_cost']:.1f}",f"{stats['mean_simulated_time']:.1f}"])
    report={"schema":"causalfill.robotics-controls.v05","passed":not failures,
        "source_fingerprint":before,"source_stable":before==after,
        "records":len(records),"controller_records":sum(v["episodes"] for v in controls.values()),
        "intervention_records":sum(v["episodes"] for v in interventions.values()),
        "stored_full_traces":len(stored),"all_trace_chains_checked":True,"physical_ledgers_checked":len(records),
        "records_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
        "policies":controls,"by_profile":by_profile,"interventions":interventions,
        "failures":failures,"elapsed_seconds":round(time.monotonic()-started,3),
        "command":f"python tools/stress_robotics_vision_v05.py --seeds {args.seeds} --seed-start {args.seed_start} --output {args.output}",
        "report_description":[
            "An opaque roof hides which of two transport lanes is open. Moving to inspection exposes an actual PNG gate observation. Three visible fiducials establish the affine camera map. Camera changes, captures and probes consume simulated time, separately from synthetic tool cost.",
            "A contact probe changes the surface through wear before returning a bounded friction interval. Gentle and firm contact therefore alter the later action conditions. Execution is terminal: a closed lane collides, insufficient traction slips, excessive fixture resistance stalls, and time or energy overruns prevent delivery."],
        "action_table":{"headers":["Operation","Tool / time","Consequence"],"rows":[
            ["Move camera","2 / 1","Change station; use 1 energy."],["Capture pixels","3 / 1","Fixed-pattern bounded noise; repeats are correlated."],
            ["Probe contact","4 / 2","Gentle adds 1 wear; firm adds 2. Reading refers to the changed surface."],
            ["Execute","2 / 5-18","A valid action commits once; completion requires successful delivery within the public limits."]]},
        "comparison_description":f"Seven scripted controls were each run on {controls['adaptive']['episodes']} episodes under the same tools and caps. The default twelve-seed protocol covers every joint deadline/contact profile: two thirds strict and one third relaxed, with equal contact-profile counts. The tool budget is 30. Strict deadlines permit 10 simulated time units; relaxed deadlines permit 26.",
        "comparison_table":{"headers":["Scripted policy","Success","Both twins","Tool cost","Obs. cost","Time"],"rows":table},
        "findings":[
            "The minimal fixed sequence is a strong comparator: inspection plus a gentle probe suffices. The budget-aware reference skips sensing when the public deadline permits a slow detour. Its sensing schedule depends on that known contract; this is not a demonstrated observation-contingent sensing advantage.",
            "Firm contact moves both initial regimes into the grip-safe range in the conditionable profile. The resistant profile preserves a case where this common-mode guarantee fails. The fixed-grip variant still succeeds on favorable individual states; complete-pair success exposes its missing guarantee.",
            "Pixel blanking and paired swaps test the route-selection sensor path. A deliberately false low-friction interval disrupts measurement-based handling, while firm-then-fixed-grip ignores that reading by construction. All physical wear and tool costs remain charged during these interventions."],
        "limits":["Scripted controls, not learned policies or physical experiments.",
            "The exact finite decision-certificate module is a separate declared abstraction; no renderer-to-certificate refinement is proved.",
            "A fixed public policy comparison is not a global optimality certificate.",
            "The recovery metric in this operational family mirrors achieved delivery; no separate latent estimate is graded.",
            "Annotated traces and all hidden fields in these records are evaluator-only."]}
    write_json(args.output/"summary.json",report)
    print(json.dumps({k:report[k] for k in ("passed","records","controller_records","intervention_records","policies","interventions","failures","elapsed_seconds")},indent=2))
    return 0 if report["passed"] else 1


if __name__=="__main__":raise SystemExit(main())
