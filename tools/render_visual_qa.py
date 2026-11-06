#!/usr/bin/env python3
"""Export scored raster fixtures, independent image checks, and readable QA sheets.

Pillow is a development-only dependency for independent PNG decoding and contact
sheets.  No annotated sheet or evaluator manifest belongs in a scored solver's
input.  A contact sheet's existence is NOT evidence that a human inspected it.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from causalfill.domains.visual import VisualTask, recover_visual_from_image
from causalfill.vision import (decode_envelope, detect_components, pixel_to_world,
                              recover_calibration, render_scene)


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _independent_decode(image):
    from PIL import Image
    data = base64.b64decode(image['png_base64'],validate=True)
    with Image.open(io.BytesIO(data)) as check:
        check.load()
        width,height,rgb = decode_envelope(image)
        return check.mode == 'RGB' and check.size == (width,height) and check.tobytes() == rgb


def _noise_error(image, clean):
    a,b = decode_envelope(image),decode_envelope(clean)
    if a[:2] != b[:2]:
        raise ValueError('noise reference dimensions mismatch')
    return max(abs(x-y) for x,y in zip(a[2],b[2]))


def _write_png(output,filename,image):
    path=output/'images'/filename
    path.write_bytes(base64.b64decode(image['png_base64'],validate=True))
    return str(path.relative_to(output))


def export_benchmark(output,seeds):
    records,pairs=[] ,[]
    for split in ('train','dev','transfer'):
        for difficulty in (1,2,3):
            for seed in range(seeds):
                tasks=[VisualTask(seed,split,difficulty,twin) for twin in (0,1)]
                same_overview=tasks[0].image('overview')==tasks[1].image('overview')
                changed_inspection=tasks[0].image('inspection')!=tasks[1].image('inspection')
                expected_equal=split!='train'
                pairs.append({'split':split,'difficulty':difficulty,'seed':seed,
                              'public_equal':tasks[0].public()==tasks[1].public() and tasks[0].files==tasks[1].files,
                              'overview_equal':same_overview,'overview_equal_expected':expected_equal,
                              'overview_equivalence_check':same_overview==expected_equal,
                              'inspection_changed':changed_inspection,
                              'dispatch_changed':tasks[0].reference_answer()['dispatch']!=tasks[1].reference_answer()['dispatch']})
                for twin,task in enumerate(tasks):
                    spec=json.loads(task.files['/scene/visual.json'])
                    full_components=detect_components(task.image('inspection'),task._palette['target'],tolerance=task._noise,min_pixels=8)
                    full_target_area=sum(component['area'] for component in full_components)
                    if full_target_area <= 0:raise ValueError('full target reference missing')
                    for view in ('overview','inspection'):
                        image=task.image(view)
                        expected_visible = view=='inspection' or split=='train'
                        clean=render_scene(task.scene_shapes(view),task._camera,noise=0)
                        noise_error=_noise_error(image,clean)
                        components=detect_components(image,task._palette['target'],tolerance=task._noise,min_pixels=8)
                        calibration=recover_calibration(image,spec['landmarks'],tolerance=task._noise)
                        maximum_calibration_error=max(abs(x-y) for x,y in zip(sum(calibration,[]),sum(task._camera['matrix'],[])))
                        visible_fraction=sum(component['area'] for component in components)/full_target_area
                        try:
                            fill=recover_visual_from_image(spec,image)
                            verdict=task.evaluate(fill)
                            decision={'returned_completion':True,'strict_success':verdict.success,'details':verdict.details}
                        except ValueError as exc:
                            decision={'returned_completion':False,'strict_success':False,'reason':str(exc)}
                        reference_expected=(decision['strict_success'] if expected_visible else not decision['returned_completion'])
                        filename=f'visual-{split}-d{difficulty}-s{seed:03d}-t{twin}-{view}.png'
                        path=_write_png(output,filename,image)
                        records.append({'kind':'benchmark_capture','split':split,'difficulty':difficulty,'seed':seed,'twin':twin,'view':view,
                                        'file':path,'sha256':image['sha256'],'width':image['width'],'height':image['height'],
                                        'independent_pillow_decode_match':_independent_decode(image),
                                        'noise_bound':task._noise,'maximum_observed_noise':noise_error,'noise_bound_check':noise_error<=task._noise,
                                        'target_visible_expected':expected_visible,'target_components':len(components),
                                        'target_visible_fraction':visible_fraction,
                                        'target_visible_pixels':sum(component['area'] for component in components),
                                        'target_full_inspection_pixels':full_target_area,
                                        'visibility_check':len(components)==int(expected_visible) and visible_fraction==float(expected_visible),
                                        'maximum_calibration_coefficient_error':maximum_calibration_error,
                                        'pixel_reference':decision,'expected_reference_behavior_check':reference_expected,
                                        'private_expected_completion':task.reference_answer()})
                print(f'visual QA {split} difficulty {difficulty} seed {seed}: 4 captures',flush=True)
    return records,pairs


def export_sensor_fixtures(output):
    # These diagnostics intentionally leave the benchmark's full-visibility and
    # <=6-noise support.  Partial centroids are measured rather than declared a
    # correctly recovered full-object pose.
    orientations=[[[1,0],[0,1]],[[0,-1],[1,0]],[[-1,0],[0,-1]],[[0,1],[-1,0]],
                  [[-1,0],[0,1]],[[1,0],[0,-1]],[[0,1],[1,0]],[[0,-1],[-1,0]]]
    landmarks=[{'world':[8,8],'rgb':[221,66,145]}, {'world':[88,8],'rgb':[39,180,194]},
               {'world':[8,88],'rgb':[149,91,218]}]
    target_color=[231,174,42]
    clipped_color=[220,73,49]
    records=[]
    for orientation,orient in enumerate(orientations):
        linear=[[2*orient[i][0],2*orient[i][1]] for i in range(2)]
        matrix=[[row[0],row[1],120-48*sum(row)] for row in linear]
        camera={'width':240,'height':240,'matrix':matrix}
        base=[{'shape':'rect','bounds':[2,2,94,94],'rgb':[241,244,248]}]
        base += [{'shape':'circle','center':l['world'],'radius':2.5,'rgb':l['rgb']} for l in landmarks]
        # Auxiliary red circle is partially outside the camera, not a target.
        base.append({'shape':'circle','center':[-8,48],'radius':12,'rgb':clipped_color})
        base.append({'shape':'circle','center':[48,48],'radius':8,'rgb':target_color})
        full=render_scene(base,camera)
        full_area=detect_components(full,target_color,tolerance=0)[0]['area']
        for noise in (0,6,32):
            for visibility in ('clear','partial'):
                shapes=deepcopy_shapes(base)
                if visibility=='partial':
                    shapes.append({'shape':'rect','bounds':[48,37,65,59],'rgb':[70,82,101]})
                image=render_scene(shapes,camera,noise=noise,noise_seed=19000+orientation)
                clean=render_scene(shapes,camera)
                comp=detect_components(image,target_color,tolerance=noise,min_pixels=8)
                clipped=detect_components(image,clipped_color,tolerance=noise,min_pixels=8)
                calibration=recover_calibration(image,landmarks,tolerance=noise)
                visible=comp[0]['area']/full_area
                point=pixel_to_world(calibration,comp[0]['center'])
                bias=math.dist(point,[48,48])
                expected_visible=1.0 if visibility=='clear' else 0.5
                filename=f'diagnostic-o{orientation}-n{noise:02d}-{visibility}.png'
                path=_write_png(output,filename,image)
                observed_noise=_noise_error(image,clean)
                records.append({'kind':'sensor_diagnostic','orientation':orientation,'noise_bound':noise,'visibility':visibility,
                                'file':path,'sha256':image['sha256'],'width':240,'height':240,
                                'independent_pillow_decode_match':_independent_decode(image),
                                'maximum_observed_noise':observed_noise,'noise_bound_check':observed_noise<=noise,
                                'target_visible_fraction':visible,'expected_visible_fraction':expected_visible,
                                'visibility_check':visible==expected_visible,'visible_centroid_world':point,'centroid_bias_world':bias,
                                'offscreen_auxiliary_components':len(clipped),'offscreen_component_touches_frame':any(0 in c['bbox'][:2] or 239 in c['bbox'][2:] for c in clipped),
                                'complete_pose_recoverable_by_visible_centroid':visibility=='clear',
                                'scope':'out-of-distribution diagnostic; no model success or benchmark-task count',
                                'target_rgb':target_color,'landmarks':landmarks})
    return records


def deepcopy_shapes(shapes):
    return json.loads(json.dumps(shapes))


def build_sheets(output,records):
    from PIL import Image,ImageDraw,ImageFont
    try:
        font=ImageFont.truetype('DejaVuSans.ttf',12)
        bold=ImageFont.truetype('DejaVuSans-Bold.ttf',13)
        title_font=ImageFont.truetype('DejaVuSans-Bold.ttf',22)
    except OSError:
        font=bold=title_font=ImageFont.load_default()
    columns,rows=4,4
    card_width,card_height=264,318
    gutter=14
    width=columns*card_width+(columns+1)*gutter
    height=rows*card_height+(rows+1)*gutter+80
    sheets=[]
    for start in range(0,len(records),16):
        canvas=Image.new('RGB',(width,height),(16,24,38))
        draw=ImageDraw.Draw(canvas)
        number=start//16+1
        draw.text((gutter,14),f'CAUSALFILL  /  VISUAL QA  /  SHEET {number:02d}',font=title_font,fill=(239,244,251))
        draw.text((gutter,46),'Evaluator annotations stay outside the observation PNGs. Generated panels are not automatically human-reviewed.',font=font,fill=(167,184,205))
        for offset,record in enumerate(records[start:start+16]):
            col,row=offset%columns,offset//columns
            x=gutter+col*(card_width+gutter)
            y=76+gutter+row*(card_height+gutter)
            draw.rounded_rectangle([x,y,x+card_width,y+card_height],radius=8,fill=(247,249,252))
            if record['kind']=='benchmark_capture':
                headline=f"{record['split'].upper()}  d{record['difficulty']} / s{record['seed']:02d} / t{record['twin']}"
                caption=f"{record['view']} / RGB noise +/-{record['noise_bound']}"
                answer=record['private_expected_completion']
                if record['target_visible_expected']:
                    footer=f"x {answer['target_world'][0]} y {answer['target_world'][1]} | left {answer['tokens_left_of_target']} | {answer['dispatch']}"
                    status='PIXEL REFERENCE PASS' if record['pixel_reference']['strict_success'] else 'REFERENCE FAILURE'
                else:
                    footer='Hidden target; pose withheld'
                    status='OCCLUDED CONTROL'
            else:
                headline=f"DIAGNOSTIC o{record['orientation']} / noise +/-{record['noise_bound']}"
                caption=f"{record['visibility']} / clipped red auxiliary"
                footer=f"visible {record['target_visible_fraction']:.0%} | centroid bias {record['centroid_bias_world']:.2f}"
                status='PARTIAL POSE IS BIASED' if record['visibility']=='partial' else 'CALIBRATION CHECK'
            for label, face in [(headline,bold),(caption,font),(footer,font)]:
                if draw.textbbox((0,0),label,font=face)[2]>card_width-24:
                    raise ValueError('contact-sheet label exceeds its card')
            draw.text((x+12,y+8),headline,font=bold,fill=(27,44,64))
            draw.text((x+12,y+27),caption,font=font,fill=(66,82,100))
            with Image.open(output/record['file']) as panel:
                panel=panel.convert('RGB')
                if panel.size!=(240,240):panel=panel.resize((240,240),resample=Image.Resampling.NEAREST)
                canvas.paste(panel,(x+12,y+48))
            draw.text((x+12,y+291),footer,font=font,fill=(30,63,90))
        path=output/f'contact-sheet-{number:02d}.png'
        canvas.save(path)
        sheets.append({'file':path.name,'sha256':_sha(path),'first_record_index':start,'record_count':min(16,len(records)-start),
                       'manual_visual_review_status':'not_recorded_by_exporter'})
    return sheets


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--seeds',type=int,default=8)
    args=parser.parse_args(argv)
    if not 1<=args.seeds<=128:parser.error('--seeds must be in [1,128]')
    if args.output.exists() and any(args.output.iterdir()):parser.error('output directory must be new or empty')
    args.output.mkdir(parents=True,exist_ok=True)
    (args.output/'images').mkdir()
    records,pairs=export_benchmark(args.output,args.seeds)
    fixtures=export_sensor_fixtures(args.output)
    records+=fixtures
    sheets=build_sheets(args.output,records)
    failure_counts={
        'independent_decode':sum(not r['independent_pillow_decode_match'] for r in records),
        'noise_bound':sum(not r['noise_bound_check'] for r in records),
        'visibility':sum(not r['visibility_check'] for r in records),
        'reference_behavior':sum(not r.get('expected_reference_behavior_check',True) for r in records),
        'pair_public':sum(not r['public_equal'] for r in pairs),
        'pair_overview':sum(not r['overview_equivalence_check'] for r in pairs),
        'pair_intervention':sum(not (r['inspection_changed'] and r['dispatch_changed']) for r in pairs),
        'offscreen_fixture':sum(not (r['offscreen_auxiliary_components']==1 and r['offscreen_component_touches_frame']) for r in fixtures),
    }
    passed=not any(failure_counts.values())
    manifest={'schema':'causalfill-visual-qa-v1','generated_utc':datetime.now(timezone.utc).isoformat(),
              'role':'evaluator-only development and image QA; no learned-model runs',
              'passed':passed,'source_sha256':{str(p.relative_to(ROOT)):_sha(p) for p in [ROOT/'causalfill/vision.py',ROOT/'causalfill/domains/visual.py',Path(__file__).resolve()]},
              'command':['python','tools/render_visual_qa.py','--output',str(args.output),'--seeds',str(args.seeds)],
              'counts':{'actual_observation_pngs':len(records),'benchmark_captures':len(records)-len(fixtures),
                        'benchmark_episodes':len(pairs)*2,'paired_scene_constructions':len(pairs),
                        'sensor_diagnostics':len(fixtures),'contact_sheets':len(sheets),
                        'independent_png_decodes':len(records),'manually_inspected_sheets_recorded_by_exporter':0},
              'failure_counts':failure_counts,'sheets':sheets,'pairs':pairs,'images':records,
              'limits':['Controlled raster primitives and known palettes, not natural imagery.',
                        'Noise is fixed-pattern and bounded, not calibrated real camera uncertainty.',
                        'Half-occluded centroids are biased; fixtures measure that failure rather than crediting full pose recovery.',
                        'Only benchmark inspection views promise fully visible targets and landmarks.',
                        'Generated files and correlated checks are not independent reasoning tasks or model evaluations.']}
    (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    (args.output/'README.md').write_text(
        '# Visual stimulus QA\n\n'
        f"This evaluator-only export contains **{len(records)} observation PNGs**: {len(records)-len(fixtures)} captures "
        f"from {len(pairs)*2} paired benchmark episodes and {len(fixtures)} sensor diagnostic fixtures. "
        f"The {len(sheets)} contact sheets are separate annotated composites.\n\n"
        'Pillow independently decoded every image and matched the benchmark decoder byte-for-byte. '
        'The manifest separately records noise support, visibility, calibration error, pixel-reference behavior, '
        'pair equivalence, and partial/offscreen diagnostics. Passing generation does not mean a human inspected '
        'every sheet; any human review must be recorded separately.\n\n'
        f'Automated gate: **{"PASS" if passed else "FAIL"}**. See `manifest.json` for source hashes and exact counts.\n\n'
        'Partial-object fixtures intentionally demonstrate centroid bias. They are outside the scored family\'s '
        'fully-visible inspection distribution and are not counted as task successes. All observation PNGs '
        'contain only RGB pixels; evaluator annotations appear only in contact sheets and the private manifest.\n')
    print(json.dumps({'passed':passed,'counts':manifest['counts'],'failure_counts':failure_counts,'output':str(args.output)}),flush=True)
    return 0 if passed else 1


if __name__=='__main__':raise SystemExit(main())
