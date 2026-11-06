#!/usr/bin/env python3
"""Export robot observations through actual Session calls and independently audit images.

This is evaluator image QA, not a controller-completion study. Each fresh episode
reads the public contract, captures overview, moves to inspection, and captures
again. No contact probe or delivery is performed. Hidden scene annotations stay
in the evaluator manifest/contact sheets, never in observation PNGs.
"""
from __future__ import annotations

import argparse
import base64
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from causalfill.domains.robotics_vision import RoboticsVisionTask
from causalfill.robotics_vision_policy import recover_open_route
from causalfill.session import Session,verify_trace
from causalfill.types import digest
from causalfill.vision import decode_envelope,detect_components,recover_calibration,render_scene


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_hashes():
    names=['causalfill/vision.py','causalfill/domains/robotics_vision.py','causalfill/robotics_vision_policy.py',
           'causalfill/session.py','causalfill/types.py','tools/render_robotics_vision_qa.py']
    return {name:_sha(ROOT/name) for name in names}


def _pillow_decode_match(image):
    from PIL import Image
    data=base64.b64decode(image['png_base64'],validate=True)
    with Image.open(io.BytesIO(data)) as opened:
        opened.load()
        width,height,rgb=decode_envelope(image)
        return opened.mode=='RGB' and opened.size==(width,height) and opened.tobytes()==rgb


def _noise_error(image,clean):
    first,second=decode_envelope(image),decode_envelope(clean)
    if first[:2]!=second[:2]:raise ValueError('noise reference dimension mismatch')
    return max(abs(x-y) for x,y in zip(first[2],second[2]))


def capture_episode(seed,split,difficulty,twin):
    task=RoboticsVisionTask(seed,split,difficulty,twin)
    session=Session(task)
    def use(name,args):
        response=session.call(name,args)
        if 'error' in response:raise ValueError(f'{name} failed: {response["error"]}')
        return response
    contract_response=use('read_file',{'path':'/scene/robotics_vision.json'})
    spec=json.loads(contract_response['content'])
    overview=use('robot_capture',{})
    move=use('robot_move_camera',{'view':'inspection'})
    inspection=use('robot_capture',{})
    return task,session,spec,{'overview':overview,'inspection':inspection},move


