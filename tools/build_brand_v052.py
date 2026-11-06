#!/usr/bin/env python3
"""Build the original, unscored v0.5.2 SVG identity and feature gallery.

SVG/HTML generation uses Python and Pillow for measured typography. PNG exports
use Inkscape. Rebuilding requires the local DejaVu Sans and Mono font files.
No benchmark result, model score, or proof result is inferred by this builder.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import html
import json
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "branding" / "v052"
VERSION = "0.5.2"
INK = "#172B43"
DEEP = "#102037"
PAPER = "#F6F4ED"
WHITE = "#FFFEFA"
BLUE = "#2455D9"
TEAL = "#126B52"
AMBER = "#825000"
MUTED = "#4B6177"
LINE = "#CCD5DE"
BLUE_TINT = "#E9EEFC"
TEAL_TINT = "#E5F1EA"
AMBER_TINT = "#F5EBDD"
DARK_MUTED = "#BFCFE0"
FONT = "DejaVu Sans,Arial,sans-serif"
MONO = "DejaVu Sans Mono,monospace"
ATTRIBUTION = "Project concept and direction: Phillip A. Holland Jr."
FONT_ROOT = Path("/usr/share/fonts/truetype/dejavu")

TASKS = [
    {"id": "words", "name": "Word recovery", "category": "Language", "cue": "Recover a routing rule", "source": "causalfill/domains/words.py", "doc": "docs/research-spec.md", "public": "Choose Boolean experiments to identify the missing literal routing words and conditions.", "verify": "An exhaustive truth table checks the recovered rule; causal and matched-slot random masks support controlled comparisons.", "limit": "A small generated rule system, with a declared vocabulary and tool contract."},
    {"id": "workflow", "name": "Executable workflow", "category": "Code", "cue": "Complete an expression", "source": "causalfill/domains/workflow.py", "doc": "docs/workflow-certification.md", "public": "Inspect the task contract and use bounded examples to recover a missing arithmetic expression.", "verify": "A restricted AST interpreter and sufficient symbolic certificate check equality and intermediate-value bounds over the stated integer domain.", "limit": "The certifier is deliberately incomplete: a rejected expression need not be mathematically wrong."},
    {"id": "grid", "name": "Grid transformation", "category": "Programs", "cue": "Infer a small program", "source": "causalfill/domains/grid.py", "doc": "docs/grid.md", "public": "Use original grid demonstrations and active experiments to infer a transformation in a typed DSL.", "verify": "The verifier checks the submitted program against finite behavioral tests and the supported language.", "limit": "Original procedural tasks; no third-party ARC task corpus is bundled."},
    {"id": "vending", "name": "Operational vending", "category": "Procurement", "cue": "Make the operation work", "source": "causalfill/domains/vending.py", "doc": "docs/research-spec.md", "public": "Recover procurement rules while observing stock, lead times, expiry, cash and actual receipts.", "verify": "A mutable simulator checks full-horizon operating and accounting goals after the procedure runs.", "limit": "Synthetic economic parameters and task costs, not a business-performance forecast."},
    {"id": "vending_adaptive", "name": "Adaptive procurement", "category": "Procurement", "cue": "Buy after learning", "source": "causalfill/domains/vending_adaptive.py", "doc": "docs/vending-adaptive.md", "public": "Gather information about hidden demand, then place irreversible orders as the operating state evolves.", "verify": "Exact finite-game cost certificates and separate strategy replay check contingent guaranteed-success procedures.", "limit": "Finite modeled markets; setup reads and final reconstruction are outside operational-game cost."},
    {"id": "robotics", "name": "Symbolic robotics", "category": "Robotics", "cue": "Recover a safe route", "source": "causalfill/domains/robotics.py", "doc": "docs/robotics.md", "public": "Combine calibrated symbolic cameras and obstacle observations to recover a target, route and handling condition.", "verify": "Exact decimal-rational predicates check workspace limits, collision and delivery in a simplified 3D scene.", "limit": "A symbolic simulator; physical actuator and contact-dynamics transfer is unestablished."},
    {"id": "robotics_barrier", "name": "Barrier navigation", "category": "Robotics", "cue": "Find the hidden gap", "source": "causalfill/domains/robotics_barrier.py", "doc": "docs/robotics-barrier.md", "public": "Use geometry-dependent observations to find a route through an initially hidden barrier gap.", "verify": "A separating-plane certificate checks paired feasible scenes that have no common valid continuous path.", "limit": "A bounded information-necessity construction, not a claim of model computational hardness."},
    {"id": "latent", "name": "Finite-field recovery", "category": "Algebra", "cue": "Identify an operator", "source": "causalfill/domains/latent.py", "doc": "docs/math-and-100d.md", "public": "Probe an affine operator over an exact finite field in the declared variable dimension.", "verify": "An affine certificate and exact arithmetic verify the reconstructed operator and controlled interventions.", "limit": "Vector probes return many field values; algebraic dimension is not a physical dimension."},
    {"id": "latent_sparse", "name": "Sparse affine recovery", "category": "Algebra", "cue": "Use scarce observations", "source": "causalfill/domains/latent.py", "doc": "docs/math-and-100d.md", "public": "Exploit sparse operator structure under a scarce synthetic observation budget.", "verify": "The same exact affine verifier checks recovery; a constructive reference uses five vector probes.", "limit": "Five 100-component probes expose 500 residues, not five scalar measurements."},
    {"id": "ambiguity", "name": "Calibrated abstention", "category": "Language", "cue": "Recognize an unseen answer", "source": "causalfill/domains/words.py", "doc": "docs/scoring.md", "public": "Two different required route words have identical permitted observations in the ambiguity control.", "verify": "Abstention is evaluated separately from answerable-task success and included in decision calibration.", "limit": "A deliberately unidentifiable control, not a generic test of uncertainty in arbitrary tasks."},
    {"id": "proof", "name": "Proof completion", "category": "Logic", "cue": "Prove the stated goal", "source": "causalfill/domains/proof.py", "doc": "docs/proof-track.md", "public": "Read immutable premises, a signed goal and the digest that binds this statement.", "verify": "A resolution refutation establishes entailment; a satisfying assignment for the premises prevents vacuous credit.", "limit": "Selected Lean claims have explicit scope; Python-to-Lean implementation equivalence is not proved."},
    {"id": "diagnosis", "name": "Adaptive diagnosis", "category": "Decisions", "cue": "Eliminate alternatives", "source": "causalfill/domains/diagnosis.py", "doc": "docs/identification-track.md", "public": "Choose binary experiments against a public candidate-world table under a certified query cap.", "verify": "The identified world must be supported by observed witnesses eliminating every competing world.", "limit": "A finite noiseless identification problem; a lucky correct guess alone is insufficient."},
    {"id": "visual", "name": "Controlled perception", "category": "Vision", "cue": "Read pixels into action", "source": "causalfill/domains/visual.py", "doc": "docs/visual-perception.md", "public": "Read actual PNG pixels with visible calibration landmarks, occlusion, palette variation and bounded noise.", "verify": "Independent latent geometry checks pose, relational object count and the executable routing choice.", "limit": "Controlled rendered scenes, not established natural-image recognition performance."},
    {"id": "robotics_vision", "name": "Rendered robotics", "category": "Robotics", "cue": "Sense, handle, deliver", "source": "causalfill/domains/robotics_vision.py", "doc": "docs/robotics-vision.md", "public": "Combine rendered scene observations with contact or friction information before irreversible simulated execution.", "verify": "The task checks delivery, sensing cost and legal robust alternatives under the public action laws.", "limit": "A small image-to-action simulator; physical robots and full 3D contact dynamics are separate work."},
    {"id": "robust_sensing", "name": "Signal Repair", "category": "Decisions", "cue": "Act despite faulty probes", "source": "causalfill/domains/robust_sensing.py", "doc": "docs/robust-sensing.md", "public": "Use costly, once-only probes under one global corruption cap, then irreversibly commit an action.", "verify": "Strict acceptance requires actual success, robust justification, operational budget compliance and observed exclusion witnesses.", "limit": "A finite symbolic controller with synthetic cost; outcome and certificate acceptance are separate diagnostics."},
]


def esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def text_width(text: str, size: float, weight: int = 400, mono: bool = False) -> float:
    try:
        from PIL import ImageFont
        name = "DejaVuSansMono" if mono else "DejaVuSans"
        if weight >= 600:
            name += "-Bold"
        font = ImageFont.truetype(str(FONT_ROOT / f"{name}.ttf"), round(size * 8))
        return float(font.getlength(text)) / 8
    except ImportError as error:
        raise RuntimeError("Brand authoring requires Pillow for measured typography; committed SVGs need no Python dependency to display") from error


def wrap(text: str, width: float, size: float, weight: int = 400) -> list[str]:
    result: list[str] = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split():
            candidate = f"{line} {word}".strip()
            if line and text_width(candidate, size, weight) > width:
                result.append(line)
                line = word
            else:
                line = candidate
        result.append(line)
    return result


class SVG:
    def __init__(self, width: int, height: int, title: str, description: str, background: str = PAPER):
        self.width, self.height = width, height
        self.parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">', f'<title id="title">{esc(title)}</title>', f'<desc id="desc">{esc(description)}</desc>']
        if background:
            self.rect(0, 0, width, height, background)

    def raw(self, value: str) -> None:
        self.parts.append(value)

    def rect(self, x, y, w, h, fill, radius=0, stroke=None, sw=1, dash=None) -> None:
        attrs = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
        if dash:
            attrs += f' stroke-dasharray="{dash}"'
        self.raw(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}"{attrs}/>')

    def line(self, x1, y1, x2, y2, color=LINE, sw=2, dash=None) -> None:
        extra = f' stroke-dasharray="{dash}"' if dash else ""
        self.raw(f'<path d="M{x1} {y1} L{x2} {y2}" stroke="{color}" stroke-width="{sw}" fill="none" stroke-linecap="round"{extra}/>')

    def circle(self, x, y, r, fill, stroke=None, sw=1) -> None:
        extra = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
        self.raw(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}"{extra}/>')

    def path(self, d, color=INK, sw=3, fill="none", dash=None) -> None:
        extra = f' stroke-dasharray="{dash}"' if dash else ""
        self.raw(f'<path d="{d}" fill="{fill}" stroke="{color}" stroke-width="{sw}" stroke-linecap="round" stroke-linejoin="round"{extra}/>')

    def text(self, x, y, value, size=24, color=INK, weight=400, width=None, anchor="start", mono=False, spacing=None) -> None:
        if width is not None and text_width(str(value), size, weight, mono) > width + 0.25:
            raise ValueError(f"Text exceeds {width}px at {size}px: {value!r}")
        attrs = f' letter-spacing="{spacing}"' if spacing else ""
        self.raw(f'<text x="{x}" y="{y}" font-family="{MONO if mono else FONT}" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" fill="{color}"{attrs}>{esc(value)}</text>')

    def para(self, x, y, value, width, size=24, leading=34, color=INK, weight=400, max_lines=None):
        lines = wrap(value, width, size, weight)
        if max_lines is not None and len(lines) > max_lines:
            raise ValueError(f"Paragraph exceeds {max_lines} lines: {value!r}")
        for index, line in enumerate(lines):
            self.text(x, y + index * leading, line, size, color, weight, width)
        return y + len(lines) * leading

    def finish(self) -> str:
        return "\n".join([*self.parts, "</svg>", ""])


def mark(s: SVG, x: float, y: float, size: float, color=INK, tile=BLUE, gap=BLUE) -> None:
    s.raw(f'<g transform="translate({x} {y}) scale({size / 80})">')
    s.path("M52 10 H23 Q10 10 10 23 V57 Q10 70 23 70 H57 Q70 70 70 57 V39", color, 7)
    s.rect(31, 31, 19, 19, "none", 3, gap, 2.8, "4 5")
    s.rect(57, 2, 21, 21, tile, 4)
    s.raw("</g>")


def symbol(s: SVG, key: str, x: float, y: float, size: float = 128, background=True) -> None:
    s.raw(f'<g transform="translate({x} {y}) scale({size / 128})">')
    if background:
        s.rect(0, 0, 128, 128, WHITE, 25, LINE, 1.3)
    stroke = 3.8

    def p(d, color=INK, sw=stroke, fill="none", dash=None):
        s.path(d, color, sw, fill, dash)

    def box(x, y, w, h, fill="none", color=INK, radius=5):
        s.rect(x, y, w, h, fill, radius, color, stroke)

    def dot(x, y, r=5, fill=BLUE, outline=None):
        s.circle(x, y, r, fill, outline, stroke)

    if key == "words":
        box(20, 27, 56, 25, PAPER)
        s.line(29, 39, 42, 39, INK, 3.8)
        s.rect(50, 32, 16, 15, BLUE_TINT, 3, BLUE, 2.5, "3 3")
        p("M47 54 V78 H87 M72 65 L87 78 L72 91", BLUE)
        box(88, 65, 21, 25, BLUE_TINT, BLUE, 4)
        p("M47 78 V103 H76")
        s.line(84, 103, 108, 103, MUTED, 3.8)
    elif key == "workflow":
        box(19, 22, 90, 84, PAPER, INK, 9)
        s.line(19, 43, 109, 43, LINE, 2)
        for xx in [30, 40, 50]:
            dot(xx, 33, 2.4, MUTED)
        p("M42 57 L28 72 L42 87 M86 57 L100 72 L86 87")
        box(54, 60, 21, 25, BLUE_TINT, BLUE, 4)
        s.line(59, 72, 70, 72, BLUE, 3)
        s.line(64.5, 66.5, 64.5, 77.5, BLUE, 3)
    elif key == "grid":
        for ix in range(3):
            for iy in range(3):
                s.rect(19 + ix * 15, 23 + iy * 15, 12, 12, BLUE if ix == 0 or iy == 2 else PAPER, 2, BLUE if ix == 0 or iy == 2 else LINE, 1.2)
        p("M78 39 H109 M98 28 L109 39 L98 50", BLUE)
        for ix in range(3):
            for iy in range(3):
                s.rect(67 + ix * 15, 66 + iy * 15, 12, 12, BLUE if ix == 2 or iy == 0 else PAPER, 2, BLUE if ix == 2 or iy == 0 else LINE, 1.2)
        p("M20 89 H49 M38 78 L49 89 L38 100", INK)
    elif key == "vending":
        box(24, 18, 76, 92, PAPER, INK, 8)
        box(33, 29, 43, 44, BLUE_TINT, BLUE, 4)
        for xx in [41, 54, 67]:
            p(f"M{xx} 38 V62", BLUE, 4.5)
        dot(87, 42, 5, AMBER_TINT, AMBER)
        s.line(83, 57, 92, 57, INK, 3)
        box(35, 84, 52, 13, PAPER, INK, 3)
        s.line(35, 111, 35, 116, INK, 4)
        s.line(89, 111, 89, 116, INK, 4)
    elif key == "vending_adaptive":
        s.path("M64 18 L81 35 L64 52 L47 35 Z", BLUE, 3.8, BLUE_TINT)
        p("M64 53 V66 H31 V83 M64 66 H97 V83")
        box(17, 84, 30, 26, PAPER, INK, 4)
        box(81, 84, 30, 26, BLUE_TINT, BLUE, 4)
        p("M17 93 H47 M81 93 H111", INK, 2.5)
        s.line(32, 84, 32, 102, INK, 2.5)
        s.line(96, 84, 96, 102, BLUE, 2.5)
        dot(102, 32, 9, AMBER_TINT, AMBER)
        s.line(99, 32, 105, 32, AMBER, 2.4)
    elif key == "robotics":
        p("M16 98 L62 116 L112 96 L67 78 Z", LINE, 2, PAPER)
        p("M29 99 H65 M47 99 V80 L70 58 L58 33", INK, 7)
        for xx, yy in [(47, 80), (70, 58), (58, 33)]:
            dot(xx, yy, 6, WHITE, INK)
        p("M58 33 L78 25 L87 35 M78 25 L83 16", BLUE, 4)
        box(85, 71, 20, 20, BLUE_TINT, BLUE, 3)
        s.line(95, 71, 95, 80, BLUE, 2.2)
    elif key == "robotics_barrier":
        box(18, 20, 92, 91, PAPER, LINE, 7)
        p("M52 21 V67 M52 94 V110 M84 21 V43 M84 70 V110", INK, 7)
        p("M30 95 V80 H68 V56 H99 V31", BLUE, 4)
        p("M92 38 L99 31 L106 38", BLUE, 3.5)
        dot(30, 95, 5, BLUE)
        s.rect(93, 25, 12, 12, BLUE_TINT, 3, BLUE, 2)
    elif key in {"latent", "latent_sparse"}:
        p("M32 20 H22 V103 H32 M96 20 H106 V103 H96", INK, 4)
        if key == "latent":
            for ix in range(4):
                for iy in range(4):
                    dot(40 + ix * 16, 35 + iy * 18, 4, BLUE if ix == iy else MUTED)
        else:
            for ix in range(4):
                for iy in range(4):
                    active = (ix, iy) in {(0, 0), (2, 1), (3, 2), (1, 3)}
                    dot(40 + ix * 16, 35 + iy * 18, 5 if active else 2.2, BLUE if active else LINE)
            p("M38 111 H89", BLUE, 4)
    elif key == "ambiguity":
        box(43, 18, 42, 26, BLUE_TINT, BLUE, 5)
        s.line(54, 31, 74, 31, BLUE, 3)
        p("M64 45 V64 H31 V82 M64 64 H97 V82", INK, 3.8)
        box(17, 83, 29, 26, PAPER, INK, 5)
        box(82, 83, 29, 26, PAPER, INK, 5)
        dot(31, 96, 3.5, INK)
        for xx in [91, 102]:
            dot(xx, 96, 3.5, INK)
        s.path("M64 77 L76 90 L64 103 L52 90 Z", AMBER, 3, AMBER_TINT)
        s.line(64, 84, 64, 91, AMBER, 2.5)
        dot(64, 96, 1.2, AMBER)
    elif key == "proof":
        p("M31 17 H78 L97 37 V107 H31 Z", INK, 3.8, PAPER)
        p("M78 17 V38 H97", INK, 3.8)
        s.line(44, 52, 66, 52, MUTED, 3)
        s.line(44, 62, 84, 62, MUTED, 3)
        s.line(42, 73, 84, 73, INK, 3)
        s.line(51, 84, 76, 84, BLUE, 3.8)
        dot(94, 97, 18, BLUE_TINT, BLUE)
        p("M85 97 L92 103 L103 90", BLUE, 3.8)
    elif key == "diagnosis":
        for xx, yy in [(36, 34), (91, 34), (36, 93), (91, 93)]:
            dot(xx, yy, 12, BLUE_TINT if (xx, yy) == (91, 93) else PAPER, BLUE if (xx, yy) == (91, 93) else LINE)
        p("M29 27 L43 41 M84 27 L98 41 M29 86 L43 100", MUTED, 3)
        dot(63, 63, 14, WHITE, INK)
        p("M73 73 L81 81 M56 63 H70 M63 56 V70", BLUE, 3.3)
        p("M47 34 L53 48 M80 43 L74 51 M47 84 L53 77", LINE, 2)
    elif key == "visual":
        box(16, 23, 96, 78, PAPER, INK, 8)
        p("M26 87 L50 56 L68 79 L86 60 L103 86", LINE, 3)
        for xx, yy in [(29, 36), (99, 36), (29, 88)]:
            s.rect(xx - 4, yy - 4, 8, 8, AMBER, 1)
        dot(79, 55, 11, BLUE_TINT, BLUE)
        p("M63 44 V36 H71 M95 44 V36 H87 M63 66 V74 H71 M95 66 V74 H87", BLUE, 2.8)
        p("M37 110 H95 M47 106 V114 M61 106 V114 M75 106 V114 M89 106 V114", MUTED, 2)
    elif key == "robotics_vision":
        box(17, 20, 39, 27, PAPER, INK, 5)
        dot(36, 33, 7, BLUE_TINT, BLUE)
        p("M56 26 L67 20 V47 L56 41 Z", INK, 3.5, PAPER)
        p("M42 54 L30 79 M60 54 L84 79", LINE, 2.4, "none", "4 5")
        p("M16 95 H113 M50 73 V95 M78 73 V95", INK, 5)
        p("M28 111 H63 V84", BLUE, 4)
        p("M56 91 L63 84 L70 91", BLUE, 3)
        box(92, 66, 17, 17, BLUE_TINT, BLUE, 3)
        p("M100 48 V57 M93 52 L100 58 L107 52", MUTED, 2.8)
    elif key == "robust_sensing":
        for yy in [24, 52, 80]:
            box(15, yy, 45, 19, AMBER_TINT if yy == 52 else PAPER, AMBER if yy == 52 else INK, 5)
            p(f"M23 {yy+10} H29 L33 {yy+5} L39 {yy+14} L43 {yy+10} H52", AMBER if yy == 52 else BLUE, 2.4)
        p("M61 33 H70 V89 H61 M70 61 H83", INK, 3)
        p("M79 56 L85 61 L79 66", BLUE, 2.7)
        p("M99 40 L113 46 V66 Q113 81 99 90 Q85 81 85 66 V46 Z", BLUE, 3.5, BLUE_TINT)
        p("M92 63 L98 69 L107 56", BLUE, 3.5)
        p("M88 105 H111 M88 112 H104", MUTED, 2.6)
    else:
        raise ValueError(key)
    s.raw("</g>")


def small_label(s, x, y, text, color=MUTED):
    s.text(x, y, text, 16, color, 700, spacing=1.8)


def pill(s, x, y, text, width, color=BLUE, tint=BLUE_TINT, size=16):
    s.rect(x, y, width, 36, tint, 18)
    s.text(x + width / 2, y + 24, text, size, color, 600, width - 24, "middle")


def make_hero(mobile=False):
    if mobile:
        s = SVG(600, 1000, "CausalFill-Bench v0.5.2", "Recover what is missing. Show why it works. An executable research benchmark for budgeted evidence, actions and verified completions.")
        mark(s, 40, 30, 60)
        s.text(116, 73, "CausalFill", 32, INK, 700)
        s.text(119, 99, "BENCH", 13, MUTED, 700, spacing=5)
        small_label(s, 44, 150, "RESEARCH BENCHMARK / v0.5.2")
        for yy, line in [(218, "Recover what’s"), (280, "missing."), (348, "Show why it works.")]:
            s.text(42, yy, line, 46, INK, 700, 516)
        s.para(44, 401, "Budgeted evidence. Consequential actions.\nTyped completions with explicit verification.", 512, 23, 34, MUTED, max_lines=3)
        s.rect(40, 500, 520, 380, DEEP, 24)
        small_label(s, 66, 538, "THE EPISODE CONTRACT", DARK_MUTED)
        rows = [("01", "Observe", "Choose useful public evidence."), ("02", "Decide", "Keep uncertainty and cost in view."), ("03", "Commit", "Make the required action real."), ("04", "Verify", "Check the completion and evidence.")]
        for index, (number, title, body) in enumerate(rows):
            yy = 566 + index * 75
            s.circle(81, yy + 17, 17, "#284263")
            s.text(81, yy + 22, number, 13, PAPER, 700, anchor="middle")
            if index < 3:
                s.line(81, yy + 39, 81, yy + 52, "#5A7591", 2)
            s.text(116, yy + 15, title, 25, PAPER, 700)
            s.text(116, yy + 43, body, 18, DARK_MUTED, width=409)
        s.text(44, 928, "15 configurations · one evidence-first workflow", 20, MUTED, width=516)
        s.text(44, 964, "Phillip A. Holland Jr. · Original work under MIT", 18, MUTED, width=516)
        return s.finish()
    s = SVG(1440, 680, "CausalFill-Bench v0.5.2", "Recover what is missing. Show why it works. Observe, decide, commit and verify across fifteen task configurations. Capability illustration; no model performance result is asserted.")
    mark(s, 58, 38, 64)
    s.text(142, 78, "CausalFill", 33, INK, 700)
    s.text(145, 104, "BENCH", 13, MUTED, 700, spacing=5)
    small_label(s, 64, 179, "RESEARCH BENCHMARK / v0.5.2")
    s.text(60, 262, "Recover what’s missing.", 57, INK, 700, 802)
    s.text(60, 338, "Show why it works.", 57, INK, 700, 802)
    s.para(64, 402, "Budgeted evidence. Consequential actions.\nTyped completions with explicit verification.", 770, 25, 38, MUTED, max_lines=2)
    pill(s, 64, 493, "15 task configurations", 237)
    pill(s, 316, 493, "Dependency-free Python core", 314, INK, "#E8E7E0")
    s.line(64, 576, 804, 576, LINE, 1.5)
    s.text(64, 611, ATTRIBUTION, 20, MUTED, width=760)
    s.text(64, 641, "Original task code and SVG artwork · MIT", 17, MUTED)
    s.rect(884, 58, 492, 564, DEEP, 27)
    small_label(s, 919, 108, "THE EPISODE CONTRACT", DARK_MUTED)
    rows = [("01", "Observe", "Choose useful evidence.", "visual"), ("02", "Decide", "Account for cost and uncertainty.", "diagnosis"), ("03", "Commit", "Execute the required action.", "vending_adaptive"), ("04", "Verify", "Check the fill and its evidence.", "proof")]
    for index, (number, title, body, key) in enumerate(rows):
        yy = 145 + index * 113
        s.rect(911, yy, 438, 96, "#1B3553", 14)
        symbol(s, key, 927, yy + 16, 64)
        s.text(1012, yy + 35, title, 27, PAPER, 700)
        s.text(1013, yy + 65, body, 18, DARK_MUTED, width=318)
        s.text(1327, yy + 30, number, 12, DARK_MUTED, 600, anchor="end", mono=True)
        if index < 3:
            s.line(958, yy + 100, 958, yy + 108, "#87A7C7", 2)
    return s.finish()


def make_social():
    s = SVG(1280, 640, "CausalFill-Bench v0.5.2 social cover", "Evidence before commitment. An executable research prototype for missing information, bounded tools and verified completions. No model score is asserted.", DEEP)
    mark(s, 58, 43, 71, PAPER, "#94B4FF", "#94B4FF")
    s.text(151, 92, "CausalFill-Bench", 34, PAPER, 700)
    small_label(s, 67, 180, "EXECUTABLE RESEARCH / v0.5.2", DARK_MUTED)
    s.text(62, 276, "Evidence before", 67, PAPER, 700, 790)
    s.text(62, 358, "commitment.", 67, PAPER, 700, 790)
    s.para(67, 424, "Recover the missing. Choose observations.\nComplete a procedure that can be checked.", 776, 25, 37, DARK_MUTED, max_lines=2)
    s.line(67, 535, 1211, 535, "#3B526D", 1.3)
    s.text(67, 580, "15 task configurations · budgeted tools · explicit verification", 20, DARK_MUTED, width=875)
    s.text(1211, 580, "PHILLIP A. HOLLAND JR.", 14, DARK_MUTED, 600, anchor="end")
    s.rect(901, 169, 300, 300, "#1B3553", 32)
    mark(s, 948, 214, 205, PAPER, "#94B4FF", "#94B4FF")
    for xx in [942, 1051, 1160]:
        s.circle(xx, 138, 7, "#94B4FF")
        s.line(xx, 149, xx, 168, "#6080A3", 2)
    return s.finish()


def make_identity():
    result = {}
    for dark in [False, True]:
        style = "dark" if dark else "light"
        bg, fg, tile = (DEEP, PAPER, "#94B4FF") if dark else (PAPER, INK, BLUE)
        s = SVG(256, 256, f"CausalFill-Bench icon, {style}", "Open frame, missing center tile, and the distinct piece that can complete it.", bg)
        mark(s, 46, 44, 164, fg, tile, tile)
        result[f"identity/icon-{style}.svg"] = s.finish()
        s = SVG(760, 180, f"CausalFill-Bench wordmark, {style}", "CausalFill-Bench open-frame identity and wordmark.", bg)
        mark(s, 26, 33, 116, fg, tile, tile)
        s.text(174, 94, "CausalFill", 55, fg, 700, 550)
        s.text(179, 132, "B E N C H", 21, fg, 600)
        result[f"identity/wordmark-{style}.svg"] = s.finish()
    return result


SIGNAL_STEPS = [
    ("01", "Choose probes", "Read each sensor at most once. Every accepted probe spends resources.", "visual"),
    ("02", "Track possibilities", "A world remains feasible while its total contradictions stay at or below k.", "diagnosis"),
    ("03", "Commit an action", "Reserve the action cost. Commit once; no probes are accepted afterward.", "vending_adaptive"),
    ("04", "Support the fill", "Bind to the public contract. Cite accepted pre-commit exclusion witnesses.", "proof"),
]


def make_signal(mobile=False):
    if mobile:
        s = SVG(600, 1210, "Signal Repair: the evidence-to-action contract", "A fixed world, costly once-only probes and one global corruption cap. Track feasible worlds, commit an action and supply observed exclusion witnesses.")
        small_label(s, 40, 54, "FEATURE 01 / SIGNAL REPAIR")
        s.text(37, 120, "Spend evidence", 47, INK, 700, 526)
        s.text(37, 179, "wisely.", 47, INK, 700, 526)
        s.para(40, 228, "A fixed world. Fallible probes.\nOne shared corruption cap.", 520, 23, 33, MUTED, max_lines=2)
        s.rect(40, 302, 520, 113, BLUE_TINT, 16)
        s.text(61, 342, "PROBE COST + ACTION COST", 18, BLUE, 700, 478)
        s.text(61, 381, "Stay within the operational budget.", 23, INK, 600, 478)
        for index, (number, title, body, key) in enumerate(SIGNAL_STEPS):
            yy = 444 + index * 151
            s.rect(40, yy, 520, 134, WHITE, 18, LINE, 1.3)
            symbol(s, key, 59, yy + 24, 62)
            s.text(142, yy + 37, title, 26, INK, 700, 395)
            s.para(143, yy + 71, body, 386, 20, 28, MUTED, max_lines=3)
        s.para(40, 1090, "Certificate rule: cite k+1 distinct contradictory observations for every world outside the action’s success set.", 520, 21, 30, INK, max_lines=3)
        s.text(40, 1190, "Finite symbolic controller · synthetic resource costs", 18, MUTED, width=520)
        return s.finish()
    s = SVG(1440, 880, "Signal Repair: spend evidence wisely", "A fixed world, costly once-only probes and one global corruption cap. Query, track compatible worlds, commit once and bind a certificate to accepted pre-commit observations. This is a capability illustration, not an evaluation result.")
    small_label(s, 64, 63, "FEATURE 01 / SIGNAL REPAIR")
    s.text(60, 143, "Spend evidence wisely.", 57, INK, 700, 1312)
    s.text(64, 193, "A fixed world. Fallible probes. One shared corruption cap.", 26, MUTED, width=1312)
    s.rect(64, 235, 1312, 99, BLUE_TINT, 18)
    s.text(90, 276, "Operational budget", 29, BLUE, 700)
    s.text(91, 310, "Accepted probes plus one terminal action", 21, MUTED)
    s.text(1336, 297, "probe cost + action cost ≤ budget", 30, INK, 600, anchor="end")
    for index, (number, title, body, key) in enumerate(SIGNAL_STEPS):
        col, row = index % 2, index // 2
        xx, yy = 64 + col * 672, 374 + row * 182
        s.rect(xx, yy, 640, 156, WHITE, 18, LINE, 1.3)
        symbol(s, key, xx + 24, yy + 30, 84)
        s.text(xx + 133, yy + 49, title, 28, INK, 700, 456)
        s.para(xx + 134, yy + 87, body, 474, 22, 30, MUTED, max_lines=2)
        s.text(xx + 616, yy + 30, number, 13, MUTED, 600, anchor="end", mono=True)
    s.para(64, 776, "Certificate rule: k+1 distinct accepted pre-commit observations must contradict every world outside the action’s success set.", 1312, 23, 33, INK, max_lines=2)
    s.text(64, 848, "Finite symbolic controller · synthetic resource costs · capability illustration", 19, MUTED)
    return s.finish()


ACCEPTANCE_CASES = [
    ("Successful, justified action; within budget; valid complete certificate", "Successful", "Accepted", True),
    ("Successful action; invalid or incomplete final certificate", "Successful", "Rejected", False),
    ("Action fails in the actual world", "Failed", "Rejected", False),
]


def make_acceptance(mobile=False):
    if mobile:
        s = SVG(600, 1250, "Outcome and acceptance are separate", "Signal Repair reports the actual committed action outcome independently of final certificate validity. Strict acceptance requires the successful outcome and every evidence and budget obligation.")
        small_label(s, 40, 54, "FEATURE 02 / SCORING CLARITY")
        s.para(37, 118, "Outcome and acceptance are separate.", 526, 43, 54, INK, 700, max_lines=3)
        s.para(40, 306, "Preserve what the committed action did, even if the final certificate is invalid.", 520, 23, 33, MUTED, max_lines=3)
        blocks = [("OUTCOME", "Did the committed action succeed in the actual world?"), ("STRICT ACCEPTANCE", "Did success, budget, justification and certificate obligations all pass?")]
        for index, (title, body) in enumerate(blocks):
            yy = 423 + index * 154
            s.rect(40, yy, 520, 134, WHITE, 16, LINE, 1.3)
            s.text(62, yy + 35, title, 17, BLUE, 700)
            s.para(62, yy + 72, body, 476, 23, 32, INK, max_lines=2)
        for index, (case, outcome, strict, passing) in enumerate(ACCEPTANCE_CASES):
            yy = 755 + index * 123
            s.rect(40, yy, 520, 108, BLUE_TINT if passing else WHITE, 15, LINE, 1.2)
            s.para(60, yy + 29, case, 480, 19, 26, INK, 600, max_lines=2)
            s.text(60, yy + 87, f"Outcome: {outcome}", 18, BLUE, 600)
            s.text(540, yy + 87, f"Strict: {strict}", 18, BLUE if passing else AMBER, 600, anchor="end")
        s.para(40, 1170, "No committed action is identified separately.\nScoring illustration; no model results asserted.", 520, 18, 27, MUTED, max_lines=2)
        return s.finish()
    s = SVG(1440, 858, "Outcome and acceptance are separate", "Signal Repair preserves actual action outcome independently of certificate validity. A successful committed action with an invalid certificate retains a successful operational outcome and fails strict acceptance. Illustration, not measured model results.")
    small_label(s, 64, 63, "FEATURE 02 / SCORING CLARITY")
    s.text(60, 141, "Outcome and acceptance are separate.", 53, INK, 700, 1312)
    s.para(64, 190, "Signal Repair preserves what the committed action did, even when the final certificate is invalid.", 1312, 25, 36, MUTED, max_lines=1)
    for xx, title, body in [(64, "OUTCOME", "Did the committed action succeed in the actual world?"), (736, "STRICT ACCEPTANCE", "Did success, budget, justification and certificate obligations all pass?")]:
        s.rect(xx, 238, 640, 154, WHITE, 18, LINE, 1.3)
        s.text(xx + 26, 276, title, 18, BLUE, 700)
        s.para(xx + 26, 322, body, 586, 27, 37, INK, max_lines=2)
    s.rect(64, 434, 1312, 52, DEEP, 9)
    s.text(88, 467, "ILLUSTRATIVE CASE", 16, PAPER, 700)
    s.text(1058, 467, "OUTCOME", 16, PAPER, 700, anchor="middle")
    s.text(1260, 467, "STRICT", 16, PAPER, 700, anchor="middle")
    for index, (case, outcome, strict, passing) in enumerate(ACCEPTANCE_CASES):
        yy = 486 + index * 83
        s.rect(64, yy, 1312, 83, BLUE_TINT if passing else WHITE)
        s.line(64, yy + 83, 1376, yy + 83, LINE, 1.2)
        lines = wrap(case, 818, 22, 500)
        start = yy + (35 if len(lines) > 1 else 50)
        s.para(88, start, case, 818, 22, 29, INK, 500, max_lines=2)
        s.text(1058, yy + 50, outcome, 22, BLUE if outcome == "Successful" else INK, 600, anchor="middle")
        s.text(1260, yy + 50, strict, 22, BLUE if passing else AMBER, 600, anchor="middle")
    s.text(64, 788, "No committed action is identified separately; abstention does not erase a preceding commitment.", 22, INK, width=1312)
    s.text(64, 828, "Illustration of Signal Repair scoring semantics · no measured model result asserted", 19, MUTED)
    return s.finish()


EVIDENCE = [
    ("Measured", "A recorded observation", BLUE, BLUE_TINT, ["Source fingerprint", "Run configuration", "Traces and record hashes", "Population and uncertainty"]),
    ("Formally checked", "A selected statement", TEAL, TEAL_TINT, ["Theorem roots and types", "Assumptions and checker", "Original evidence version", "Explicit implementation scope"]),
    ("Proposed", "A research question", AMBER, AMBER_TINT, ["Independent model evaluation", "New authored mechanisms", "Replication and critique", "Transfer studied separately"]),
]


def evidence_symbol(s, index, x, y, size, color):
    if index == 0:
        for ix, height in enumerate([24, 42, 62]):
            s.rect(x + ix * size * .29, y + size - height * size / 70, size * .18, height * size / 70, color, 3)
    elif index == 1:
        s.rect(x, y + 4, size * .8, size * .8, "none", 7, color, 4)
        s.path(f"M{x + size*.17} {y+size*.46} L{x+size*.34} {y+size*.62} L{x+size*.65} {y+size*.27}", color, 4)
    else:
        mid, inset = size / 2, size * .08
        s.path(f"M{x+mid} {y+inset} L{x+size-inset} {y+mid} L{x+mid} {y+size-inset} L{x+inset} {y+mid} Z", color, 4)


def make_evidence(mobile=False):
    if mobile:
        s = SVG(600, 1330, "Keep every claim attached to evidence", "Measured observations, formally checked statements and proposed research each have distinct labels and provenance. Retained formal records preserve their original version.")
        small_label(s, 40, 54, "FEATURE 03 / EVIDENCE LANGUAGE")
        s.para(37, 119, "Keep every claim attached to evidence.", 526, 44, 55, INK, 700, max_lines=3)
        for index, (title, subtitle, color, tint, points) in enumerate(EVIDENCE):
            yy = 292 + index * 290
            s.rect(40, yy, 520, 266, WHITE, 18, LINE, 1.3)
            s.rect(40, yy, 520, 84, tint, 18)
            s.rect(40, yy + 62, 520, 22, tint)
            evidence_symbol(s, index, 62, yy + 22, 42, color)
            s.text(122, yy + 37, title, 25, color, 700, 416)
            s.text(122, yy + 65, subtitle, 19, INK, width=416)
            for line, point in enumerate(points):
                s.circle(66, yy + 118 + line * 35, 3, color)
                s.text(83, yy + 124 + line * 35, point, 21, INK, width=452)
        s.para(40, 1195, "Retained formal records keep their original version. A current code release does not certify new proof runs.", 520, 22, 32, MUTED, max_lines=4)
        return s.finish()
    s = SVG(1440, 836, "Keep every claim attached to evidence", "Measured observations, formally checked statements and proposed research have different requirements. Each claim keeps a specific source, scope and original evidence version. This guide is not a new proof or model evaluation.")
    small_label(s, 64, 63, "FEATURE 03 / EVIDENCE LANGUAGE")
    s.text(60, 141, "Keep every claim attached to evidence.", 53, INK, 700, 1312)
    s.text(64, 193, "Clear labels keep implementation, experiments and research goals readable.", 25, MUTED, width=1312)
    for index, (title, subtitle, color, tint, points) in enumerate(EVIDENCE):
        xx = 64 + index * 448
        s.rect(xx, 244, 416, 403, WHITE, 20, LINE, 1.3)
        s.rect(xx, 244, 416, 178, tint, 20)
        s.rect(xx, 402, 416, 20, tint)
        evidence_symbol(s, index, xx + 28, 270, 52, color)
        s.text(xx + 28, 364, title, 29, color, 700, 360)
        s.text(xx + 29, 397, subtitle, 21, INK, width=360)
        for line, point in enumerate(points):
            s.circle(xx + 31, 466 + line * 44, 3, color)
            s.text(xx + 47, 473 + line * 44, point, 21, INK, width=341)
    s.rect(64, 684, 1312, 98, "#E8E7E0", 15)
    s.para(88, 724, "Retained formal records keep their original version. A current code release does not certify new proof runs.", 1262, 25, 35, INK, max_lines=2)
    s.text(64, 817, "Evidence guide · no new theorem, frontier-model score or physical-robot transfer claimed", 19, MUTED)
    return s.finish()


def make_atlas():
    s = SVG(1500, 1010, "CausalFill-Bench task icon atlas", "Fifteen original configuration icons: word recovery, workflow, grids, vending, adaptive procurement, symbolic robotics, barrier navigation, finite-field and sparse recovery, abstention, proof, diagnosis, controlled perception, rendered robotics and Signal Repair. Capability illustrations, not scores.")
    small_label(s, 50, 49, "CAUSALFILL-BENCH / v0.5.2")
    s.text(47, 104, "Fifteen configurations. Distinct evidence problems.", 40, INK, 700, 1406)
    for index, task in enumerate(TASKS):
        col, row = index % 5, index // 5
        xx, yy = 50 + col * 283, 148 + row * 269
        s.rect(xx, yy, 268, 249, WHITE, 17, LINE, 1.2)
        symbol(s, task["id"], xx + 86, yy + 18, 96)
        s.text(xx + 134, yy + 146, task["name"], 18, INK, 700, 244, "middle")
        s.text(xx + 134, yy + 174, task["id"], 14.5, BLUE, 500, 244, "middle", mono=True)
        lines = wrap(task["cue"], 232, 17)
        for line, body in enumerate(lines):
            s.text(xx + 134, yy + 205 + line * 24, body, 17, MUTED, width=232, anchor="middle")
    s.text(50, 988, "Original vector artwork · conceptual domains may share configurations · capability illustrations, not evaluation results", 18, MUTED, width=1400)
    return s.finish()


def make_gallery():
    cards = []
    for task in TASKS:
        cards.append(f'''<article class="task-card" id="{esc(task['id'])}">
  <div class="task-top"><img src="icons/{esc(task['id'])}.svg" alt="" width="72" height="72"><span class="category">{esc(task['category'])}</span></div>
  <h3>{esc(task['name'])}</h3><code>{esc(task['id'])}</code>
  <p>{esc(task['public'])}</p>
  <details><summary>Verification and scope</summary><dl><dt>Acceptance</dt><dd>{esc(task['verify'])}</dd><dt>Boundary</dt><dd>{esc(task['limit'])}</dd></dl><a href="../../{esc(task['doc'])}">Read the task documentation <span aria-hidden="true">↗</span></a></details>
</article>''')
    return '''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<title>CausalFill-Bench v0.5.2 — visual feature guide</title>
<meta name="description" content="A visual guide to CausalFill-Bench: budgeted evidence, consequential actions, typed completions and explicit verification across fifteen task configurations.">
<link rel="icon" type="image/svg+xml" href="identity/icon-light.svg">
<style>
:root{--ink:#172B43;--deep:#102037;--paper:#F6F4ED;--white:#FFFEFA;--blue:#2455D9;--muted:#4B6177;--line:#CCD5DE;--teal:#126B52;--amber:#825000;--radius:18px}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:90px}body{margin:0;background:var(--paper);color:var(--ink);font:17px/1.65 system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}a{color:var(--blue);text-underline-offset:4px}a:hover{text-decoration-thickness:2px}a:focus-visible,summary:focus-visible{outline:3px solid var(--blue);outline-offset:5px;border-radius:3px}.skip{position:absolute;left:24px;top:-80px;background:var(--white);padding:10px 18px;z-index:9}.skip:focus{top:14px}.site-nav{border-bottom:1px solid var(--line);background:var(--paper)}.nav-inner{max-width:1312px;margin:auto;padding:19px 30px;display:flex;align-items:center;justify-content:space-between;gap:25px}.brand{display:flex;gap:12px;align-items:center;color:var(--ink);font-size:20px;font-weight:750;text-decoration:none}.brand img{width:42px;height:42px}.nav-links{display:flex;gap:26px;font-size:14px;font-weight:650}.nav-links a{color:var(--muted);text-decoration:none}.nav-links a:hover{color:var(--blue)}main{max-width:1376px;padding:0 32px;margin:0 auto}.hero{display:block;width:100%;height:auto}.hero-wrap{margin:18px -32px 0}.intro{padding:30px 32px 60px;display:grid;grid-template-columns:1.05fr 1fr;gap:70px;border-bottom:1px solid var(--line)}.eyebrow{text-transform:uppercase;letter-spacing:.13em;color:var(--muted);font-size:12px;font-weight:750;margin:0 0 16px}.intro h1{font-size:clamp(30px,3.1vw,44px);line-height:1.2;letter-spacing:-.035em;margin:0}.intro p{margin:0 0 18px}.button-row{display:flex;flex-wrap:wrap;gap:10px;margin-top:24px}.button{display:inline-block;background:var(--blue);color:white;text-decoration:none;padding:10px 17px;border-radius:8px;font-size:14px;font-weight:650}.button.secondary{background:transparent;color:var(--blue);box-shadow:inset 0 0 0 1px var(--blue)}section{padding:60px 0;scroll-margin-top:24px}.section-head{max-width:820px;margin:0 0 28px}.section-head h2{font-size:clamp(30px,3.3vw,44px);line-height:1.18;letter-spacing:-.03em;margin:0 0 18px}.section-head p{color:var(--muted);margin:0}.feature{border:1px solid var(--line);border-radius:var(--radius);overflow:hidden;background:var(--white);margin-top:28px}.feature img{display:block;width:100%;height:auto}.feature-text{padding:28px 36px 32px;border-top:1px solid var(--line);display:grid;grid-template-columns:1.1fr 1fr;gap:42px;background:var(--white)}.feature-text h3{font-size:23px;line-height:1.3;margin:0 0 12px}.feature-text p{margin:0 0 14px}.feature-text p:last-child{margin-bottom:0}.small{font-size:14px;color:var(--muted)}.tag{display:inline-flex;align-items:center;gap:7px;font-size:12px;font-weight:750;letter-spacing:.06em;text-transform:uppercase;background:#E9EEFC;color:var(--blue);padding:6px 10px;border-radius:99px}.tag:before{content:"";width:6px;height:6px;border-radius:50%;background:currentColor}.atlas-head{display:flex;justify-content:space-between;align-items:end;gap:32px}.atlas-head .section-head{margin-bottom:0}.atlas-head .button{white-space:nowrap}.task-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px;margin-top:32px;align-items:start}.task-card{background:var(--white);border:1px solid var(--line);border-radius:var(--radius);padding:25px;min-width:0}.task-top{display:flex;justify-content:space-between;align-items:center;gap:16px;margin-bottom:20px}.task-top img{flex-shrink:0}.category{font-size:12px;letter-spacing:.06em;text-transform:uppercase;font-weight:700;color:var(--muted)}.task-card h3{font-size:21px;line-height:1.3;margin:0 0 8px;letter-spacing:-.015em}.task-card code{font:13px/1.6 ui-monospace,SFMono-Regular,Consolas,monospace;color:var(--blue)}.task-card p{font-size:15px;line-height:1.6;margin:17px 0 22px}.task-card details{border-top:1px solid var(--line);padding-top:16px;font-size:14px}.task-card summary{cursor:pointer;font-weight:700;color:var(--blue);padding:2px 0;list-style-position:outside;margin-left:16px}.task-card details[open] summary{margin-bottom:16px}.task-card dl{margin:0 0 16px}.task-card dt{font-size:12px;letter-spacing:.07em;text-transform:uppercase;font-weight:750;color:var(--muted);margin:15px 0 6px}.task-card dd{margin:0}.evidence-notes{display:grid;grid-template-columns:repeat(3,1fr);gap:20px;margin-top:24px}.note{border-left:3px solid var(--blue);padding:8px 20px}.note h3{font-size:18px;margin:0 0 10px}.note p{font-size:15px;margin:0}.note.formal{border-color:var(--teal)}.note.proposed{border-color:var(--amber)}.build{background:var(--deep);color:var(--paper);border-radius:20px;padding:36px;margin:18px 0 70px}.build h2{margin:0 0 16px;font-size:30px;letter-spacing:-.025em}.build p{color:#BFCFE0;max-width:880px}.build a{color:#AFC6FF}.build pre{overflow-x:auto;background:#1B3553;color:var(--paper);padding:20px;border-radius:10px;font-size:14px;line-height:1.7;border:1px solid #3B526D}.build code{font-family:ui-monospace,SFMono-Regular,Consolas,monospace}.build-links{display:flex;gap:25px;flex-wrap:wrap;font-size:14px}.site-footer{max-width:1312px;margin:auto;border-top:1px solid var(--line);padding:28px 32px 40px;color:var(--muted);font-size:13px;display:flex;justify-content:space-between;gap:24px}.site-footer p{margin:0}.credit{max-width:760px}picture{display:block}@media(max-width:1000px){.intro{gap:35px;padding-left:0;padding-right:0}.task-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.feature-text{padding:26px;gap:26px}.nav-links{gap:16px}}@media(max-width:700px){body{font-size:16px}.nav-inner{padding:15px 20px;gap:12px;flex-wrap:wrap}.brand{font-size:18px}.brand img{width:34px;height:34px}.nav-links{gap:12px;font-size:12px;width:100%;justify-content:space-between}main{padding:0 20px}.hero-wrap{margin:6px -20px 0}.intro{grid-template-columns:1fr;gap:24px;padding:22px 0 40px}.intro h1{font-size:32px}.intro .button{font-size:13px}section{padding:42px 0}.feature{border-radius:13px}.feature-text{grid-template-columns:1fr;gap:18px;padding:24px}.feature-text h3{font-size:22px}.atlas-head{align-items:start;flex-direction:column;gap:20px}.task-grid{grid-template-columns:1fr;gap:15px;margin-top:26px}.task-card{padding:24px}.task-card p{font-size:16px}.task-card details{font-size:15px}.task-card h3{font-size:23px}.task-top{margin-bottom:17px}.task-top img{width:68px;height:68px}.evidence-notes{grid-template-columns:1fr;gap:23px}.build{padding:25px 22px;margin-bottom:44px}.build pre{font-size:12px;padding:15px}.build h2{font-size:27px}.site-footer{flex-direction:column;padding:24px 20px 36px;gap:12px}.section-head h2{font-size:32px}}@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}@media print{body{background:white}.site-nav,.button-row,.atlas-head .button{display:none}main{max-width:none;padding:0}.hero-wrap{margin:0}.task-grid{grid-template-columns:repeat(2,1fr)}.task-card,.feature{break-inside:avoid}.build{color:black;background:white;border:1px solid #CCD5DE}.build p,.build a{color:#172B43}.build pre{background:#F6F4ED;color:#172B43}section{padding:25px 0}}
</style>
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="site-nav"><nav class="nav-inner" aria-label="Primary"><a class="brand" href="#main"><img src="identity/icon-light.svg" width="42" height="42" alt="">CausalFill<span aria-hidden="true"> / </span><span>Bench</span></a><div class="nav-links"><a href="#features">Features</a><a href="#tasks">Task atlas</a><a href="#evidence">Evidence</a><a href="#rebuild">Rebuild</a></div></nav></header>
<main id="main">
<div class="hero-wrap"><picture><source media="(max-width:700px)" srcset="hero-mobile.svg"><img class="hero" src="hero.svg" width="1440" height="680" alt="CausalFill-Bench v0.5.2. Recover what is missing. Show why it works. Observe, decide, commit and verify."></picture></div>
<div class="intro"><div><p class="eyebrow">Visual feature guide · author/evaluator view</p><h1>Make the completed procedure work. Account for the evidence.</h1></div><div><p>CausalFill-Bench is an executable research prototype for agents that recover missing information, choose bounded observations and produce typed completions. Some tasks also require irreversible action and an observed certificate.</p><p>This gallery explains the implemented mechanisms. It contains capability illustrations, with no new model-performance or theorem result asserted.</p><div class="button-row"><a class="button" href="../../README.md">Open the benchmark</a><a class="button secondary" href="../../docs/brand-v052.md">Asset and build guide</a></div></div></div>
<section id="features" aria-labelledby="features-title"><div class="section-head"><p class="eyebrow">Mechanisms that matter</p><h2 id="features-title">From missing information to a checked completion.</h2><p>The public episode defines what can be observed, what actions cost and what the verifier expects. The agent must make those pieces work together.</p></div>
<article class="feature"><picture><source media="(max-width:700px)" srcset="features/signal-repair-mobile.svg"><img src="features/signal-repair.svg" width="1440" height="880" loading="lazy" alt="Signal Repair: costly once-only probes, one shared corruption cap, robust action commitment and observed exclusion witnesses."></picture><div class="feature-text"><div><span class="tag">Implemented · robust_sensing</span><h3>Evidence can change which action is justified.</h3><p>One world is fixed, and at most <em>k</em> distinct probes may return a flipped answer. A world remains possible while the total disagreement with accepted observations is at most <em>k</em>. That allowance never resets between observations.</p><p>The agent can stop when it has enough evidence for an action that succeeds in every remaining world. A common successful bypass can need no sensing.</p></div><div><h3>The final fill carries an obligation.</h3><p>For every world outside the committed action’s success set, the fill cites at least <em>k</em>+1 distinct accepted pre-commit probe observations that contradict that world. The statement digest binds the fill to the public contract.</p><p class="small">Tool cost is a synthetic resource convention. The finite controller does not establish physical-sensor reliability or real-world robotics transfer.</p><a href="../../docs/robust-sensing.md">Read the complete Signal Repair contract ↗</a></div></div></article>
<article class="feature"><picture><source media="(max-width:700px)" srcset="features/outcome-acceptance-mobile.svg"><img src="features/outcome-acceptance.svg" width="1440" height="858" loading="lazy" alt="Outcome and strict acceptance are separate. A successful action can keep its successful outcome while an invalid final certificate is rejected."></picture><div class="feature-text"><div><span class="tag">v0.5.2 · scoring clarity</span><h3>Record the action that actually happened.</h3><p>Signal Repair diagnostics derive outcome and robust justification from the committed action and its captured observation history. Malformed final text does not rewrite that history. A later abstention or termination does not erase a preceding commitment.</p></div><div><h3>Keep acceptance strict.</h3><p>Strict acceptance still needs successful operation, robust justification, a valid complete certificate and compliance with the operational budget. A separate flag identifies episodes with no committed action.</p><a href="../../docs/scoring.md">Read the scoring definitions ↗</a></div></div></article>
<article class="feature"><div class="feature-text" style="border-top:0"><div><span class="tag">v0.5.2 · offline run review</span><h3>Inspect each run in context.</h3><p>The review command turns recorded episodes into a self-contained evaluator HTML page. Configuration-separated summaries sit beside task, split and result filters, operational outcomes, costs and expandable episode records.</p><p><code>python -m causalfill review RUN_DIR --output review.html --verify-traces</code></p></div><div><h3>Check the supplied provenance.</h3><p>When requested, the loader verifies supplied trace chains and final record bindings. It checks a supplied manifest against the record population and recomputes the summary from those records.</p><p class="small">The review contains private evaluator details. A consistent trace establishes internal consistency, not authenticated model authorship, enforced solver isolation or a rerun of the task.</p><a href="../../README.md">Run the benchmark and inspect its outputs ↗</a></div></div></article>
</section>
<section id="tasks" aria-labelledby="tasks-title"><div class="atlas-head"><div class="section-head"><p class="eyebrow">Fifteen runnable configurations</p><h2 id="tasks-title">Different gaps. Explicit contracts.</h2><p>These configurations span nine conceptual domains. Related configurations share a domain; the number of generated instances or passing controls is not an intelligence score.</p></div><a class="button secondary" href="icon-atlas.svg">Open the SVG atlas</a></div><div class="task-grid">''' + "\n".join(cards) + '''</div></section>
<section id="evidence" aria-labelledby="evidence-title"><div class="section-head"><p class="eyebrow">Claims with a scope</p><h2 id="evidence-title">Make the evidence easy to inspect.</h2><p>Design intent, observed behavior and selected proof statements answer different questions. CausalFill keeps those categories visible.</p></div><div class="feature"><picture><source media="(max-width:700px)" srcset="features/evidence-language-mobile.svg"><img src="features/evidence-language.svg" width="1440" height="836" loading="lazy" alt="Measured observations need run provenance. Formal statements need roots, assumptions and checker records. Proposed research needs independent evaluation and replication."></picture></div><div class="evidence-notes"><div class="note"><h3>Measured</h3><p>Scripted controls establish behavior of those controls in the reported setup. A model study must identify its actual model, harness, budget and held-out population.</p></div><div class="note formal"><h3>Formally checked</h3><p>Selected Lean claims retain their original evidence version. They do not prove the whole Python runtime, optimizer, renderer or physical robot.</p></div><div class="note proposed"><h3>Proposed</h3><p>Broader model comparisons, independently authored hidden mechanisms and external replication remain research objectives until measured.</p></div></div></section>
<section class="build" id="rebuild" aria-labelledby="build-title"><p class="eyebrow" style="color:#BFCFE0">Original vector assets · MIT</p><h2 id="build-title">Rebuild the complete visual system.</h2><p>Run the deterministic authoring tool from the repository root. Authoring uses Python, Pillow and local DejaVu fonts for measured typography. PNG exports additionally use Inkscape. The committed SVGs and gallery display without these authoring tools.</p><pre><code>python tools/build_brand_v052.py
python tools/build_brand_v052.py --check
python tools/build_brand_v052.py --render</code></pre><p>The manifest binds each asset to exact bytes and records its documentation sources. This checks packaging and provenance; it does not rerun an experiment or a proof.</p><div class="build-links"><a href="manifest.json">Asset manifest</a><a href="social-card.svg">Social cover</a><a href="../../docs/brand-v052.md">Brand guidance</a><a href="../../LICENSE">MIT license</a></div></section>
</main><footer class="site-footer"><p class="credit">Project concept and direction: <strong>Phillip A. Holland Jr.</strong><br>AI-assisted implementation and design. Original task code and SVG artwork under MIT; retained third-party proof dependencies keep their upstream terms.</p><p>CausalFill-Bench v0.5.2<br>Capability illustrations · no new model scores</p></footer>
</body></html>
'''


def contrast(a, b):
    def luminance(color):
        components = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [v / 12.92 if v <= 0.04045 else ((v + .055) / 1.055) ** 2.4 for v in components]
        return sum(x * weight for x, weight in zip(linear, [.2126, .7152, .0722]))
    aa, bb = sorted((luminance(a), luminance(b)), reverse=True)
    return (aa + .05) / (bb + .05)


def verify_svg(name, data):
    root = ET.fromstring(data)
    if root.tag != "{http://www.w3.org/2000/svg}svg":
        raise ValueError(f"Not an SVG: {name}")
    ns = "{http://www.w3.org/2000/svg}"
    if root.find(ns + "title") is None or root.find(ns + "desc") is None:
        raise ValueError(f"Missing accessible title/description: {name}")
    banned = {"script", "foreignObject", "image", "filter", "animate", "animateTransform", "set"}
    for element in root.iter():
        tag = element.tag.split("}")[-1]
        if tag in banned:
            raise ValueError(f"Unsupported active/external element {tag}: {name}")
        for key, value in element.attrib.items():
            local = key.split("}")[-1]
            if local.lower().startswith("on") or local in {"href", "src"} or "url(" in value:
                raise ValueError(f"External/active SVG content: {name}")


def verify_registry():
    tree = ast.parse((ROOT / "causalfill/registry.py").read_text())
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "factories")
    returned = next(node.value for node in ast.walk(function) if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict))
    ids = [ast.literal_eval(key) for key in returned.keys]
    expected = [task["id"] for task in TASKS]
    if ids != expected:
        raise ValueError(f"Task atlas does not match runtime registry: {ids!r} != {expected!r}")


def build_assets():
    verify_registry()
    assets = {"hero.svg": make_hero(), "hero-mobile.svg": make_hero(True), "social-card.svg": make_social(), "icon-atlas.svg": make_atlas(), "features/signal-repair.svg": make_signal(), "features/signal-repair-mobile.svg": make_signal(True), "features/outcome-acceptance.svg": make_acceptance(), "features/outcome-acceptance-mobile.svg": make_acceptance(True), "features/evidence-language.svg": make_evidence(), "features/evidence-language-mobile.svg": make_evidence(True), "index.html": make_gallery()}
    assets.update(make_identity())
    for task in TASKS:
        s = SVG(128, 128, f"CausalFill-Bench: {task['name']}", task["public"] + " " + task["verify"], "")
        symbol(s, task["id"], 0, 0)
        assets[f"icons/{task['id']}.svg"] = s.finish()
    assets["tokens.json"] = json.dumps({"schema": "causalfill.brand-tokens.v052", "version": VERSION, "colors": {"ink": INK, "deep_ink": DEEP, "paper": PAPER, "white": WHITE, "measured": BLUE, "formally_checked": TEAL, "proposed": AMBER, "muted": MUTED, "line": LINE}, "fonts": {"sans": FONT, "mono": MONO}, "evidence_labels_required": True, "original_artwork_license": "MIT"}, indent=2) + "\n"
    for name, content in assets.items():
        if name.endswith(".svg"):
            verify_svg(name, content)
    pairs = [(INK, PAPER), (MUTED, PAPER), (BLUE, BLUE_TINT), (TEAL, TEAL_TINT), (AMBER, AMBER_TINT), (PAPER, DEEP), (DARK_MUTED, "#1B3553")]
    checks = [{"foreground": a, "background": b, "ratio": round(contrast(a, b), 3)} for a, b in pairs]
    if any(check["ratio"] < 4.5 for check in checks):
        raise ValueError("A body-text palette pair fails the 4.5:1 contrast check")
    sources = sorted({"causalfill/registry.py", "causalfill/review.py", "causalfill/cli.py", "docs/brand.md", "docs/brand-v052.md", "LICENSE", *[task["source"] for task in TASKS], *[task["doc"] for task in TASKS]})
    manifest = {"schema": "causalfill.brand-assets.v052", "release_version": VERSION, "attribution": ATTRIBUTION, "artwork_license": "MIT", "evidence_kind": "capability illustrations and scoring semantics", "model_results_asserted": False, "new_proof_runs_asserted": False, "builder": {"path": "tools/build_brand_v052.py", "sha256": digest(Path(__file__).read_bytes())}, "registry_configuration_ids": [task["id"] for task in TASKS], "source_bindings": [{"path": path, "sha256": digest((ROOT / path).read_bytes())} for path in sources], "contrast_checks": checks, "assets": [{"path": name, "bytes": len(content.encode()), "sha256": digest(content.encode())} for name, content in sorted(assets.items())], "validation": {"xml_parse": "pass", "svg_title_and_description": "pass", "no_active_or_remote_svg_content": "pass", "registry_ids": "pass", "body_text_palette_contrast": "pass"}, "visual_qa": "See visual-qa.json for named inspected renders; structural validation is not visual inspection."}
    assets["manifest.json"] = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    return assets


def render_assets():
    inkscape = shutil.which("inkscape")
    if not inkscape:
        raise RuntimeError("PNG rendering requires Inkscape on PATH")
    preview = OUTPUT / "previews"
    preview.mkdir(exist_ok=True)
    requests = [("hero.svg", 900), ("hero-mobile.svg", 375), ("social-card.svg", 960), ("icon-atlas.svg", 1200), ("features/signal-repair.svg", 900), ("features/signal-repair-mobile.svg", 375), ("features/outcome-acceptance.svg", 900), ("features/outcome-acceptance-mobile.svg", 375), ("features/evidence-language.svg", 900), ("features/evidence-language-mobile.svg", 375), ("identity/wordmark-light.svg", 760), ("identity/wordmark-dark.svg", 760)]
    record = []
    composites = []
    for name, width in requests:
        filename = name.replace("/", "--").removesuffix(".svg") + f"-{width}.png"
        target = preview / filename
        command = [inkscape, str(OUTPUT / name), "--export-type=png", f"--export-width={width}", f"--export-filename={target}"]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(f"Inkscape failed for {name}: {result.stderr}")
        record.append({"source": name, "source_sha256": digest((OUTPUT / name).read_bytes()), "render": str(target.relative_to(OUTPUT)), "sha256": digest(target.read_bytes()), "width": width})
    # A compact icon sheet tests the marks at actual UI size, without labels
    # baked into the glyphs. Pillow is only an authoring dependency.
    try:
        from PIL import Image, ImageDraw, ImageFont
        font = ImageFont.truetype(str(FONT_ROOT / "DejaVuSans.ttf"), 12)
        canvas = Image.new("RGB", (860, 350), PAPER)
        draw = ImageDraw.Draw(canvas)
        draw.text((22, 17), "Task glyphs at 64 px / 32 px", font=font, fill=INK)
        for index, task in enumerate(TASKS):
            name = f"icons/{task['id']}.svg"
            target = preview / f"icon-{task['id']}-128.png"
            result = subprocess.run([inkscape, str(OUTPUT / name), "--export-type=png", "--export-width=128", f"--export-filename={target}"], capture_output=True, text=True)
            if result.returncode:
                raise RuntimeError(f"Icon export failed: {task['id']}")
            image = Image.open(target).convert("RGBA")
            xx, yy = 22 + index % 5 * 168, 50 + index // 5 * 98
            canvas.paste(image.resize((64, 64), Image.Resampling.LANCZOS), (xx, yy), image.resize((64, 64), Image.Resampling.LANCZOS))
            small = image.resize((32, 32), Image.Resampling.LANCZOS)
            canvas.paste(small, (xx + 78, yy + 21), small)
            draw.text((xx, yy + 69), task["id"], font=font, fill=INK)
            record.append({"source": name, "source_sha256": digest((OUTPUT / name).read_bytes()), "render": str(target.relative_to(OUTPUT)), "sha256": digest(target.read_bytes()), "width": 128})
        sheet = preview / "icons-ui-contact-sheet.png"
        canvas.save(sheet)
        composites.append({"render": str(sheet.relative_to(OUTPUT)), "sha256": digest(sheet.read_bytes()), "sources": [f"icons/{task['id']}.svg" for task in TASKS], "description": "Task glyphs shown at 64 and 32 pixels."})
        overview = Image.new("RGB", (1600, 1760), PAPER)
        heading = ImageFont.truetype(str(FONT_ROOT / "DejaVuSans-Bold.ttf"), 32)
        label = ImageFont.truetype(str(FONT_ROOT / "DejaVuSans.ttf"), 20)
        draw = ImageDraw.Draw(overview)
        draw.text((40, 28), "CausalFill-Bench / v0.5.2", font=heading, fill=INK)
        draw.text((40, 76), "SVG system contact sheet · capability illustrations", font=label, fill=MUTED)
        placements = [("hero-900.png", 40, 120, 1040), ("hero-mobile-375.png", 1180, 120, 375), ("icon-atlas-1200.png", 40, 650, 1080), ("identity--wordmark-dark-760.png", 1180, 790, 375), ("social-card-960.png", 1180, 930, 375), ("features--signal-repair-900.png", 40, 1400, 480), ("features--outcome-acceptance-900.png", 560, 1400, 480), ("features--evidence-language-900.png", 1080, 1400, 480)]
        for filename, xx, yy, width in placements:
            picture = Image.open(preview / filename).convert("RGB")
            height = round(picture.height * width / picture.width)
            overview.paste(picture.resize((width, height), Image.Resampling.LANCZOS), (xx, yy))
        draw.text((40, 1718), "Original SVG artwork · Phillip A. Holland Jr. project concept and direction · MIT", font=label, fill=MUTED)
        target = preview / "brand-contact-sheet.png"
        overview.save(target)
        composites.append({"render": str(target.relative_to(OUTPUT)), "sha256": digest(target.read_bytes()), "sources": ["previews/" + row[0] for row in placements], "description": "Asset contact sheet, not a browser screenshot."})
    except ImportError:
        pass
    (OUTPUT / "render-record.json").write_text(json.dumps({"schema": "causalfill.brand-render.v052", "renderer": "Inkscape", "renders": record, "composites": composites, "claim": "Rendered assets only; see the separate visual QA record for actual inspection."}, indent=2, sort_keys=True) + "\n")
    return len(record)


def main():
    global FONT_ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Check deterministic outputs and source bindings without writing")
    parser.add_argument("--render", action="store_true", help="Export SVG previews with Inkscape")
    parser.add_argument("--font-dir", type=Path, default=FONT_ROOT, help="Directory containing DejaVuSans and DejaVuSansMono regular/bold .ttf files")
    args = parser.parse_args()
    if args.check and args.render:
        parser.error("--check and --render are separate operations")
    FONT_ROOT = args.font_dir
    try:
        assets = build_assets()
        if args.check:
            mismatches = [name for name, content in assets.items() if not (OUTPUT / name).is_file() or (OUTPUT / name).read_bytes() != content.encode()]
            if mismatches:
                raise ValueError("Missing, changed or stale generated assets: " + ", ".join(mismatches))
            print(json.dumps({"status": "pass", "release": VERSION, "generated_files": len(assets), "svg_assets": sum(name.endswith('.svg') for name in assets), "task_icons": len(TASKS), "model_results_asserted": False}))
        else:
            OUTPUT.mkdir(parents=True, exist_ok=True)
            for name, content in assets.items():
                target = OUTPUT / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content.encode())
            rendered = render_assets() if args.render else 0
            print(json.dumps({"status": "written", "release": VERSION, "generated_files": len(assets), "svg_assets": sum(name.endswith('.svg') for name in assets), "task_icons": len(TASKS), "rendered_previews": rendered}))
    except (ValueError, RuntimeError, OSError) as error:
        print(f"brand build failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
