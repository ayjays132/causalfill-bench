"""Self-contained evaluator run review. This is not an agent-facing endpoint.

The page uses the same configuration-separated summaries as the CLI, includes
no remote assets, and renders record strings as text rather than HTML. A hash
chain proves internal consistency only; it does not authenticate its author.
"""
from __future__ import annotations

import base64
import hashlib
import html
import json
from pathlib import Path
import re

from . import __version__
from .metrics import _canonical, _identity, summarize
from .session import verify_trace
from .types import digest


def _load_json(text: str):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def reject(value):
        raise ValueError("nonfinite JSON value: " + value)

    return json.loads(text, object_pairs_hook=pairs, parse_constant=reject)


def load_run(source: Path, check_traces: bool = False) -> dict:
    """Validate records and optional manifest/trace bindings before rendering."""
    source = Path(source)
    records_path = source / "records.jsonl" if source.is_dir() else source
    records = []
    for number, line in enumerate(records_path.read_text(encoding="utf-8").splitlines(), 1):
        if line.strip():
            try:
                records.append(_load_json(line))
            except (ValueError, RecursionError) as exc:
                raise ValueError(f"invalid record on line {number}: {exc}") from exc
    summary = summarize(records)
    manifest_path = records_path.parent / "manifest.json"
    manifest = _load_json(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else None
    if manifest is not None:
        if not isinstance(manifest, dict):
            raise ValueError("manifest must be an object")
        if (type(manifest.get("records")) is not int or manifest["records"] != len(records)
                or manifest.get("records_sha256") != digest(records)):
            raise ValueError("manifest record count or records digest does not match")
        if manifest.get("scoring_version") is not None and any(
            record.get("scoring_version") != manifest["scoring_version"] for record in records
        ):
            raise ValueError("manifest scoring version does not match records")
    trace_count = 0
    episode_ids = set()
    for record in records:
        if check_traces:
            episode_id = record.get("episode_id")
            if not isinstance(episode_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", episode_id):
                raise ValueError("trace verification needs a safe episode_id in every record")
            if episode_id in episode_ids:
                raise ValueError("duplicate episode_id makes trace binding ambiguous")
            episode_ids.add(episode_id)
            trace_path = records_path.parent / "traces" / (episode_id + ".json")
            if (trace_path.is_symlink() or not trace_path.is_file()
                    or not trace_path.resolve().is_relative_to(records_path.parent.resolve())):
                raise ValueError(f"missing or linked trace for episode {episode_id}")
            trace = _load_json(trace_path.read_text(encoding="utf-8"))
            events = trace.get("events") if isinstance(trace, dict) else None
            if (not isinstance(events, list) or not events or not all(isinstance(event, dict) for event in events)
                    or not verify_trace(events)
                    or events[-1].get("hash") != record.get("trace_hash")
                    or not isinstance(trace.get("public"), dict)
                    or trace["public"].get("episode_id") != episode_id):
                raise ValueError(f"trace chain or record binding failed for episode {episode_id}")
            trace_count += 1
    groups = {group["group_id"]: [] for group in summary["groups"]}
    for record in records:
        group_id = hashlib.sha256(_canonical(_identity(record)).encode()).hexdigest()[:16]
        groups[group_id].append(record)
    return {
        "review_schema": "causalfill.review.v1", "viewer_version": __version__,
        "source_name": records_path.parent.name, "record_count": len(records),
        "records_file_sha256": hashlib.sha256(records_path.read_bytes()).hexdigest(),
        "manifest": manifest, "manifest_binding_checked": manifest is not None,
        "trace_chains_checked": trace_count, "trace_check_requested": check_traces,
        "summary": summary, "records_by_group": groups,
    }


_CSS = r"""
:root{color-scheme:light;--ink:#172b43;--muted:#526078;--paper:#f6f4ed;--blue:#2455d9;--teal:#126b52;--amber:#825000;--line:#d8dfeb;--white:#fff}
*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.6 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
header{background:#102037;color:#fff;padding:36px max(24px,calc((100vw - 1320px)/2)) 32px}header .eyebrow{color:#a8c2ff;letter-spacing:.16em;text-transform:uppercase;font-size:11px;font-weight:750}h1{font-size:clamp(32px,4vw,48px);line-height:1.12;letter-spacing:-.04em;margin:12px 0}header p{max-width:830px;color:#d0dbea;margin:0}.brand{display:flex;align-items:center;gap:12px}.mark{width:25px;height:25px;border:4px solid #89aaff;border-right-color:transparent;position:relative}.mark:after{content:"";position:absolute;width:10px;height:10px;background:#fff;right:-9px;top:-8px}main{max-width:1368px;margin:auto;padding:24px}h2{font-size:20px;letter-spacing:-.02em;margin:0 0 14px}h3{font-size:15px;margin:0 0 8px}p{margin:0 0 12px}a{color:var(--blue)}.notice{border-left:4px solid var(--amber);padding:13px 18px;background:#fff8e9;border-radius:0 8px 8px 0;margin-bottom:24px}.panel{background:#fff;border:1px solid var(--line);border-radius:14px;padding:24px;margin-bottom:24px}.row{display:flex;gap:18px;align-items:end;flex-wrap:wrap}.grow{flex:1;min-width:240px}label{display:block;font-size:12px;font-weight:700;letter-spacing:.02em;margin-bottom:6px}select,input,button{font:inherit;color:var(--ink);border:1px solid #b7c3d6;border-radius:7px;background:#fff;padding:9px 11px}select,input{width:100%;min-width:0}button{cursor:pointer;font-size:13px;font-weight:650}button:hover{background:#edf2ff;border-color:var(--blue)}button:disabled{opacity:.45;cursor:default}:focus-visible{outline:3px solid #2455d9;outline-offset:3px}.small{font-size:12px;color:var(--muted)}.mono{font-family:ui-monospace,"DejaVu Sans Mono",monospace;overflow-wrap:anywhere}.identity{margin-top:14px;overflow-wrap:anywhere}.cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin:20px 0}.card{padding:18px;border:1px solid var(--line);border-radius:10px;background:#fafbfe}.card .value{font-size:30px;line-height:1.2;font-weight:750;letter-spacing:-.03em;margin:6px 0}.card.primary{background:#edf2ff;border-color:#b8cafd}.card .caption{font-size:12px;color:var(--muted)}.two{display:grid;grid-template-columns:1fr 1fr;gap:24px}.bars{display:grid;gap:9px}.bar-row{display:grid;grid-template-columns:minmax(110px,1.1fr) 2fr 48px;align-items:center;gap:10px;font-size:12px}.track{height:9px;border-radius:6px;background:#e9eef8;overflow:hidden}.fill{height:100%;background:var(--blue)}ul{padding-left:20px;margin:10px 0}.filters{display:grid;grid-template-columns:1fr 1fr 1fr 1.4fr;gap:12px;margin-bottom:18px}.table-wrap{overflow:auto;max-height:620px;border:1px solid var(--line);border-radius:8px}table{width:100%;border-collapse:collapse;text-align:left;font-size:13px;white-space:nowrap}th{background:#edf2f9;font-size:11px;letter-spacing:.04em;text-transform:uppercase;position:sticky;top:0;z-index:1}th,td{padding:11px 13px;border-bottom:1px solid #e4e9f1}tbody tr:hover{background:#f6f8fd}.tag{display:inline-block;padding:2px 8px;border-radius:5px;background:#edf2f9;font-size:11px;font-weight:750}.pass{background:#e2f3eb;color:#12533f}.fail{background:#fff1df;color:#784800}.paging{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:16px;flex-wrap:wrap}.paging .buttons{display:flex;gap:9px}.empty{padding:28px;text-align:center;color:var(--muted)}details>summary{cursor:pointer;font-weight:700}pre{margin:14px 0 0;background:#f2f5fa;padding:18px;border-radius:8px;white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.65 ui-monospace,monospace;max-height:420px;overflow:auto}.binding{display:grid;grid-template-columns:1fr 1fr;gap:12px}.binding>div{border:1px solid var(--line);padding:14px;border-radius:8px}.eyebrow{font-weight:700;font-size:11px;text-transform:uppercase;letter-spacing:.1em}.detail{border:2px solid #aec1f4;scroll-margin-top:20px}.detail-head{display:flex;justify-content:space-between;gap:20px}.hidden{display:none}footer{color:var(--muted);font-size:12px;text-align:center;padding:0 24px 32px}@media(max-width:850px){.cards{grid-template-columns:repeat(2,minmax(0,1fr))}.two,.binding{grid-template-columns:1fr}.filters{grid-template-columns:1fr 1fr}}@media(max-width:500px){main{padding:14px}.panel{padding:18px}.filters{grid-template-columns:1fr}.cards{gap:8px}.card{padding:12px}.card .value{font-size:26px}.bar-row{grid-template-columns:115px 1fr 42px}.grow{min-width:0;width:100%}header{padding:28px 20px}}
"""

_BODY = """
<header><div class="brand"><span class="mark" aria-hidden="true"></span><span class="eyebrow">CausalFill · Evaluator workspace</span></div><h1>Evidence into action.</h1><p>Review strict success, observed outcomes, resource use, and the evidence behind each episode. Every configuration keeps its own score.</p></header>
<main><div class="notice"><strong>Evaluator-only review.</strong> This file contains private result details and may contain seeds. Scripted controls are development evidence. A consistent trace is not an authenticated model evaluation.</div>
<section class="panel" aria-labelledby="configuration-title"><div class="row"><div class="grow"><h2 id="configuration-title">Run configuration</h2><label for="group">Select a separately scored configuration</label><select id="group"></select></div><div class="small" id="run-label"></div></div><p class="small mono identity" id="identity"></p><div id="cards" class="cards"></div><div class="two"><div><h3>Strict success by task configuration</h3><p class="small">Answerable episodes only. Ambiguity controls have a separate abstention result.</p><div class="bars" id="bars"></div></div><div><h3>How to read this score</h3><div id="interpretation"></div></div></div></section>
<section class="panel" aria-labelledby="episodes-title"><h2 id="episodes-title">Episode explorer</h2><p class="small">Filters change the table below. The configuration score above always uses the complete selected group.</p><div class="filters"><div><label for="family">Task configuration</label><select id="family"></select></div><div><label for="split">Split</label><select id="split"></select></div><div><label for="status">Result</label><select id="status"><option value="all">All results</option><option value="pass">Strict success</option><option value="fail">Strict failure</option><option value="gap">Outcome without strict success</option><option value="abstain">Abstained</option></select></div><div><label for="search">Find episode or failure detail</label><input id="search" type="search" placeholder="Episode ID or text"></div></div><div class="table-wrap"><table><thead><tr><th>Task / split</th><th>Difficulty / twin</th><th>Strict result</th><th>Outcome</th><th>Tool cost</th><th>Calls / invalid</th><th>Inspect</th></tr></thead><tbody id="episodes"></tbody></table></div><div id="empty" class="empty hidden">No episodes match these filters.</div><div class="paging"><span id="page-label" class="small" aria-live="polite"></span><div class="buttons"><button id="previous" type="button">Previous</button><button id="next" type="button">Next</button></div></div></section>
<section id="detail" class="panel detail hidden" aria-labelledby="detail-title"><div class="detail-head"><div><h2 id="detail-title">Episode details</h2><p id="detail-label" class="mono small"></p></div><button id="close-detail" type="button">Close</button></div><p class="small">The full evaluator record is shown below. Outcome and safety are task-specific diagnostics; strict success also enforces the task's submission requirements.</p><pre id="record"></pre></section>
<section class="panel" aria-labelledby="provenance-title"><h2 id="provenance-title">Provenance and scope</h2><div id="binding" class="binding"></div><p class="small" style="margin-top:16px">This review recomputes summaries from the input records. It does not replay tasks, authenticate a provider, run Lean, or establish that the solver was isolated. Trace verification checks chains and their final record bindings.</p><details><summary>Run manifest and summary methodology</summary><pre id="provenance"></pre></details></section></main>
<footer>Created with CausalFill-Bench · Project concept and direction: Phillip A. Holland Jr. · Original code and visual identity: MIT</footer>
"""

_JS = r"""
"use strict";
const data=JSON.parse(document.getElementById("run-data").textContent), $=id=>document.getElementById(id);
const el=(tag,text,cls)=>{const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(cls)node.className=cls;return node;};
const percent=n=>n===null||n===undefined?"N/A":(n*100).toFixed(1)+"%";
const number=n=>n===null||n===undefined?"N/A":Number(n).toLocaleString(undefined,{maximumFractionDigits:2});
const groups=data.summary.groups;let current=null,rows=[],visible=[],page=0;const size=50;
function option(select,value,label){const item=el("option",label);item.value=value;select.append(item);}
function card(label,value,caption,primary=false){const box=el("div",undefined,"card"+(primary?" primary":""));box.append(el("div",label,"eyebrow"),el("div",value,"value"),el("div",caption,"caption"));$("cards").append(box);}
function changeGroup(){current=groups[Number($("group").value)];rows=current?data.records_by_group[current.group_id]:[];$("cards").replaceChildren();$("bars").replaceChildren();$("interpretation").replaceChildren();$("identity").textContent=current?JSON.stringify(current.identity):"No records supplied.";$("detail").classList.add("hidden");
 if(current){const a=current.aggregate,means=a.metric_means;card("Strict success",percent(current.headline.value),"Macro average across "+current.headline.answerable_families+" answerable configurations",true);card("Actual outcome",percent(means.outcome.mean),"Task-defined outcome · "+means.outcome.n+" recorded values");card("Joint twin success",percent(current.paired.joint_solvable_success_rate),current.paired.solvable_complete_pairs+" complete answerable pairs");card("Mean tool cost",number(means.tool_cost.mean),"Synthetic cost units · "+a.episodes+" episodes");
 for(const [name,value] of Object.entries(current.per_family)){const row=el("div",undefined,"bar-row"),track=el("div",undefined,"track"),fill=el("div",undefined,"fill");fill.style.width=((value.solvable_success_rate||0)*100)+"%";track.append(fill);row.append(el("span",name),track,el("span",percent(value.solvable_success_rate)));$("bars").append(row);}
 const details=[a.solvable_successes+" / "+a.answerable_episodes+" answerable episodes passed all strict checks.",a.unanswerable_correct_abstentions+" / "+a.unanswerable_episodes+" unanswerable controls were correctly declined.","Outcome is a recorded diagnostic, not a substitute for certificate acceptance. Its mean includes all recorded values in this group.","Structural clusters: "+current.uncertainty.cluster_count+". 95% macro interval: "+(current.headline.ci95?current.headline.ci95.map(percent).join(" to "):"withheld ("+current.uncertainty.ci_unavailable_reason+")")+".",...current.notes];const ul=el("ul");for(const text of details)ul.append(el("li",text,"small"));$("interpretation").append(ul);}
 for(const field of ["family","split"]){const select=$(field);select.replaceChildren();option(select,"all","All "+(field==="family"?"task configurations":"splits"));for(const value of [...new Set(rows.map(r=>r[field]||"unspecified"))].sort())option(select,value,value);}
 $("status").value="all";$("search").value="";filter();}
function filter(){const family=$("family").value,split=$("split").value,status=$("status").value,query=$("search").value.trim().toLowerCase();visible=rows.filter(r=>(family==="all"||(r.family||"unspecified")===family)&&(split==="all"||(r.split||"unspecified")===split)&&(status==="all"||(status==="pass"&&r.success)||(status==="fail"&&!r.success)||(status==="gap"&&r.outcome>0&&!r.success)||(status==="abstain"&&r.abstained))&&(!query||JSON.stringify(r).toLowerCase().includes(query)));page=0;renderRows();}
function inspect(record){$("detail").classList.remove("hidden");$("detail-label").textContent=record.episode_id||"Episode without identifier";$("record").textContent=JSON.stringify(record,null,2);$("detail").scrollIntoView({behavior:"smooth",block:"start"});}
function renderRows(){$("episodes").replaceChildren();for(const record of visible.slice(page*size,(page+1)*size)){const tr=el("tr"),name=el("td");name.append(el("strong",record.family),el("div",record.split||"unspecified","small"));const outcome=el("td",number(record.outcome)),status=el("td");status.append(el("span",record.success?"PASS":record.abstained?"ABSTAIN":"FAIL","tag "+(record.success?"pass":"fail")));const actions=el("td"),button=el("button","Details");button.type="button";button.setAttribute("aria-label","Inspect episode "+(record.episode_id||record.family));button.addEventListener("click",()=>inspect(record));actions.append(button);tr.append(name,el("td",(record.difficulty??"—")+" / "+(record.twin??"—")),status,outcome,el("td",number(record.tool_cost)),el("td",number(record.tool_calls)+" / "+number(record.invalid_calls)),actions);$("episodes").append(tr);}
 $("empty").classList.toggle("hidden",visible.length>0);$("previous").disabled=page===0;$("next").disabled=(page+1)*size>=visible.length;$("page-label").textContent=visible.length?(page*size+1)+"–"+Math.min((page+1)*size,visible.length)+" of "+visible.length+" matching episodes":"0 matching episodes";}
for(let i=0;i<groups.length;i++){const id=groups[i].identity;option($("group"),String(i),(id.policy||"unspecified")+" · "+(id.model||"no model ID")+" · "+id.config_id+" · "+(id.scoring_version||"legacy-unspecified"));}
$("group").addEventListener("change",changeGroup);for(const id of ["family","split","status"])$(id).addEventListener("change",filter);$("search").addEventListener("input",filter);$("previous").addEventListener("click",()=>{page--;renderRows();});$("next").addEventListener("click",()=>{page++;renderRows();});$("close-detail").addEventListener("click",()=>$("detail").classList.add("hidden"));
$("run-label").textContent=data.source_name+" · "+data.record_count+" episodes · "+groups.length+" configurations";
const bindings=[["Record manifest",data.manifest_binding_checked?"Count and canonical records digest match the supplied manifest.":"No manifest supplied; record provenance was not bound."],["Trace consistency",data.trace_check_requested?data.trace_chains_checked+" chains and final record bindings checked. Authorship is not authenticated.":"Not checked in this review. Regenerate with --verify-traces to inspect supplied trace files."],["Benchmark source",data.manifest?.source_sha256||"No source fingerprint supplied."],["Records file SHA-256",data.records_file_sha256]];
for(const [label,value] of bindings){const item=el("div");item.append(el("h3",label),el("p",value,"small mono"));$("binding").append(item);}$("provenance").textContent=JSON.stringify({viewer_version:data.viewer_version,manifest:data.manifest,methodology:data.summary.methodology},null,2);changeGroup();
"""


def render_review(data: dict) -> str:
    """Render JSON as inert script data, escaping HTML-significant characters."""
    payload = json.dumps(data, ensure_ascii=True, separators=(",", ":"), allow_nan=False)
    payload = payload.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    script_hash = base64.b64encode(hashlib.sha256(_JS.encode()).digest()).decode()
    # Inline style attributes are used only for numeric bars and fixed layout.
    csp = f"default-src 'none'; script-src 'sha256-{script_hash}'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"
    title = html.escape("CausalFill run review · " + data["source_name"])
    return ("<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">"
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<meta http-equiv="Content-Security-Policy" content="' + html.escape(csp, quote=True) + '">'
            "<title>" + title + "</title><style>" + _CSS + "</style></head><body>" + _BODY
            + '<script id="run-data" type="application/json">' + payload + "</script>"
            + "<script>" + _JS + "</script></body></html>\n")


def write_review(source: Path, output: Path, check_traces: bool = False) -> dict:
    output = Path(output)
    if output.suffix.lower() not in (".html", ".htm"):
        raise ValueError("review output must end in .html or .htm")
    if output.exists():
        raise ValueError("review output must be a new file")
    data = load_run(source, check_traces)
    document = render_review(data)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as handle:
        handle.write(document)
    return {"output": str(output), "records": data["record_count"],
            "groups": data["summary"]["group_count"],
            "manifest_binding_checked": data["manifest_binding_checked"],
            "trace_chains_checked": data["trace_chains_checked"], "authenticated": False}