def record_image(output,task,session,spec,response,full_area,seed,split,difficulty,twin,view):
    image=response['image']
    width,height,_=decode_envelope(image)
    clean=render_scene(task.scene_shapes(view),task._camera,noise=0)
    noise_error=_noise_error(image,clean)
    rgb=spec['palette']['opening']
    tolerance=spec['perception']['rgb_noise_bound']
    components=detect_components(image,rgb,tolerance=tolerance,min_pixels=8)
    area=sum(component['area'] for component in components)
    visible_fraction=area/full_area
    matrix=recover_calibration(image,spec['landmarks'],tolerance=tolerance)
    calibration_error=max(abs(x-y) for x,y in zip(sum(matrix,[]),sum(task._camera['matrix'],[])))
    true_point=[60,26 if task._open_route=='upper' else 54]
    pixel_reference={'returned_completion':False,'strict_success':False}
    try:
        route,support=recover_open_route(spec,image)
        point=support['estimated_center_world']
        error=max(abs(x-y) for x,y in zip(point,true_point))
        separator_distance=abs(point[1]-40)
        pixel_reference={'returned_completion':True,'strict_success':route==task._open_route and error<=support['center_allowance_world'],
                         'route':route,'estimated_center_world':point,'maximum_position_error_world':error,
                         'center_allowance_world':support['center_allowance_world'],'distance_to_separator_world':separator_distance}
    except ValueError as exc:
        pixel_reference['reason']=str(exc)
    expected_visible=view=='inspection'
    expected_reference=(pixel_reference['strict_success'] if expected_visible else not pixel_reference['returned_completion'])
    classification_margin=(not expected_visible or (pixel_reference.get('distance_to_separator_world',0)>=spec['perception']['classification_margin_world']))
    filename=f'robotics-{split}-d{difficulty}-s{seed:03d}-t{twin}-{view}.png'
    relative='images/'+filename
    (output/relative).write_bytes(base64.b64decode(image['png_base64'],validate=True))
    public_metadata={key:deepcopy(value) for key,value in response.items() if key!='image'}
    envelope_metadata={key:deepcopy(value) for key,value in image.items() if key!='png_base64'}
    # The pair checker compares the complete response dict. The stored PNG plus
    # these two metadata objects can reconstruct that exact public payload.
    reconstructed=deepcopy(public_metadata)
    reconstructed['image']=deepcopy(envelope_metadata)
    reconstructed['image']['png_base64']=base64.b64encode((output/relative).read_bytes()).decode('ascii')
    true_resources={'overview':{'elapsed':1,'energy_used':0,'primitive_steps':1},
                    'inspection':{'elapsed':3,'energy_used':1,'primitive_steps':3}}[view]
    resource_check=all(response['resources'][key]==value for key,value in true_resources.items())
    resource_check=resource_check and response['resources']['wear']==0 and not response['resources']['terminal']
    return {'kind':'benchmark_capture','split':split,'difficulty':difficulty,'seed':seed,'twin':twin,
            'view':view,'file':relative,'sha256':image['sha256'],'width':width,'height':height,
            'twin_kind':task.twin_kind,'profile':task.profile,'contact_profile':task.contact_profile,
            'noise_bound':tolerance,'maximum_observed_noise':noise_error,'noise_bound_check':noise_error<=tolerance,
            'independent_pillow_decode_match':_pillow_decode_match(image),
            'target_visible_expected':expected_visible,'target_components':len(components),
            'target_visible_pixels':area,'target_full_inspection_pixels':full_area,'target_visible_fraction':visible_fraction,
            'visibility_check':len(components)==int(expected_visible) and visible_fraction==float(expected_visible),
            'maximum_calibration_coefficient_error':calibration_error,'pixel_reference':pixel_reference,
            'expected_reference_behavior_check':expected_reference,'classification_margin_check':classification_margin,
            'public_response_metadata':public_metadata,'image_envelope_metadata':envelope_metadata,
            'public_response_sha256':digest(response),'response_reconstruction_check':reconstructed==response,
            'session_resource_check':resource_check,'trace_integrity_check':verify_trace(session.trace),
            'private_expected_completion':{'open_route':task._open_route,'opening_center_world':true_point,
                                           'initial_friction':task._initial_friction,'profile':task.profile,
                                           'contact_profile':task.contact_profile},
            'scope':'Actual public Session capture, evaluator-annotated image QA; no delivery completion or model evaluation.'}


