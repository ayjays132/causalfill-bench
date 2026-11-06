#!/usr/bin/env python3
"""Build the separate v0.3 stress/formal research PDF; leave the v0.2 brief intact.

Final build reads reports/build-verification-v0.3.json. A draft may be rendered
earlier with --draft; it is marked and written under tmp/pdfs by default.
Individual evidence schemas are read defensively. In particular, the workflow
follow-up replaces the stale workflow section of the initial operations run.

Requires reportlab and pypdf. Optional --render uses pdftoppm. The finished PDF
embeds the complete two exported Lean proofs, their original JSON statements
and fills, the common Lean project, manifests, and verification records.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import subprocess
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Flowable, Frame, Paragraph, Spacer, Table, TableStyle
import reportlab
from pypdf import PdfReader, PdfWriter


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / "reports/build-verification-v0.3.json"
DEFAULT_OUTPUT = ROOT.parent / "output/CausalFill_Stress_and_Formal_Report_v0.3.pdf"
W, H = A4
MARGIN = 48
CONTENT = W - 2*MARGIN
NAVY = colors.HexColor("#102B40")
TEAL = colors.HexColor("#007F7D")
INK = colors.HexColor("#213747")
MUTED = colors.HexColor("#536773")
LINE = colors.HexColor("#D7E3E8")
PALE = colors.HexColor("#EDF6F4")
BLUE = colors.HexColor("#EDF2F7")
AMBER = colors.HexColor("#FFF4DD")
RED = colors.HexColor("#B74B42")
VIOLET = colors.HexColor("#75538C")


def load_json(path: Path, default=None):
    if not path.exists():
        return {} if default is None else default
    return json.loads(path.read_text())


def number(value) -> str:
    return f"{value:,}" if isinstance(value, int) else str(value if value is not None else "not recorded")


def plain(value: object) -> str:
    return str(value).translate(str.maketrans({"\u2011": "-", "\u2013": "-", "\u2014": "-",
                                              "\u2212": "-", "\u2018": "'", "\u2019": "'",
                                              "\u201c": '"', "\u201d": '"', "\u00a0": " "}))


def report_path(manifest: dict, keys: tuple[str, ...], fallback: str) -> Path:
    for scope in (manifest.get("stress_reports", {}), manifest.get("reports", {}), manifest):
        if not isinstance(scope, dict):
            continue
        for key in keys:
            value = scope.get(key)
            if isinstance(value, dict):
                value = value.get("path") or value.get("report") or value.get("results") or value.get("audit_path")
            if isinstance(value, str) and value.endswith(".json"):
                path = Path(value)
                return path if path.is_absolute() else ROOT/path
    return ROOT/fallback


def sections(report: dict) -> dict:
    raw = report.get("sections", [])
    if isinstance(raw, dict):
        return raw
    return {item.get("name", str(i)): item for i, item in enumerate(raw) if isinstance(item, dict)}


@dataclass
class Evidence:
    manifest_path: Path
    draft: bool

    def __post_init__(self):
        self.manifest = load_json(self.manifest_path)
        if not self.manifest and not self.draft:
            raise SystemExit("Final evidence manifest is absent. Use --draft for a clearly marked working report.")
        defaults = {
            "formal": (("formal", "formal_stress"), "reports/stress-v0.3/formal-results.json"),
            "protocol": (("protocol", "protocol_stress"), "reports/stress-v0.3/protocol.json"),
            "operations": (("operations", "operations_stress"), "reports/stress-v0.3/operations.json"),
            "workflow_followup": (("workflow_followup", "workflow_stress"), "reports/stress-v0.3/operations-workflow-followup.json"),
            "workflow_independent": (("workflow_independent", "workflow_independent_audit"), "reports/stress-v0.3/workflow-independent-audit.json"),
            "workflow_tests": (("workflow_tests",), "reports/stress-v0.3/formal-workflow-verification.json"),
            "barrier": (("barrier_independent", "robotics_barrier", "barrier", "barrier_audit"), "reports/stress-v0.3/barrier-independent-audit.json"),
            "lean": (("lean", "formal_assurance"), "formal/verification/results.json"),
        }
        self.paths = {key: report_path(self.manifest, names, fallback) for key, (names, fallback) in defaults.items()}
        if not self.paths["barrier"].exists():
            for fallback in ("reports/stress-v0.3/robotics-barrier-audit.json", "reports/stress-v0.3/barrier.json"):
                if (ROOT/fallback).exists():
                    self.paths["barrier"] = ROOT/fallback
                    break
        self.data = {key: load_json(path) for key, path in self.paths.items()}
        self.operational = sections(self.data["operations"])
        followup = sections(self.data["workflow_followup"])
        workflow_findings=self.operational.get("workflow", {}).get("failure_counts", {})
        if "workflow" in followup and ("workflow" not in self.operational or any(workflow_findings.values())):
            self.operational["workflow"] = followup["workflow"]
            self.workflow_replaced=True
        else:
            self.workflow_replaced=False
        self.baseline = sections(load_json(ROOT/"reports/stress-v0.3/operations-baseline.json"))
        self.protocol_baseline = load_json(ROOT/"reports/stress-v0.3/protocol-baseline.json")
        self.lean_agent = load_json(ROOT/"formal/verification/agent-results.json")
        self.export_manifests = {name: load_json(ROOT/f"formal/CausalFill/Release{name.title()}.manifest.json")
                                 for name in ("model", "reference")}
        self.date = str(self.manifest.get("verified_utc", self.manifest.get("created_utc", "2026-11-01")))[:10]
        self.version = str(self.manifest.get("version", "0.3.0"))
        unit = self.manifest.get("unit_and_integration_tests", self.manifest.get("tests", {}))
        self.unit = unit if isinstance(unit, dict) else {}
        self.unit_passed = self.unit.get("passed", self.unit.get("tests_run", self.unit.get("total")))
        self.unit_failed = self.unit.get("failed", self.unit.get("failures", 0))
        self.unit_errors = self.unit.get("errors", 0)
        self.no_models = self.manifest.get("new_model_solver_trials", 0)

    def count(self, section: str, key: str, default=0):
        return self.operational.get(section, {}).get("counters", {}).get(key, default)

    def path_label(self, key: str) -> str:
        try:
            return str(self.paths[key].relative_to(ROOT))
        except ValueError:
            return str(self.paths[key])


def register_fonts():
    local = Path("/usr/share/fonts/truetype/dejavu")
    bundled = Path(reportlab.__file__).parent/"fonts"
    choices = {
        "CFSans": local/"DejaVuSans.ttf" if (local/"DejaVuSans.ttf").exists() else bundled/"Vera.ttf",
        "CFSans-Bold": local/"DejaVuSans-Bold.ttf" if (local/"DejaVuSans-Bold.ttf").exists() else bundled/"VeraBd.ttf",
        "CFSans-Italic": local/"DejaVuSans-Oblique.ttf" if (local/"DejaVuSans-Oblique.ttf").exists() else bundled/"VeraIt.ttf",
        "CFMono": local/"DejaVuSansMono.ttf" if (local/"DejaVuSansMono.ttf").exists() else bundled/"Vera.ttf",
    }
    for name, path in choices.items():
        pdfmetrics.registerFont(TTFont(name, str(path)))
    pdfmetrics.registerFontFamily("CFSans", normal="CFSans", bold="CFSans-Bold", italic="CFSans-Italic", boldItalic="CFSans-Bold")


def make_styles():
    return {
        "title": ParagraphStyle("title", fontName="CFSans-Bold", fontSize=28, leading=32, textColor=NAVY, spaceAfter=15),
        "section": ParagraphStyle("section", fontName="CFSans-Bold", fontSize=23, leading=27, textColor=NAVY, spaceAfter=13),
        "sub": ParagraphStyle("sub", fontName="CFSans", fontSize=12.1, leading=17, textColor=MUTED, spaceAfter=14),
        "h": ParagraphStyle("h", fontName="CFSans-Bold", fontSize=10.9, leading=14.7, textColor=TEAL, spaceBefore=9, spaceAfter=5),
        "body": ParagraphStyle("body", fontName="CFSans", fontSize=10.0, leading=14.4, textColor=INK, spaceAfter=8),
        "small": ParagraphStyle("small", fontName="CFSans", fontSize=8.5, leading=11.8, textColor=MUTED, spaceAfter=7),
        "caption": ParagraphStyle("caption", fontName="CFSans", fontSize=7.8, leading=10.5, textColor=MUTED, spaceAfter=5),
        "table": ParagraphStyle("table", fontName="CFSans", fontSize=8.5, leading=11.7, textColor=INK),
        "thead": ParagraphStyle("thead", fontName="CFSans-Bold", fontSize=8.5, leading=11.7, textColor=colors.white),
        "code": ParagraphStyle("code", fontName="CFMono", fontSize=7.7, leading=11.2, textColor=NAVY, spaceAfter=6),
        "path": ParagraphStyle("path", fontName="CFMono", fontSize=7.1, leading=9.7, textColor=MUTED, wordWrap="CJK", spaceAfter=5),
        "stat": ParagraphStyle("stat", fontName="CFSans-Bold", fontSize=22, leading=27, textColor=TEAL, spaceAfter=3),
        "kicker": ParagraphStyle("kicker", fontName="CFSans-Bold", fontSize=8, leading=11, textColor=TEAL, spaceAfter=9),
    }


class BarrierFigure(Flowable):
    def __init__(self):
        super().__init__(); self.width=CONTENT; self.height=202

    def draw(self):
        c=self.canv
        panel=(CONTENT-24)/3
        for i,title in enumerate(("A: upper passage", "B: lower passage", "Union: complete barrier")):
            x=i*(panel+12); y=29; size=panel-12; scale=size/12
            c.setFillColor(NAVY);c.setFont("CFSans-Bold",7.5);c.drawString(x,y+size+15,title)
            c.setFillColor(colors.white);c.setStrokeColor(LINE);c.rect(x,y,size,size,fill=1,stroke=1)
            wallx=x+5*scale;wallw=scale
            if i==0: lo,hi=0,8
            elif i==1: lo,hi=4,12
            else: lo,hi=0,12
            c.setFillColor(colors.HexColor("#E3D2DE") if i==2 else colors.HexColor("#D5E3EC"))
            c.rect(wallx,y+lo*scale,wallw,(hi-lo)*scale,fill=1,stroke=0)
            c.setStrokeColor(VIOLET if i==2 else MUTED);c.setLineWidth(1)
            c.line(x+5.5*scale,y,x+5.5*scale,y+size)
            if i<2:
                routey=10 if i==0 else 2
                points=[(1,1),(2,routey),(8,routey),(10,9)]
                path=c.beginPath();path.moveTo(x+points[0][0]*scale,y+points[0][1]*scale)
                for a,b in points[1:]:path.lineTo(x+a*scale,y+b*scale)
                c.setStrokeColor(TEAL);c.setLineWidth(2);c.drawPath(path)
            for px,py,label in ((1,1,"s"),(10,9,"g")):
                c.setFillColor(NAVY);c.circle(x+px*scale,y+py*scale,2.6,fill=1,stroke=0)
                c.setFont("CFSans",7);c.drawString(x+px*scale+4,y+py*scale-2,label)
            c.setFillColor(MUTED);c.setFont("CFSans",7)
            c.drawString(x,y-13,("wall y = [0,8]", "wall y = [4,12]", "plane x = 5.5 fully covered")[i])
        c.setFillColor(MUTED);c.setFont("CFSans",7)
        c.drawString(0,2,"Exact illustrative geometry: workspace [0,12]^3; wall x=[5,6], z=[0,12]. Clearance omitted visually.")


class AssuranceFigure(Flowable):
    def __init__(self):
        super().__init__();self.width=CONTENT;self.height=116

    def draw(self):
        c=self.canv
        width=(CONTENT-26)/3
        items=[("Statement", "Immutable premises + signed goal"),
               ("Certificate", "Every inference + a model witness"),
               ("Checked claim", "Satisfiable premises entail the goal")]
        for i,(title,caption) in enumerate(items):
            x=i*(width+13)
            c.setFillColor(PALE);c.setStrokeColor(LINE);c.roundRect(x,43,width,58,6,fill=1,stroke=1)
            c.setFillColor(NAVY);c.setFont("CFSans-Bold",10);c.drawString(x+10,80,title)
            words=caption.split();line="";lines=[]
            for word in words:
                if pdfmetrics.stringWidth(line+" "+word,"CFSans",7.5)>width-20:
                    lines.append(line);line=word
                else: line=(line+" "+word).strip()
            if line:lines.append(line)
            c.setFont("CFSans",7.5)
            for j,line in enumerate(lines):c.drawString(x+10,65-j*10,line)
            if i<2:
                c.setStrokeColor(TEAL);c.line(x+width+2,72,x+width+11,72)
                c.line(x+width+11,72,x+width+7,75);c.line(x+width+11,72,x+width+7,69)
        c.setFillColor(MUTED);c.setFont("CFSans",8)
        c.drawString(0,24,"Lean proves this chain for its typed definitions. JSON/Python correspondence is a separate boundary.")
        c.drawString(0,10,"Hash binding identifies the exact statement; it is neither a signature nor a proof of truth.")


class Report:
    def __init__(self, evidence: Evidence):
        self.e=evidence;self.styles=make_styles();self.pages=[];self.current=[]

    def p(self, text: str, style="body"):
        self.current.append(Paragraph(plain(text), self.styles[style]))

    def h(self, text: str): self.p(text,"h")
    def gap(self, height=6):self.current.append(Spacer(1,height))

    def page(self, title: str, kicker: str):
        self.current=[];self.pages.append((title,self.current))
        self.p(kicker.upper(),"kicker");self.p(title,"section")

    def table(self, headers: list, rows: list, ratios: list[float], compact=False):
        data=[[Paragraph(escape(plain(x)),self.styles["thead"]) for x in headers]]
        data += [[Paragraph(plain(cell),self.styles["table"]) for cell in row] for row in rows]
        total=sum(ratios);widths=[CONTENT*ratio/total for ratio in ratios]
        t=Table(data,colWidths=widths,hAlign="LEFT",repeatRows=1)
        pad=6 if compact else 8
        t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),NAVY),("VALIGN",(0,0),(-1,-1),"TOP"),
            ("LEFTPADDING",(0,0),(-1,-1),7),("RIGHTPADDING",(0,0),(-1,-1),7),
            ("TOPPADDING",(0,0),(-1,-1),pad),("BOTTOMPADDING",(0,0),(-1,-1),pad),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,BLUE]),
            ("LINEBELOW",(0,0),(-1,0),0.5,NAVY),("LINEBELOW",(0,1),(-1,-1),0.35,LINE)]))
        self.current += [t,Spacer(1,9)]

    def note(self,title,text,tone=PALE):
        content=[Paragraph(title,self.styles["h"]),Paragraph(plain(text),self.styles["body"])]
        t=Table([[content]],colWidths=[CONTENT])
        t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),tone),("BOX",(0,0),(-1,-1),0.5,LINE),
                               ("LEFTPADDING",(0,0),(-1,-1),12),("RIGHTPADDING",(0,0),(-1,-1),12),
                               ("TOPPADDING",(0,0),(-1,-1),2),("BOTTOMPADDING",(0,0),(-1,-1),7)]))
        self.current += [t,Spacer(1,9)]

    def code(self,text):
        self.note("", "<font name='CFMono' size='7.7'>"+escape(plain(text)).replace("\n","<br/>")+"</font>",BLUE)

    def sources(self,text):self.p("Evidence: "+escape(text),"caption")

    def stats(self,values):
        row=[]
        for value,label in values:
            row.append([Paragraph(escape(str(value)),self.styles["stat"]),Paragraph(label,self.styles["small"])])
        t=Table([row],colWidths=[CONTENT/len(row)]*len(row))
        t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),PALE),("VALIGN",(0,0),(-1,-1),"TOP"),
                              ("LEFTPADDING",(0,0),(-1,-1),12),("RIGHTPADDING",(0,0),(-1,-1),9),
                              ("TOPPADDING",(0,0),(-1,-1),12),("BOTTOMPADDING",(0,0),(-1,-1),7),
                              ("LINEAFTER",(0,0),(-2,-1),1,colors.white)]))
        self.current += [t,Spacer(1,15)]

    def compose(self):
        e=self.e;f=e.data["formal"];p=e.data["protocol"];l=e.data["lean"]
        totals=f.get("totals",{});measure=f.get("measurements",{})
        certs=l.get("certificates",e.lean_agent.get("roundtrips",{}))
        independent=e.data["workflow_independent"]
        proto_fail=p.get("failure_count",0)
        self.page("CausalFill-Bench",f"Stress testing and formal assurance | v{e.version} | {e.date}")
        self.p("Stronger checks.<br/>Sharper claims.<br/>Explicit assumptions.","title")
        self.p("A research report on evaluator defects, independent stress tests, checked proof artifacts, and the limits of the resulting evidence.","sub")
        self.stats([(number(totals.get("checks")),"formal-audit assertions<br/>finite, reproducible corpus"),
                    ("2","complete Lean proof exports<br/>with exact statement binding"),
                    (str(e.no_models),"new model-solver trials<br/>in this development phase")])
        self.h("What changed")
        self.p("The release adds Lean soundness theorems and checks two full exported proofs; replaces workflow's sampled-only acceptance with a scoped symbolic certificate; corrects geometric boundary decisions; hardens protocol and numerical edge cases; and introduces a separately versioned robotics barrier profile whose paired worlds require geometry-dependent observation.")
        self.h("What the findings change")
        self.p("The audit found real acceptance errors and also found legal shortcuts. The old robotics distribution admits a common high route and conservative force. A fixed Express ordering schedule succeeds throughout the audited vending distribution. These are reasons to narrow difficulty and causal-dependence claims, not reasons to reject valid solutions.")
        self.note("The scientific conclusion", "This phase strengthens evaluator assurance. It does not establish frontier difficulty, new model capability, physical-robot safety, or generalization beyond the declared task grammars.")
        unit=number(e.unit_passed) if e.unit_passed is not None else "pending final manifest"
        self.p(f"<b>Final Python test gate:</b> {unit} passed. <b>Lean gate:</b> {escape(str(l.get('status','recorded separately')))}.<br/><b>Project concept and direction:</b> Phillip A. Holland Jr. <b>Development:</b> AI-assisted. Independent oracle and reviewer work is internal to this build, not external human or laboratory replication. Original MIT-licensed project.","small")
        if e.draft:self.note("DRAFT - FINAL EVIDENCE NOT YET LOCKED", "This layout uses available individual reports. Final totals and the barrier-profile status will be refreshed from the v0.3 verification manifest.",AMBER)

        self.page("Defects, repairs, and residual limits","01 | Before and after")
        self.table(["Finding","Captured before-fix evidence","Repair and measured follow-up"],[
            ["Workflow range blind spot","1,440 wrong threshold additions passed the larger initial operational run; 720 appeared in the smaller baseline.","Symbolic identity plus totality/resource certification. The follow-up rejects all 1,440 attacks while retaining valid alternatives."],
            ["Robotics boundary tolerance","144 outside-workspace false accepts and 197 clear-path false rejects in the smaller baseline; 63 false collision rejections in standalone geometry.","Exact decimal-rational predicates. Larger post-fix geometry and legacy-robotics samples report no mismatches."],
            ["Protocol / metrics edges","The captured protocol baseline has four failed checks: two duplicate-key stdio cases and two finite-mean cases.",f"Strict parsing and exact-intermediate mean aggregation, including subnormals. The final protocol run records {number(p.get('checks'))} checks and {number(proto_fail)} failures."],
            ["Barrier statement binding","An independently constructed forgery substituted JSON true for numeric 1 and recomputed the digest; Python equality treated the evidence as equal.","Canonical typed JSON equality binds the paired observations. Final tests rerun after this repair; pre-fix passes are not final evidence."],
            ["Legal default policies","A fixed business schedule and common legacy robot route meet the stated contracts.","Preserve valid successes; report the shortcuts. A new barrier profile changes the geometry claim explicitly."],
        ],[0.8,1.55,1.65],compact=True)
        self.h("An explicit counterexample beats a reassuring sample score")
        self.code("candidate = correct_expression + max(0, scale - 19)\nold behavioral diagnostics: 131 / 131 pass\nin-domain counterexample: scale = 20\nnew strict success: false; behavior pass rate remains 1.0")
        self.p("Increasing the largest sampled scale merely moves this exploit. The repair changes the acceptance argument: equal sound normal forms and bounded evaluation over a public integer box are required in addition to behavioral checks. Unsupported equivalences are labeled not_certified.")
        self.p("The barrier alias defect was directly reproduced before repair, but that review did not capture an old-source hash. Its report preserves the mutations and pinned post-fix regression results.","small")
        self.sources("[E2] operations-baseline.json; [E3] initial operations.json; [E4] operations-workflow-followup.json; [E5] protocol-baseline.json and protocol.json.")

        self.page("Different claims require different evidence","02 | An assurance map")
        self.current.append(AssuranceFigure());self.gap(5)
        self.table(["Claim","Current support","Boundary"],[
            ["Finite propositional entailment","Lean soundness theorem; full exported derivations and a checked consistency model.","The theorem concerns typed Lean definitions. Python parsing and translation correspondence are not Lean-proved."],
            ["Workflow equality on a box","Sufficient rational-polynomial/lattice proof system and original-AST bounds.","Python implementation; conservative and incomplete. Integer domain and resource caps are part of the claim."],
            ["Exact diagnosis query depth","Finite recurrence certificate, independent tree check, small complete-policy enumeration.","Explicit noiseless binary table; deterministic adaptive queries. No unrestricted hardness claim."],
            ["Geometric validity / barrier","Exact represented-number predicates; independent route and separator checks.","Idealized piecewise-linear paths and supplied geometry. No physical perception, dynamics, or safety transfer."],
            ["Model competence / novelty","No new comparative model study in this phase.","More tests, proof steps, dimensions or generated episodes do not establish intelligence."],
        ],[0.95,1.55,1.65],compact=True)
        self.note("Keep the trusted components visible", "Logical soundness, data correspondence, evaluator implementation, isolation, and experimental interpretation are separate obligations. A stronger result in one layer does not automatically discharge the others.")
        self.sources("[E1] final verification manifest; [E6] formal/verification/results.json; [E7] docs/formal-assurance.md; [E8] workflow certification/audit.")

        self.page("The Lean theorem and its axioms","03 | A mathematical contract for resolution")
        self.p("The typed Lean checker models a literal as a variable and Boolean polarity, a clause as a disjunction, and a CNF as a conjunction. The central end-to-end logical claim is nonvacuous entailment: a checked model satisfies the original premises, and a checked refutation after adding the negated goal establishes that those premises entail the signed goal.")
        self.code("checkModel assignment F = true\nrefutes (F ++ [[complement goal]]) steps = true\n------------------------------------------------\nSatisfiable F AND Entails F goal")
        self.h("The local rule matters")
        self.p("Resolution removes the selected positive pivot from one parent and the selected negative pivot from the other, then forms the union. Removing both signs after the union is unsound when a parent is tautological. Lean proves the exact membership equation for the resolvent, semantic preservation of duplicate removal, local resolution soundness, derivation soundness, and the refutation-to-entailment result.")
        self.table(["Theorem layer","Representative declarations"],[
            ["Representation and one step","mem_deduplicate; sameClause_holds; mem_mergeResolvent; resolve_sound"],
            ["Whole derivation / executable checker","derivable_sound; derive_sound; refutes_unsatisfiable"],
            ["Goal plus nonvacuity","refutation_entails; checkModel_sound; checked_nonvacuous; checked_derivation_nonvacuous"],
        ],[1,2.3],compact=True)
        self.h("Audited logical assumptions")
        self.p("The pinned toolchain is <b>Lean 4.35.0</b>, with Std and no external Lean package dependencies. The axiom audit permits exactly <font name='CFMono'>propext</font>, <font name='CFMono'>Classical.choice</font>, and <font name='CFMono'>Quot.sound</font>. The model-checker soundness theorem uses the smaller propext/Quot.sound set. No custom axiom, admitted proof, native_decide, or unsafe proof escape is accepted. [E6, R1]")
        self.p("These are applications of established propositional resolution and standard Lean principles. The result does not introduce a new logical axiom or a new resolution algorithm. It makes the benchmark's assurance argument inspectable. [R2, R3]","small")
        self.sources("[E6-E7] Lean verification and assurance contract. Source: formal/CausalFill/Resolution.lean; audit: formal/CausalFill/Audit.lean.")

        self.page("Two complete proof exports, exactly bound","04 | Full certificates checked and attached")
        self.p("Both complete release artifacts compiled successfully. Each contains a local kernel-checked proof for every resolution step, an empty-clause derivation, and a separately checked model proving satisfiable entailment. The full indexed checker was also executed as a supplementary operational check. The complete Lean and JSON artifacts are embedded as PDF attachments and remain in the source package.")
        for name,label in (("model","ReleaseModel"),("reference","ReleaseReference")):
            manifest=e.export_manifests[name];check=certs.get(name,{})
            self.h(f"{label}: {number(check.get('proof_steps',manifest.get('proof_steps')))} resolution steps")
            self.p(f"<b>{number(manifest.get('nvars'))} variables; {number(manifest.get('premises'))} original clauses.</b> Conclusion: <font name='CFMono' size='7.5'>CausalFill.Exported.{label}.certifiedNonvacuous</font>.","small")
            self.p("Canonical statement SHA-256:","caption")
            self.p(escape(str(check.get("canonical_statement_sha256",manifest.get("canonical_statement_sha256","pending")))),"code")
            self.p(f"Exact Lean-data round trip: <b>{str(check.get('exact_roundtrip',False)).lower()}</b>. Input/source hashes agree: <b>{str(check.get('input_and_generated_source_hashes_match',False)).lower()}</b>.","small")
        self.h("What the round trip actually compares")
        self.p("The exported Lean program emits its actual nvars, ordered raw clauses, signed goal, complete assignment, and complete step list. The verification gate compares all five fields with the source JSON, checks the input and generated-source hashes, and enforces the theorem axiom whitelist. A translator proposing a wrong local resolvent cannot make its Lean equation proof pass.")
        self.note("Do not compare unrelated proof lengths", "The two hashes above bind different release statements. The historical same-statement comparison used 865 model steps and 6,073 reference steps; the separate exported reference certificate has 6,018 steps. None of these lengths is a general model score.",AMBER)
        self.p("The translator and round-trip program are not formally verified. The Lean theorem does not prove Python's parser, set/sort behavior, one-based validation, resource limits, or hash implementation equivalent to Lean. The pinned kernel, permitted standard axioms, source integrity, and checked correspondence remain explicit trust boundaries.","small")
        self.sources("[E6] verification/results.json; ReleaseModel.manifest.json; ReleaseReference.manifest.json; [E9] same-statement-comparison.json.")

        self.page("Workflow: a scoped symbolic guarantee","05 | A stronger acceptance condition")
        self.p("Strict success now requires both a symbolic equality certificate and conservative total evaluation over a public finite input box. Balance, amount, fee, reserve and ceiling are integers in [-1,000,000, 1,000,000]; scale is an integer in [1,1,000,000]. The floor/cap task additionally declares reserve &lt;= ceiling. Arithmetic is exact, with no rounding.")
        self.h("A sufficient proof system")
        self.p("The checker normalizes rational polynomials over variable and canonical min/max atoms. It supports arithmetic identities and lattice commutativity, associativity, idempotence, absorption and distributivity. Only proved equality, exact constant ordering and the declared reserve/ceiling relation justify leaf-order rewrites. Every divisor must normalize to a nonzero rational constant.")
        self.table(["Original AST operation","Absolute-value bound M","Denominator divisor D"],[
            ["Integer input","1,000,000","1"],["Add / subtract","M_a + M_b","lcm(D_a,D_b)"],
            ["Multiply","M_a M_b","D_a D_b"],["Divide by reduced p/q, p != 0","M_a q / abs(p)","D_a abs(p)"],
            ["min / max","Maximum child M","LCM of child D"],
        ],[1.4,1.15,1.1],compact=True)
        self.p("For a reduced value n/d, d divides D and |value| &lt;= M imply |n| &lt;= M D and d &lt;= D. Every original AST value must satisfy M D &lt;= 10^30 and D &lt;= 10^30 before cancellation. Thus neither a pole such as 0/(scale-20) nor an oversized intermediate hidden in u-u can be erased by normalization.")
        self.note("Incompleteness is part of the contract", "Not_certified does not mean mathematically false. For example, balance/scale*scale is equivalent on positive scale but remains unsupported because its divisor varies. Bounds can also reject safe expressions conservatively. Work, expansion, coefficient, and representation limits are public.")
        self.p("Independent differential review checked 4,808 lattice expressions in two constraint modes, 480,800 exact expression values, and 411,928 original mixed-AST Fraction values without a false certification or bound violation. Numeric bounds do not establish wall-clock or operating-system memory guarantees; this checker is reviewed/tested Python, not Lean-verified.","small")
        self.sources("[E8] docs/workflow-certification.md; formal-workflow-verification.json; workflow-independent-audit.json; [E4] workflow follow-up.")

        self.page("Independent formal stress methods","06 | Oracles that do not copy the evaluator")
        rm=measure.get("resolution_exhaustive",{});gm=measure.get("generated_proof_statement_semantics",{})
        sm=measure.get("satisfiable_multistep_semantics",{});dm=measure.get("diagnosis_observed_eliminations",{})
        self.table(["Method","Concrete coverage","What it tests"],[
            ["Resolution truth tables",f"{number(rm.get('clause_pair_pivot_cases'))} clause-pair/pivot cases over 1-4 variables; {number(rm.get('accepted_inferences'))} accepted inferences.","Every literal subset, including empty and tautological clauses. Accepted conclusions checked against Boolean semantics."],
            ["Independent proof construction","160 complete-blocker statements; 1,920 internal-step corruptions; valid redundant and transported proofs.","No production proof-search oracle. Distinguishes malformed proofs from legitimate alternatives."],
            ["Satisfiable multistep cases",f"{number(sm.get('satisfiable_formulas'))} formulas; {number(sm.get('constructed_steps'))} constructed steps.","Final entailment under complete valuations, where an unsound conclusion cannot hide behind inconsistent premises."],
            ["Generated statement semantics",f"{number(gm.get('statements'))} statements; {number(gm.get('complete_valuations'))} complete valuations.","Nonvacuity and the exact signed goal. Larger transfer formulas are outside exhaustive truth enumeration."],
            ["Complete diagnosis policies","All 259 distinct-row tables of widths 1-3; 96 width-4 samples with 2-4 worlds.","Assign a query to each node of a full policy, replay each world, and find the smallest distinguishing depth."],
            ["Diagnosis evidence / forgery",f"{number(dm.get('table_world_cases'))} table/world cases plus bound, strategy, hash, node and witness mutations.","Reject lucky guesses, unobserved queries, missing competitors, wrong depths and omitted alternative-query states."],
        ],[1.0,1.5,1.7],compact=True)
        self.p(f"The full deterministic run has <b>{number(totals.get('checks'))} assertions</b>: {number(totals.get('acceptance_checks'))} acceptance decisions and {number(totals.get('invariant_checks'))} semantic/integrity invariants. It records {number(totals.get('false_accepts'))} false accepts, {number(totals.get('false_rejects'))} false rejects, {number(totals.get('invariant_failures'))} failed invariants and {number(totals.get('exceptions'))} unexpected exceptions.")
        self.p("The diagnosis oracle enumerates complete policies instead of reimplementing Bellman recurrence. Large generated tables receive independent strategy replay and evidence checks; their lower bounds still rely on the recurrence checker. Mutation controls verify that accept-everything and reject-everything substitutes are detected.","small")
        self.sources("[E10] formal-results.json; tools/stress_formal.py. Fixed seed 2026110103; exact per-section counts and transcript digest are recorded.")

        self.page("Robotics predicates now honor exact boundaries","07 | Correct represented-number geometry")
        self.p("The old geometry code used tolerances that changed the contract at boundaries: an outside-workspace point could pass, while a path with a positive clearance gap could fail. The repair interprets each finite supplied numeric value as its shortest decimal string, then uses exact rational arithmetic for segment/box and workspace predicates.")
        self.table(["Boundary case","Before","After"],[
            ["Workspace lower limit minus 5e-9 m","Could be accepted despite extending outside.","Rejected. No epsilon expands the permitted workspace."],
            ["Obstacle roof plus clearance plus 5e-9 m","Could be rejected despite positive separation.","Accepted when the full path is otherwise valid."],
            ["Exact contact with a clearance-expanded closed box","Collision semantics could be blurred by tolerance.","Contact is a collision. Strictly positive separation is clear."],
        ],[1.45,1.25,1.4])
        self.h("A different algorithm supplies the oracle")
        self.p("Production uses a rational segment/box predicate. The independent stress oracle checks endpoints and exact intersections with all six box faces. Its corpus includes degenerate segments and boxes, parallel directions, exact corners/edges, tiny signed gaps, clearances, random boxes, endpoint reversal and cyclic axis permutations.")
        self.stats([(number(e.count('geometry','checks')),"exact geometry comparisons"),
                    (number(e.count('robotics','episodes')),"legacy robotics episodes"),
                    (number(e.count('robotics','checks')),"robotics assertions")])
        self.p("The selected post-fix runs report no false accepts, false rejects or unexpected exceptions in these sections. Target-coordinate and camera-calibration tolerances remain separate from exact collision/workspace predicates. Exactness applies to the chosen numerical representation, not to unknown physical geometry.")
        self.note("Simulation scope", "The robot model remains symbolic and kinematic. Numerical cameras, supplied obstacles, a point path with prescribed clearance, and simple force constraints do not model pixels, sensor error, contact dynamics, actuator limits, or real-world manipulation safety.")
        self.sources("[E2-E3] geometry baseline and operational follow-up; docs/assumptions-and-guarantees.md; causalfill/domains/robotics.py.")

        self.page("A barrier profile with a precise necessity claim","08 | Observation dependence, not computational hardness")
        self.current.append(BarrierFigure());self.gap(4)
        self.p("The new profile preserves the old robotics family and adds a different paired construction. The twins share the start, target, workspace and pre-geometry camera evidence. A full-height wall occupies the same interior x slab but shifts in y, leaving opposite passages. Each world has a checked feasible route.")
        self.h("Why one fixed continuous route cannot serve both worlds")
        self.p("A separating plane lies strictly between the start and the entire permitted goal region. At that plane, the union of the two worlds' clearance-expanded forbidden sections covers the whole permitted workspace cross-section. Every continuous start-to-goal path crosses the plane. A route safe in both worlds would avoid both forbidden sets there, contradicting complete coverage.")
        self.p("The independent certificate validator binds the supplied paired statement, checks shared public evidence, reconstructs the target with exact Gaussian elimination, verifies the whole goal-tolerance region lies on the opposite side, checks rectangle-union coverage, and validates constructive routes with independent face intersections.")
        barrier=e.data["barrier"]
        if barrier:
            self.p(f"<b>Final profile stress:</b> {number(e.count('robotics_barrier','valid_pair_certificates'))} valid paired certificates, {number(e.count('robotics_barrier','constructive_route_successes'))} successful route witnesses, and {number(e.count('robotics_barrier','certificate_forgeries_rejected'))} rejected forgeries. The focused independent review also retested the Boolean/numeric binding repair. [E3, E11]","small")
        else:
            self.p("<b>Profile audit record:</b> awaiting the final barrier audit artifact. Construction and validator are present; final numerical claims are deliberately withheld in this draft.","small")
        self.note("What is necessary", "Guaranteed success across the matched worlds requires distinguishing geometry-dependent evidence. Lidar is not uniquely necessary: a suitable path probe also suffices. With equally weighted worlds, identical restricted observation laws and world-independent randomness, expected success without such evidence is at most one half. This is not a bound on every realized sample or a computational-hardness result.")
        self.sources("[E11] docs/robotics-barrier.md; barrier certificate and audit; causalfill/domains/robotics_barrier.py. This is a versioned added profile.")

        self.page("Legal shortcuts are substantive findings","09 | Preserve successes; revise difficulty claims")
        self.h("Vending: a fixed schedule within the generated bounds")
        self.p("The audited policy sets price 359, orders five Express cases on days 0, 4, 8, and so on, and advances daily. It does not adapt to demand, stock, Cedar lead time, or the causal twin. Three Cedar quotes are still used to recover the required repair fields; the business trajectory then uses Express only.")
        self.table(["Difficulty","Minimum profit / four days","Intervals","Minimum total / target"],[
            ["1","644 cents","4","2,576 / 2,000 cents"],["2","624 cents","5","3,120 / 2,500 cents"],
            ["3","604 cents","6","3,624 / 3,000 cents"],
        ],[0.6,1.2,0.65,1.55],compact=True)
        self.p("Thirty fresh units arrive each interval. Demand is 4-10 per day, giving at least 75% service and at least three selling days per four-day interval. The worst shipment costs 4,980 cents; minimum interval revenue is 5,744 cents. Fees produce the bounds above. Stock and pending orders stay below the limit, and initial cash covers prepaid deliveries.")
        self.p(f"The fixed policy succeeded in all <b>{number(e.count('vending','fixed_express_episodes'))}</b> budgeted public-interface sessions. The random-action audit separately checked {number(e.count('vending','actions'))} actions, including {number(e.count('vending','invalid_actions'))} invalid actions for atomicity. These are implementation controls, not learned-model results.")
        self.h("Legacy robotics: a common high route and force")
        self.p("After camera-based target recovery, a route through z=10 and a 0.5 N force limit succeeds throughout the audited legacy family. The clearance-expanded obstacle roof is at most 6.725 m; the two vertical legs lie outside its x interval. The common force is permitted for every material. Neither lidar nor material-specific force adaptation is needed for this distribution's strict success.")
        self.note("Do not repair an evaluation by banning a valid answer", "The old contracts continue to accept these strategies. The new barrier profile changes a declared environment property and supplies a separate necessity argument. Adaptive procurement, force optimization and physical transfer remain future versioned research questions.",AMBER)
        self.sources("[E3] operations.json, fixed-policy counters and notes. Bounds and constructive shortcut arguments: operations-findings.md, historical finding sections only.")

        self.page("Stress accounting and protocol integrity","10 | Checks, episodes, and actions are different units")
        rows=[]
        for key,label in (("geometry","Geometry"),("robotics","Legacy robotics"),("robotics_barrier","Barrier profile"),("vending","Vending"),("workflow","Certified workflow"),("grid","Grid"),("latent","Latent / sparse")):
            section=e.operational.get(key,{});c=section.get("counters",{});fail=section.get("failure_counts",{})
            failures=sum(value for name,value in fail.items() if ":" not in name and isinstance(value,int))
            rows.append([label,number(c.get("checks")),number(c.get("episodes",c.get("fuzz_episodes"))) if key!="geometry" else "20,000 base cases",str(failures)])
        rows.append(["<b>Operational total</b>","<b>"+number(sum(x.get("counters",{}).get("checks",0) for x in e.operational.values()))+"</b>","Correlated assertions","0"])
        self.table(["Selected current section","Assertions","Episode / base-case scope","Findings"],rows,[1.25,0.85,1.3,0.55],compact=True)
        self.p("The workflow row uses post-fix evidence; the earlier operational run's stale workflow section is excluded. Historical failing reports remain evidence of the defects, not current success rates. Assertions within a trajectory, metamorphic variants and repeated counterexamples are correlated and must not be counted as independent benchmark episodes.")
        self.h("Protocol stress")
        config=p.get("configuration",{})
        self.p(f"The protocol audit records <b>{number(p.get('checks'))} checks</b> across {number(config.get('parser_cases'))} generated parser cases, {number(config.get('sessions'))} sessions, and {number(config.get('http_trials'))} HTTP trials. It tests rejected-action atomicity, state separation, trace integrity, response separation, closure, at-most-once grading, authentication, concurrent requests, persisted hashes, duplicate keys and finite metric aggregation.")
        self.p("The public service remains an observation boundary, not an operating-system sandbox. A scored solver needs a separate environment without evaluator source, seeds, memory or private results. Hash chains detect changes relative to a trusted anchor; an actor able to rewrite the chain and its anchor can create a new consistent history.")
        self.note("How to interpret zero observed failures", "It means no mismatch occurred in the recorded finite corpus under the stated oracle and assumptions. It is not a universal reliability probability. Repetition improves coverage within a mechanism; it does not manufacture independent mechanisms or certify intelligence.")
        self.sources("[E3-E5, E10] selected reports, their exact seeds and source SHA-256 maps. New barrier results are reported separately in [E11].")

        self.page("What has and has not been measured","11 | Evaluator assurance is not a model leaderboard")
        self.p(f"<b>New model-solver trials: {e.no_models}. New physical-robot trials: 0.</b> This phase measures evaluator stress tests, proof/certificate checks and scripted controls. Independent oracle and reviewer work was internal AI-assisted verification, not external human or laboratory replication. Evaluator access prevents labeling this development process a blind scored solver run.")
        controls=e.manifest.get("scripted_controls",{})
        policies=controls.get("policies",{}) if isinstance(controls,dict) else {}
        if policies:
            rows=[]
            for key,label in (("evidence","Public-tool reference"),("blind","Blind completion"),("abstain","Always abstain")):
                policy=policies.get(key,{})
                rows.append([label,f"{number(policy.get('answerable_successes'))} / {number(policy.get('answerable'))}",f"{number(policy.get('correct_unanswerable_abstentions'))} / {number(policy.get('unanswerable'))}"])
            self.table(["New v0.3 scripted control","Answerable success","Correct abstention"],rows,[1.4,1.0,1.0],compact=True)
            self.p(f"All {number(controls.get('stored_traces_rechecked'))} stored traces were rechecked; each policy used the same 990-episode design. These are constructive/negative controls, not LLM scores.","small")
        self.h("Historical results retain their original qualifications")
        self.p("The v0.2 package separately recorded 2,700 control episodes and exploratory sparse, robotics and proof completions. Those assistant trials had shared-host isolation/provenance limitations, with earlier sparse context exposure. They remain historical exploratory artifacts, not new or clean comparative scores.")
        self.h("A stronger future experiment")
        self.p("Freeze the exact task version, permitted tools, input domains, budgets and score definitions before running models. Keep model identity, deployment, prompts, sampling, retries, context/skill conditions, token and tool costs, and all excluded attempts. Use independent solver isolation, hidden structural test families, preregistered ablations, and independent task/checker review.")
        self.table(["Question","Evidence still needed"],[
            ["Does active information acquisition help?","Matched-information static versus active evidence; record what each condition can observe."],
            ["Does the causal masking choice matter?","Complete procedure, random omission and causal omission with appropriate information/token controls."],
            ["Are tasks challenging for strong systems?","Real model and human comparisons, strong legal baselines, failure analysis and structural holdouts."],
            ["Is the contribution new?","Comparison with established infilling, formal proof, active learning, skill and operational benchmarks; independent replication."],
        ],[1.2,2.8],compact=True)
        self.sources("[E1] final manifest; historical reports/build-verification.json and v0.2 development manifest; [R2, R4-R7] prior work.")

        self.page("Reproduce and inspect the release","12 | Exact artifacts before external claims")
        self.p("The source package preserves before-fix reports, current follow-ups, exact seeds, source fingerprints and standalone audit scripts. The report builder consumes the v0.3 verification manifest and individual evidence records. It does not silently relabel earlier failed runs as current passes.")
        self.code("python -m unittest discover -s tests -v\npython tools/stress_formal.py --output reports/stress-v0.3/formal-results.json\npython tools/stress_protocol.py --help\npython tools/stress_operations.py --help\npython formal/verify.py --toolchain /path/to/lean-4.35.0-linux\npython tools/build_stress_report.py")
        self.p("Use the exact recorded arguments for the protocol, operational and barrier runs; --help exposes their local interfaces. Run Lean verification from the documented project layout. The pinned release toolchain hash and command exit codes are in the formal verification evidence. The two generated theorem files also require their companion core project.","small")
        self.h("Inspect the complete proof attachments")
        self.p("This PDF embeds both original statement/fill JSON pairs, both full exported Lean modules and manifests, the common Lean sources, the pinned project configuration, and the Lean verification record. Extract attachments preserving their stored relative paths, or use the same files from the source package. The attachment readme lists the contents and SHA-256 values.")
        self.h("Final release gates")
        self.p("The final Python suite, current stress reports, Lean axiom gate, two exact round trips, independent workflow audit and new barrier audit should agree with the frozen source version. Re-run affected gates after changes. Preserve failure examples and limitations. External publication, repository deployment and leaderboard submission require separate authorization and are not part of this authoring task.")
        if e.manifest:
            digest=hashlib.sha256(e.manifest_path.read_bytes()).hexdigest()
            self.p("Verification-manifest SHA-256:","caption");self.p(digest,"code")
            fingerprint=e.manifest.get("source_sha256",e.manifest.get("source_fingerprint"))
            if isinstance(fingerprint,str):
                self.p("Recorded source fingerprint:","caption");self.p(escape(fingerprint),"code")
        else:
            self.note("Draft provenance", "The final v0.3 manifest has not yet been supplied. Source-bound final totals and release metadata will appear here when it is available.",AMBER)
        self.p("A digest identifies bytes relative to a trusted copy; it is not an author signature. Lean proves the exact typed statement, not the scientific significance of the benchmark. A geometric impossibility certificate establishes the declared observation dependency, not an empirical lower bound on model computation.","small")
        self.sources("[E1, E6, E10-E11] final verification manifest, Lean gate and recorded standalone audit commands.")

        self.page("Primary references and evidence ledger","13 | Credit the ingredients; delimit the contribution")
        references=[
            ("R1","Lean: Axioms and Computation","https://lean-lang.org/theorem_proving_in_lean4/Axioms-and-Computation/","Official account of Lean's standard logical principles and the distinction between kernel reduction and compiled computation."),
            ("R2","Axiom, Proof of Concept","https://axiommath.ai/research/proof-of-concept/","Primary description of generating proof artifacts accepted by Lean/Mathlib. The present project formalizes ordinary finite resolution; it does not reproduce Axiom's mathematics."),
            ("R3","J. A. Robinson, 1965","https://doi.org/10.1145/321250.321253","A Machine-Oriented Logic Based on the Resolution Principle. Foundational resolution prior art; DOI provided for attribution."),
            ("R4","miniF2F","https://github.com/openai/miniF2F","Existing cross-system formal mathematics benchmark."),
            ("R5","VERINA","https://github.com/sunblaze-ucb/verina","Benchmark for code, specification and proof generation and their combinations."),
            ("R6","Vending-Bench 2","https://andonlabs.com/evals/vending-bench-2","Primary operational benchmark with a much longer business horizon and different environment mechanics."),
            ("R7","SkillsBench","https://github.com/benchflow-ai/skillsbench","Agent-skill evaluation and task-verification prior work."),
            ("R8","Bshouty and Haddad-Zaknoon, ALT 2019","https://proceedings.mlr.press/v98/bshouty19a.html","Adaptive exact learning from membership queries; query-learning context rather than a claim that this finite-table checker implements that paper."),
        ]
        for tag,title,url,note in references:
            self.p(f"<b>[{tag}] <link href='{url}' color='#007F7D'>{escape(title)}</link>.</b> {escape(note)}","small")
            self.p(f"<link href='{url}' color='#007F7D'>{escape(url)}</link>","path")
        self.p("Primary web sources checked November 1, 2026. The Robinson DOI endpoint denied automated retrieval; its bibliographic entry is attribution, not a newly verified result. No benchmark tasks, model weights or third-party proof claims are reproduced here.","caption")
        self.h("Local evidence keys")
        local=[
            ("E1","reports/build-verification-v0.3.json"),
            ("E2-E4","Historical: reports/stress-v0.3/operations-baseline.json and operations.json. Current: "+e.path_label("operations")+"; "+e.path_label("workflow_followup")),
            ("E5","Historical: reports/stress-v0.3/protocol-baseline.json. Current: "+e.path_label("protocol")),
            ("E6-E7","formal/verification/results.json; docs/formal-assurance.md; formal/CausalFill/*"),
            ("E8","docs/workflow-certification.md; reports/stress-v0.3/workflow-independent-audit.json; formal-workflow-verification.json"),
            ("E9","reports/certificates/same-statement-comparison.json"),
            ("E10","reports/stress-v0.3/formal-results.json; tools/stress_formal.py"),
            ("E11",e.path_label("barrier")+"; docs/robotics-barrier.md"),
        ]
        for key,path in local:self.p(f"<b>{key}</b> "+escape(path),"caption")
        self.p("The meaningful advance in this release is a more explicit relationship between a claim, its assumptions, its independently checkable artifact, and the tests capable of falsifying its implementation. Model capability and scientific novelty remain questions for a separately controlled study.","small")
        return self.pages


def attachment_sources(e: Evidence) -> dict[str, bytes]:
    paths=[
        "formal/lean-toolchain", "formal/lakefile.lean", "formal/CausalFill.lean",
        "formal/CausalFill/Resolution.lean", "formal/CausalFill/Examples.lean", "formal/CausalFill/Audit.lean",
        "formal/CausalFill/ReleaseModel.lean", "formal/CausalFill/ReleaseReference.lean",
        "formal/CausalFill/ReleaseModel.manifest.json", "formal/CausalFill/ReleaseReference.manifest.json",
        "reports/certificates/model-statement.json", "reports/certificates/model-fill.json",
        "reports/certificates/reference-statement.json", "reports/certificates/reference-fill.json",
        "formal/verification/results.json", "formal/export_certificate.py", "formal/verify.py",
    ]
    if e.manifest_path.exists():
        try: paths.append(str(e.manifest_path.relative_to(ROOT)))
        except ValueError: pass
    result={path:(ROOT/path).read_bytes() for path in paths if (ROOT/path).exists()}
    readme=["CausalFill-Bench v0.3 - complete proof attachments", "",
            "Preserve the stored relative paths when extracting. These are the full two exported Lean proofs, original statement/fill inputs, their manifests, common project, and verification evidence.",
            "The PDF discusses their scope and trust boundaries. The source archive remains the complete benchmark release.", "", "SHA-256:"]
    for path, content in result.items():readme.append(hashlib.sha256(content).hexdigest()+"  "+path)
    result["ATTACHMENTS-README.txt"]=("\n".join(readme)+"\n").encode()
    return result


def decorate(c: canvas.Canvas, page: int, total: int, e: Evidence):
    c.saveState()
    c.setStrokeColor(LINE);c.line(MARGIN,H-39,W-MARGIN,H-39)
    c.setFillColor(MUTED);c.setFont("CFSans",7.3)
    c.drawString(MARGIN,H-29,"CAUSALFILL-BENCH  /  STRESS + FORMAL ASSURANCE")
    c.drawRightString(W-MARGIN,H-29,"DRAFT" if e.draft else f"v{e.version}")
    c.setStrokeColor(LINE);c.line(MARGIN,45,W-MARGIN,45)
    c.setStrokeColor(TEAL);c.setLineWidth(1.8);c.line(MARGIN,45,MARGIN+CONTENT*page/total,45)
    c.setFillColor(MUTED);c.setFont("CFSans",7)
    c.drawString(MARGIN,29,f"{e.date}  |  Phillip A. Holland Jr.  |  AI-assisted research prototype")
    c.drawRightString(W-MARGIN,29,f"{page:02d} / {total:02d}")
    c.restoreState()


def build(e: Evidence, destination: Path, render_dir: Path | None = None) -> dict:
    register_fonts()
    report=Report(e);pages=report.compose()
    if not 10<=len(pages)<=14:raise ValueError("report must contain 10-14 deliberately composed pages")
    temporary=ROOT/"tmp/pdfs";temporary.mkdir(parents=True,exist_ok=True)
    layout=temporary/"stress-report-layout.pdf"
    c=canvas.Canvas(str(layout),pagesize=A4,pageCompression=1)
    c.setTitle("CausalFill-Bench: Stress Testing and Formal Assurance v0.3")
    c.setAuthor("Phillip A. Holland Jr.; AI-assisted development")
    c.setSubject("Evaluator integrity, exact proof artifacts, symbolic guarantees, operational shortcuts, and scoped research claims")
    for index,(title,flowables) in enumerate(pages,1):
        decorate(c,index,len(pages),e)
        frame=Frame(MARGIN,62,CONTENT,H-118,leftPadding=0,rightPadding=0,topPadding=0,bottomPadding=0)
        remaining=list(flowables)
        frame.addFromList(remaining,c)
        if remaining:
            raise RuntimeError(f"Layout overflow on page {index} ({title}): {len(remaining)} remaining flowables")
        c.showPage()
    c.save()
    attachments=attachment_sources(e)
    reader=PdfReader(str(layout));writer=PdfWriter();writer.clone_document_from_reader(reader)
    for name,content in attachments.items():writer.add_attachment(name,content)
    writer.add_metadata({"/Title":"CausalFill-Bench: Stress Testing and Formal Assurance v0.3",
                         "/Author":"Phillip A. Holland Jr.; AI-assisted development",
                         "/Keywords":"CausalFill-Bench, Lean, resolution, workflow certification, evaluator integrity, research prototype"})
    destination.parent.mkdir(parents=True,exist_ok=True)
    with destination.open("wb") as stream:writer.write(stream)
    reopened=PdfReader(str(destination))
    if len(reopened.pages)!=len(pages):raise RuntimeError("page count changed during attachment embedding")
    if len(reopened.attachments)!=len(attachments):raise RuntimeError("attachment inventory is incomplete")
    extracted="\n".join(page.extract_text() or "" for page in reopened.pages)
    if "\ufffd" in extracted:raise RuntimeError("replacement character in extracted text")
    for required in ("0b2fbd2916a4bf10d536aada3c30467b8713b59ca0592f5a6e8e044b6fda9298",
                     "7ef0583aa6f7a0b3c26a8d8ed32ac4ff2605c3d68b534e3c2918f82e6016c77a"):
        if required not in extracted.replace("\n",""):raise RuntimeError("full release statement commitment missing from PDF text")
    if render_dir:
        render_dir.mkdir(parents=True,exist_ok=True)
        subprocess.run(["pdftoppm","-r","100","-png",str(destination),str(render_dir/"page")],check=True)
    return {"output":str(destination),"pages":len(pages),"embedded_attachments":len(attachments),
            "bytes":destination.stat().st_size,"draft":e.draft,
            "pdf_sha256":hashlib.sha256(destination.read_bytes()).hexdigest(),
            "manifest":str(e.manifest_path),"selected_evidence":{key:str(path) for key,path in e.paths.items()},
            "visual_qa_required":True,"render_directory":str(render_dir) if render_dir else None}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest",type=Path,default=DEFAULT_MANIFEST)
    parser.add_argument("--output",type=Path)
    parser.add_argument("--draft",action="store_true")
    parser.add_argument("--render",type=Path,help="Render all pages to this temporary directory for visual inspection.")
    args=parser.parse_args()
    output=args.output or (ROOT/"tmp/pdfs/CausalFill_Stress_and_Formal_Report_v0.3_DRAFT.pdf" if args.draft else DEFAULT_OUTPUT)
    print(json.dumps(build(Evidence(args.manifest,args.draft),output,args.render),indent=2))


if __name__=="__main__":main()
