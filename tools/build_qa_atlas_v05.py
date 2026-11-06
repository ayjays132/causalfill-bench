#!/usr/bin/env python3
"""Build an offline evaluator-only observation atlas from frozen QA manifests.

The HTML uses relative local PNG paths and inlined CSS/JavaScript; it fetches
nothing from the network. Answers are hidden in the initial UI, but remain in
its source. This report must never be supplied to a scored solver.

Usage:
  python tools/build_qa_atlas_v05.py
  python tools/build_qa_atlas_v05.py --robotics reports/v05/robotics-qa/manifest.json

Additional manifests may use images/frames/captures arrays containing a file
path relative to the manifest, a SHA256 digest, and optional display metadata.
The image bytes and manifest hashes are checked before constructing the report.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import struct
import sys
from urllib.parse import quote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def local_reference(base, value):
    if type(value) is not str or not value or urlsplit(value).scheme or '\x00' in value:
        raise ValueError('atlas image reference must be a local path')
    path = (base / value).resolve()
    if not path.is_relative_to(ROOT) or not path.is_file() or path.suffix.lower() != '.png':
        raise ValueError(f'image must be an existing PNG inside the source tree: {value}')
    return path


def rel_url(path, output):
    relative = os.path.relpath(path, output.parent).replace(os.sep,'/')
    return quote(relative,safe='/._-')


def normalize_manifest(path, label, output):
    data = path.read_bytes()
    model = json.loads(data)
    rows = next((model[key] for key in ('images','frames','captures') if isinstance(model.get(key),list)), None)
    if rows is None:
        raise ValueError(f'{path.name}: missing images/frames/captures list')
    result = []
    seen = set()
    for index, row in enumerate(rows):
        if type(row) is not dict:
            raise ValueError(f'{path.name}: malformed image record {index}')
        file = next((row[key] for key in ('file','path','png_file','png_path') if isinstance(row.get(key),str)), None)
        if file is None:
            raise ValueError(f'{path.name}: missing image file in record {index}')
        image = local_reference(path.parent, file)
        if image in seen:
            raise ValueError(f'{path.name}: duplicate image reference')
        seen.add(image)
        actual_hash = sha256(image)
        expected_hash = row.get('sha256',row.get('png_sha256'))
        if expected_hash is not None and actual_hash != expected_hash:
            raise ValueError(f'{path.name}: image digest mismatch for {file}')
        header=image.read_bytes()[:24]
        if len(header)!=24 or header[:8]!=b'\x89PNG\r\n\x1a\n' or header[12:16]!=b'IHDR':
            raise ValueError(f'{path.name}: invalid PNG header for {file}')
        width,height=struct.unpack('>II',header[16:24])
        kind=str(row.get('kind',row.get('category','benchmark_capture')))
        diagnostic=('diagnostic' in kind or 'fixture' in kind)
        split=str(row.get('split','diagnostic' if diagnostic else 'unspecified'))
        view=str(row.get('view',row.get('visibility',row.get('camera','unspecified'))))
        difficulty=str(row.get('difficulty','ungraded'))
        seed=row.get('seed')
        twin=row.get('twin')
        noise=row.get('noise_bound',row.get('rgb_noise_bound'))
        visible=row.get('target_visible_fraction',row.get('visible_fraction'))
        pixel_ref=row.get('pixel_reference',{})
        known_flags={key:value for key,value in row.items() if key.endswith('_check') and type(value) is bool}
        for key in ('independent_pillow_decode_match','decode_match','passed'):
            if type(row.get(key)) is bool:known_flags[key]=row[key]
        failures=[key for key,value in known_flags.items() if not value]
        qa_state='fail' if failures else ('pass' if known_flags else 'unreported')
        answer=row.get('private_expected_completion',row.get('expected_completion',row.get('private_expected',row.get('oracle_answer'))))
        if answer is None and diagnostic:
            answer={key:row[key] for key in ('visible_centroid_world','centroid_bias_world','target_rgb','expected_visible_fraction') if key in row}
        if not answer:answer=None
        details={key:row[key] for key in ('maximum_observed_noise','target_visible_pixels','target_full_inspection_pixels',
                  'maximum_calibration_coefficient_error','centroid_bias_world','offscreen_component_touches_frame',
                  'target_visible_expected','scope') if key in row}
        if pixel_ref:details['pixel_reference']=pixel_ref
        summary=[]
        if noise is not None:summary.append(f'RGB noise ±{noise}')
        if type(visible) in (int,float):summary.append(f'{visible:.0%} target visible')
        if pixel_ref.get('returned_completion') is False:summary.append('pose withheld')
        elif pixel_ref.get('strict_success') is True:summary.append('scripted reference passed')
        title=f'{split.upper()} · d{difficulty}' if difficulty!='ungraded' else f'{split.upper()} · diagnostic'
        if seed is not None:title+=f' · s{seed}'
        if twin is not None:title+=f' · t{twin}'
        if 'orientation' in row:title+=f' · o{row["orientation"]}'
        result.append({'dataset':label,'file':rel_url(image,output),'filename':image.name,'sha256':actual_hash,
                       'width':width,'height':height,'kind':kind,'diagnostic':diagnostic,'split':split,
                       'view':view,'difficulty':difficulty,'seed':seed,'twin':twin,'title':title,
                       'summary':' · '.join(summary),'qa_state':qa_state,'flags':known_flags,'failures':failures,
                       'details':details,'answer':answer,'manifest_index':index,
                       'search_text':' '.join([label,image.name,split,view,difficulty,str(seed),str(twin),kind]).lower()})
    expected=model.get('counts',{}).get('actual_observation_pngs')
    if expected is not None and expected!=len(result):
        raise ValueError(f'{path.name}: manifest image count mismatch')
    source={'dataset':label,'file':rel_url(path,output),'filename':path.name,'sha256':hashlib.sha256(data).hexdigest(),
            'images':len(result),'schema':model.get('schema','unspecified'),'passed':model.get('passed'),
            'counts':model.get('counts',{}),'generated_utc':model.get('generated_utc'),
            'source_hashes':model.get('source_sha256',{})}
    return result,source


def safe_json(value):
    return json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False).replace('&','\\u0026').replace('<','\\u003c').replace('>','\\u003e').replace('\u2028','\\u2028').replace('\u2029','\\u2029')


STYLE = r'''
:root{color-scheme:light;--ink:#15243a;--muted:#52657b;--line:#d8e1eb;--paper:#f4f7fa;--blue:#18559b;--teal:#166f69;--amber:#805519;--red:#a02937;--white:#fff}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--paper);color:var(--ink);font-family:ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;line-height:1.5}button,input,select{font:inherit}button,a,input,select,summary{outline-offset:4px}button,summary{cursor:pointer}button{border:1px solid var(--line);border-radius:9px;padding:8px 13px;background:#fff;color:var(--ink)}button:hover{border-color:#6b91bd;background:#eff5fc}a{color:var(--blue)}header{background:#13243c;color:#fff;padding:34px max(24px,calc((100vw - 1440px)/2));border-bottom:4px solid #45b8a6}.eyebrow{margin:0 0 12px;color:#a4c6e8;font-size:12px;font-weight:750;letter-spacing:.15em;text-transform:uppercase}h1{font-size:clamp(30px,4vw,48px);line-height:1.15;letter-spacing:-.035em;margin:0 0 14px}header .intro{max-width:850px;color:#c5d5e7;font-size:16px;margin:0 0 22px}.private-notice{border:1px solid #b28a4a;background:#fff5df;color:#604114;padding:12px 16px;border-radius:10px;font-size:14px;max-width:1100px}.private-notice strong{color:#4f330a}main{max-width:1490px;padding:26px 24px 70px;margin:auto}.metrics{display:grid;grid-template-columns:repeat(4,minmax(140px,1fr));gap:14px;margin-bottom:24px}.metric{background:#fff;border:1px solid var(--line);border-radius:12px;padding:18px 20px}.metric b{font-size:30px;display:block;line-height:1.2}.metric span{font-size:13px;color:var(--muted)}.metric small{display:block;color:var(--muted);font-size:11px;margin-top:5px}.controls{background:#fff;border:1px solid var(--line);border-radius:14px;padding:18px;margin-bottom:18px;box-shadow:0 3px 12px #142e4b06}.filter-grid{display:grid;grid-template-columns:repeat(5,minmax(110px,1fr)) minmax(170px,1.3fr);gap:12px}.control{display:flex;flex-direction:column;gap:5px}.control>span{font-size:11px;text-transform:uppercase;letter-spacing:.07em;font-weight:700;color:var(--muted)}select,input[type=search]{border:1px solid #bccbda;border-radius:8px;background:#fff;padding:8px 9px;min-width:0;width:100%;color:var(--ink)}.control-row{display:flex;align-items:center;justify-content:space-between;gap:14px;flex-wrap:wrap;margin-top:16px}.answer-toggle{display:flex;align-items:center;gap:9px;color:#704b13;font-size:14px;font-weight:650}.answer-toggle input{width:18px;height:18px;accent-color:#986c24}.result-count{font-size:14px;color:var(--muted)}.result-count strong{color:var(--ink)}.gallery{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px}.frame-card{border:1px solid var(--line);border-radius:13px;background:#fff;overflow:hidden;box-shadow:0 3px 11px #132a4405;content-visibility:auto;contain-intrinsic-size:350px}.frame-card[hidden]{display:none}.card-head{padding:13px 14px 10px;min-height:74px}.card-head h2{font-size:12px;margin:6px 0 0;letter-spacing:.015em;font-weight:750;line-height:1.5}.topline{display:flex;gap:6px;justify-content:space-between;align-items:center}.dataset{font-size:10px;color:var(--muted);letter-spacing:.09em;font-weight:750;text-transform:uppercase}.badge{font-size:10px;font-weight:750;border-radius:99px;padding:2px 7px;background:#edf1f6;color:#4c6077}.badge.pass{background:#e6f5ee;color:#176449}.badge.fail{background:#ffe9ec;color:#962b3a}.image-open{display:flex;width:100%;border:0;border-radius:0;padding:10px;background:#edf2f8;align-items:center;justify-content:center;min-height:250px}.image-open:hover{background:#e3edf8}.image-open img{display:block;max-width:100%;width:auto;height:240px;object-fit:contain;filter:none}.card-body{padding:12px 14px}.view-label{font-size:13px;font-weight:750;margin:0 0 4px}.summary{font-size:11px;color:var(--muted);min-height:34px;margin:0 0 10px}.card-foot{display:flex;justify-content:space-between;gap:8px;align-items:center;font-size:10px;color:#6b7d90}.card-foot code{font-size:10px}.card-foot button{font-size:11px;padding:4px 8px}.private-answer{display:none;background:#fff6e7;border:1px solid #ead3a6;border-radius:8px;padding:10px;margin-top:12px}.show-answers .private-answer{display:block}.private-answer h3{font-size:10px;color:#725018;text-transform:uppercase;letter-spacing:.08em;margin:0 0 7px}.private-answer pre{margin:0;font-size:11px;color:#614310;white-space:pre-wrap;overflow-wrap:anywhere;line-height:1.5}.empty{padding:60px 24px;text-align:center;border:1px dashed #b9c8d7;border-radius:12px;color:var(--muted);grid-column:1/-1}.provenance{margin-top:28px;background:#fff;border:1px solid var(--line);border-radius:12px;padding:18px}.provenance>summary{font-weight:750;font-size:15px}.provenance p{color:var(--muted);font-size:13px}.source-list{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:16px}.source{background:#f4f7fb;border:1px solid #e1e8f1;border-radius:10px;padding:14px}.source h3{font-size:14px;margin:0 0 8px}.source p{margin:6px 0}.hash{font-size:11px;overflow-wrap:anywhere;user-select:all}.limits{font-size:13px;color:var(--muted);max-width:1000px}.footer{margin-top:18px;font-size:11px;color:var(--muted)}dialog{border:1px solid #a5b9d0;border-radius:16px;padding:0;width:min(1180px,94vw);max-height:94vh;background:#fff;color:var(--ink);box-shadow:0 18px 80px #0b1c3f4d}dialog::backdrop{background:#0b1d35b8}.dialog-head{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:17px 20px;border-bottom:1px solid var(--line)}.dialog-head h2{font-size:17px;margin:0}.dialog-head p{font-size:12px;color:var(--muted);margin:4px 0 0}.dialog-grid{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(280px,1fr);min-height:420px;max-height:calc(94vh - 90px)}.inspection-pane{padding:18px;background:#e9eff6;display:flex;flex-direction:column;min-width:0;overflow:auto}.zoom-tools{display:flex;gap:7px;align-items:center;flex-wrap:wrap;margin-bottom:14px}.zoom-tools button{font-size:12px;padding:5px 9px}.zoom-tools label{font-size:12px;display:flex;gap:5px;align-items:center;margin-left:auto}.image-stage{display:flex;align-items:flex-start;justify-content:flex-start;overflow:auto;min-height:300px;padding:10px;border:1px solid #c7d4e3;border-radius:10px;background:#dce5f0}.detail-image{display:block;max-width:none;height:auto;margin:auto;flex:none}.nearest{image-rendering:pixelated}.details-pane{padding:18px 20px;overflow:auto}.details-pane h3{font-size:12px;letter-spacing:.04em;margin:18px 0 8px;text-transform:uppercase}.details-pane h3:first-child{margin-top:0}.detail-facts{font-size:12px;margin:0}.detail-facts dt{color:var(--muted);margin-top:8px}.detail-facts dd{margin:2px 0 0;overflow-wrap:anywhere}.checks{list-style:none;padding:0;margin:0;font-size:12px}.checks li{display:flex;gap:8px;padding:5px 0;border-bottom:1px solid #edf1f5}.check-label{overflow-wrap:anywhere}.check-mark{color:#187154;font-weight:800}.check-mark.fail{color:var(--red)}.detail-json{font-size:11px;line-height:1.5;white-space:pre-wrap;overflow-wrap:anywhere;border-radius:8px;background:#f2f5f9;padding:10px}.noscript{padding:15px;background:#fff2da;border:1px solid #cfb174;border-radius:10px;margin-bottom:15px}
@media(max-width:1180px){.gallery{grid-template-columns:repeat(3,minmax(0,1fr))}.filter-grid{grid-template-columns:repeat(3,minmax(0,1fr))}}@media(max-width:850px){.gallery{grid-template-columns:repeat(2,minmax(0,1fr))}.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.dialog-grid{grid-template-columns:1fr;max-height:none}.inspection-pane{max-height:60vh}.details-pane{max-height:none}.dialog-head{position:sticky;top:0;background:#fff;z-index:1}}@media(max-width:520px){header{padding:27px 18px}main{padding:20px 14px 50px}.gallery{grid-template-columns:1fr}.filter-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.metric{padding:13px}.metric b{font-size:25px}.card-head{min-height:0}.image-open img{height:240px}.dialog-head h2{font-size:14px}.control-row{align-items:flex-start}.result-count{width:100%}}@media print{header{background:#fff;color:#111;border-color:#333}header .intro,.eyebrow{color:#444}.controls,.card-foot button,dialog{display:none}.gallery{grid-template-columns:repeat(3,minmax(0,1fr))}.frame-card{break-inside:avoid;content-visibility:visible}.provenance{break-before:page}.private-notice{background:#fff}.metric b{font-size:22px}main{padding:12px}.image-open{min-height:0}.image-open img{height:170px}.show-answers .private-answer{display:block}}
'''


SCRIPT = r'''
(function(){
'use strict';
function matches(record,filter){
  if(filter.dataset&&record.dataset!==filter.dataset)return false;
  if(filter.split&&record.split!==filter.split)return false;
  if(filter.view&&record.view!==filter.view)return false;
  if(filter.difficulty&&record.difficulty!==filter.difficulty)return false;
  if(filter.scope==='diagnostic'&&!record.diagnostic)return false;
  if(filter.scope==='benchmark'&&record.diagnostic)return false;
  if(filter.search&&!record.search_text.includes(filter.search.toLowerCase().trim()))return false;
  return true;
}
if(typeof module!=='undefined'&&module.exports){module.exports={matches};return;}
const payload=JSON.parse(document.getElementById('atlas-data').textContent);
const records=payload.images;
const cards=Array.from(document.querySelectorAll('.frame-card'));
const fields=['dataset','split','view','difficulty','scope','search'];
let visible=records.map((_,i)=>i),current=-1,returnFocus=null;
const el=id=>document.getElementById(id);
function fillOptions(name,label){
 const values=Array.from(new Set(records.map(r=>r[name]))).sort((a,b)=>a.localeCompare(b,undefined,{numeric:true}));
 for(const value of values){const option=document.createElement('option');option.value=value;option.textContent=value;el(name).appendChild(option);}
}
for(const name of ['dataset','split','view','difficulty'])fillOptions(name);
function getFilter(){return Object.fromEntries(fields.map(name=>[name,el(name).value]));}
function filter(){
 const selected=getFilter();visible=[];
 cards.forEach((card,i)=>{const shown=matches(records[i],selected);card.hidden=!shown;if(shown)visible.push(i);});
 el('shown-count').textContent=visible.length.toLocaleString();
 el('empty').hidden=visible.length>0;
}
for(const name of fields)el(name).addEventListener(name==='search'?'input':'change',filter);
el('reset').addEventListener('click',()=>{for(const name of fields)el(name).value='';filter();});
el('answers').addEventListener('change',()=>{document.body.classList.toggle('show-answers',el('answers').checked);});
function addFact(list,name,value){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=name;dd.textContent=String(value);list.append(dt,dd);}
function inspect(index){
 if(!Number.isInteger(index)||!records[index])return;
 current=index;const r=records[index];
 el('detail-title').textContent=r.title;
 el('detail-subtitle').textContent=r.dataset+' / '+r.view+' / '+r.filename;
 const image=el('detail-image');image.src=r.file;image.alt=r.title+'; '+r.view;image.style.width=(r.width*2)+'px';
 el('zoom-label').textContent='200%';
 const facts=el('detail-facts');facts.replaceChildren();
 for(const pair of [['Dimensions',r.width+' × '+r.height+' RGB pixels'],['Image SHA-256',r.sha256],['Observation file',r.filename],['Record kind',r.kind],['Manifest record',r.manifest_index]])addFact(facts,...pair);
 const checks=el('detail-checks');checks.replaceChildren();
 const entries=Object.entries(r.flags);
 if(!entries.length){const item=document.createElement('li');item.textContent='No per-image check flags reported by this manifest.';checks.appendChild(item);}
 for(const [key,value] of entries){const item=document.createElement('li'),mark=document.createElement('span'),label=document.createElement('span');mark.className='check-mark'+(value?'':' fail');mark.textContent=value?'PASS':'FAIL';label.className='check-label';label.textContent=key.replaceAll('_',' ');item.append(mark,label);checks.appendChild(item);}
 el('detail-json').textContent=JSON.stringify(r.details,null,2);
 el('detail-answer').textContent=r.answer?JSON.stringify(r.answer,null,2):'No expected completion recorded in this manifest.';
 const open=el('open-original');open.href=r.file;open.textContent='Open original '+r.width+' × '+r.height+' PNG';
 if(!el('inspector').open)el('inspector').showModal();
 const at=visible.indexOf(index);el('previous').disabled=at<=0;el('next').disabled=at<0||at>=visible.length-1;
}
document.getElementById('gallery').addEventListener('click',event=>{const button=event.target.closest('[data-inspect]');if(!button)return;returnFocus=button;inspect(Number(button.dataset.inspect));});
el('close-inspector').addEventListener('click',()=>el('inspector').close());
el('inspector').addEventListener('close',()=>{if(returnFocus)returnFocus.focus();});
function step(delta){const at=visible.indexOf(current),next=at+delta;if(at>=0&&next>=0&&next<visible.length)inspect(visible[next]);}
el('previous').addEventListener('click',()=>step(-1));el('next').addEventListener('click',()=>step(1));
el('inspector').addEventListener('keydown',event=>{if(event.key==='ArrowLeft'){event.preventDefault();step(-1);}if(event.key==='ArrowRight'){event.preventDefault();step(1);}});
for(const button of document.querySelectorAll('[data-zoom]'))button.addEventListener('click',()=>{const factor=Number(button.dataset.zoom);el('detail-image').style.width=(records[current].width*factor)+'px';el('zoom-label').textContent=(factor*100)+'%';});
el('nearest').addEventListener('change',()=>el('detail-image').classList.toggle('nearest',el('nearest').checked));
filter();
})();
'''


def build_html(images,sources,output):
    escaped=lambda value:html.escape(str(value),quote=True)
    count=len(images)
    diagnostics=sum(row['diagnostic'] for row in images)
    checks=sum(row['qa_state']=='pass' for row in images)
    failures=sum(row['qa_state']=='fail' for row in images)
    payload={'schema':'causalfill.offline-qa-atlas.v1','generated_utc':datetime.now(timezone.utc).isoformat(),
             'role':'evaluator-only; hidden answers embedded in source','sources':sources,'images':images}
    cards=[]
    for index,row in enumerate(images):
        answer=json.dumps(row['answer'],indent=2) if row['answer'] is not None else 'No expected completion recorded.'
        state_label={'pass':'QA PASS','fail':'QA FAIL','unreported':'QA UNREPORTED'}[row['qa_state']]
        cards.append(f'''<article class="frame-card" data-index="{index}">
<div class="card-head"><div class="topline"><span class="dataset">{escaped(row['dataset'])}</span><span class="badge {row['qa_state']}">{state_label}</span></div><h2>{escaped(row['title'])}</h2></div>
<button class="image-open" type="button" data-inspect="{index}" aria-label="Inspect {escaped(row['title'])}, {escaped(row['view'])}"><img src="{escaped(row['file'])}" width="{row['width']}" height="{row['height']}" loading="lazy" decoding="async" alt="{escaped(row['title'])}; {escaped(row['view'])}"></button>
<div class="card-body"><p class="view-label">{escaped(row['view'])}</p><p class="summary">{escaped(row['summary'])}</p><div class="card-foot"><code title="{row['sha256']}">{row['sha256'][:12]}</code><button type="button" data-inspect="{index}">Inspect image</button></div><div class="private-answer"><h3>Private evaluator annotation</h3><pre>{escaped(answer)}</pre></div></div></article>''')
    sources_html=[]
    for source in sources:
        sources_html.append(f'''<section class="source"><h3>{escaped(source['dataset'])} / {source['images']} images</h3><p><a href="{escaped(source['file'])}">Open source manifest</a></p><p>Schema: {escaped(source['schema'])}</p><p class="hash">SHA-256<br>{source['sha256']}</p><p>Manifest gate: {escaped(source['passed'])}</p></section>''')
    filters=''.join(f'<label class="control"><span>{label}</span><select id="{name}"><option value="">All {label.lower()}</option></select></label>' for name,label in [('dataset','Datasets'),('split','Splits'),('view','Views'),('difficulty','Difficulties')])
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="referrer" content="no-referrer"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src 'self' file: data:; style-src 'unsafe-inline'; script-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; connect-src 'none'; object-src 'none'"><title>CausalFill v0.5 · Observation QA atlas</title><style>{STYLE}</style></head>
<body><header><p class="eyebrow">CausalFill Bench / v0.5 / Offline evidence</p><h1>Observation QA atlas</h1><p class="intro">Inspect the actual pixels behind the perception and action tasks. Filter paired scenes, compare occluded views, and open any observation at its original resolution.</p><div class="private-notice"><strong>Evaluator-only report.</strong> Hidden answers are embedded in this file, even when the answer toggle is off. Keep this atlas, its manifests, and annotated sheets out of scored solver environments.</div></header>
<main><section class="metrics" aria-label="Atlas counts"><div class="metric"><b>{count:,}</b><span>Observation PNGs</span><small>Individual images, not model trials</small></div><div class="metric"><b>{count-diagnostics:,}</b><span>Benchmark captures</span><small>Repeated views may share one episode</small></div><div class="metric"><b>{diagnostics:,}</b><span>Sensor diagnostic fixtures</span><small>Reported separately from scored tasks</small></div><div class="metric"><b>{checks:,}</b><span>Per-image QA passes</span><small>{failures} reported failures; flags are manifest evidence</small></div></section>
<noscript><p class="noscript">JavaScript is disabled. All observation images remain visible below. Filters, image inspection, and answer toggles require local JavaScript; nothing connects to the network.</p></noscript>
<section class="controls" aria-label="Image filters"><div class="filter-grid">{filters}<label class="control"><span>Scope</span><select id="scope"><option value="">All observations</option><option value="benchmark">Benchmark captures</option><option value="diagnostic">Sensor diagnostics</option></select></label><label class="control"><span>Find a record</span><input id="search" type="search" placeholder="Seed, filename, view…" autocomplete="off"></label></div><div class="control-row"><label class="answer-toggle"><input id="answers" type="checkbox"> Show private evaluator annotations</label><div class="result-count" role="status" aria-live="polite">Showing <strong id="shown-count">{count}</strong> of {count} images</div><button id="reset" type="button">Reset filters</button></div></section>
<section id="gallery" class="gallery" aria-label="Observation images">{''.join(cards)}<div id="empty" class="empty" hidden>No images match these filters. Reset the controls to see the full atlas.</div></section>
<details class="provenance"><summary>Source manifests and interpretation</summary><p>The builder verified each local image's SHA-256 against its manifest when a digest was supplied. These hashes bind this report to its source artifacts; they do not establish scientific correctness or independent replication.</p><div class="source-list">{''.join(sources_html)}</div><p class="limits">A successful script, a decoded image, a rendered instance, a visually inspected panel, and a model episode are different evidence units. The visual family uses known color palettes and controlled 2D raster scenes. Diagnostic partial-object centroids can be biased. A green QA badge means the manifest's reported checks passed, including expected refusal where applicable; it does not mean a model solved that image.</p><p class="limits">Answers are a display toggle, not access control. This complete page is an evaluator artifact. All styles, behavior, and record metadata are embedded locally; image and manifest links are relative to this file.</p></details>
<p class="footer">Project concept and direction: Phillip A. Holland Jr. · AI-assisted implementation · Built {escaped(payload['generated_utc'])} · This atlas makes no external requests.</p></main>
<dialog id="inspector" aria-labelledby="detail-title"><div class="dialog-head"><div><h2 id="detail-title">Observation</h2><p id="detail-subtitle"></p></div><button id="close-inspector" type="button" aria-label="Close image inspector">Close ×</button></div><div class="dialog-grid"><div class="inspection-pane"><div class="zoom-tools"><button id="previous" type="button" aria-label="Previous filtered image">← Previous</button><button id="next" type="button" aria-label="Next filtered image">Next →</button><button type="button" data-zoom="1">100%</button><button type="button" data-zoom="2">200%</button><button type="button" data-zoom="4">400%</button><span id="zoom-label">200%</span><label><input id="nearest" type="checkbox" checked> Crisp pixels</label></div><div class="image-stage"><img id="detail-image" class="detail-image nearest" alt="Selected observation"></div><p><a id="open-original" href="#" target="_blank" rel="noopener">Open original PNG</a></p></div><div class="details-pane"><h3>Observation provenance</h3><dl id="detail-facts" class="detail-facts"></dl><h3>Reported QA checks</h3><ul id="detail-checks" class="checks"></ul><h3>Measurement details</h3><pre id="detail-json" class="detail-json"></pre><div class="private-answer"><h3>Private evaluator annotation</h3><pre id="detail-answer"></pre></div></div></div></dialog>
<script id="atlas-data" type="application/json">{safe_json(payload)}</script><script>{SCRIPT}</script></body></html>'''


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--visual',type=Path,default=ROOT/'reports/v05/visual-qa/manifest.json')
    parser.add_argument('--robotics',type=Path)
    parser.add_argument('--output',type=Path,default=ROOT/'reports/v05/qa-atlas.html')
    args=parser.parse_args(argv)
    output=args.output.resolve()
    if not output.is_relative_to(ROOT):parser.error('output must be inside the source tree')
    sources,images=[],[]
    for label,path in [('visual',args.visual),('robotics',args.robotics)]:
        if path is None:continue
        path=path.resolve()
        if not path.is_file():parser.error(f'manifest not found: {path}')
        try:rows,source=normalize_manifest(path,label,output)
        except (ValueError,TypeError,KeyError,json.JSONDecodeError) as exc:parser.error(str(exc))
        images.extend(rows);sources.append(source)
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(build_html(images,sources,output),encoding='utf-8')
    provenance={'schema':'causalfill.offline-qa-atlas-build.v1','builder_sha256':sha256(Path(__file__).resolve()),
                'html':output.name,'html_sha256':sha256(output),'images':len(images),'sources':sources,
                'relative_local_image_references':True,'external_dependencies':False,'answers_embedded':True,
                'answers_initially_visible':False,'role':'evaluator-only report, not solver input'}
    output.with_suffix('.build.json').write_text(json.dumps(provenance,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'output':str(output),'images':len(images),'manifests':len(sources),'bytes':output.stat().st_size,
                      'sha256':provenance['html_sha256']},indent=2))
    return 0


if __name__=='__main__':raise SystemExit(main())