def build_sheets(output,records):
    from PIL import Image,ImageDraw,ImageFont
    try:
        font=ImageFont.truetype('DejaVuSans.ttf',12)
        bold=ImageFont.truetype('DejaVuSans-Bold.ttf',13)
        titlefont=ImageFont.truetype('DejaVuSans-Bold.ttf',22)
    except OSError:
        font=bold=titlefont=ImageFont.load_default()
    columns,rows=4,4
    card_width,card_height,gutter=264,333,14
    width=columns*card_width+(columns+1)*gutter
    height=rows*card_height+(rows+1)*gutter+80
    sheets=[]
    for start in range(0,len(records),16):
        canvas=Image.new('RGB',(width,height),(16,24,38))
        draw=ImageDraw.Draw(canvas)
        number=start//16+1
        draw.text((gutter,14),f'CAUSALFILL  /  ROBOT OBSERVATION QA  /  SHEET {number:02d}',font=titlefont,fill=(239,244,251))
        draw.text((gutter,46),'Actual Session captures. Hidden gate/friction annotations stay outside the observation PNGs.',font=font,fill=(167,184,205))
        for offset,record in enumerate(records[start:start+16]):
            col,row=offset%columns,offset//columns
            x=gutter+col*(card_width+gutter)
            y=76+gutter+row*(card_height+gutter)
            draw.rounded_rectangle([x,y,x+card_width,y+card_height],radius=8,fill=(247,249,252))
            headline=f"{record['split'].upper()}  d{record['difficulty']} / s{record['seed']:02d} / t{record['twin']}"
            twin_label='gate twin' if record['twin_kind']=='gate_lane' else 'friction twin'
            caption=f"{record['view']} / {twin_label} / +/-{record['noise_bound']}"
            expected=record['private_expected_completion']
            if record['target_visible_expected']:
                footer=f"Open {expected['open_route']} | mu {expected['initial_friction']:.2f} | {record['profile']}"
            else:
                footer=f"Opening hidden | mu {expected['initial_friction']:.2f}"
            state=record['public_response_metadata']['resources']
            bottom=f"Time {state['elapsed']} / energy {state['energy_used']} / wear {state['wear']}"
            for label,face in [(headline,bold),(caption,font),(footer,font),(bottom,font)]:
                if draw.textbbox((0,0),label,font=face)[2]>card_width-24:raise ValueError('robot sheet label too wide')
            draw.text((x+12,y+8),headline,font=bold,fill=(27,44,64))
            draw.text((x+12,y+27),caption,font=font,fill=(66,82,100))
            with Image.open(output/record['file']) as panel:
                # Enlarged only on the annotated sheet. Saved public PNG stays
                # exactly the original 192x192 tool payload.
                panel=panel.convert('RGB').resize((240,240),resample=Image.Resampling.NEAREST)
                canvas.paste(panel,(x+12,y+48))
            draw.text((x+12,y+291),footer,font=font,fill=(30,63,90))
            draw.text((x+12,y+309),bottom,font=font,fill=(78,97,118))
        path=output/f'contact-sheet-{number:02d}.png'
        canvas.save(path)
        sheets.append({'file':path.name,'sha256':_sha(path),'first_record_index':start,
                       'record_count':min(16,len(records)-start),'manual_visual_review_status':'not_recorded_by_exporter'})
    return sheets


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--seeds',type=int,default=8)
    args=parser.parse_args(argv)
    if not 1<=args.seeds<=128:parser.error('seeds must be in[1,128]')
    if args.output.exists() and any(args.output.iterdir()):parser.error('output directory must be new or empty')
    before=_source_hashes()
    args.output.mkdir(parents=True,exist_ok=True);(args.output/'images').mkdir()
    records,pairs=[],[]
    for split in ('train','dev','transfer'):
        for difficulty in (1,2,3):
            for seed in range(args.seeds):
                episodes=[capture_episode(seed,split,difficulty,twin) for twin in (0,1)]
                first,second=episodes[0],episodes[1]
                kind=first[0].twin_kind
                overview_equal=first[3]['overview']==second[3]['overview']
                inspection_equal=first[3]['inspection']==second[3]['inspection']
                expected_inspection_equal=kind=='surface_friction'
                pair={'split':split,'difficulty':difficulty,'seed':seed,'twin_kind':kind,
                      'public_contract_equal':first[0].public()==second[0].public() and first[0].files==second[0].files,
                      'complete_overview_payload_equal':overview_equal,'complete_inspection_payload_equal':inspection_equal,
                      'inspection_equality_expected':expected_inspection_equal,
                      'overview_payload_equivalence_check':overview_equal,
                      'inspection_payload_intervention_check':inspection_equal==expected_inspection_equal,
                      'camera_move_payload_equal':first[4]==second[4],
                      'single_intervention_check':(first[0]._initial_friction==second[0]._initial_friction and first[0]._open_route!=second[0]._open_route) if kind=='gate_lane' else (first[0]._initial_friction!=second[0]._initial_friction and first[0]._open_route==second[0]._open_route)}
                pairs.append(pair)
                for twin,(task,session,spec,captures,move) in enumerate(episodes):
                    full=detect_components(captures['inspection']['image'],spec['palette']['opening'],tolerance=spec['perception']['rgb_noise_bound'],min_pixels=8)
                    area=sum(c['area'] for c in full)
                    if area<=0:raise ValueError('inspection opening missing')
                    if session.cost!=9 or session.calls!=4 or task.elapsed!=3 or task.energy_used!=1:
                        raise ValueError('capture sequence resource accounting changed')
                    for view in ('overview','inspection'):
                        records.append(record_image(args.output,task,session,spec,captures[view],area,seed,split,difficulty,twin,view))
            print(f'robotics image QA {split} difficulty {difficulty}: {args.seeds*4} captures',flush=True)
    sheets=build_sheets(args.output,records)
    after=_source_hashes()
    checks=['noise_bound_check','independent_pillow_decode_match','visibility_check',
            'expected_reference_behavior_check','classification_margin_check','response_reconstruction_check',
            'session_resource_check','trace_integrity_check']
    failures={key:sum(not record[key] for record in records) for key in checks}
    for key in ['public_contract_equal','overview_payload_equivalence_check','inspection_payload_intervention_check',
                'camera_move_payload_equal','single_intervention_check']:
        failures[key]=sum(not pair[key] for pair in pairs)
    failures['source_changed_during_export']=int(before!=after)
    errors=[record['pixel_reference']['maximum_position_error_world'] for record in records if record['view']=='inspection' and record['pixel_reference']['returned_completion']]
    counts={'actual_observation_pngs':len(records),'benchmark_captures':len(records),'benchmark_episodes':2*len(pairs),
            'paired_scene_constructions':len(pairs),'gate_pairs':sum(p['twin_kind']=='gate_lane' for p in pairs),
            'friction_pairs':sum(p['twin_kind']=='surface_friction' for p in pairs),'sensor_diagnostics':0,
            'contact_sheets':len(sheets),'independent_png_decodes':len(records),'actual_session_capture_calls':len(records),
            'actual_session_camera_moves':2*len(pairs),'actual_session_contract_reads':2*len(pairs),
            'completed_delivery_trials':0,'learned_model_runs':0,'manually_inspected_sheets_recorded_by_exporter':0}
    passed=not any(failures.values())
    manifest={'schema':'causalfill.robotics-image-qa.v1','generated_utc':datetime.now(timezone.utc).isoformat(),
              'role':'evaluator-only image QA through Session; no delivery success study','passed':passed,
              'command':['python','tools/render_robotics_vision_qa.py','--output',str(args.output),'--seeds',str(args.seeds)],
              'source_sha256':before,'source_sha256_after':after,'source_stable':before==after,'counts':counts,
              'failure_counts':failures,'inspection_pose_error_world':{'minimum_max_coordinate_error':min(errors),'maximum_max_coordinate_error':max(errors),'declared_allowance':1.0},
              'per_episode_capture_sequence':{'tools':['read_file','robot_capture','robot_move_camera','robot_capture'],
                                              'session_cost':9,'simulated_time':3,'energy':1,'wear':0,'delivery_executed':False},
              'sheets':sheets,'pairs':pairs,'images':records,
              'limits':['Camera images are controlled2D affine raster scenes, not natural images or physical robot sensors.',
                        'Image pairs with different friction are deliberately identical; appearance cannot reveal friction in this contract.',
                        'The one-world-unit allowance is an authored family assumption tested here, not a statistical confidence interval.',
                        'Counts refer to captures/task instances. No probe, delivery attempt, learned model or physical robot trial occurs in this image-QA export.',
                        'Contact sheets enlarge192x192 pixels for review and add private annotations; the underlying PNGs are exact public payloads.']}
    (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (args.output/'README.md').write_text(
        '# Robot observation QA\n\n'
        f"This export contains **{len(records)} exact public PNGs**, captured through Session in {2*len(pairs)} "
        f"fresh task instances and organized into {len(pairs)} paired scenes. The {len(sheets)} annotated contact sheets are separate composites.\n\n"
        'Each sequence reads the contract, captures overview, moves to inspection, and captures again. '
        'It costs9 synthetic Session units,3 simulated time units, and1 energy unit; wear remains0. '
        'These are capture-only QA sequences, not completed delivery/controller trials.\n\n'
        'Every PNG is independently decoded with Pillow and compared byte-for-byte with the benchmark decoder. '
        'The manifest checks noise support, measured gate visibility, calibrated lane classification, exact complete '
        'public-response pair equivalence, resource ledgers, trace integrity, and source stability. The stored PNG plus '
        'its public response/envelope metadata reconstructs each hashed capture response exactly.\n\n'
        'Gate twins have identical overview responses and different inspection responses. Friction twins have '
        'identical responses in both views: their friction difference is deliberately not visible. Private labels '
        'exist only in this manifest and the contact-sheet margins.\n\n'
        f"Automated gate: **{'PASS' if passed else 'FAIL'}**. Inspection maximum-coordinate error range: "
        f"{min(errors):.8f} to{max(errors):.8f} world units; declared allowance1.0.\n\n"
        'Generated contact sheets are not automatically visually reviewed. A separate review record must identify '
        'the inspected sheets, hashes, method, findings, and reviewer. No human study or model result is implied.\n')
    print(json.dumps({'passed':passed,'counts':counts,'failure_counts':failures,'inspection_pose_error_world':manifest['inspection_pose_error_world'],'output':str(args.output)}),flush=True)
    return 0 if passed else 1


if __name__=='__main__':raise SystemExit(main())
