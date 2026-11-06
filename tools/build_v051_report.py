#!/usr/bin/env python3
"""Create the source-bound CausalFill-Bench v0.5.1 release report.

The consolidated release-verification record must exist and pass before this
tool writes a PDF. ReportLab and Pillow are authoring dependencies only. The
tool does not run evaluators, classify novelty, or manufacture missing results.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
from html import escape
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph


ROOT = Path(__file__).resolve().parents[1]
WIDTH, HEIGHT = A4
MARGIN = 47
CONTENT = WIDTH - 2 * MARGIN
PAGES = 14
PAL = {
    "ink": "#172B43", "deep": "#102037", "paper": "#F6F4ED",
    "white": "#FFFFFF", "muted": "#52647B", "line": "#D7DFE8",
    "blue": "#2455D9", "blue_light": "#EAF0FF", "teal": "#126B52",
    "teal_light": "#E5F5EC", "mint": "#87E3BA", "amber": "#825000",
    "amber_light": "#FFF0D9", "light": "#BDCBDD",
}
FONT_FILES = {
    "CF": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "CF-Bold": "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "CF-Mono": "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
}
REFERENCES = [
    ("Ulam's liar game", "Osthus and Watkinson (2008). A simple solution to Ulam's liar game with one lie.",
     "https://ems.press/content/serial-article-files/45347?nt=1"),
    ("Decision-region determination", "Javdani et al. (2014). Near Optimal Bayesian Active Learning for Decision Making.",
     "https://proceedings.mlr.press/v33/javdani14.html"),
    ("Environment design", "Dennis et al. (2020). Emergent Complexity and Zero-shot Transfer via Unsupervised Environment Design.",
     "https://proceedings.neurips.cc/paper_files/paper/2020/hash/985e9a46e10005356bbaf194249f6856-Abstract.html"),
    ("Partial observation", "Kaelbling, Littman and Cassandra (1998). Planning and acting in partially observable stochastic domains.",
     "https://people.csail.mit.edu/lpk/papers/aij98-pomdp.pdf"),
    ("ARC-AGI-3", "ARC Prize Foundation (2026). ARC-AGI-3 technical report.",
     "https://arcprize.org/media/ARC_AGI_3_Technical_Report.pdf"),
    ("Vending-Bench 2", "Andon Labs. Persistent simulated business operations and delayed consequences.",
     "https://andonlabs.com/evals/vending-bench-2"),
    ("Proof-producing research", "Axiom. Proof of Concept.",
     "https://axiommath.ai/research/proof-of-concept/"),
    ("OpenAI mathematics", "OpenAI. Public mathematical research repository.",
     "https://github.com/openai/math"),
    ("Scientific context", "OpenAI. Working with academic communities to build scientific understanding.",
     "https://openai.com/index/building-scientific-understanding-with-academic-communities/"),
    ("Skills evaluation", "SkillsBench. Paired evaluation of skills for tool-using agents.",
     "https://github.com/benchflow-ai/skillsbench"),
    ("Proof checker", "Lean 4.35.0 release documentation.",
     "https://lean-lang.org/doc/reference/latest/releases/v4.35.0/"),
    ("Adversarial robustness", "OpenAI. GPT-Red: Unlocking Self-Improvement for Robustness.",
     "https://openai.com/index/unlocking-self-improvement-gpt-red/"),
]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def clean(value: Any) -> str:
    return str(value).replace("\u2011", "-").replace("\u2013", "-").replace("\u2014", "-").replace("\u2212", "-")


def number(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("Expected a recorded nonnegative integer, got " + repr(value))
    return f"{value:,}"


def count(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("A Boolean is not a count.")
    if isinstance(value, int):
        return value
    if isinstance(value, (list, dict)):
        return len(value)
    raise ValueError("Expected an integer count or explicit collection.")


def shown(value: Any) -> str:
    if value is None:
        return "Not recorded"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, int):
        return number(value)
    if isinstance(value, float):
        return f"{value:,.2f}".rstrip("0").rstrip(".")
    if isinstance(value, list):
        return ", ".join(shown(v) for v in value)
    if isinstance(value, dict):
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    return clean(value)


def passed(value: Any) -> bool:
    return value is True or isinstance(value, str) and value.lower() in {"passed", "pass", "verified", "complete", "success"}


class Report:
    def __init__(self, output: Path, data: dict[str, Any], source: Path):
        self.data, self.source, self.output = data, source, output
        for name, file in FONT_FILES.items():
            pdfmetrics.registerFont(TTFont(name, file))
        pdfmetrics.registerFontFamily("CF", normal="CF", bold="CF-Bold", italic="CF", boldItalic="CF-Bold")
        self.c = canvas.Canvas(str(output), pagesize=A4, pageCompression=1)
        self.c.setTitle("CausalFill-Bench v0.5.1 - Signal Repair research report")
        self.c.setAuthor("Phillip A. Holland Jr. | AI-assisted research and implementation")
        self.c.setSubject("Source-bound release evidence, bounded-fault decisions, formal scope and experimental limits")
        self.c.setCreator("CausalFill-Bench original report builder")
        self.page = 0
        self.y = 0.0
        self.page_records: list[dict[str, Any]] = []

    def color(self, key):
        return colors.HexColor(PAL.get(key, key))

    def rect(self, x, y, w, h, fill, radius=0, border=None):
        self.c.setFillColor(self.color(fill))
        self.c.setStrokeColor(self.color(border or fill))
        self.c.setLineWidth(.6)
        self.c.roundRect(x, HEIGHT-y-h, w, h, radius, stroke=bool(border), fill=1)

    def text(self, x, y, value, size=10.5, color="ink", bold=False, mono=False):
        self.c.setFillColor(self.color(color))
        self.c.setFont("CF-Mono" if mono else "CF-Bold" if bold else "CF", size)
        self.c.drawString(x, HEIGHT-y, clean(value))

    def line(self, x1, y1, x2, y2, color="line", width=.6):
        self.c.setStrokeColor(self.color(color))
        self.c.setLineWidth(width)
        self.c.line(x1, HEIGHT-y1, x2, HEIGHT-y2)

    def mark(self, x, y, size=28, dark=False):
        s = size / 80
        self.c.saveState()
        self.c.translate(x, HEIGHT-y-size)
        self.c.scale(s, s)
        self.c.setStrokeColor(self.color("paper" if dark else "ink"))
        self.c.setLineWidth(8)
        self.c.setLineCap(1)
        p = self.c.beginPath()
        p.moveTo(52,70); p.lineTo(23,70); p.curveTo(10,70,10,65,10,57)
        p.lineTo(10,23); p.curveTo(10,10,15,10,23,10)
        p.lineTo(57,10); p.curveTo(70,10,70,15,70,23); p.lineTo(70,41)
        self.c.drawPath(p)
        self.c.setFillColor(self.color("mint" if dark else "blue"))
        self.c.roundRect(57,57,21,21,4,stroke=0,fill=1)
        self.c.setStrokeColor(self.color("amber" if not dark else "mint"))
        self.c.setLineWidth(2.5); self.c.setDash(3,4)
        self.c.roundRect(31,31,19,19,3,stroke=1,fill=0)
        self.c.restoreState()

    def paragraph(self, value, x=None, y=None, width=None, size=10.5, leading=None, color="ink", bold=False,
                  gap=8, advance=True):
        x = MARGIN if x is None else x
        y = self.y if y is None else y
        width = CONTENT if width is None else width
        style = ParagraphStyle("body", fontName="CF-Bold" if bold else "CF", fontSize=size,
                               leading=leading or size*1.47, textColor=self.color(color), alignment=TA_LEFT,
                               spaceAfter=0, allowWidows=0, allowOrphans=0, splitLongWords=True)
        paragraph = Paragraph(escape(clean(value)).replace("\n", "<br/>"), style)
        _, h = paragraph.wrap(width, HEIGHT)
        if y + h > HEIGHT - 61:
            raise ValueError(f"Page {self.page} content overflows: {clean(value)[:90]}")
        paragraph.drawOn(self.c, x, HEIGHT-y-h)
        if advance:
            self.y = y + h + gap
        return h

    def new_page(self, section, title, deck="", evidence=None):
        if self.page:
            self.finish_page()
            self.c.showPage()
        self.page += 1
        self.rect(0, 0, WIDTH, HEIGHT, "paper")
        self.mark(MARGIN, 26, 24)
        self.text(MARGIN+34, 43, "CAUSALFILL / RESEARCH REPORT", 8.3, "muted", True)
        self.text(WIDTH-MARGIN-30, 43, "0.5.1", 8.3, "muted", mono=True)
        self.line(MARGIN, 60, WIDTH-MARGIN, 60)
        self.text(MARGIN, 88, section.upper(), 8.5, "blue", True)
        self.y = 104
        self.paragraph(title, size=28, leading=34, bold=True, gap=13)
        if deck:
            self.paragraph(deck, size=10.8, leading=16, color="muted", gap=14)
        if evidence:
            labels = {"measured": ("Measured", "blue", "blue_light"), "formal": ("Formally checked", "teal", "teal_light"), "proposed": ("Proposed", "amber", "amber_light")}
            text, color, bg = labels[evidence]
            w = pdfmetrics.stringWidth(text, "CF-Bold", 8.3)+20
            self.rect(MARGIN, self.y, w, 20, bg, 9)
            self.text(MARGIN+10, self.y+13.5, text, 8.3, color, True)
            self.y += 33
        self.page_records.append({"page": self.page, "section": section, "title": title})

    def finish_page(self):
        self.line(MARGIN, HEIGHT-47, WIDTH-MARGIN, HEIGHT-47)
        self.text(MARGIN, HEIGHT-29, "Phillip A. Holland Jr. / AI-assisted research", 7.2, "muted")
        label = f"{self.page:02d} / {PAGES}"
        self.text(WIDTH-MARGIN-36, HEIGHT-29, label, 8, "muted", mono=True)

    def heading(self, value):
        self.y += 2
        self.paragraph(value, size=13.1, leading=17.5, bold=True, gap=6)

    def note(self, label, body, kind="blue"):
        bg = {"blue":"blue_light", "teal":"teal_light", "amber":"amber_light"}[kind]
        y = self.y
        style = ParagraphStyle("note", fontName="CF", fontSize=10, leading=14.5, textColor=self.color("ink"))
        p = Paragraph(escape(clean(body)), style)
        _, ph = p.wrap(CONTENT-28, HEIGHT)
        h = 40+ph
        if y+h > HEIGHT-61:
            raise ValueError(f"Page {self.page} note overflows: {label}")
        self.rect(MARGIN, y, CONTENT, h, bg, 9)
        self.text(MARGIN+14, y+22, label.upper(), 8.5, kind, True)
        p.drawOn(self.c, MARGIN+14, HEIGHT-y-34-ph)
        self.y += h+10

    def kpis(self, cells):
        columns = 2 if len(cells) in (2,4) else 3
        gap, h = 11, 104
        w = (CONTENT-(columns-1)*gap)/columns
        start = self.y
        for i, (value, label, scope) in enumerate(cells):
            x, y = MARGIN+(i%columns)*(w+gap), start+(i//columns)*(h+gap)
            self.rect(x, y, w, h, "white", 10, "line")
            size = 28
            while pdfmetrics.stringWidth(clean(value), "CF-Mono", size) > w-25 and size > 16:
                size -= 1
            self.text(x+13, y+36, value, size, "ink", mono=True)
            self.paragraph(label, x+13, y+49, w-26, 9.1, 12.5, bold=True, advance=False)
            self.paragraph(scope, x+13, y+76, w-26, 7.8, 10.5, color="muted", advance=False)
        self.y = start + ((len(cells)+columns-1)//columns)*(h+gap)

    def table(self, headers, rows, fractions, size=9.4):
        widths = [CONTENT*f/sum(fractions) for f in fractions]
        all_rows = [headers]+rows
        for ri, row in enumerate(all_rows):
            style = ParagraphStyle("cell", fontName="CF-Bold" if ri==0 else "CF", fontSize=8.1 if ri==0 else size,
                                   leading=11.3 if ri==0 else size*1.38,
                                   textColor=self.color("white" if ri==0 else "ink"), splitLongWords=True)
            ps, heights = [], []
            for value, width in zip(row, widths):
                p=Paragraph(escape(clean(value)).replace("\n","<br/>"),style)
                _,hh=p.wrap(width-16,HEIGHT)
                ps.append(p); heights.append(hh)
            rh=max(heights)+16
            if self.y+rh>HEIGHT-62:
                raise ValueError(f"Page {self.page} table exceeds page at row {ri}")
            self.rect(MARGIN,self.y,CONTENT,rh,"ink" if ri==0 else "white" if ri%2 else "blue_light")
            xx=MARGIN
            for p,hh,ww in zip(ps,heights,widths):
                p.drawOn(self.c,xx+8,HEIGHT-self.y-9-hh); xx+=ww
            self.y+=rh
        self.y+=12

    def source_note(self, value):
        self.paragraph("Source: "+value,size=7.6,leading=11,color="muted",gap=8)

    def cost_chart(self, profiles):
        grouped=defaultdict(list)
        for p in profiles:
            grouped[(p["split"],p["difficulty"])].append(p)
        order={"train":0,"dev":1,"transfer":2}
        keys=sorted(grouped,key=lambda k:(order.get(k[0],3),k[1]))
        xmax=max(p["certified_operational_budget"] for p in profiles)
        plot_x=MARGIN+102; plot_w=CONTENT-155; row_h=34
        top=self.y+20
        for tick in range(xmax+1):
            if xmax>14 and tick%2:
                continue
            xx=plot_x+plot_w*tick/xmax
            self.line(xx,top-12,xx,top+len(keys)*row_h-16)
            self.text(xx-2.3,top-19,str(tick),8,"muted",mono=True)
        for i,key in enumerate(keys):
            row=grouped[key]; yy=top+i*row_h
            lo=min(p["certified_operational_budget"] for p in row)
            hi=max(p["certified_operational_budget"] for p in row)
            self.text(MARGIN,yy+4,f"{key[0]} / d{key[1]}",9.5,"ink",True)
            xlo=plot_x+plot_w*lo/xmax; xhi=plot_x+plot_w*hi/xmax
            self.line(plot_x,yy,xhi,yy,"line",5)
            self.line(xlo,yy,xhi,yy,"blue",7)
            self.c.setFillColor(self.color("blue"))
            self.c.circle(xlo,HEIGHT-yy,3.7,stroke=0,fill=1)
            self.c.circle(xhi,HEIGHT-yy,3.7,stroke=0,fill=1)
            self.text(plot_x+plot_w+13,yy+3,f"{lo}" if lo==hi else f"{lo}-{hi}",9,"ink",mono=True)
        self.y=top+len(keys)*row_h+6
        self.paragraph("Certified operational cost: queries plus the terminal action. Dots show the minimum and maximum across recorded seeds, not a confidence interval.",size=8.8,leading=13,color="muted",gap=12)

    def build(self):
        d=self.data; unit=d["unit_and_integration_tests"]; robust=d["robust_sensing"]
        checks=robust["checks"]; runtime=robust["runtime"]; formal=d["formal_assurance"]; pilot=d["assistant_pilot"]
        self.cover()

        self.new_page("01 / Release evidence", "Inspectable evidence", "The release combines executable masked tasks, budgeted observations and acceptance rules. Its strongest claim is about what has been checked under explicit models.", "measured")
        self.kpis([
            (number(unit["tests"]),"Unit and integration tests",f'{number(unit["failed"])} failures; {number(unit["errors"])} errors'),
            (number(checks["independent_optimum"]),"Independent optimum comparisons","Finite models and objectives"),
            (number(checks["certificate_mutation_rejected"]),"Certificate mutations rejected","Specified mutation families"),
            (f'{number(pilot["successes"])} / {number(pilot["episodes"])}',"Assistant pilot episodes passed","Small development pilot"),
        ])
        self.heading("Three evidence classes")
        self.table(["Label","What it supports"],[
            ["Measured","An observed test, replay, episode or implementation property in the recorded configuration."],
            ["Formally checked","A named theorem accepted by the listed proof-checking configurations, under its stated assumptions."],
            ["Proposed","A future experiment, generalization claim or research goal that this release has not established."],
        ],[.27,.73],9.7)
        self.note("Interpretation", "These counts use different units and must not be added into an intelligence score. The report separates scripted controls, finite certificate audits, formal theorem checks and a small assistant pilot.")
        self.source_note("reports/v051/release-verification.json; exact record hash on page 12.")

        self.new_page("02 / Benchmark contract", "One protocol, several kinds of missing information", f'{number(d["task_configurations"])} runnable configurations across {number(d["conceptual_domains"])} conceptual domains. Signal Repair adds robust_sensing to the diagnosis and decision domain.')
        self.table(["Domain","Configurations","What must be completed"],[
            ["Routing words","words, ambiguity","A condition or a justified abstention"],
            ["Executable workflow","workflow","An expression meeting a restricted semantic contract"],
            ["Grid induction","grid","A transformation inferred from examples and experiments"],
            ["Procurement","vending, vending_adaptive","An operational purchasing procedure"],
            ["Robotics in simulation","robotics, robotics_barrier, robotics_vision","A geometry-dependent plan or controlled image-to-action choice"],
            ["Mathematical state","latent, latent_sparse","A finite-field operator or sparse structure"],
            ["Proof completion","proof","A proof of a fixed claim with a consistency witness"],
            ["Diagnosis and decision","diagnosis, robust_sensing","A justified state or robust terminal action"],
            ["Controlled vision","visual","Pixel-derived spatial facts and an executable choice"],
        ],[.25,.32,.43],9.2)
        self.note("Common contract", "A public episode exposes the missing component and permitted tools. The agent spends a declared budget, submits a typed completion, and faces evaluator-owned acceptance checks.")
        self.paragraph("The computer interface is a virtual workspace with typed tools. The image and robotics tasks use controlled renderings and small simulations. Their results do not establish real desktop competence or physical robot transfer.",size=10)
        self.source_note("README.md; docs/protocol.md; docs/scoring.md.")

        self.new_page("03 / Signal Repair", "A shared fault cap changes what evidence means", "A fixed hidden world determines truthful binary sensor replies. Up to k replies may be flipped across the whole episode, and each listed query may be used once.")
        self.note("Information state", "For each world, retain its discrepancy count and the remaining queries. A world is feasible exactly when its discrepancy count is at most k. A set of surviving world IDs alone loses necessary fault-history information.")
        self.rect(MARGIN,self.y,CONTENT,62,"ink",8)
        self.text(MARGIN+16,self.y+25,"d_h(w) = number of replies disagreeing with world w",9.5,"white",mono=True)
        self.text(MARGIN+16,self.y+46,"possible(h) = { w : d_h(w) <= k }",10.2,"mint",mono=True)
        self.y+=80
        self.heading("Worked example: one possible flipped reply")
        self.paragraph("Two worlds require exclusive left/right actions. Three unit-cost queries all truthfully report 0 in the left world and 1 in the right world. A terminal action costs 2. The example illustrates the published model; it is not a model-evaluation episode.",size=10.2)
        self.table(["Query","Left truth","Right truth","Observed"],[
            ["sensor_a","0","1","1"],["sensor_b","0","1","0"],["sensor_c","0","1","0"],
        ],[.4,.2,.2,.2],10)
        self.paragraph("The left world needs one flip; the right world needs two. With k = 1, sensor_b and sensor_c are distinct observed contradictions that exclude the unsafe right world. The action can now be justified.",size=10.2)
        self.note("Exact example cost", "A policy can stop after two equal readings. Its worst-case action cost is 3 queries + 2 for the terminal action = 5. Identification alone costs 3. These are analytic fixture values, not a frontier score.")
        self.source_note("docs/robust-decisions.md; docs/robust-research.md.")

        self.new_page("04 / Certificate scope", "An attaining policy is only half the argument", "The release separates exact optimization, independent certificate checking, fixed-world policy replay and observed evidence checking.")
        self.table(["Component","Representation","Claim checked"],[
            ["Optimizer","Disjoint world bitmasks at each fault-debt layer","Proposes state values and attaining choices"],
            ["Exact certificate checker","Integer discrepancy tuples and explicit world sets","All available alternatives and feasible observation children"],
            ["Policy replay","A fixed world and the faults actually consumed","Successful execution and an upper cost bound"],
            ["Completion evidence","Distinct accepted observations from the transcript","At least k+1 contradictions for each unsafe world"],
        ],[.25,.35,.40],9.7)
        self.heading("The exact finite objective")
        self.paragraph("At a nonempty feasible state, consider every action that succeeds in every remaining world and every unasked query. A query contributes its cost plus the worst feasible child value. The minimum is the exact guaranteed cost. An impossible continuation remains distinct from zero and from a missing row.")
        self.rect(MARGIN,self.y,CONTENT,58,"ink",8)
        self.text(MARGIN+15,self.y+24,"V(state) = min(safe terminal costs,",10.3,"white",mono=True)
        self.text(MARGIN+15,self.y+44,"               query cost + max(child values))",10.3,"mint",mono=True)
        self.y+=75
        self.note("Why the distinction matters", "A replayed policy may be valid but needlessly expensive. Exactness requires checking every legal alternative, including queries the attaining policy does not choose. The zero-cost safe-action shortcut follows from nonnegative costs.")
        self.paragraph("The Python finite-state certificate is not itself a Lean proof of the optimizer or of the runtime. The separately checked generic Lean statements have a narrower scope, described on page 8.",size=10)
        self.source_note("docs/robust-decisions.md; formal scope recorded in release-verification.json.")

        self.new_page("05 / Exact cost profiles", "A budget grounded in attainable cost", "Source-derived costs for the recorded runtime profiles. These synthetic operational units measure permitted sensing and commitment, not tokens, dollars or elapsed time.", "measured")
        self.cost_chart(runtime["profiles"])
        self.paragraph(f'{number(len(runtime["profiles"]))} profile records cover {number(runtime["cases"])} fixed-world/fault cases. The runtime checks recorded {number(checks["runtime_bound_attained"])} attained profile bounds.',size=10.2)
        self.note("Read the units", "The certified operational budget covers domain probes and the terminal action. Public-file reads and fill-envelope work may have separate tool costs. A lower cost in one structural family is not evidence that it is easier for a language model.")
        self.source_note("release-verification.json / robust_sensing.runtime.profiles and checks.runtime_bound_attained.")

        self.new_page("06 / Independent audit", "Stress tests aimed at concrete failure modes", "Different representations and analytic fixtures challenge the implementation from several directions. Coverage counts remain tied to their own units.", "measured")
        tiny=robust["complete_tiny_corpus"]
        self.kpis([
            (number(tiny["models"]),"Complete tiny models",f'{number(tiny["objectives_per_model"])} objectives per model'),
            (number(robust["random_models"]),"Additional random models","Deterministic recorded generation"),
            (number(checks["certificate_mutation_rejected"]),"Mutant artifacts rejected","Targeted certificate alterations"),
            (number(runtime["cases"]),"Executed runtime cases","World/fault assignments in profiles"),
        ])
        self.table(["Audit","Recorded count","Interpretation"],[
            ["Independent optima",number(checks["independent_optimum"]),"Optimizer versus independently represented exact oracle"],
            ["Policy replay",number(checks["independent_policy_replay"]),"Fixed-world corruption histories"],
            ["Analytic formula cases",number(checks["analytic_cube_formula"]),"Weighted cube family with derived cost"],
            ["Oracle states",number(robust["independent_oracle_states"]),"Finite search coverage; not independent tasks"],
            ["Certificate state occurrences",number(robust["verified_certificate_state_occurrences"]),"Occurrences across checks; repeats are possible"],
        ],[.35,.19,.46],9.1)
        self.paragraph("Mutations target stale model digests, wrong optima, duplicate states, missing roots and objective confusion. Additional checks exercise cost scaling, renaming and bit polarity, corruption monotonicity, and query-addition monotonicity.",size=9.7)
        self.source_note("reports/robust-stress-v0.5.1/result.json via the consolidated record. Tiny-corpus scope: "+tiny["scope"])

        self.new_page("07 / Formal assurance", "Generic guarantees with an explicit boundary", "The formal gate concerns declared Lean theorem statements. It is separate from the finite Python optimal-cost certificate and the executed task runtime.", "formal")
        self.kpis([
            (number(count(formal["roots"])),"Audited theorem roots","Required root inventory"),
            (number(count(formal["checker_configurations"])),"Checker configurations","Recorded proof-checking backends"),
            (number(count(formal["valid_kernel_checks"])),"Valid kernel checks","Accepted exported proof artifacts"),
        ])
        self.heading("What the generic statements cover")
        self.paragraph("The bounded-fault development formalizes discrepancy accounting, preservation of a true world within the global fault cap, permanent exclusion after too many contradictions, occurrence-supported witnesses, and justified actions over overlapping success regions.")
        self.paragraph("These claims assume one fixed true world in the published world list and an actual corruption count within the cap. The occurrence-based Lean witness and the runtime's once-only experiment-ID witness still require an explicit correspondence boundary.",size=10.1)
        self.note("Not established by this formal gate", "The Bellman optimizer's exact result, general Python/Lean equivalence, sensor-table correctness, fault bounds on physical hardware, physical execution and frontier-model difficulty remain outside these generic theorem statements.","teal")
        self.paragraph("Recorded allowed axioms: "+shown(formal["allowed_axioms"]),size=9.3)
        self.paragraph("The checker configurations share portions of the toolchain. Their count does not mean wholly independent proof stacks.",size=9.3)
        self.paragraph("Negative kernel checks: "+number(count(formal["negative_kernel_checks"]))+". Statement-binding and negative controls are retained in the formal source record; successful proof checking cannot substitute for checking that the intended statement was proved.",size=9.5)
        self.source_note(clean(formal["source_file"])+"; formal/verify_bounded_fault.py; docs/robust-research.md.")

        self.new_page("08 / Assistant pilot", "What the pilot establishes", "The pilot records public-interface attempts separately from scripted development controls. Its sample size and isolation conditions must travel with the success count.", "measured")
        self.kpis([(f'{number(pilot["successes"])} / {number(pilot["episodes"])}',"Pilot episodes passed","Observed development attempts"),
                   (shown(pilot["source_stable_during_run"]),"Core source stable","Fingerprint checked during pilot")])
        rows=[]
        for row in pilot["results"]:
            detail=row.get("verdict",{}).get("details",{})
            worlds=detail.get("compatible_worlds_at_commit")
            label=f'{row.get("split",row["label"])} d{row.get("difficulty","?")} / '+("pass" if row["success"] else "fail")
            rows.append([label,shown(detail.get("queries_used")),shown(detail.get("operational_cost")),
                         shown(count(worlds)) if isinstance(worlds,(list,dict)) else shown(worlds),
                         shown(detail.get("assigned_corruptions")),shown(detail.get("observed_corruptions"))])
        self.table(["Episode / result","Queries","Operation cost","Worlds left","Assigned faults","Observed faults"],rows,[.28,.12,.15,.13,.16,.16],8.7)
        self.paragraph("Assigned fault slots need not be queried. A bypass can succeed without observing a corrupted reply; action sufficiency can also leave several worlds unresolved.",size=9.5)
        all_pass=pilot["successes"]==pilot["episodes"]
        self.note("Hardness boundary", "All recorded pilot episodes succeeded. This is evidence against presenting this small pilot set as currently unsolved or frontier-hard. It motivates independent structural holdouts and stronger calibrated tests." if all_pass else "The recorded failures identify cases for analysis. This small pilot cannot establish broad model difficulty, a leaderboard ranking or a breakthrough.","amber")
        self.paragraph("OS-enforced solver isolation: "+shown(pilot["os_enforced_isolation"])+". Model inference telemetry available: "+shown(pilot["model_inference_telemetry_available"])+". Wall time is recorded execution time and must not be presented as inference latency.",size=9.5)
        self.source_note("release-verification.json / assistant_pilot; the source record retains tool cost and per-episode details.")

        self.new_page("09 / Scripted controls", "Controls and ablations", "These are restricted, task-aware development scripts. Their success counts measure behavior under the task contract, not trained-model capability.", "measured")
        controls=d["scripted_controls"]
        self.paragraph("Recorded control episodes: "+number(controls["records"])+". The table separates answerable completion from correct handling of deliberately unanswerable cases.")
        rows=[]
        for key,label in [("evidence","Task-aware evidence reference"),("blind","Blind control"),("abstain","Abstention control")]:
            row=controls["policies"][key]
            rows.append([label,number(row["episodes"]),f'{number(row["answerable_successes"])} / {number(row["answerable_episodes"])}',
                         f'{number(row["correct_unanswerable_abstentions"])} / {number(row["unanswerable_episodes"])}'])
        self.table(["Policy","Episodes","Answerable success","Correct unanswerable abstention"],rows,[.37,.15,.23,.25],9.7)
        self.heading("Signal Repair ablations")
        ablations=d["robust_ablation"]
        ablation_rows=[]
        for row in ablations["policies"]:
            total=number(row["episodes"])
            label={"assume_no_corruption":"Assume no corruption","query_every_sensor":"Query every sensor"}.get(row["mode"],row["mode"])
            ablation_rows.append([label,f'{number(row["strict_success"])} / {total}',
                                  f'{number(row["actual_operation_succeeded"])} / {total}',
                                  f'{number(row["justified_at_commit"])} / {total}'])
        self.table(["Restricted script","Strict success","Actual operation succeeded","Justified at commit"],ablation_rows,[.34,.19,.25,.22],9.1)
        self.note("Outcome and evidence differ", "A lucky action in the selected world does not establish that the action was justified across all compatible worlds. Conversely, requesting every sensor can spend resources that were needed for the terminal action.")
        self.paragraph("The next model study should freeze settings and compare matched with-skill and without-skill conditions. Preserve valid alternative strategies and report outcome, justification, cost and abstention separately.",size=9.6)
        self.source_note("release-verification.json / scripted_controls and robust_ablation; reports/v051/robust-ablation/summary.json; SkillsBench [10].")

        self.new_page("10 / Robotics relevance", "Choose a valid action before recovering every detail", "Signal Repair isolates a useful decision problem: act successfully across all remaining hypotheses while preserving resources for the action.", "proposed")
        self.table(["Controlled ingredient","Robotics interpretation","Separate validation needed"],[
            ["Finite worlds","Candidate object, route or fixture states","Coverage of real states and unmodeled obstacles"],
            ["Shared corruption cap","A bounded number of contradictory sensor reports","Justification of the fault bound and sensor table"],
            ["Overlapping success sets","Several scenes permit the same safe choice","Actuation, dynamics and geometry of each action"],
            ["Paid evidence","Views, contact checks or calibration steps","Actual sensing cost and whether a probe changes state"],
        ],[.27,.34,.39],9.8)
        self.heading("A staged transfer experiment")
        self.paragraph("First keep the symbolic model fixed and replace one observation channel with controlled rendered pixels. Next test calibration and fault extraction on recorded sensor data. Only then evaluate a bounded physical task with measured actuator limits and an independently justified hypothesis set.")
        self.paragraph("Persistent degradation, continuous noise, moving objects and contact-dependent measurements need richer state models. A deterministic fault cap does not yield a probability of success. A synthetic finite certificate should therefore be treated as a component-level diagnostic.")
        self.note("Proposed evaluation", "Measure action success, robust justification, observation cost, unnecessary identification, abstention and assumption violations. Compare these quantities before and after training on the benchmark; retain a mechanism-level holdout.","amber")
        self.source_note("docs/robust-research.md; docs/robotics-vision.md; partial-observation planning [4].")

        self.new_page("11 / Reproducibility", "The evidence belongs to an exact source state", "The consolidated record binds the release's checks. The restored source and retained evidence keep their own version and provenance.")
        retained=d["retained_evidence"]
        self.table(["Record","Value"],[
            ["Release status",shown(d["status"])],
            ["Retained source version",shown(retained["version"])],
            ["Source inventory files verified",shown(retained["source_inventory_files_verified"])],
            ["Unchanged / modified / new files",f'{number(count(retained["unchanged_files"]))} / {number(count(retained["modified_files"]))} / {number(count(retained["new_files"]))}'],
            ["Stress source remained stable",shown(robust["source_stable"])],
        ],[.52,.48],10)
        self.heading("Integrity identifiers")
        for label,value in [("Core source fingerprint",d["source_fingerprint"]),("Consolidated verification JSON SHA-256",digest(self.source)),("Restored archive SHA-256",retained["source_archive_sha256"])]:
            self.paragraph(label,size=8.7,bold=True,gap=3)
            self.text(MARGIN,self.y+9,clean(value),7.5,"muted",mono=True); self.y+=25
        self.heading("Reproduce and inspect")
        self.paragraph("Start from README.md and docs/release-gates.md. The record's artifacts map points to the unit, scripted-control, stress, formal and pilot outputs. Rebuild cards with tools/build_release_cards.py and this report with tools/build_v051_report.py.",size=10)
        self.note("Keep the scientific boundary", "Freeze the evaluator before scored solving. Preserve solver/evaluator separation, source hashes, episode traces, budgets and model settings. A public small generator is a development resource; private future families and independent replication remain necessary for broad claims.")
        self.source_note("reports/v051/release-verification.json; AGENTS.md; docs/release-gates.md.")

        self.new_page("12 / Prior art and next questions", "A focused contribution within an established field", "The contribution is the integration of masked completion, budgeted observations, executable consequences and explicit certificates. The mathematical and evaluation ingredients have substantial prior art.")
        self.table(["Research line","Relationship to this release"],[
            ["Bounded lies [1]","A fixed hidden object and a global corruption allowance are classical. The release applies them to a finite task contract."],
            ["Decision regions [2]","A valid action can require less information than exact world recovery. The new objective is worst-case rather than Bayesian."],
            ["Environment design [3]","Exact feasibility and attainable cost can gate generated tasks. They do not themselves measure a model's difficulty."],
            ["ARC and Vending [5, 6]","Human calibration, action efficiency and delayed consequences motivate the protocol. No official tasks or published scores are imported."],
            ["Axiom and OpenAI math [7, 8]","Proof-producing workflows motivate checked artifacts. The finite benchmark does not reproduce their research mathematics."],
        ],[.31,.69],9.4)
        self.heading("Interpret the 100D ambition precisely")
        self.paragraph("The retained 100D tasks are finite-field operator-recovery problems. They do not establish physical 100-dimensional perception, a new OpenAI algorithm, or a method named '100D red teaming'. OpenAI's scientific work, public math repository and GPT-Red are distinct sources [8, 9, 12].",size=10)
        self.note("Next falsifiable claim", "Test whether an agent trained to preserve fault debt and submit observed witnesses improves budgeted decisions on independently authored, held-out mechanisms. Pre-register the comparison and report negative results as carefully as positive ones.","amber")
        self.source_note("docs/related-work.md; docs/math-and-100d.md; docs/robust-research.md.")

        self.new_page("13 / References", "Primary sources and local evidence", "External work motivates the design; it is not evidence of CausalFill performance. The local consolidated verification record is the source for release measurements.")
        for index,(label,description,url) in enumerate(REFERENCES,1):
            self.paragraph(f"[{index}] {label}. {description}",size=8.6,leading=11.4,bold=False,gap=2)
            y=self.y
            h=self.paragraph(url,size=7.5,leading=10.3,color="blue",gap=11)
            self.c.linkURL(url,(MARGIN,HEIGHT-y-h,WIDTH-MARGIN,HEIGHT-y),relative=0,thickness=0)
        self.source_note("Local records: reports/v051/release-verification.json; reports/robust-stress-v0.5.1/result.json; the formal and pilot artifacts named in the consolidated record.")
        self.finish_page()
        if self.page!=PAGES:
            raise ValueError(f"Expected {PAGES} pages, generated {self.page}.")
        self.c.save()

    def cover(self):
        self.page=1
        self.rect(0,0,WIDTH,HEIGHT,"paper")
        self.text(MARGIN,48,"CAUSALFILL-BENCH / RESEARCH RELEASE",9.3,"muted",True)
        self.text(WIDTH-MARGIN-35,48,"0.5.1",9.3,"blue",mono=True)
        hero=ROOT/"branding/previews/hero.png"
        if not hero.is_file():
            raise ValueError("Render branding assets before building the report: "+str(hero))
        self.c.drawImage(str(hero),0,HEIGHT-81-WIDTH*760/1800,width=WIDTH,height=WIDTH*760/1800,mask="auto")
        self.y=369
        self.paragraph("Signal Repair",size=35,leading=42,bold=True,gap=16)
        self.paragraph("Evidence before irreversible action.",size=20,leading=27,bold=True,gap=17)
        self.paragraph("A source-bound release report on globally bounded sensor corruption, exact finite cost certificates, generic formal guarantees and the limits revealed by development evaluation.",size=12,leading=18.5,color="muted",gap=24)
        self.kpis([(number(self.data["task_configurations"]),"Task configurations","Implemented suite"),
                   (number(self.data["conceptual_domains"]),"Conceptual domains","Shared public protocol"),
                   ("Passed","Release verification","Consolidated source record")])
        self.paragraph("Concept and direction: Phillip A. Holland Jr.\nImplementation and research synthesis: AI-assisted.",size=10.5,leading=16,color="muted",gap=0)
        self.page_records.append({"page":1,"section":"Cover","title":"Signal Repair"})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record",type=Path,default=ROOT/"reports/v051/release-verification.json")
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--render",action="store_true")
    parser.add_argument("--render-dir",type=Path,default=ROOT/"branding/report-preview")
    args=parser.parse_args()
    record=args.record.resolve()
    data=json.loads(record.read_text())
    if data.get("version")!="0.5.1" or not passed(data.get("status")):
        raise ValueError("The completed v0.5.1 passing verification record is required; no asserted-metric preview is generated.")
    for key in ["source_fingerprint","task_configurations","conceptual_domains","unit_and_integration_tests","scripted_controls","robust_sensing","robust_ablation","formal_assurance","assistant_pilot","retained_evidence","artifacts","claim_boundaries"]:
        if key not in data:
            raise ValueError("Verification record is missing "+key)
    unit=data["unit_and_integration_tests"]
    for key in ["passed","tests","failed","errors","skipped"]:
        number(unit[key])
    if unit["passed"]!=unit["tests"] or any(unit[key] for key in ["failed","errors","skipped"]) or not passed(data["formal_assurance"]["status"]):
        raise ValueError("Unit and formal gates must pass before producing this completed release report.")
    for key in ["task_configurations","conceptual_domains"]:
        number(data[key])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    report=Report(args.output,data,record)
    report.build()
    from pypdf import PdfReader
    reader=PdfReader(str(args.output))
    if len(reader.pages)!=PAGES:
        raise ValueError("Unexpected written page count.")
    extracted=[page.extract_text() or "" for page in reader.pages]
    if any(not text.strip() or "\ufffd" in text for text in extracted):
        raise ValueError("Empty page or Unicode replacement character in extracted PDF text.")
    rendered=[]
    if args.render:
        command=shutil.which("pdftoppm")
        if not command:
            raise ValueError("Rendering requires pdftoppm on PATH.")
        args.render_dir.mkdir(parents=True,exist_ok=True)
        subprocess.run([command,"-r","105","-png",str(args.output),str(args.render_dir/"page")],check=True)
        rendered=[{"path":str(p),"sha256":digest(p)} for p in sorted(args.render_dir.glob("page-*.png"))]
        from PIL import Image,ImageDraw,ImageFont
        tw,pad,gap=300,22,18
        tiles=[]
        for p in sorted(args.render_dir.glob("page-*.png")):
            im=Image.open(p).convert("RGB")
            tiles.append((p.stem,im.resize((tw,round(tw*im.height/im.width)),Image.Resampling.LANCZOS)))
        th=max(im.height for _,im in tiles)+23
        sheet=Image.new("RGB",(pad*2+3*tw+2*gap,pad*2+((len(tiles)+2)//3)*(th+gap)),PAL["paper"])
        draw=ImageDraw.Draw(sheet); ff=ImageFont.truetype(FONT_FILES["CF"],13)
        for i,(name,im) in enumerate(tiles):
            x=pad+(i%3)*(tw+gap); y=pad+(i//3)*(th+gap)
            draw.text((x,y),name,font=ff,fill=PAL["muted"]); sheet.paste(im,(x,y+22))
        sheet.save(args.render_dir/"contact-sheet.png")
    sources=[record,ROOT/"docs/robust-decisions.md",ROOT/"docs/robust-research.md",ROOT/"docs/related-work.md",ROOT/"docs/math-and-100d.md"]
    meta={"schema":"causalfill.report-build.v1","created_utc":datetime.now(timezone.utc).isoformat(),
          "pdf":str(args.output.resolve()),"pdf_sha256":digest(args.output),"pages":PAGES,
          "builder_sha256":digest(Path(__file__)),"record_sha256":digest(record),
          "sources":[{"path":str(p),"sha256":digest(p)} for p in sources],"page_index":report.page_records,
          "page_text_characters":[len(t) for t in extracted],"renders":rendered,
          "visual_qa":"Rendering and text extraction passed; human/assistant visual page inspection is separately required.",
          "scope":"Presentation of recorded evidence. This builder does not verify the experiments or proof artifacts."}
    (ROOT/"branding/report-build.json").write_text(json.dumps(meta,indent=2)+"\n")
    print(json.dumps({"output":str(args.output),"pages":PAGES,"rendered_pages":len(rendered),"pdf_sha256":meta["pdf_sha256"]},indent=2))


if __name__=="__main__":
    main()
