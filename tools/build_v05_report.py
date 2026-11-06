#!/usr/bin/env python3
"""Build the source-bound v0.5 research report from completed release evidence.

Development dependencies: ReportLab, Pillow. Exact stimuli come from the tested
renderer. This report is not itself evidence that a gate was executed.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
WIDTH, HEIGHT = 612, 792
LEFT, RIGHT, TOP, BOTTOM = 48, 564, 727, 62
INK = colors.HexColor("#182B42")
MUTED = colors.HexColor("#53667D")
TEAL = colors.HexColor("#087F8C")
LIGHT = colors.HexColor("#EDF4F8")
GOLD = colors.HexColor("#D8A238")


def load(path):
    return json.loads(path.read_text())


class Report:
    def __init__(self, path):
        for name, file in (("CF","DejaVuSans.ttf"),("CF-Bold","DejaVuSans-Bold.ttf"),
                           ("CF-Mono","DejaVuSansMono.ttf")):
            pdfmetrics.registerFont(TTFont(name,"/usr/share/fonts/truetype/dejavu/"+file))
        self.c = canvas.Canvas(str(path), pagesize=(WIDTH,HEIGHT), pageCompression=1)
        self.c.setTitle("CausalFill-Bench v0.5.0 - Pixels, Decisions and Verification")
        self.c.setAuthor("Phillip A. Holland Jr.; AI-assisted research and implementation")
        self.page_number = 0
        self.y = TOP
        self.styles = {
            "body":ParagraphStyle("body",fontName="CF",fontSize=10,leading=14.5,textColor=INK,spaceAfter=8),
            "small":ParagraphStyle("small",fontName="CF",fontSize=8.5,leading=12,textColor=MUTED),
            "h2":ParagraphStyle("h2",fontName="CF-Bold",fontSize=15,leading=19,textColor=INK),
            "cell":ParagraphStyle("cell",fontName="CF",fontSize=8.1,leading=11.2,textColor=INK),
            "headcell":ParagraphStyle("headcell",fontName="CF-Bold",fontSize=8.1,leading=11,textColor=colors.white),
            "code":ParagraphStyle("code",fontName="CF-Mono",fontSize=8,leading=11.5,textColor=INK),
        }

    def page(self, title, kicker):
        if self.page_number:
            self.footer()
            self.c.showPage()
        self.page_number += 1
        self.c.setFillColor(TEAL)
        self.c.rect(0,HEIGHT-7,WIDTH,7,fill=1,stroke=0)
        self.c.setFont("CF-Bold",8)
        self.c.setFillColor(MUTED)
        self.c.drawString(LEFT,HEIGHT-31,"CAUSALFILL-BENCH / RESEARCH + VERIFICATION")
        self.c.drawRightString(RIGHT,HEIGHT-31,"v0.5.0")
        self.y = TOP
        self.p(kicker.upper(),"small",after=10)
        style=ParagraphStyle("title",fontName="CF-Bold",fontSize=27,leading=32,textColor=INK)
        self.draw_paragraph(title,style,after=16)

    def footer(self):
        self.c.setStrokeColor(colors.HexColor("#D9E3EB"))
        self.c.line(LEFT,45,RIGHT,45)
        self.c.setFillColor(MUTED)
        self.c.setFont("CF",7)
        self.c.drawString(LEFT,30,"2026-11-05 | Phillip A. Holland Jr. | AI-assisted research prototype")
        self.c.drawRightString(RIGHT,30,f"{self.page_number:02d}")

    def draw_paragraph(self,text,style,after=8,width=None,x=None):
        width=RIGHT-LEFT if width is None else width
        x=LEFT if x is None else x
        para=Paragraph(text,style)
        _,h=para.wrap(width,HEIGHT)
        if self.y-h < BOTTOM:
            raise ValueError(f"page {self.page_number} overflow: {text[:80]}")
        para.drawOn(self.c,x,self.y-h)
        self.y-=h+after
        return h

    def p(self,text,style="body",after=8):
        return self.draw_paragraph(text,self.styles[style],after)

    def h(self,text):
        self.y-=5
        self.p(text,"h2",after=8)

    def table(self,headers,rows,widths):
        data=[[Paragraph(escape(str(v)),self.styles["headcell"]) for v in headers]]
        data += [[Paragraph(escape(str(v)),self.styles["cell"]) for v in row] for row in rows]
        table=Table(data,colWidths=widths,hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND",(0,0),(-1,0),INK),("VALIGN",(0,0),(-1,-1),"TOP"),
            ("LEFTPADDING",(0,0),(-1,-1),8),("RIGHTPADDING",(0,0),(-1,-1),8),
            ("TOPPADDING",(0,0),(-1,-1),8),("BOTTOMPADDING",(0,0),(-1,-1),8),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[LIGHT,colors.white]),
            ("LINEBELOW",(0,0),(-1,0),.5,INK),
        ]))
        _,h=table.wrap(RIGHT-LEFT,HEIGHT)
        if self.y-h < BOTTOM: raise ValueError(f"page {self.page_number} table overflow")
        table.drawOn(self.c,LEFT,self.y-h)
        self.y-=h+13

    def callout(self,title,text):
        para=Paragraph(text,self.styles["body"])
        _,h=para.wrap(RIGHT-LEFT-26,HEIGHT)
        total=h+43
        if self.y-total < BOTTOM: raise ValueError(f"page {self.page_number} callout overflow")
        self.c.setFillColor(LIGHT)
        self.c.roundRect(LEFT,self.y-total,RIGHT-LEFT,total,7,fill=1,stroke=0)
        self.c.setFillColor(TEAL)
        self.c.rect(LEFT,self.y-total,4,total,fill=1,stroke=0)
        self.c.setFont("CF-Bold",10)
        self.c.drawString(LEFT+13,self.y-19,title)
        para.drawOn(self.c,LEFT+13,self.y-31-h)
        self.y-=total+14

    def image_row(self,items,size=160):
        available=RIGHT-LEFT
        gap=(available-len(items)*size)/max(1,len(items)-1)
        top=self.y
        for i,(path,label) in enumerate(items):
            x=LEFT+i*(size+gap)
            self.c.drawImage(str(path),x,top-size,width=size,height=size,preserveAspectRatio=True,mask='auto')
            labelp=Paragraph(label,self.styles["small"])
            _,h=labelp.wrap(size,50)
            labelp.drawOn(self.c,x,top-size-8-h)
        self.y=top-size-51
        if self.y < BOTTOM: raise ValueError(f"page {self.page_number} images overflow")

    def finish(self):
        self.footer();self.c.save()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence",type=Path,default=ROOT/"reports/v05/release-verification.json")
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args()
    e=load(args.evidence)
    if e["status"] != "passed-development-verification": raise ValueError("release evidence has not passed")
    args.output.parent.mkdir(parents=True,exist_ok=True)
    r=Report(args.output)
    units=e["unit_and_integration_tests"]
    suite=e["scripted_controls"]
    new=e["new_evidence"]
    qa=new["visual_qa"]
    robot_qa=new["robotics_qa"]
    audit=new["independent_audit"]
    decision=new["decision_sufficiency"]
    interventions=new["visual_interventions"]
    robot=new["robotics_controls"]
    visual_images=ROOT/"reports/v05/visual-qa/images"
    robot_images=ROOT/"reports/v05/robotics-qa/images"
    total_pngs=qa["counts"]["actual_observation_pngs"]+robot_qa["counts"]["actual_observation_pngs"]

    r.page("Pixels that matter.<br/>Decisions with consequences.","Research and verification report | November 5, 2026")
    r.p("CausalFill-Bench v0.5.0 extends the earlier symbolic benchmark with actual image observations, calibrated spatial recovery and costly sensing before an irreversible simulated action. The release keeps the original tasks and proof artifacts, adds two task configurations, and records the tests supporting each new claim.")
    r.table(["Complete test gate","Visual stimulus QA","Scripted control matrix"],[[f"{units['passed']:,} tests",f"{total_pngs:,} PNG observations",f"{suite['records']:,} episodes"]],[172,172,172])
    r.h("The concrete advance")
    r.p("The agent must obtain information through the public sensor interface. A pixel reader calibrates a camera from visible landmarks, interprets a scene, and completes a decision. A separate robotics configuration assigns time and consequences to sensing, probing and execution. The evaluator retains the true scene and checks what actually happened. [E1-E5]")
    r.h("A stronger question than reconstruction alone")
    r.p("A recovered component matters when changing it changes a later decision. The release therefore measures recovery, outcome, observation cost and paired interventions separately. Its finite decision certificates also accept successful actions that do not identify every hidden detail. One checked fixture permits guaranteed action even though exact world identity remains unobservable. [E6]")
    r.callout("What these results support","A reproducible, controlled image-to-decision research prototype with audited scripted references. The measured results concern its declared finite scenes and software. General image understanding, learned control and physical transfer require their own experiments.")
    r.p("Concept and direction: Phillip A. Holland Jr. Implementation, research synthesis and review: AI-assisted. Original project source and generated stimuli: MIT. Internal independent checkers provide different constructions; they are not external laboratory replication.","small")

    r.page("From the earlier roadmap<br/>to executable experiments","01 | What changed")
    r.p("The earlier report proposed noisy calibrated sensors, conservative action conditions, equal-budget controller comparisons and rendered scenes. Version 0.5 implements a bounded first step and identifies the experiments still needed beyond it. [E0-E5]")
    r.table(["Earlier boundary","v0.5 implementation","Remaining evidence"],[
        ["Numerical camera coordinates","RGB PNG observations; visible landmarks; affine camera recovery","Natural scenes, depth, perspective, lens effects"],
        ["No image occlusion study","Opaque shutters; byte-identical hidden twins; useful alternative views","3D occlusion and realistic camera-motion planning"],
        ["Exact symbolic geometry","Rendered lane evidence and explicit simulated execution outcomes","Rigid-body contact dynamics and real actuators"],
        ["Observation necessity only","Costed sensing, conservative alternatives and intervention controls","Strong learned controllers under enforced isolation"],
        ["Finite identity recovery","Overlapping noisy supports and action-sufficiency certificates","Statistical calibration and simulator refinement proofs"]
    ],[131,196,189])
    r.h("Fourteen configurations, nine conceptual domains")
    r.p("Language conditions, executable arithmetic, grid rules, procurement, robotics, finite-field state recovery, proof, diagnosis and visual perception share the typed tool protocol. The new visual family adds pose, spatial counting and dispatch recovery. The robotics_vision family joins the original robotics and barrier configurations. Earlier valid solutions remain accepted; new contracts are versioned separately.")
    r.p("The core still runs on Python 3.10 or newer without third-party runtime dependencies. Pillow is used for independent image QA and contact sheets; ReportLab builds this report. Those development dependencies do not become solver requirements.")

    r.page("Pixels are the<br/>public evidence","02 | The public pixel contract")
    r.p("Each image payload contains PNG bytes, width, height, MIME type and SHA-256. The PNG contains only image header, compressed pixel data and end chunks. It carries no object coordinates, camera matrix, seed, segmentation channel or embedded answer. The contract separately declares colors, three landmark world points, sensor bounds and permitted tools. [E1-E2]")
    r.image_row([
        (visual_images/"visual-transfer-d3-s000-t0-overview.png","Occluded overview, twin 0"),
        (visual_images/"visual-transfer-d3-s000-t1-overview.png","Occluded overview, twin 1"),
        (visual_images/"visual-transfer-d3-s000-t0-inspection.png","Useful inspection view")
    ])
    r.p("The two occluded overviews above are identical for the paired target intervention. Looking harder at that same image cannot recover the missing target location. The inspection view reveals the target while retaining the same declared camera and fixed noise realization. The image hash is included in the equivalence check; compression length is not ignored.")
    r.h("Calibrate before interpreting west")
    r.p("The affine map can rotate, reflect, translate and shear the scene. World-west means smaller world x after calibration, and need not mean image-left. Transfer cases include fractional pixel shifts, which produce measurable raster quantization error. The point estimate is checked against a declared 0.6 world-unit acceptance tolerance; it is not a probabilistic confidence interval.")
    r.p("The independent audit exhausts all 192 canonical transfer camera/target configurations. Its exact maximum centroid-derived coordinate error is 673/12012, about 0.05603 world units. This bound relies on the finite camera support, no clipping, and separated bounded RGB color supports. It does not calibrate a physical sensor. [E2]","small")
    r.p("The standalone image client saves exactly the public PNG received over authenticated HTTP and returns its local path. A copied-client integration test checks the complete transport without importing evaluator code. The host must still enforce solver/evaluator isolation.","small")

    r.page("Recover a component,<br/>then use it","03 | Controlled visual reasoning")
    r.table(["Requested completion","Independent acceptance condition"],[
        ["Target world position","Each coordinate lies within 0.6 world units of private geometry."],
        ["Token objects west of the target","Exact relational count computed from private object positions."],
        ["Dispatch branch","WEST when target x is below 48; EAST otherwise."]
    ],[174,342])
    r.p("Strict success requires all three fields. Recovery and dispatch-rule correctness are reported separately, so a lucky correct branch does not hide a wrong pose. The visual task scores a submitted route label; mutable execution is tested in the robotics family. The scorer does not invoke the pixel reader or its calibration routine. Exact represented-decimal rational comparisons enforce the tolerance boundary. [E1-E2]")
    r.image_row([
        (visual_images/"visual-dev-d2-s000-t0-inspection.png","Same nuisance variables; first target state"),
        (visual_images/"visual-dev-d2-s000-t1-inspection.png","Only target x changes; count and dispatch change")
    ],size=206)
    r.p("The generator changes one target coordinate between paired worlds. Colors, camera, noise, landmarks, distractors and other objects remain fixed. Randomized initial polarity avoids a fixed twin-to-answer convention. The development and transfer overviews conceal the entire changed target support.")
    r.p("The scene vocabulary is intentionally small: separated colored discs and rectangular distractors under a known legend. The task-aware detector is a solvability control for this contract. Its success should not be presented as a learned vision result or a measure of frontier-model difficulty.","small")

    r.page("Observation has a cost.<br/>Action has a consequence.","04 | Rendered robotics")
    r.p("The new robotics configuration links rendered evidence to a finite operational task. The solver chooses sensing and handling actions through the same budgeted Session interface, and execution changes the simulated state. The outcome cannot be repaired by merely submitting the correct latent label afterward. [E3-E5]")
    for paragraph in robot["report_description"]:
        r.p(paragraph)
    r.table(robot["action_table"]["headers"],robot["action_table"]["rows"],robot["action_table"].get("widths",[128,93,295]))
    r.callout("Conservative alternatives are legitimate","A robust action is accepted whenever it meets the same public completion, time and safety requirements. The scorer does not require a named sensor or maximum hidden-state recovery. A strict profile and a robust profile therefore test different decision problems.")
    r.p("This is an authored finite control abstraction with raster observations. Its time, friction and damage rules are explicit simulator semantics. They are not identified parameters of a real robot, a physical safety certificate or a contact-rich 3D dynamics engine.","small")

    r.page("Observe the gate.<br/>Change the contact.","04A | Two distinct routes to a successful decision")
    r.image_row([
        (robot_images/"robotics-transfer-d3-s000-t0-overview.png","Roof hides the usable lane"),
        (robot_images/"robotics-transfer-d3-s000-t0-inspection.png","Inspection reveals one opening"),
        (robot_images/"robotics-transfer-d3-s000-t1-inspection.png","Gate twin reveals the other opening")
    ])
    r.p("These are actual 192 by 192 public camera observations. The overview is identical across gate twins; inspection distinguishes them. Friction twins have identical images in both views. The sensor contract therefore requires different evidence for route geometry and contact handling. [E3-E5]")
    r.table(["Public contact profile","Largest initial friction","After one firm contact","Common grip succeeds?"],[
        ["Conditionable","0.65","0.41","Yes: both states are at or below 0.45."],
        ["Resistant","0.75","0.51","No: the dry state still exceeds 0.45."]
    ],[123,105,114,174])
    r.p("Firm contact adds two wear units, reducing friction by 0.24 with a floor of 0.1. On conditionable surfaces, a controller can then use grip without interpreting the returned reading. On resistant surfaces, the same fixed-grip action may stall. These authored profiles test when changing the environment can substitute for identifying its earlier state.")
    r.p("The contact sensor refers to the surface after its own intervention. Repeated probing is neither a passive observation nor an independent sample. The task charges the extra time, energy and wear, and a failed execution remains terminal.")

    r.page("Compare controllers on<br/>the same task contract","05 | Robot policy controls")
    r.p(robot["comparison_description"])
    r.table(robot["comparison_table"]["headers"],robot["comparison_table"]["rows"],robot["comparison_table"].get("widths",[128,74,74,80,80,80]))
    for paragraph in robot["findings"][:2]:
        r.p(paragraph)
    r.p("Costs and time are per-episode means. Observation cost includes captures and probes; tool cost also includes the read, camera move and execution. A fixed sensing policy may use every returned observation to choose its terminal action. The source report retains collisions, slips, stalls, profile strata and sensor interventions. These are scripted control contrasts; transfer labels do not establish learned-policy generalization. [E3-E5]","small")

    r.page("Useful information can be<br/>less than complete identity","06 | Exact finite decision certificates")
    r.p("The new finite model represents possible worlds, terminal actions and sensor observation supports. A sensor may return several values in one world; the supports can overlap across worlds. The controller keeps every compatible world and must choose an action that succeeds in all of them. Each sensor is available once and has a positive integer cost. [E6]")
    rows=[]
    labels={"decision":"Relevant lane only","robust":"Common robust action","ambiguous":"Persistent blur ambiguity","noisy_resolvable":"Useful alternative noisy view","adaptive":"Conditional expensive probes","action_ambiguity":"Action despite ambiguous identity"}
    for name, values in decision["examples"].items():
        a=values["action"]["adaptive_cost"];i=values["identification"]["adaptive_cost"]
        rows.append([labels.get(name,name),"No guarantee" if a is None else str(a),"No guarantee" if i is None else str(i)])
    r.table(["Constructed fixture","Successful action","Full identification"],rows,[256,130,130])
    r.p("All terminal actions in this table cost zero, so the values compare observation costs. The general schema also permits positive action costs; action and identification totals are then different objectives and must not be subtracted as a universal information advantage.")
    r.h("A strict, finite adaptive advantage")
    r.p("In the conditional-probe fixture, a cheap selector followed by the relevant expensive probe costs 3 in the worst case. The best fixed sensor subset costs 4, even though its final action can use every returned observation. Complete alternatives are checked rather than comparing only a preferred reference against an obviously weak control.")
    r.p("The certificate verifies the minimum over legal stopping actions and sensor choices, including every needed nonempty observation branch. A zero-cost successful action permits pruning because no nonnegative alternative can improve it. The remaining sensor set shrinks even after an uninformative reading. An absent guarantee is represented explicitly.")

    r.page("An ambiguous world can<br/>still permit a reliable choice","07 | Why action compatibility is richer than a label")
    r.table(["Possible world","Camera support","Successful terminal action(s)"],[
        ["Left-only","L","Left"],["Shared","L or R","Left or right"],["Right-only","R","Right"]
    ],[160,140,216])
    r.p("After L, the world may be Left-only or Shared; Left succeeds in both. After R, it may be Shared or Right-only; Right succeeds in both. One observation therefore guarantees a successful action although neither result identifies the exact world. All four supported fixed-world observation paths are checked. [E6]")
    r.h("Avoid an incorrect shortcut in the abstraction")
    r.p("Sharing a successful action is not generally an equivalence relation. Left-only and Shared are compatible, and Shared and Right-only are compatible, but Left-only and Right-only share no successful terminal action. Taking a transitive closure would falsely merge the entire set. The implementation retains the actual action-success sets.")
    r.h("Three different obligations")
    r.p("The optimizer proposes a minimum and a selected action. A separate set-based checker validates every needed recurrence and alternative, binding the intended problem with SHA-256. A fixed-world traversal then replays the selected policy under every supported observation. The small-policy audit uses a further independent construction: enumerate complete syntactic decision trees and execute raw paths.")
    n=audit["measurements"]["small_policy_oracle"]
    r.callout("Independent finite-policy oracle",f"{n['model_objective_comparisons']:,} exact optimum comparisons agreed with {n['whole_policy_evaluations']:,} complete syntactic policy evaluations over the declared tiny corpus. These counts measure finite checker coverage, not independent research tasks.")
    r.p("The proofs in this section are finite Python certificate checks. The historical Lean artifacts in the archive concern earlier formal tracks and retain their earlier versions. No new Lean proof or generic Python-to-physics equivalence is asserted.","small")

    r.page("Image QA checks meaning,<br/>visibility and failure modes","08 | Visual verification")
    counts=qa["counts"]
    r.table(["QA evidence","Count / scope"],[
        ["Actual observation PNGs",f"{total_pngs:,}: {counts['actual_observation_pngs']} visual + {robot_qa['counts']['actual_observation_pngs']} robotics"],
        ["Benchmark captures",f"{counts['benchmark_captures']+robot_qa['counts']['benchmark_captures']:,} from {counts['benchmark_episodes']+robot_qa['counts']['benchmark_episodes']:,} task instances"],
        ["Sensor diagnostic fixtures",str(counts['sensor_diagnostics'])],
        ["Independent PNG decodes",str(counts['independent_png_decodes']+robot_qa['counts']['independent_png_decodes'])],
        ["Annotated contact sheets",str(counts['contact_sheets']+robot_qa['counts']['contact_sheets'])],
        ["Final visual review",f"{new['combined_visual_review']['contact_sheets_reviewed']} sheets / {new['combined_visual_review']['panels_reviewed']} panels; AI inspection"]
    ],[241,275])
    r.p("Automated checks inspect RGB byte equivalence with Pillow, declared noise support, target visibility, fiducial calibration, pixel-derived completion, causal twin behavior and offscreen geometry. The independent raster oracle evaluates sampled pixel centers with exact rational arithmetic rather than calling the production shape classifier. [E1-E2]")
    r.p("The robotics gallery adds 288 captures through real Session tool calls. Those are image-QA sequences, not delivery trials. Its maximum observed opening-coordinate error is 0.2611 world units against the declared allowance of 1.0. The combined offline atlas includes all 624 observations with filters, zoom and separate evaluator annotations.","small")
    r.h("Partial visibility is a measured failure mode")
    r.p("A half-hidden disc has a biased visible-pixel centroid. The diagnostic fixtures record that bias and the visible fraction; they do not count the biased centroid as correct full-object recovery. Scored inspection views promise complete visible target support. Extending that promise to arbitrary occluded objects requires a different inference model.")
    r.h("The review changed the implementation")
    r.p("Development review found that integer-aligned scene centers made calibration artificially exact. Fractional pixel translations were added to the transfer distribution and verified at nonzero position error. Contact-sheet captions were shortened and checked against their card widths. Numeric input validation was hardened for extreme integers. These concrete findings are retained with their repaired follow-ups.")
    r.p("Noise levels outside the scored support, clipped objects and partial visibility are diagnostic controls. A generated image count is not a visual reasoning score. Contact sheets are evaluator artifacts containing annotations; only unannotated PNG observations belong in a scored solver environment.","small")

    r.page("Do the delivered pixels<br/>cause the reference's success?","09 | Paired image interventions")
    rows=[]
    for k,v in interventions["summary"].items():
        rows.append([k.replace('_',' ').title(),f"{v['successes']}/{v['episodes']}",f"{v['pair_successes']}/{v['complete_pairs']}",f"{v['mean_tool_cost']:.1f}"])
    r.table(["Delivered observation","Strict success","Complete pairs","Mean cost"],rows,[225,105,105,81])
    r.p("The instrumented controls retain the same public task and costs while replacing the delivered pixels with a valid alternative PNG. Original hidden labels remain fixed. Intact-image success confirms solvability; blanking removes evidence; a paired swap supplies plausible evidence about the other causal world; forced occlusion removes the useful target only in the splits where the overview shutter exists. [E4]")
    r.h("Why these are useful negative controls")
    r.p("A pipeline could otherwise ignore images, recover labels from metadata, or claim perception success because its generator and answer function share state. These interventions test the actual sensor path used by the scripted reference. The paired swap changes its recovered answer and downstream dispatch; the failure is scored against the original world.")
    r.p("The test does not establish that no future model could exploit a public distribution shortcut. Prompt-only and fixed-action searches, independently authored mechanisms, and isolated learned-model runs remain necessary. All reported controls are source-bound development tests, with representative full traces and all episode records retained.")
    r.p("Robot interventions retain physical contact and timing rules while changing sensor evidence. On strict episodes, blanking forces the reference into a late detour; swapping gate-twin images produces collisions. False contact readings can cause stalls, while a conditioning policy that ignores the reading is unaffected. Relaxed reference episodes skip sensing and are explicitly unexposed controls. [E3]","small")
    r.callout("Bandwidth is part of the experiment","A 240 by 240 RGB observation contains 172,800 uncompressed channel bytes before PNG compression. Image queries are not scalar measurements. The release records delivered bytes and dimensions separately from synthetic tool cost.")

    r.page("Stress evidence with<br/>honest units and provenance","10 | Release verification")
    ds=decision["counts"]
    r.table(["Gate","Recorded result"],[
        ["Complete unit/integration discovery",f"{units['passed']:,} passed; {units['failed']} failed; {units['errors']} errors"],
        ["Full scripted suite",f"{suite['records']:,} episodes; trace integrity checked"],
        ["Robot control and intervention study",f"{robot['controller_records']:,} controls + {robot['intervention_records']:,} interventions"],
        ["Independent combined audit",f"{sum(audit['counts'].values()):,} checks; {audit['failure_count']} failures"],
        ["Independent robot transition oracle",f"{audit['measurements']['robot_transitions']['committed_transition_cases']:,} committed cases against exact rational conditions"],
        ["Noisy-decision random fixtures",f"{ds['models']:,} models; {ds['certificates']:,} certificates"],
        ["Certificate forgery controls",f"{ds['forged_certificates_rejected']:,} rejected"],
        ["Metamorphic comparisons",f"{ds['metamorphic_comparisons']:,}"],
        ["Independent finite policy comparisons",f"{audit['measurements']['small_policy_oracle']['model_objective_comparisons']:,}"],
        ["Original-release baseline", "214 tests; 1,296 episodes; formal/protocol stress passed"],
        ["New learned-model / physical trials", "None in this release"]
    ],[248,268])
    r.p("The baseline ran from a fresh extraction of the original archive so concurrent development could not alter it. The final gates identify the new source version, commands, records and file hashes. A changed verifier or generator invalidates earlier source-bound conclusions until it is checked again. Development runs are retained separately from final runs. [E0-E7]")
    r.h("A replay scaling flaw found and repaired")
    r.p("Naive replay of synonymous observation labels could expand exponentially while visiting few distinct beliefs. The repaired replay combines equivalent fixed-world states, preserving exact path multiplicity and minimum/maximum costs. The regression represents over two billion label paths with 76 executed states. That is a compact exact accounting check, not billions of executed trials.")
    r.p("Hash chains detect modification relative to trusted evaluator records; they do not authenticate a malicious host. The local HTTP interface withholds grades and private state, but a shared filesystem is not enforced isolation. The benchmark should be deployed with a separate evaluator boundary for scored model experiments.","small")

    r.page("A disciplined next experiment","11 | Transfer and the 100D boundary")
    r.p("The release now supplies controlled pixel observations and simulated decisions. The next scientific question is whether a learned controller benefits from choosing evidence when nuisance changes, camera calibration is imperfect, and a robust action competes with further sensing. That requires a frozen model study rather than more generated seeds alone.")
    r.table(["Stage","Concrete experiment","Advance criterion"],[
        ["Isolated model study","Freeze the task contract and compare active, fixed-sensing and robust controllers at matched caps.","A reproducible outcome/cost advantage on independently authored mechanisms."],
        ["Contact-rich simulation","Connect a physics simulator, separate privileged state from sensors, and audit transition correspondence.","Success under unseen object/contact configurations with measured abstraction errors."],
        ["Physical validation","Use a controlled laboratory task with measured sensors, actuator limits and intervention recovery.","Task completion and failure recovery supported by real trials under the lab protocol."]
    ],[107,224,185])
    r.h("100D still means mathematical state dimension")
    r.p("The existing latent tasks recover operators over 8, 32 or 100 finite-field variables. Five probes at dimension 100 return 500 field values. The new image track does not turn these into 100 physical dimensions or prove improved robot perception. The useful shared idea is to account for what an observation reveals and whether that knowledge changes a successful decision.")
    r.p("Classical belief-space planning already links sensing and action [R1]. CLEVR motivates controlled visual diagnostics and distribution controls [R2]. ManiSkill's official interface distinguishes privileged states from sensor data [R3], and its physics simulator represents a later experimental layer with contact-rich dynamics [R4]. These are grounding sources, not evidence that this release matches their scope or results.")

    r.page("Reproduce, inspect and extend","12 | Evidence map and commands")
    commands=[
        "python -m causalfill list",
        "python -m causalfill demo --family visual --split transfer --difficulty 3",
        "python -m causalfill demo --family robotics_vision --split transfer --difficulty 3",
        "python -m unittest discover -s tests -v",
        "python tools/stress_decision_v05.py --cases 256 --output private-runs/decisions.json",
        "python tools/stress_vision_audit_v05.py --output private-runs/audit.json",
        "python tools/render_visual_qa.py --seeds 8 --output private-runs/visual-qa",
    ]
    for command in commands:r.p(escape(command),"code",after=7)
    r.p("Use a new output directory for each run. Windows users may replace python with py. The commands run scripted development checks. An external model must receive only a public episode and the allowed tools, with its own inference budget and enforced isolation.","small")
    r.table(["Evidence","Source-relative artifact"],[
        ["E0: prior baseline","reports/v05/legacy-baseline-summary.json"],
        ["E1: generated pixel QA","reports/v05/visual-qa/manifest.json"],
        ["Robot image QA / combined atlas","reports/v05/robotics-qa/manifest.json; reports/v05/qa-atlas.html"],
        ["E2: independent audit","reports/v05/independent-vision-audit-final.json"],
        ["E3: robot controls","reports/v05/robotics-controls/summary.json"],
        ["E4: pixel interventions","reports/v05/visual-interventions/summary.json"],
        ["E5: task contracts","docs/visual-perception.md; docs/robotics-vision.md"],
        ["E6: noisy decision certificates","reports/v05/decision-stress-final.json; reports/v05/decision-certificates/"],
        ["E7: consolidated release","reports/v05/release-verification.json"]
    ],[146,370])
    r.p("The archive includes per-file SHA-256 inventory, source, tests, configuration, generated stimuli and preserved historical proof evidence. The companion verification JSON records the exact release gates. These integrity records do not substitute for external replication.","small")

    r.page("Sources and claim boundaries","13 | Research grounding")
    sources=load(ROOT/"configs/research-provenance-v0.5.json")
    for source in sources["sources"]:
        r.h(f"{source['id']} | {escape(source['title'])}")
        r.p(escape(source["design_relevance"]))
        r.p(f'<link href="{escape(source["url"])}" color="#087F8C">{escape(source["url"])}</link>',"small",after=12)
    r.h("Release claim")
    r.p("CausalFill-Bench v0.5.0 is an executable extension from symbolic recovery to controlled pixel evidence, costed simulated decisions, and exact finite decision-sufficiency auditing. Its references are inspectable and its negative controls are recorded. A broad breakthrough, state-of-the-art ranking, learned world-model result or physical robot improvement has not been measured by these tests.")
    r.p("The staged research direction is concrete: preserve observation integrity, accept successful alternatives, test what information changes action, measure the costs, and require separate evidence at each increase in realism. The full source and evidence make those next experiments reviewable and reproducible.")
    r.finish()
    print(json.dumps({"output":str(args.output),"pages":r.page_number,"bytes":args.output.stat().st_size},indent=2))


if __name__ == "__main__":main()
