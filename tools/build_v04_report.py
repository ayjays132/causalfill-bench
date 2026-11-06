#!/usr/bin/env python3
"""Build the twelve-page v0.4 research report from recorded evidence.

The final build requires the release manifest and the final 29-root kernel
replay result. --draft can be used before these exist and visibly labels that
state. This is a report builder: it does not run the benchmark, amend evidence,
or rerun a proof gate. Selected evidence snapshots are attached to the PDF.
The PDF skill authoring marker was run once before creating this script;
subsequent rebuilds of this same deliverable must not repeat that marker.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import subprocess
from xml.sax.saxutils import escape

from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.platypus import Flowable, Frame, Paragraph, Spacer, Table, TableStyle

from build_stress_report import (
    Report as BaseReport, register_fonts, make_styles, plain, number,
    NAVY, TEAL, INK, MUTED, LINE, PALE, BLUE, AMBER, RED,
)


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "reports/build-verification-v0.4.json"
OUTPUT = ROOT / "output/pdf/CausalFill_Research_Report_v0.4.0.pdf"
W, H = A4
MARGIN = 48
CONTENT = W - 2 * MARGIN

EVIDENCE_PATHS = {
    "runtime": "reports/stress-v0.4/adaptive-runtime-complete-responses.json",
    "enumeration": "reports/stress-v0.4/belief-games-independent-audit.json",
    "analytic": "reports/stress-v0.4/belief-analytic-final.json",
    "suite": "reports/development-run-v0.4-final/summary.json",
    "suite_manifest": "reports/development-run-v0.4-final/manifest.json",
    "pilot": "reports/public-interface-pilot-v0.4/manifest.json",
    "formal": "formal/verification-v04-current/results.json",
    "binding": "formal/verification-v04-binding/results.json",
    "formal_stress": "formal/verification-v04-stress/results.json",
    "review": "reports/stress-v0.4/formal-binding-review.json",
    "regression": "formal/verification-v04-final/results.json",
    "kernels": "formal/verification-v04-kernels/replay/results.json",
    "kernel_baseline": "formal/verification-v04-kernels/replay-negative-selection-baseline/baseline-note.json",
}

REFERENCES = [
    ("R1", "Kaelbling, Littman and Cassandra (1998). Planning and acting in partially observable stochastic domains.",
     "https://people.csail.mit.edu/lpk/papers/aij98-pomdp.pdf"),
    ("R2", "Axiom (2026). Proof of Concept. Generated proof artifacts accepted through Lean/Mathlib checking.",
     "https://axiommath.ai/research/proof-of-concept/"),
    ("R3", "Andon Labs. Vending-Bench 2. Year-long simulated business operations and final-cash evaluation.",
     "https://andonlabs.com/evals/vending-bench-2"),
    ("R4", "Lean Language Reference. Validating a Lean Proof. Statement meaning, axiom inventories and external checking.",
     "https://lean-lang.org/doc/reference/latest/ValidatingProofs/"),
    ("R5", "OpenAI. math repository. Research manuscripts and proof artifacts with differing verification status.",
     "https://github.com/openai/math"),
    ("R6", "ARC Prize. ARC-AGI-3. Interactive exploration, adaptation and action efficiency.",
     "https://arcprize.org/arc-agi/3"),
]


def load(path: Path):
    return json.loads(path.read_text()) if path.exists() else {}


def sha(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass
class Evidence:
    manifest_path: Path
    draft: bool

    def __post_init__(self):
        self.manifest = load(self.manifest_path)
        self.paths = {key: ROOT / path for key, path in EVIDENCE_PATHS.items()}
        self.data = {key: load(path) for key, path in self.paths.items()}
        self.version = str(self.manifest.get("version", "0.4.0"))
        self.date = str(self.manifest.get("verified_utc", self.manifest.get("created_utc", "2026-11-04")))[:10]
        test_path = ROOT / "reports/unittest-v0.4.txt"
        test_text = test_path.read_text() if test_path.exists() else ""
        test_match = re.search(r"Ran (\d+) tests? in", test_text)
        self.tests = int(test_match.group(1)) if test_match else None
        self.tests_ok = test_match is not None and re.search(r"\nOK\s*$", test_text) is not None
        self.reference = next((g for g in self.data["suite"].get("groups", [])
                               if g.get("identity", {}).get("policy") == "evidence"), {})
        self.aggregate = self.reference.get("aggregate", {})
        self.rc = self.data["runtime"].get("counts", {})
        self.ac = self.data["analytic"].get("counts", {})
        self.pilot = self.data["pilot"].get("results", [])
        self.pilot_success = sum(row.get("success") is True for row in self.pilot)
        self.generic_roots = [name for name in self.data["formal"].get("axioms", {})
                              if name.startswith("CausalFill.Information.")]
        self.kernel = self.data["kernels"]
        self.kernel_ready = self.kernel.get("status") == "passed"
        self.kernel_roots = self.kernel.get("required_theorem_roots", [])
        self.kernel_commands = self.kernel.get("commands", [])
        self.kernel_valid = sum(row.get("variant") == "valid" and row.get("expected_verdict_met") is True
                                for row in self.kernel_commands)
        self.kernel_negative = sum(row.get("variant") == "corrupted" and row.get("expected_verdict_met") is True
                                   for row in self.kernel_commands)
        if not self.draft:
            if not self.manifest:
                raise SystemExit("Final release manifest absent; use --draft for a marked working report.")
            if self.manifest.get("status") != "passed-development-verification" or self.version != "0.4.0":
                raise SystemExit("Expected the passed v0.4.0 development-verification manifest.")
            for name, relative in self.manifest.get("reports", {}).items():
                expected = self.manifest.get("report_sha256", {}).get(name)
                path = ROOT / relative
                if not expected or not path.exists() or sha(path) != expected:
                    raise SystemExit(f"Recorded report hash no longer matches: {relative}")
            required_passes = ("runtime", "enumeration", "analytic", "formal", "binding", "formal_stress", "regression")
            for key in required_passes:
                if self.data[key].get("status") != "passed":
                    raise SystemExit(f"Final evidence gate not passed: {self.paths[key]}")
            if not self.kernel_ready or len(self.kernel_roots) != 29 or self.kernel_valid != 6 or self.kernel_negative != 6:
                raise SystemExit("Final 29-root / six-checker export replay is incomplete or failed.")
            if not self.kernel.get("all_required_roots_present_as_theorems"):
                raise SystemExit("Final export did not establish the required theorem inventory.")
            if not self.kernel.get("injected_axiom_inventory_rejected") or not self.kernel.get("omitted_required_root_rejected"):
                raise SystemExit("Final export inventory negative controls did not pass.")
            if not self.tests_ok or self.tests != 214:
                raise SystemExit("The current report expects the recorded 214-test release gate.")
            if len(self.generic_roots) != 21:
                raise SystemExit("Generic new-theorem inventory changed; review report wording.")
            if len(self.pilot) != 6 or self.pilot_success != 6:
                raise SystemExit("Pilot report changed; review the six-episode discussion.")
            if self.data["pilot"].get("transport") != "public-json-mailbox":
                raise SystemExit("Pilot transport changed; review the isolation discussion.")
            assertions = [
                (self.rc.get("reachable_states_replayed"), 83616),
                (self.rc.get("transitions_executed"), 139080),
                (self.rc.get("assertions"), 2951089),
                (self.data["suite"].get("record_count"), 3240),
                (self.aggregate.get("solvable_successes"), 990),
                (self.aggregate.get("answerable_episodes"), 990),
                (self.aggregate.get("unanswerable_correct_abstentions"), 90),
                (self.data["enumeration"].get("exact_optimum_comparisons"), 1024),
                (self.data["enumeration"].get("complete_syntactic_policies_enumerated"), 601600),
                (self.data["analytic"].get("configuration", {}).get("cases"), 60),
                (self.ac.get("certificates"), 240),
                (self.ac.get("metamorphic_cases"), 180),
                (self.ac.get("forged_certificates_rejected"), 720),
            ]
            if any(actual != expected for actual, expected in assertions):
                raise SystemExit("Recorded release counts changed; review narrative before building final PDF.")


class PilotCosts(Flowable):
    """Vector grouped bars: one common unit and explicit comparison scopes."""
    def __init__(self, rows):
        super().__init__()
        self.width, self.height, self.rows = CONTENT, 170, rows

    def draw(self):
        c = self.canv
        left, right, top, bottom = 98, CONTENT - 26, 143, 36
        plot = right - left
        for tick in (0, 5, 10, 15, 20):
            x = left + plot * tick / 22
            c.setStrokeColor(LINE); c.setLineWidth(.5); c.line(x, bottom, x, top)
            c.setFillColor(MUTED); c.setFont("CFSans", 7.7); c.drawCentredString(x, bottom-13, str(tick))
        for i, (label, bound, observed) in enumerate(self.rows):
            y = top - 11 - i * 35
            c.setFillColor(INK); c.setFont("CFSans-Bold", 8.7); c.drawRightString(left-12, y-3, label)
            for value, color, dy in ((bound, TEAL, 0), (observed, colors.HexColor("#798EA1"), -12)):
                c.setFillColor(color); c.rect(left, y+dy, plot*value/22, 9, fill=1, stroke=0)
                c.setFont("CFSans-Bold", 8); c.drawString(left+plot*value/22+5, y+dy+1, str(value))
        c.setFillColor(MUTED); c.setFont("CFSans", 7.6)
        c.drawCentredString((left+right)/2, 5, "Operational tool-cost units (setup excluded)")
        c.setFillColor(TEAL); c.rect(0, 157, 8, 8, fill=1, stroke=0)
        c.setFillColor(INK); c.setFont("CFSans", 7.5); c.drawString(13, 158, "Certified guaranteed worst-case minimum")
        c.setFillColor(colors.HexColor("#798EA1")); c.rect(260, 157, 8, 8, fill=1, stroke=0)
        c.setFillColor(INK); c.drawString(273, 158, "Observed pilot trajectory")


class BindingFigure(Flowable):
    """Show the independent-renderer fork and explicit unproved projection."""
    def __init__(self):
        super().__init__(); self.width, self.height = CONTENT, 157

    def draw(self):
        c = self.canv
        def box(x, y, w, h, title, sub, tint):
            c.setFillColor(tint); c.setStrokeColor(LINE); c.roundRect(x, y, w, h, 4, fill=1, stroke=1)
            c.setFillColor(NAVY); c.setFont("CFSans-Bold", 8.5); c.drawCentredString(x+w/2, y+h-15, title)
            c.setFillColor(MUTED); c.setFont("CFSans", 7.2); c.drawCentredString(x+w/2, y+10, sub)
        def arrow(x1,y1,x2,y2):
            c.setStrokeColor(MUTED); c.setLineWidth(.8); c.line(x1,y1,x2,y2)
            c.line(x2,y2,x2-3,y2+5); c.line(x2,y2,x2+3,y2+5)
        box(117, 118, 265, 34, "Checked Python belief arena", "Raw-game projection remains outside the Lean theorem", BLUE)
        arrow(CONTENT/2,118,111,98); arrow(CONTENT/2,118,CONTENT-111,98)
        box(0,55,222,43,"Exported arena A","First translation into Lean definitions",BLUE)
        box(CONTENT-222,55,222,43,"Expected arena B","Separate literal renderer; no shared emitter",PALE)
        arrow(111,55,CONTENT/2,40); arrow(CONTENT-111,55,CONTENT/2,40)
        box(71,0,CONTENT-142,40,"Kernel-checked A = B","Entire node vector and root; guarantee transported to B",PALE)


class Report(BaseReport):
    def __init__(self, evidence):
        super().__init__(evidence)
        self.styles["body"].fontSize = 9.7
        self.styles["body"].leading = 14.1
        self.styles["body"].spaceAfter = 7.2
        self.styles["section"].fontSize = 22
        self.styles["section"].leading = 26.5
        self.styles["section"].spaceAfter = 12
        self.styles["small"].fontSize = 8.3
        self.styles["small"].leading = 11.5
        self.styles["table"].fontSize = 8.1
        self.styles["table"].leading = 11.1
        self.styles["thead"].fontSize = 8.1
        self.styles["thead"].leading = 11.1

    def equation(self, text, note=""):
        style = self.styles["body"].clone("equation", fontSize=11, leading=21, spaceAfter=5)
        content = [Paragraph(plain(text), style)]
        if note:
            content.append(Paragraph(plain(note), self.styles["small"]))
        box = Table([[content]], colWidths=[CONTENT])
        box.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,-1),BLUE),
            ("BOX",(0,0),(-1,-1),.5,LINE), ("LEFTPADDING",(0,0),(-1,-1),12),
            ("RIGHTPADDING",(0,0),(-1,-1),12), ("TOPPADDING",(0,0),(-1,-1),6),
            ("BOTTOMPADDING",(0,0),(-1,-1),5)]))
        self.current += [box, Spacer(1,9)]

    def compose(self):
        e = self.e
        r, a, n = e.rc, e.ac, e.data["enumeration"]
        agg = e.aggregate
        self.page("CausalFill-Bench", f"Research and verification report | v{e.version} | {e.date}")
        self.p("Adaptive decisions.<br/>Checkable guarantees.<br/>Measured limits.", "title")
        self.p("A benchmark for recovering missing components, choosing useful evidence, and making the completed procedure succeed.", "sub")
        self.stats([(number(e.tests), "unit and integration tests<br/>recorded release gate"),
                    (number(r.get("transitions_executed")), "runtime transitions executed<br/>27 finite market graphs"),
                    (f"{e.pilot_success}/{len(e.pilot)}", "exploratory assistant episodes<br/>public-mailbox pilot")])
        self.h("The concrete advance")
        self.p("Version 0.4 adds a sequential procurement task in which hidden demand changes across rounds, observations have a cost, and a wrong purchase cannot be undone. A complete finite model supports independently checked optimality certificates. Lean proofs establish generic information and strategy bounds; separate equality proofs bind four concrete policy-mode arenas to the intended data. [E2-E8]")
        self.h("The measured result")
        self.p(f"The {number(e.data['suite'].get('record_count'))}-episode scripted control matrix has {number(agg.get('solvable_successes'))}/{number(agg.get('answerable_episodes'))} answerable evidence-reference successes and {number(agg.get('unanswerable_correct_abstentions'))} correct abstentions. The small assistant pilot also succeeds on every selected episode. These findings establish working tasks and usable interfaces; they do not establish frontier difficulty. [E1, E9]")
        self.note("A research artifact with a bounded claim", "The strongest result is verifiable engineering: explicit assumptions, exhaustive finite alternatives, independent numerical checks, concrete proof artifacts, and recorded negative controls. No new axiom, new planning algorithm, human-level result, or scientific breakthrough is claimed.")
        self.p("<b>Concept and direction:</b> Phillip A. Holland Jr. <b>Implementation and synthesis:</b> AI-assisted. Original project code and assets: MIT. Internal independent checker and reviewer work is not external laboratory replication.", "small")
        if e.draft:
            self.note("DRAFT - FINAL EVIDENCE NOT YET LOCKED", "This working layout uses individual evidence records. The final build requires the release manifest and a passed 29-root, six-checker replay. Draft status must not be interpreted as that gate passing.", AMBER)

        self.page("What the benchmark measures", "01 | The task and its research hypothesis")
        self.p("The unit of evaluation is a missing component that affects a declared task outcome. The agent receives typed gaps, a public contract, a virtual workspace, and a tool budget. It gathers evidence, submits a completion, and is evaluated by a separate verifier. Recovery, downstream success, observation cost, and justified abstention are recorded separately. [E0]")
        self.table(["Conceptual domain", "Configurations", "Completion and acceptance"], [
            ["Language conditions", "words; ambiguity", "Restore routing conditions; exhaustive Boolean checks, or abstain when evidence cannot identify a unique answer."],
            ["Executable procedures", "workflow", "Fill a restricted expression; sufficient symbolic equivalence and bounded-totality checks."],
            ["Rule induction", "grid", "Recover an original transformation program; typed grammar and finite behavior checks."],
            ["Procurement", "vending; vending_adaptive", "Repair economic rules and operate an actual mutable simulation; adaptive variant has a finite-game certificate."],
            ["Symbolic robotics", "robotics; robotics_barrier", "Recover scene state and choose a feasible path and handling condition; exact represented-number geometry."],
            ["Mathematical state", "latent; latent_sparse", "Recover an affine finite-field operator in up to 100 variables; exact equality certificate."],
            ["Logical proof", "proof", "Prove a fixed conclusion and exhibit a model of the premises to rule out vacuous entailment."],
            ["Identification", "diagnosis", "Identify one listed world using observed elimination witnesses within a certified query cap."],
        ], [1.0, 1.25, 2.85], compact=True)
        self.h("An omission must change the decision problem")
        self.p("A visually large mask can still be irrelevant, and a complex-looking simulator can still admit a universal script. Earlier audits found a valid fixed Express ordering schedule in the original vending distribution and a common high route in the original robotics distribution. Those successes remain accepted. The adaptive market and barrier scene are separate configurations with stronger, explicitly changed contracts. [E0]")
        self.p("The proposed research contribution is the combination of structured gaps, active evidence, executable consequences, and checkable claims. The ingredients have substantial prior art. ARC's interactive exploration, Vending-Bench's persistent business, classical belief-space planning, and Axiom's checked-artifact workflow inform the design without making this a reproduction or official extension of those projects. [R1-R3, R6]", "small")
        self.p("Vending-Bench 2 evaluates business coherence over a simulated year using ending cash. This release's two-to-four-round market instead isolates a completely enumerable information-and-decision problem. It has no supplier negotiation, competitors, or year-long model trajectory. The two benchmarks therefore support different claims. [R3]", "small")
        self.sources("[E0] README and release manifest. Domain definitions and assumptions are included in the accompanying source release.")

        self.page("An irreversible market with alternatives", "02 | Economics, experiments and public hypotheses")
        self.p("Each episode has two to four rounds. One case exactly fills storage; each round demands one case of either tea or cocoa. The complete possible-world table is public, while its true row is hidden. An order immediately spends cash and creates pending stock. Settlement records delivery, sells the requested product, expires leftovers, and charges an operating fee. Missing any request permanently closes the service contract. [E2]")
        self.table(["Public action", "Cost units", "Information or economic effect"], [
            ["calibrate", "1", "One shared calibration bit, available once before an order."],
            ["forecast / assay", "1 / 2", "One sample per round: coded demand or direct demand."],
            ["order", "2", "Irreversibly buy one product from the standard or express supplier."],
            ["settle", "1", "Advance the round; deliver, sell, expire, pay fees, reveal realized demand."],
            ["quote / status / ledger", "1 each", "Static tariffs or already public accounting; no future-demand channel."],
        ], [1.18, .62, 3.12], compact=True)
        self.h("A measurable cash constraint")
        self.p("Let u be case size, p sale price per unit, w wholesale price, f the fixed shipping fee, c the case fee, o the round operating fee, and e the express surcharge. All money is integer cents. The standard per-round margin and final goal are:")
        self.equation("π = up - (uw + f + c) - o<br/>C<sub>target</sub> = C<sub>0</sub> + Tπ - e",
                      "T rounds; initial cash funds every admissible order prefix without borrowing.")
        self.p("All requests served with standard delivery leaves an extra e cents above the goal. Exactly one express order is also successful; two express surcharges make the goal unreachable. Correct term recovery alone cannot repair a failed business, and business success alone cannot fill the four procurement-rule holes. [E2]")
        self.table(["Split", "Forecast rule", "Worlds: 2 / 3 / 4 rounds"], [
            ["Train", "Current demand d<sub>t</sub>", "4 / 8 / 16"],
            ["Dev", "d<sub>t</sub> XOR calibration k", "8 / 16 / 32"],
            ["Transfer", "d<sub>t</sub> XOR k XOR previous demand", "4 / 12 / 28"],
        ], [.7, 2.4, 1.8], compact=True)
        self.p("Transfer excludes constant demand sequences. A known prefix can therefore determine a later demand without another sample. Direct assays can replace calibration and forecasts entirely. Scoring requires outcomes, never a named sensor or minimum query count. The twin complements the categorical demand trajectory; paired episodes reset agent state. [E2]", "small")

        self.page("The exact finite planning claim", "03 | Belief states, costs and policy classes")
        self.p("A belief B is the set of concrete states consistent with the interaction history. The initial unknown state is fixed for an episode. Actions have deterministic effects in each world; observations partition the resulting states. Every edge decreases a natural-number rank, so the operational arena is finite and acyclic. This is a small deterministic, worst-case planning model related to established partially observed planning, not a new POMDP algorithm. [E3-E6, R1]")
        self.equation("B<sub>a,z</sub> = { T(s,a) : s ∈ B and O(T(s,a)) = z }<br/>V(B) = min<sub>a ∈ A(B)</sub> [ c(a) + max<sub>z</sub> V(B<sub>a,z</sub>) ]",
                      "V = 0 when every state succeeds; V = ∞ if any state has failed or no action can guarantee success. Empty observation branches are omitted.")
        self.p("The certificate's lower obligation checks <b>every</b> available action. Its upper obligation supplies an action attaining the stated value and a strictly decreasing rank. Thus the checked claim combines a lower bound with a terminating witness strategy. A separate checker replays the strategy from every raw initial world. A policy-only success test would establish attainment but not optimality. [E3-E6]")
        self.table(["Policy class", "Explicit experiments", "Feedback used"], [
            ["adaptive", "Allowed", "All modeled observations"],
            ["no_observe", "Excluded", "Operational outcomes still available"],
            ["open_loop", "Allowed", "All observations ignored; one fixed script"],
            ["open_loop_no_observe", "Excluded", "One fixed script"],
        ], [1.5, 1.05, 2.3], compact=True)
        self.table(["Guaranteed operational minimum", "2 rounds", "3 rounds", "4 rounds"], [
            ["Train", "8", "12", "16"], ["Dev", "9", "13", "17"], ["Transfer", "8", "13", "17"],
        ], [2.2, .9, .9, .9], compact=True)
        self.p("All three restricted classes lack a guaranteed-success strategy in the audited market profiles. The full four-round dev graph has 8,192 states and 13,664 edges, including both suppliers, both sample choices, calibration, no-order settlement, and wrong purchases. No search cutoff discards a legal alternative. [E2]")
        self.note("Budget scope", "The numbers above are synthetic operational tool-cost units, not cents, tokens, seconds, or model-computation costs. They exclude contract reads, static quotes, final fill reconstruction and submission. A sufficient setup uses one contract read and two quotes at three extra units. No end-to-end setup optimum is claimed.")

        self.page("Independent checks of the planner", "04 | Different numerical oracles, different failure modes")
        self.p("A producer and checker that share the same recurrence can agree on the same mistake. The audit therefore adds numerical oracles with different constructions: complete small-policy enumeration and an analytic sensor-selection family. Both inspect exact outputs, including losing games; neither substitutes a self-reported solver grade. [E3-E4]")
        self.stats([(number(n.get("exact_optimum_comparisons")), "exact optimum comparisons<br/>256 games x four modes"),
                    (number(n.get("complete_syntactic_policies_enumerated")), "complete syntactic policies<br/>small depth-three games"),
                    (number(a.get("certificates")), "analytic certificates<br/>60 generated cases")])
        self.h("Complete small-policy enumeration")
        self.p("The independent oracle enumerates full depth-three binary-feedback contingency assignments and replays raw transitions for every initial world. It does not call the production Bellman recurrence, belief updater, or certificate transition routine. The returned optimum agrees in all 1,024 game-mode comparisons. Syntactic assignments can contain unreachable branches and induce the same realized behavior, so 601,600 is a count of policy encodings, not independent reasoning problems. [E3]")
        self.h("A second oracle with a known mathematical structure")
        self.p("The analytic family reveals subsets of a hidden bit cube at weighted costs. Independent subset enumeration finds the minimum sensor-set cover needed for guaranteed recovery. Its 60 cases produce 240 four-mode certificates, 180 metamorphic cases, and 720 rejected certificate forgeries. It also replays 560 initial-world trajectories and checks 22,488 belief entries. These are correlated implementation checks with a precise finite target. [E4]")
        self.table(["Check", "What an error could reveal", "What a pass supports"], [
            ["Raw policy enumeration", "Wrong branching, action masks or cost aggregation", "Correct minima on the complete small corpus"],
            ["Analytic subset oracle", "Incorrect information accumulation or weighted cost", "Agreement with a structurally distinct known optimum"],
            ["Metamorphic cases", "Sensitivity to irrelevant representation choices", "Invariance for the specified transformations"],
            ["Forged certificates", "Missing alternative, false value or broken witness checks", "Rejection of the finite mutation battery"],
        ], [1.18, 1.8, 1.95], compact=True)
        self.p("No mismatches were recorded in these final audits. The result is stronger assurance for a bounded Python implementation. It is not a proof of all Python executions, a model benchmark score, or evidence that large generated arenas are intrinsically difficult for a language model. [E3-E4]", "small")

        self.page("From the finite model to real responses", "05 | Complete outgoing edges, explicit history limits")
        self.p("The market compiler derives projected cash and stock from stage, order status, service history, and express count. The runtime separately mutates invoices, deliveries, sales, expiry, fees, and cash. The conformance harness selects a canonical witness history for each reachable projected state, replays actual public tools, and executes every outgoing legal edge. [E2]")
        self.table(["Audited object", "Count", "Unit / interpretation"], [
            ["Generated games", "27", "3 seeds x 3 splits x 3 difficulties"],
            ["Reachable states replayed", number(r.get("reachable_states_replayed")), "One canonical witness history per projected state"],
            ["Legal transitions executed", number(r.get("transitions_executed")), "Every outgoing edge from those states"],
            ["Stuttering-tool checks", number(r.get("stuttering_tools_checked")), "Static or repeated-observation responses"],
            ["Invalid-action checks", number(r.get("invalid_actions_checked")), "Finite typed battery; domain mutation and error behavior"],
            ["Equivalent-history comparisons", number(r.get("equivalent_history_response_comparisons")), "Full public response comparisons"],
            ["Equivalent-transition comparisons", number(r.get("equivalent_transition_response_comparisons")), "Full outgoing transition responses"],
            ["Assertions", number(r.get("assertions")), "Correlated test assertions, not independent episodes"],
        ], [1.5, .8, 2.55], compact=True)
        self.h("The public interface is part of the model")
        self.p("Matching a designated observation token is insufficient if another response field leaks the hidden world. The final audit also compares quotes, invoices, market records, accounting totals, ledgers, errors, and Session metadata under the tested equivalent histories. It checks charged costs and invalid-action atomicity as well as state transitions. All 384 initial worlds across the 27 games also admit an attaining strategy through the budgeted Session interface. [E2]")
        self.h("Why the coverage qualification matters")
        self.p("A state can be reached through multiple histories. Enumerating all states and outgoing edges under one representative history does not enumerate every history, every malformed byte sequence, or every possible host behavior. Full-response comparison adds a targeted information-leak check, while the source design keeps omitted static reads and invalid operations as costly stutters. A generic simulator-refinement theorem remains future work. [E2]")
        self.note("The released evidence is the final response-complete audit", "The source fingerprint was stable during this run, and the final report has no failed assertions. Earlier smaller or observation-token-only runs are retained as development history; their coverage must not be substituted for the scope stated here.")

        self.page("What Lean actually proves", "06 | Generic theorems and one concrete market")
        self.p("The new development contains 21 named generic information and finite-strategy theorems. Observation equivalence forces a deterministic policy to return the same completion; incompatible successful completions therefore cannot both succeed without distinguishing information. A more general finite counting theorem bounds success by the best completion's capacity within an observation class. It does not formalize randomized-policy probabilities. [E5]")
        self.h("An exact budget is two theorems together")
        self.p("<font name='CFMono'>CanWin</font> denotes a finite successful strategy under a natural-number budget. <font name='CFMono'>ValidLower</font> bounds every alternative; induction over any winning strategy proves no smaller budget can work. <font name='CFMono'>ValidUpper</font> gives an attaining action with lower-ranked children; rank induction constructs a terminating strategy. The executable finite checks imply these premises. <font name='CFMono'>none</font> in <font name='CFMono'>Option Nat</font> means infinity or unwinnability, never zero. [E5]")
        self.table(["Concrete mode", "Belief nodes", "Kernel-checked root result"], [
            ["adaptive", "326", "Exact guaranteed-success operational cost 8"],
            ["no_observe", "63", "No finite guaranteed-success strategy"],
            ["open_loop", "40", "No finite guaranteed-success strategy"],
            ["open_loop_no_observe", "10", "No finite guaranteed-success strategy"],
        ], [1.4, .7, 2.7], compact=True)
        self.p("These are four policy-mode projections of <b>the same</b> two-round, four-world game: 448 raw states and 732 transition edges. They are not four independent market problems. The adaptive projection checks 495 available alternatives. Each concrete theorem also proves the shape conditions: goal nodes terminate and an action cannot win vacuously through an empty successor list. [E5]")
        self.h("Stronger statement correspondence")
        self.current.append(BindingFigure()); self.gap(7)
        self.p("Four additional boundProfile theorems include equality of the entire imported arena to separately rendered expected data and transport the guarantee to that data. This closes a concrete correspondence gap beyond comparing exporter-written JSON. It still trusts Python parsing and raw-game-to-belief projection; it does not prove the economic runtime correct. [E6]")

        self.page("Proof checking needs a trusted statement", "07 | Negative controls, kernel replay and remaining trust")
        self.p("Review reproduced a metadata defect: changing only a copied manifest's policy-mode label could misreport an adaptive result as open-loop. The theorem itself remained true for its actual arena. The repair binds mode, node count, root and root value to the checked arena; all four mutation cases are rejected. A separate forged-JSON test alters the arena while emitting matching expected JSON, and the new whole-arena equality fails in the kernel. [E7]")
        self.p("Ten formal controls passed, covering false lower/upper claims, nondecreasing rank, empty successor branches, altered alternatives and successors, forged correspondence, custom axioms, and missing or duplicate audit roots. The retained 865-step and 6,018-step resolution exports also passed their regression gate with its archived verifier source. These are distinct from the new market-arena proofs. [E7, E10]")
        self.h("The final serialized declaration replay")
        if e.kernel_ready:
            self.p(f"The final export includes <b>{len(e.kernel_roots)} required theorem roots</b>: 21 new generic theorems, four concrete profiles, and four full-arena bindings. All {e.kernel_valid} checker configurations accept the valid export, and all {e.kernel_negative} reject the corrupted target proof with the expected type-failure diagnostic. An independent inventory also rejects an injected unsupported axiom and an omitted required root. [E8]")
        else:
            self.note("Pending final replay", "The 29-root export is not yet supported here by a completed final replay record. No result from an earlier smoke test is counted as that final gate. This paragraph is replaced only after replay/results.json records the completed checks.", AMBER)
        rows = []
        for key, label in (("lean_default", "Lean checker"), ("lean_hardened", "Lean hardened variant"),
                           ("lean4lean", "lean4lean"), ("nanoda", "nanoda"),
                           ("con_ron", "con-ron"), ("con_leche", "con-leche")):
            actual = {row["variant"]: row for row in e.kernel_commands if row.get("checker") == key}
            passed = lambda variant: "accepted" if variant == "valid" and actual.get(variant, {}).get("expected_verdict_met") else "rejected as expected" if actual.get(variant, {}).get("expected_verdict_met") else "pending"
            rows.append([label, passed("valid"), passed("corrupted")])
        self.table(["Checker configuration", "Valid export", "Corrupted proof"], rows, [1.7, 1.3, 1.7], compact=True)
        self.p("The first negative-control selection used a term with an undefined universe parameter. All six checkers rejected it, but the expected type-mismatch diagnostic was absent. The harness was corrected to select a closed Sort 0 term and rerun; the preserved baseline is a test-control defect, not a failed theorem or changed checker. [E8]", "small")
        self.p("The pinned toolchain is Lean 4.35.0 with Std and no Mathlib dependency. The allowed standard axiom set is propext, Classical.choice and Quot.sound; the new concrete profile/binding results use only propext and Quot.sound. No custom axiom, sorry, or native_decide proof shortcut is accepted. [E5-E8]")
        self.note("Six configurations are not six independent software stacks", "The set includes Lean's own checker, its hardened variant, and four bundled external checkers. They were invoked directly on serialized declarations. Lake's full paranoid build sandbox was not run on this host. Logic, implementations, host integrity, input selection, the second renderer, and Python projection remain trust boundaries. [E8, R4]")

        self.page("A real assistant pilot, with clear limits", "08 | Six fresh-context public-interface episodes")
        self.p("A fresh-context assistant solved six selected episodes using only public JSON mailbox requests in the recorded interaction: four-round train/dev/transfer procurement, transfer barrier robotics, transfer diagnosis, and transfer proof. All six accepted submissions were independently graded successful, with no invalid calls. The earlier unreachable HTTP attempt is excluded; it is an infrastructure failure, not a model task failure. [E9]")
        self.table(["Episode", "Success", "Total tool cost", "Observed artifact / outcome"], [
            ["Procurement: train / dev / transfer", "3 / 3", "26 each", "Four rounds served; restored rules; cash goal met"],
            ["Barrier robotics", "1 / 1", "19", "Valid symbolic state, two-segment route and handling"],
            ["Diagnosis", "1 / 1", "6", "Five experiments; witnesses eliminate 31 alternatives"],
            ["Proof", "1 / 1", "4", "Own 865-step resolution artifact; consistent premises"],
        ], [1.7, .55, .8, 2.05], compact=True)
        self.h("The pilot chose a legitimate alternative")
        self.p("For procurement the assistant used direct assays rather than the reference controller's calibration and coded forecasts. Four assays, four orders and four settlements cost 20 operational units. Its six additional setup units bring the recorded episode total to 26. The strategy succeeds without satisfying any artificial sensor-name requirement. [E9]")
        self.current.append(PilotCosts([("Train", 16, 20), ("Dev", 17, 20), ("Transfer", 17, 20)])); self.gap(3)
        self.p("The chart compares different scopes explicitly: observed trajectory cost versus the minimum budget guaranteeing success over every world in the profile. It is not a per-instance regret estimate or a language-model efficiency ranking. No tokenizer-exact compute budget or exact model snapshot was recorded. [E2, E9]", "caption")
        self.note("Exploratory, instruction-isolated evidence", "The mailbox exposes only public requests and the solver did not receive authoring context, but both processes share a host. Isolation was instructed rather than enforced by an OS boundary. Six selected cases, no model comparison, and incomplete inference telemetry do not support a certified leaderboard score or a frontier-hardness claim.")

        self.page("A disciplined path toward robotics", "09 | Information before commitment, with transfer still untested")
        self.p("The useful transferable idea is to make an observation matter before an irreversible choice. For a robot, a missing component might be an object's pose, a camera transform, a hidden opening, a contact mode, or a friction regime. An experiment can reduce uncertainty, but its cost and physical consequence must be modeled. Whether a camera move, touch probe, or path probe is worthwhile is a decision problem, not merely a reconstruction score. Classical partially observed planning already provides this framework. [R1]")
        self.table(["Current implementation", "What it checks", "What remains to be built"], [
            ["Symbolic calibrated cameras", "Numerical projection and recovered target state", "Images, occlusion, calibration drift, perception uncertainty"],
            ["Exact represented-number geometry", "Workspace and piecewise-linear path feasibility", "Dynamics, contact, actuator limits and timing"],
            ["Barrier paired scenes", "Each scene solvable; no common path through both", "Closed-loop sensing under noisy geometry and uncertainty"],
            ["100-variable affine field tasks", "Exact operator recovery under a restricted algebra", "Evidence that representations predict physical outcomes"],
        ], [1.35, 1.65, 1.85], compact=True)
        self.h("100D is a mathematical state dimension")
        self.p("The latent tracks use 8, 32 or 100 algebraic variables over a finite field. They do not model a 100-dimensional physical space or prove that a robot sees better. Five vector probes in the sparse reference return 500 field values at dimension 100; those are not five scalar observations. The toy algebra can test structured recovery and accounting for information bandwidth, while any physical relevance requires separate evidence. [E0]")
        self.h("A proposed staged experiment")
        self.p("First, add noisy but explicitly calibrated sensors to small scenes and define a finite abstraction with conservative action preconditions. Compare query-free, fixed-query and adaptive controllers using the same available observations and resource cap. Measure success, collisions, observation cost, and whether a recovered component actually improves a subsequent decision.")
        self.p("Next, move to rendered scenes and held-out camera, object and contact configurations. Keep the evaluator's hidden state separate from pixels delivered to the solver. Check whether abstraction errors explain failures, and include robust actions that can succeed without identifying every latent detail. Only after those simulator results should controlled physical trials test task completion and intervention recovery under appropriate laboratory safeguards.")
        self.note("The present claim stops at symbolic simulation", "The current release contains no visual perception study, physical robot experiment, learned world model, or safety certification. Its verified information-necessity examples offer a precise test-design ingredient; transfer to embodied reasoning remains a research hypothesis.")

        self.page("Reproduce the evidence and improve the study", "10 | Source release, commands and scientific next steps")
        self.p("The benchmark core uses Python 3.10+ without third-party runtime dependencies; the recorded build used Linux and Python 3.12. Lean checks require the separately installed pinned official 4.35.0 toolchain. The report builder additionally uses ReportLab and pypdf. Source fingerprints and command logs identify what actually ran. GitHub CI has not run for this restored release, and no public repository publication is asserted. [E0-E1]")
        self.code("python -m unittest discover -s tests -v\npython -m causalfill suite --output private-runs/controls \\\n  --splits train dev transfer --difficulties 1 2 3 --count 5 \\\n  --policies evidence blind abstain\npython tools/stress_belief_v04.py --cases 60 \\\n  --output private-runs/belief.json\npython tools/stress_adaptive_v04.py --seeds 3 \\\n  --output private-runs/adaptive.json")
        self.p("Use fresh output directories. The suite command creates the 3,240 scripted controls including paired variants; it does not invoke a language model. Do not mount evaluator code, seeds, answers, private traces, or authoring artifacts into a scored solver environment. The exact formal source, binding, export, replay and negative-control commands are documented in formal/README.md and docs/formal-information.md and preserved in their JSON reports. [E0-E8]", "small")
        self.h("A stronger model evaluation needs a different experiment")
        self.p("Pre-register a task roster, strong model baselines, inference limits, and scoring rules. Use a separate container or VM with only the public protocol. Compare complete-skill, matched random-mask, causal-mask, static-evidence and active-evidence conditions while preserving the same decision information where that comparison is intended. Include legitimate alternative solutions and deliberately unidentifiable controls.")
        self.p("Hold out structural mechanisms rather than only generator seeds. Evaluate newly authored future families and ask external reviewers to search for universal shortcuts and grader exploits. Report family-level success, paired robustness, budget curves, and failure categories. Treat correlated seeds and shared templates as clusters; do not turn raw assertion counts into confidence about intelligence.")
        self.h("Axiom-level aspiration, operationalized")
        self.p("Axiom's published workflow accepts generated proof artifacts through a separate Lean/Mathlib checker. The applicable lesson is artifact quality and exact statement checking, not a claim to match Axiom's research results. OpenAI's math repository likewise distinguishes verification stages and cautions that unformalized manuscripts may contain issues. This release imports neither project's mathematical results or model weights. [R2, R5]")
        self.note("What could justify a stronger future claim", "A pre-registered advantage on previously unseen mechanisms, replicated by independent evaluators under enforced isolation, would test the research hypothesis. A formal simulator-refinement proof would strengthen the engineering guarantee. Neither has been supplied by this release.")

        self.page("Sources and evidence map", "11 | Exact records, primary references and attribution")
        self.p("Bracketed E references name local release evidence; R references name primary prior work. Selected JSON snapshots and the test log are embedded as PDF attachments with SHA-256 hashes in ATTACHMENTS-README.txt. The complete source release contains raw traces, Lean sources, manifests, checkers and reproduction instructions. External references were checked on 2026-11-04.", "small")
        evidence_rows = [
            ["E0", "reports/build-verification-v0.4.json; README.md; domain/assumption documentation"],
            ["E1", "reports/unittest-v0.4.txt; reports/development-run-v0.4-final/{summary,manifest}.json"],
            ["E2", EVIDENCE_PATHS["runtime"]],
            ["E3", EVIDENCE_PATHS["enumeration"]],
            ["E4", EVIDENCE_PATHS["analytic"]],
            ["E5-E6", "formal/verification-v04-current/results.json; formal/verification-v04-binding/results.json"],
            ["E7", "formal/verification-v04-stress/results.json; reports/stress-v0.4/formal-binding-review.json"],
            ["E8", EVIDENCE_PATHS["kernels"]],
            ["E9", EVIDENCE_PATHS["pilot"]],
            ["E10", "formal/verification-v04-final/results.json; archived verifier source in that record's directory"],
        ]
        self.table(["ID", "Release-relative record"], evidence_rows, [.5, 5], compact=True)
        for key, title, url in REFERENCES:
            self.p(f"<b>[{key}]</b> {escape(title)}", "small")
            self.p(f"<link href='{escape(url)}' color='#007F7D'>{escape(url)}</link>", "path")
        self.p("Original concept and direction: <b>Phillip A. Holland Jr.</b> AI-assisted implementation and research synthesis. Original project code and assets are MIT-licensed. External sources are cited as prior work; no affiliation, endorsement, copied dataset, or reproduction of their reported results is implied.", "small")
        return self.pages


def attachments(e):
    data = {str(path.relative_to(ROOT)): path.read_bytes()
            for path in e.paths.values() if path.exists()}
    for relative in ("reports/unittest-v0.4.txt", "LICENSE"):
        path = ROOT / relative
        if path.exists():
            data[relative] = path.read_bytes()
    if e.manifest_path.exists():
        data["release-manifest-snapshot.json"] = e.manifest_path.read_bytes()
    readme = ["CausalFill-Bench v0.4.0 research report evidence snapshots", "",
              "These are recorded engineering evidence, not additional model trials.",
              "The release manifest and complete source archive accompany this PDF.",
              "Each entry below is SHA-256 followed by the release-relative path.", ""]
    for name, payload in sorted(data.items()):
        readme.append(hashlib.sha256(payload).hexdigest() + "  " + name)
    data["ATTACHMENTS-README.txt"] = ("\n".join(readme) + "\n").encode()
    return data


def decorate(c, page, total, e):
    c.saveState()
    c.setStrokeColor(LINE); c.setLineWidth(.5); c.line(MARGIN,H-39,W-MARGIN,H-39)
    c.setFillColor(MUTED); c.setFont("CFSans",7.2)
    c.drawString(MARGIN,H-29,"CAUSALFILL-BENCH  /  RESEARCH + VERIFICATION")
    c.drawRightString(W-MARGIN,H-29,"DRAFT" if e.draft else f"v{e.version}")
    c.line(MARGIN,45,W-MARGIN,45)
    c.setStrokeColor(TEAL); c.setLineWidth(1.8); c.line(MARGIN,45,MARGIN+CONTENT*page/total,45)
    c.setFillColor(MUTED); c.setFont("CFSans",6.9)
    c.drawString(MARGIN,29,f"{e.date}  |  Phillip A. Holland Jr.  |  AI-assisted research prototype")
    c.drawRightString(W-MARGIN,29,f"{page:02d} / {total:02d}")
    c.restoreState()


def build(e, destination, render_dir=None):
    register_fonts()
    report = Report(e)
    pages = report.compose()
    if len(pages) != 12:
        raise ValueError("The report must contain twelve deliberately composed pages.")
    temp = ROOT / "tmp/pdfs"
    temp.mkdir(parents=True, exist_ok=True)
    layout = temp / "v04-report-layout.pdf"
    c = canvas.Canvas(str(layout), pagesize=A4, pageCompression=1)
    title = "CausalFill-Bench v0.4.0: Adaptive Decisions and Checkable Guarantees"
    c.setTitle(title)
    c.setAuthor("Phillip A. Holland Jr.; AI-assisted development")
    c.setSubject("Finite-game optimality, runtime conformance, exact proof binding, public-interface pilot and research limits")
    for index, (heading, flowables) in enumerate(pages, 1):
        decorate(c, index, len(pages), e)
        c.bookmarkPage(f"page-{index}")
        c.addOutlineEntry(heading, f"page-{index}", level=0)
        frame = Frame(MARGIN, 60, CONTENT, H-116, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
        remaining = list(flowables)
        frame.addFromList(remaining, c)
        if remaining:
            raise RuntimeError(f"Layout overflow on page {index} ({heading}): {len(remaining)} flowables remain")
        c.showPage()
    c.save()
    bundle = attachments(e)
    reader = PdfReader(str(layout)); writer = PdfWriter(); writer.clone_document_from_reader(reader)
    for name, payload in bundle.items():
        writer.add_attachment(name, payload)
    writer.add_metadata({"/Title": title, "/Author": "Phillip A. Holland Jr.; AI-assisted development",
                         "/Subject": "Research prototype; bounded finite-model guarantees and explicit trust boundaries",
                         "/Keywords": "CausalFill-Bench, finite belief games, Lean, procurement, evaluation, reproducibility"})
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as out:
        writer.write(out)
    final = PdfReader(str(destination))
    text = "\n".join(page.extract_text() or "" for page in final.pages)
    if len(final.pages) != 12 or len(final.attachments) != len(bundle):
        raise RuntimeError("PDF page or attachment inventory changed")
    if "\ufffd" in text or "\u25a0" in text:
        raise RuntimeError("Unexpected missing-glyph marker in PDF text")
    if not e.draft and ("Pending final replay" in text or "DRAFT" in text):
        raise RuntimeError("Final PDF still contains a draft status")
    if render_dir:
        render_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(["pdftoppm", "-r", "110", "-png", str(destination), str(render_dir/"page")], check=True)
    return {"output": str(destination), "pages": 12, "bytes": destination.stat().st_size,
            "pdf_sha256": sha(destination), "draft": e.draft, "attachments": len(bundle),
            "manifest": str(e.manifest_path), "kernel_replay_status": e.kernel.get("status", "pending"),
            "required_kernel_roots": len(e.kernel_roots), "render_directory": str(render_dir) if render_dir else None,
            "word_count_approx": len(text.split()), "visual_inspection_required": True,
            "evidence_sha256": {key: sha(path) for key, path in e.paths.items() if path.exists()}}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", type=Path, default=MANIFEST)
    p.add_argument("--output", type=Path)
    p.add_argument("--draft", action="store_true")
    p.add_argument("--render", type=Path, help="Render every page with Poppler for visual inspection")
    args = p.parse_args()
    destination = args.output or (ROOT/"tmp/pdfs/CausalFill_Research_Report_v0.4.0_DRAFT.pdf" if args.draft else OUTPUT)
    print(json.dumps(build(Evidence(args.manifest, args.draft), destination, args.render), indent=2))


if __name__ == "__main__":
    main()
