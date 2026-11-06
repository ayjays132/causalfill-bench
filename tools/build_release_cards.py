#!/usr/bin/env python3
"""Build the CausalFill visual identity and source-bound SVG evidence cards.

This is a documentation tool, not a benchmark evaluator. Pillow is used for
conservative text measurement; Inkscape is optional for PNG preview rendering.
The delivered SVGs contain no scripts, remote assets, embedded fonts or filters.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from html import escape
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError as error:
    raise SystemExit("Card authoring requires Pillow; benchmark execution does not.") from error


ROOT = Path(__file__).resolve().parents[1]
PALETTE = {
    "ink": "#172B43",
    "ink_deep": "#102037",
    "ink_lift": "#223A56",
    "paper": "#F6F4ED",
    "white": "#FFFFFF",
    "muted": "#52647B",
    "light_text": "#BDCBDD",
    "line": "#D7DFE8",
    "dark_line": "#3B536F",
    "blue": "#2455D9",
    "blue_light": "#EAF0FF",
    "blue_bright": "#7FA9FF",
    "teal": "#126B52",
    "teal_light": "#E5F5EC",
    "mint": "#87E3BA",
    "amber": "#825000",
    "amber_light": "#FFF0D9",
    "gold": "#F6BC62",
}
KINDS = {
    "measured": ("Measured", PALETTE["blue"], PALETTE["blue_light"]),
    "formal": ("Formally checked", PALETTE["teal"], PALETTE["teal_light"]),
    "proposed": ("Proposed", PALETTE["amber"], PALETTE["amber_light"]),
}
FONT_FAMILY = "DejaVu Sans, Arial, sans-serif"
MONO_FAMILY = "DejaVu Sans Mono, Consolas, monospace"
FONT_CANDIDATES = {
    "regular": ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "C:/Windows/Fonts/arial.ttf"],
    "bold": ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "C:/Windows/Fonts/arialbd.ttf"],
    "mono": ["/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", "C:/Windows/Fonts/consola.ttf"],
}
FONT_PATHS: dict[str, str] = {}
FONT_CACHE: dict[tuple[str, int], Any] = {}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def font(size: float, style: str = "regular"):
    key = (style, round(size))
    if key not in FONT_CACHE:
        candidates = ([FONT_PATHS[style]] if style in FONT_PATHS else []) + FONT_CANDIDATES[style]
        for candidate in candidates:
            try:
                FONT_CACHE[key] = ImageFont.truetype(candidate, key[1])
                FONT_PATHS[style] = candidate
                break
            except OSError:
                continue
        else:
            raise ValueError("No supported local font for " + style + "; use --font-regular/--font-bold/--font-mono")
    return FONT_CACHE[key]


def text_width(text: str, size: float, style: str = "regular", spacing: float = 0) -> float:
    return float(font(size, style).getlength(text)) + max(0, len(text) - 1) * spacing


def wrap(text: str, width: float, size: float, style: str = "regular", max_lines: int = 10) -> list[str]:
    lines: list[str] = []
    for paragraph in str(text).split("\n"):
        line = ""
        for word in paragraph.split():
            trial = word if not line else line + " " + word
            if text_width(trial, size, style) <= width:
                line = trial
            elif line:
                lines.append(line)
                line = word
            else:
                raise ValueError("A word is too wide for its card: " + word)
            if text_width(line, size, style) > width:
                raise ValueError("A word is too wide for its card: " + line)
        lines.append(line)
    if len(lines) > max_lines:
        raise ValueError(f"Text needs {len(lines)} lines, maximum {max_lines}: {text}")
    return lines


def safe_id(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-z][a-z0-9-]{0,60}", value):
        raise ValueError("Card IDs must use lowercase letters, digits and hyphens.")
    return value


class SVG:
    def __init__(self, width: int, height: int, title: str, description: str, background: str | None = None):
        self.width, self.height = width, height
        self.title, self.description = title, description
        self.body: list[str] = []
        self.texts: list[dict[str, Any]] = []
        if background:
            self.rect(0, 0, width, height, background)

    def add(self, raw: str):
        self.body.append(raw)

    def rect(self, x, y, w, h, fill, radius=0, stroke=None, sw=1, dash=None):
        more = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
        more += f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}"{more}/>')

    def line(self, x1, y1, x2, y2, color, width=1, dash=None):
        more = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="{width}" stroke-linecap="round"{more}/>')

    def path(self, d, color, width=1, fill="none", dash=None):
        more = f' stroke-dasharray="{dash}"' if dash else ""
        self.add(f'<path d="{d}" fill="{fill}" stroke="{color}" stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round"{more}/>')

    def circle(self, x, y, r, fill, stroke=None, sw=1):
        more = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
        self.add(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{fill}"{more}/>')

    def text(self, x, y, value: str, size=28, color=None, style="regular", anchor="start", spacing=0):
        value = str(value)
        color = color or PALETTE["ink"]
        weight = "700" if style == "bold" else "400"
        family = MONO_FAMILY if style == "mono" else FONT_FAMILY
        more = f' letter-spacing="{spacing}"' if spacing else ""
        self.add(f'<text x="{x}" y="{y}" fill="{color}" font-family="{family}" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}"{more}>{escape(value)}</text>')
        measured = text_width(value, size, style, spacing)
        left = x if anchor == "start" else x - measured / 2 if anchor == "middle" else x - measured
        bbox = font(size, style).getbbox(value, anchor="ls")
        self.texts.append({"text": value, "x": round(left, 3), "y_top": round(y + bbox[1], 3),
                           "right": round(left + measured, 3), "bottom": round(y + bbox[3], 3), "font_size": size})

    def block(self, x, y, value: str, width: float, size=28, color=None, style="regular", leading=None, max_lines=10):
        lines = wrap(value, width, size, style, max_lines)
        leading = leading or size * 1.45
        for index, line in enumerate(lines):
            self.text(x, y + index * leading, line, size, color, style)
        return y + len(lines) * leading

    def write(self, path: Path):
        for item in self.texts:
            if item["x"] < -0.1 or item["right"] > self.width + .1 or item["y_top"] < -0.1 or item["bottom"] > self.height + .1:
                raise ValueError(f"Text outside SVG bounds in {path.name}: {item}")
        content = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" height="{self.height}" '
                   f'viewBox="0 0 {self.width} {self.height}" role="img" aria-labelledby="title desc">\n'
                   f'<title id="title">{escape(self.title)}</title>\n<desc id="desc">{escape(self.description)}</desc>\n'
                   + "\n".join(self.body) + "\n</svg>\n")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return {"path": path.as_posix(), "width": self.width, "height": self.height,
                "sha256": sha(path), "title": self.title, "text_elements": len(self.texts),
                "text_bounds_passed": True}


def mark(s: SVG, x: float, y: float, size: float, dark=True):
    """An open square frame plus a separate filling tile; original geometric art."""
    scale = size / 80
    stroke = PALETTE["paper"] if dark else PALETTE["ink"]
    s.add(f'<g transform="translate({x} {y}) scale({scale})">')
    s.path("M52 10 H23 Q10 10 10 23 V57 Q10 70 23 70 H57 Q70 70 70 57 V39", stroke, 8)
    s.rect(31, 31, 19, 19, "none", 3, PALETTE["gold"] if dark else PALETTE["blue"], 3, "4 5")
    s.rect(57, 2, 21, 21, PALETTE["mint"] if dark else PALETTE["blue"], 4)
    s.add('</g>')


def small_symbol(s: SVG, x: float, y: float, kind: str, color: str, size=30):
    scale = size / 30
    s.add(f'<g transform="translate({x} {y}) scale({scale})">')
    if kind == "measured":
        s.line(3, 26, 27, 26, color, 2)
        s.rect(4, 16, 4, 7, color, 1)
        s.rect(13, 10, 4, 13, color, 1)
        s.rect(22, 3, 4, 20, color, 1)
    elif kind == "formal":
        s.rect(3, 3, 24, 24, "none", 5, color, 2)
        s.path("M8 15 L13 20 L22 10", color, 3)
    else:
        s.path("M15 2 L28 15 L15 28 L2 15 Z", color, 2)
        s.circle(15, 15, 3, color)
    s.add('</g>')


def chip(s: SVG, x, y, label, kind, small=False):
    title, color, pale = KINDS[kind]
    text = label or title
    size = 18 if small else 22
    width = text_width(text, size, "bold") + (55 if small else 66)
    height = 38 if small else 46
    s.rect(x, y, width, height, pale, height / 2)
    small_symbol(s, x + 12, y + 8, kind, color, 22 if small else 28)
    s.text(x + (42 if small else 50), y + (25 if small else 31), text, size, color, "bold")
    return width


def wordmark(dark=True):
    bg = PALETTE["ink_deep"] if dark else PALETTE["paper"]
    foreground = PALETTE["paper"] if dark else PALETTE["ink"]
    s = SVG(1040, 180, "CausalFill-Bench wordmark", "CausalFill-Bench: an open frame and a filling tile, with the project name.", bg)
    mark(s, 36, 45, 90, dark)
    s.text(158, 107, "CausalFill", 76, foreground, "bold")
    s.line(603, 58, 603, 126, PALETTE["dark_line"] if dark else PALETTE["line"], 2)
    s.text(635, 105, "BENCH", 37, PALETTE["mint"] if dark else PALETTE["blue"], "bold", spacing=4)
    return s


def motif(s: SVG, x: float, y: float, width: float, dark=True):
    """Diagrammatic missing-component art; no model score or theorem is asserted."""
    scale = width / 600
    s.add(f'<g transform="translate({x} {y}) scale({scale})">')
    ink, lifted, line = PALETTE["ink_deep"], PALETTE["ink_lift"], PALETTE["dark_line"]
    # The backdrop is deliberately geometric rather than a decorative neural net.
    s.rect(55, 102, 515, 390, "#0B182B", 24)
    s.rect(42, 89, 515, 390, lifted, 24, line, 2)
    s.line(66, 146, 534, 146, line, 1)
    for i in range(3):
        s.circle(76 + 21 * i, 118, 4.5, PALETTE["light_text"])
    # 3x3 procedure grid with one explicitly missing center.
    for row in range(3):
        for col in range(3):
            xx, yy = 88 + 101 * col, 176 + 88 * row
            if row == col == 1:
                s.rect(xx, yy, 83, 70, ink, 10, PALETTE["gold"], 3, "7 8")
                s.path(f"M{xx+29} {yy+24} H{xx+54} M{xx+29} {yy+35} H{xx+45} M{xx+29} {yy+46} H{xx+50}", PALETTE["gold"], 3)
            else:
                s.rect(xx, yy, 83, 70, "#2B4564", 10, "#4B6380", 1)
                if (row, col) in {(0, 0), (2, 1)}:
                    s.path(f"M{xx+23} {yy+35} L{xx+34} {yy+46} L{xx+59} {yy+23}", PALETTE["mint"], 4)
                else:
                    s.line(xx + 22, yy + 29, xx + 61, yy + 29, "#93ABC7", 4)
                    s.line(xx + 22, yy + 43, xx + 47, yy + 43, "#6F88A8", 4)
    # A distinct observation panel sits above the task; its data are abstract bars.
    s.rect(0, 0, 300, 107, PALETTE["paper"], 16)
    s.circle(28, 28, 7, PALETTE["blue"])
    s.rect(48, 21, 140, 13, PALETTE["ink"], 4)
    for index, length in enumerate((190, 132, 160)):
        s.rect(26, 49 + 14 * index, length, 6, "#A8B8CE" if index != 1 else PALETTE["blue"], 3)
    # The recovered tile remains visibly separated, connected by a routing line.
    s.rect(436, 275, 132, 132, "#0B182B", 19)
    s.rect(424, 263, 132, 132, PALETTE["mint"], 19)
    s.path("M456 327 L478 349 L525 302", PALETTE["ink_deep"], 10)
    s.path("M423 324 H385 V299 H286", PALETTE["gold"], 3, dash="5 8")
    s.path("M297 291 L286 299 L297 307", PALETTE["gold"], 3)
    s.rect(358, 27, 202, 57, PALETTE["ink_deep"], 28, PALETTE["dark_line"], 2)
    s.circle(386, 55, 7, PALETTE["gold"])
    for i in range(4):
        s.rect(407 + i * 28, 48, 18, 14, PALETTE["blue_bright"] if i < 2 else PALETTE["ink_lift"], 3)
    s.add('</g>')


def hero(mobile=False):
    w, h = (760, 1140) if mobile else (1800, 760)
    s = SVG(w, h, "CausalFill-Bench — recover the missing, prove the result",
            "A research benchmark for tool-using agents. Recover what is missing, choose the evidence, and make the completed procedure work. Concept and direction: Phillip A. Holland Jr.", PALETTE["ink_deep"])
    pad = 50 if mobile else 80
    for x in range(pad, w, 80):
        s.line(x, 0, x, h, "#1A2D47", 1)
    for y in range(40, h, 80):
        s.line(0, y, w, y, "#1A2D47", 1)
    s.rect(0, h - 10, w * .64, 10, PALETTE["mint"])
    s.rect(w * .64, h - 10, w * .36, 10, PALETTE["blue"])
    mark(s, pad, 46 if mobile else 55, 58 if mobile else 64, True)
    s.text(pad + 82, 88 if mobile else 103, "CausalFill", 40 if mobile else 48, PALETTE["paper"], "bold")
    s.text(pad + 82, 118 if mobile else 137, "BENCH", 16 if mobile else 18, PALETTE["mint"], "bold", spacing=4)
    if mobile:
        s.text(pad, 187, "A BENCHMARK FOR TOOL-USING AGENTS", 18, PALETTE["light_text"], "bold", spacing=.7)
        s.text(pad, 270, "Recover", 76, PALETTE["paper"], "bold")
        s.text(pad, 355, "the missing.", 76, PALETTE["paper"], "bold")
        s.text(pad, 440, "Prove the result.", 59, PALETTE["mint"], "bold")
        s.block(pad, 496, "Choose what to observe.\nMake the completed procedure work.", 660, 26, PALETTE["light_text"], leading=39, max_lines=2)
        motif(s, 94, 590, 570)
        s.text(pad, 1096, "Concept + direction: Phillip A. Holland Jr.", 17, PALETTE["light_text"])
    else:
        s.text(pad, 205, "A BENCHMARK FOR TOOL-USING AGENTS", 21, PALETTE["light_text"], "bold", spacing=2)
        s.text(pad, 316, "Recover the missing.", 78, PALETTE["paper"], "bold")
        s.text(pad, 416, "Prove the result.", 78, PALETTE["mint"], "bold")
        s.block(pad, 488, "Choose what to observe.\nMake the completed procedure work.", 880, 30, PALETTE["light_text"], leading=44, max_lines=2)
        labels = [("MASKED TASKS", 80, 258), ("ACTIVE EVIDENCE", 358, 300), ("CHECKED OUTCOMES", 678, 336)]
        for value, x, ww in labels:
            s.rect(x, 598, ww, 52, PALETTE["ink_lift"], 10, PALETTE["dark_line"], 1)
            s.text(x + 20, 631, value, 19, PALETTE["paper"], "bold", spacing=.4)
        s.text(pad, 711, "Concept + direction: Phillip A. Holland Jr.  /  AI-assisted research", 18, PALETTE["light_text"])
        motif(s, 1100, 163, 620)
        s.text(1100, 718, "OBSERVATION  /  COMPLETION  /  VERIFICATION", 17, PALETTE["light_text"], "bold", spacing=1)
    return s


def cover(social=False):
    w, h = (1280, 640) if social else (1600, 1000)
    s = SVG(w, h, "CausalFill-Bench research cover", "CausalFill-Bench. Recover the missing. Prove the result. Original concept and direction: Phillip A. Holland Jr.", PALETTE["paper"])
    s.rect(w * .63, 0, w * .37, h, PALETTE["ink_deep"])
    pad = 60 if social else 80
    mark(s, pad, pad, 65 if social else 80, False)
    s.text(pad + (88 if social else 110), pad + (45 if social else 55), "CausalFill", 44 if social else 58, PALETTE["ink"], "bold")
    s.text(pad + (88 if social else 110), pad + (73 if social else 92), "BENCH", 18 if social else 22, PALETTE["blue"], "bold", spacing=4)
    s.text(pad, 212 if social else 300, "RESEARCH / EVIDENCE / ACTION", 18 if social else 22, PALETTE["muted"], "bold", spacing=1)
    if social:
        s.text(pad, 302, "Recover the", 64, PALETTE["ink"], "bold")
        s.text(pad, 376, "missing.", 64, PALETTE["ink"], "bold")
        s.text(pad, 453, "Prove the result.", 46, PALETTE["blue"], "bold")
        motif(s, 838, 162, 385)
        s.text(pad, 584, "Phillip A. Holland Jr.  /  AI-assisted research", 18, PALETTE["muted"])
    else:
        s.text(pad, 430, "Recover the", 87, PALETTE["ink"], "bold")
        s.text(pad, 535, "missing.", 87, PALETTE["ink"], "bold")
        s.text(pad, 655, "Prove the result.", 65, PALETTE["blue"], "bold")
        s.block(pad, 746, "A benchmark for agents that choose evidence,\nrestore a component, and make a procedure work.", 850, 28, PALETTE["muted"], leading=42, max_lines=3)
        motif(s, 1052, 276, 495)
        s.text(pad, 936, "Concept + direction: Phillip A. Holland Jr.", 23, PALETTE["muted"])
        s.text(1053, 937, "RESEARCH PROTOTYPE", 19, PALETTE["light_text"], "bold", spacing=1.1)
    s.rect(0, h - 10, w * .63, 10, PALETTE["blue"])
    s.rect(w * .63, h - 10, w * .37, 10, PALETTE["mint"])
    return s


def evidence_legend(mobile=False):
    descriptions = {
        "measured": "Observed in a recorded run. Read the units, configuration and source.",
        "formal": "A specified theorem was checked. Its assumptions and scope still matter.",
        "proposed": "A research goal or planned experiment. No completed result is implied.",
    }
    w, h = (760, 850) if mobile else (1800, 420)
    s = SVG(w, h, "CausalFill evidence legend", "Three explicit evidence classes: Measured, Formally checked and Proposed. Color is supplemented by words and symbols.", PALETTE["paper"])
    s.text(44, 63, "READ THE CLAIM. THEN READ ITS SCOPE.", 23 if mobile else 29, PALETTE["ink"], "bold", spacing=.5)
    for index, kind in enumerate(KINDS):
        xx, yy, ww, hh = (32, 101 + index * 237, 696, 215) if mobile else (32 + index * 590, 110, 556, 268)
        title, color, pale = KINDS[kind]
        s.rect(xx, yy, ww, hh, PALETTE["white"], 18, PALETTE["line"], 1)
        s.rect(xx, yy, 7, hh, color, 3)
        small_symbol(s, xx + 26, yy + 26, kind, color, 37)
        s.text(xx + 82, yy + 54, title, 29, color, "bold")
        s.block(xx + 29, yy + 104, descriptions[kind], ww - 62, 24, PALETTE["muted"], leading=35, max_lines=4)
    return s


def metric_card(metric: dict[str, Any], version: str, preview=False):
    kind = metric["kind"]
    title, color, pale = KINDS[kind]
    value = str(metric["display_value"])
    s = SVG(800, 500, metric["label"] + ": " + value,
            f'{title}. {metric["label"]}: {value}. Scope: {metric["scope"]}. Source: {metric.get("source", "design preview")}.', PALETTE["paper"])
    s.rect(14, 14, 772, 472, PALETTE["white"], 22, PALETTE["line"], 1)
    s.rect(14, 14, 10, 472, color, 5)
    chip(s, 48, 42, None, kind)
    stamp = "LAYOUT ONLY" if preview else metric.get("record_label", version)
    if stamp:
        if text_width(stamp, 18, "mono") > 324:
            raise ValueError("Record label is too long for the evidence card: " + stamp)
        s.text(746, 72, stamp, 18, PALETTE["muted"], "mono", "end")
    value_size = 105
    while text_width(value, value_size, "mono") > 690 and value_size > 40:
        value_size -= 1
    s.text(48, 212, value, value_size, PALETTE["ink"], "mono")
    label_y = 266
    end_y = s.block(48, label_y, metric["label"], 690, 31, PALETTE["ink"], "bold", leading=40, max_lines=2)
    s.block(48, max(337, end_y + 12), metric["scope"], 690, 26, PALETTE["muted"], leading=32, max_lines=3)
    s.line(48, 438, 746, 438, PALETTE["line"], 1)
    source = "Design preview — no result asserted" if preview else Path(metric.get("source", "Research proposal")).name
    while text_width(source, 19, "mono") > 660 and len(source) > 12:
        source = source[:-2] + "…"
    s.text(48, 468, source, 19, PALETTE["muted"], "mono")
    return s


def metric_sheet(metrics: list[dict[str, Any]], version: str, mobile=False, preview=False):
    """Compose the same cards as vectors, with a dedicated one-column layout."""
    columns = 1 if mobile else 2
    width, pad, gap = (760, 20, 18) if mobile else (1800, 64, 32)
    card_width = (width - 2 * pad - (columns - 1) * gap) / columns
    scale = card_width / 800
    card_height = 500 * scale
    rows = math.ceil(len(metrics) / columns)
    header = 160 if mobile else 220
    footer = 100 if mobile else 120
    height = math.ceil(header + rows * card_height + max(0, rows - 1) * gap + footer)
    title = "Evidence at a glance" if not preview else "Evidence card design preview"
    s = SVG(width, height, title, " ".join(
        f'{KINDS[row["kind"]][0]}. {row["label"]}: {row["display_value"]}. {row["scope"]}' for row in metrics), PALETTE["paper"])
    s.text(pad + 14, 66 if mobile else 88, title, 32 if mobile else 52, PALETTE["ink"], "bold")
    s.block(pad + 14, 108 if mobile else 145,
            "Every result carries its evidence class, scope and source.", width - 2 * pad - 28,
            23 if mobile else 29, PALETTE["muted"], leading=32, max_lines=2)
    for index, row in enumerate(metrics):
        child = metric_card(row, version, preview)
        x = pad + (index % columns) * (card_width + gap)
        y = header + (index // columns) * (card_height + gap)
        s.add(f'<g transform="translate({x} {y}) scale({scale})">')
        s.body.extend(child.body)
        s.add('</g>')
        s.texts.extend({**item, "x": round(x + item["x"] * scale, 3),
                        "right": round(x + item["right"] * scale, 3),
                        "y_top": round(y + item["y_top"] * scale, 3),
                        "bottom": round(y + item["bottom"] * scale, 3),
                        "font_size": item["font_size"] * scale} for item in child.texts)
    s.text(pad + 14, height - 55, "SCOPE IS PART OF THE RESULT.", 20 if mobile else 24,
           PALETTE["blue"], "bold", spacing=.7)
    s.text(pad + 14, height - 22, "Phillip A. Holland Jr. / AI-assisted research", 17 if mobile else 20, PALETTE["muted"])
    return s


TASKS = [
    ("words", "Routing words", "words", "A missing condition", "Chosen Boolean experiments", "A procedure that routes correctly"),
    ("workflow", "Executable workflow", "workflow", "A missing expression", "Public specifications and examples", "Checked equivalence within the DSL"),
    ("grid", "Grid induction", "grid", "A missing transformation", "Examples and active experiments", "A typed program with correct outputs"),
    ("market", "Adaptive procurement", "market", "A missing decision procedure", "Forecasts, assays and receipts", "Service and cash goals achieved"),
    ("robotics", "Robotics in simulation", "robotics", "State and action preconditions", "Views, geometry and contact probes", "A valid simulated delivery"),
    ("latent", "Mathematical state", "latent", "A structured hidden operator", "Finite-field vector probes", "An exact affine completion"),
    ("proof", "Proof completion", "proof", "A proof of a fixed claim", "An immutable statement", "A checked proof plus consistency"),
    ("diagnosis", "Diagnosis", "diagnosis", "A hidden candidate state", "Budgeted experiments", "Observed elimination evidence"),
    ("vision", "Controlled vision", "vision", "Pixel-derived spatial facts", "Rendered calibrated observations", "Recovery and an executable choice"),
]


def task_icon(s: SVG, x, y, name, color=PALETTE["blue"], scale=1):
    s.add(f'<g transform="translate({x} {y}) scale({scale})">')
    if name == "grid":
        for row in range(3):
            for col in range(3):
                s.rect(col * 18, row * 18, 13, 13, "none" if row == col == 1 else color, 2, color if row == col == 1 else None, 2)
    elif name == "words":
        s.line(0, 8, 50, 8, color, 4)
        s.line(0, 25, 15, 25, color, 4)
        s.rect(23, 17, 24, 16, "none", 3, color, 2, "3 4")
        s.line(0, 45, 36, 45, color, 4)
    elif name == "workflow":
        s.path("M15 8 L2 25 L15 42 M36 8 L49 25 L36 42 M30 3 L21 47", color, 4)
    elif name == "market":
        s.path("M3 20 H49 L43 4 H9 Z M7 22 V49 H45 V22 M18 49 V35 H34 V49", color, 3)
        s.path("M3 20 Q9 30 15 20 Q21 30 27 20 Q33 30 39 20 Q45 30 49 20", color, 3)
    elif name == "robotics":
        s.circle(10, 44, 5, color)
        s.circle(26, 21, 5, color)
        s.circle(45, 6, 5, color)
        s.line(10, 44, 26, 21, color, 6)
        s.line(26, 21, 45, 6, color, 6)
        s.path("M45 6 H56 V17 M0 53 H24", color, 4)
    elif name == "latent":
        s.path("M7 3 H0 V51 H7 M47 3 H54 V51 H47", color, 3)
        for row in range(3):
            for col in range(3):
                s.circle(16 + col * 11, 12 + row * 15, 2.8, color)
    elif name == "proof":
        s.rect(5, 1, 39, 51, "none", 5, color, 3)
        s.line(15, 13, 34, 13, color, 3)
        s.line(15, 21, 29, 21, color, 3)
        s.path("M14 36 L22 43 L38 28", color, 4)
    elif name == "diagnosis":
        s.circle(24, 24, 19, "none", color, 3)
        s.line(38, 38, 53, 53, color, 5)
        s.line(14, 24, 34, 24, color, 3)
        s.line(24, 14, 24, 34, color, 3)
    else:
        s.path("M0 26 Q26 -2 53 26 Q26 54 0 26 Z", color, 3)
        s.circle(26.5, 26, 9, "none", color, 3)
        s.circle(26.5, 26, 3, color)
    s.add('</g>')


def task_card(task, index):
    identity, title, icon, gap, evidence, outcome = task
    s = SVG(800, 510, title + " task card", f'{title}. Missing component: {gap}. Evidence: {evidence}. Acceptance: {outcome}. Controlled research task.', PALETTE["paper"])
    s.rect(14, 14, 772, 482, PALETTE["white"], 22, PALETTE["line"], 1)
    s.rect(46, 43, 76, 76, PALETTE["blue_light"], 17)
    task_icon(s, 58, 55, icon, scale=.95)
    s.text(745, 82, f"{index:02d}", 26, PALETTE["muted"], "mono", "end")
    s.text(46, 170, title, 34, PALETTE["ink"], "bold")
    for row, (name, content) in enumerate((("GAP", gap), ("EVIDENCE", evidence), ("ACCEPTANCE", outcome))):
        yy = 222 + row * 86
        s.text(46, yy, name, 16, PALETTE["blue"], "bold", spacing=1.7)
        s.block(46, yy + 34, content, 694, 25, PALETTE["muted"], leading=32, max_lines=2)
    return s


def signal_repair_card():
    s = SVG(800, 620, "Signal Repair — evidence before irreversible action",
            "A feature within the diagnosis and decision domain. One shared corruption cap across sensor queries; evidence before irreversible action; finite worst-case cost and a robust decision certificate. No model score is asserted.", PALETTE["paper"])
    s.rect(14, 14, 772, 592, PALETTE["white"], 22, PALETTE["line"], 1)
    s.rect(48, 44, 76, 76, PALETTE["blue_light"], 16)
    for index in range(3):
        y = 62 + 18 * index
        s.circle(65, y + 4, 4, PALETTE["blue"] if index != 1 else PALETTE["amber"])
        s.line(79, y + 4, 106, y + 4, PALETTE["blue"] if index != 1 else PALETTE["amber"], 3,
               "4 5" if index == 1 else None)
    s.text(744, 88, "DECISION DOMAIN / FEATURE", 18, PALETTE["muted"], "mono", "end")
    s.text(48, 178, "Signal Repair", 41, PALETTE["ink"], "bold")
    s.text(48, 220, "Evidence before irreversible action", 25, PALETTE["muted"])
    blocks = [
        ("SHARED CORRUPTION CAP", "One global budget for unreliable sensor replies."),
        ("ROBUST DECISION", "Act only when the evidence justifies the choice."),
        ("FINITE COST CERTIFICATE", "Check the worst-case cost within the stated model."),
    ]
    for index, (label, body) in enumerate(blocks):
        y = 286 + index * 96
        s.text(48, y, label, 18, PALETTE["blue"], "bold", spacing=1)
        s.block(48, y + 35, body, 692, 25, PALETTE["muted"], leading=34, max_lines=2)
    s.line(48, 557, 744, 557, PALETTE["line"], 1)
    s.text(48, 585, "A feature of the diagnosis and decision domain.", 18, PALETTE["muted"])
    return s


def benchmark_card(data: dict[str, Any], version: str, mobile=False, preview=False):
    w = 760 if mobile else 1800
    fields = data["fields"]
    if len(fields) != 6:
        raise ValueError("The benchmark card requires six concise fields.")
    pad = 42 if mobile else 64
    title_size, title_leading = (49, 62) if mobile else (68, 80)
    title_lines = wrap(data["title"], w - 2 * pad, title_size, "bold", 2)
    subtitle_y = max(281 if mobile else 226, 151 + (len(title_lines) - 1) * title_leading + 62)
    subtitle_size, subtitle_leading = (24, 34) if mobile else (27, 38)
    subtitle_lines = wrap(data["subtitle"], w - 2 * pad, subtitle_size, max_lines=2)
    base_header = 360 if mobile else 278
    header = max(base_header, subtitle_y + (len(subtitle_lines) - 1) * subtitle_leading + (45 if mobile else 52))
    extra_header = header - base_header
    h = (2080 if mobile else 1270) + extra_header
    s = SVG(w, h, data["title"] + " — benchmark card", data["subtitle"] + " " + " ".join(f'{f["label"]}: {f["body"]}' for f in fields), PALETTE["paper"])
    s.rect(0, 0, w, header, PALETTE["ink_deep"])
    mark(s, pad, 36, 45, True)
    s.text(pad + 67, 70, "CAUSALFILL / BENCHMARK CARD", 19 if mobile else 23, PALETTE["paper"], "bold", spacing=.6)
    stamp = "DESIGN PREVIEW" if preview else version
    if not mobile and stamp:
        s.text(w - pad, 70, stamp, 20, PALETTE["mint"], "mono", "end")
    elif stamp:
        s.text(pad, header - 13, stamp, 17, PALETTE["mint"], "mono")
    s.block(pad, 151, data["title"], w - 2 * pad, title_size, PALETTE["paper"], "bold", leading=title_leading, max_lines=2)
    s.block(pad, subtitle_y, data["subtitle"], w - 2 * pad, subtitle_size, PALETTE["light_text"], leading=subtitle_leading, max_lines=2)
    card_w = w - 2 * pad if mobile else (w - 2 * pad - 28) / 2
    card_h = 240 if mobile else 250
    for index, field in enumerate(fields):
        xx = pad if mobile else pad + (index % 2) * (card_w + 28)
        yy = header + 28 + (index if mobile else index // 2) * (card_h + 22)
        s.rect(xx, yy, card_w, card_h, PALETTE["white"], 16, PALETTE["line"], 1)
        s.text(xx + 26, yy + 48, f"0{index+1}", 22, PALETTE["blue"], "mono")
        if text_width(field["label"], 24, "bold") > card_w - 105:
            raise ValueError("Benchmark field label is too wide: " + field["label"])
        s.text(xx + 79, yy + 49, field["label"], 24, PALETTE["ink"], "bold")
        s.block(xx + 27, yy + 101, field["body"], card_w - 54, 25, PALETTE["muted"], leading=36, max_lines=4)
    note_y = (1995 if mobile else 1191) + extra_header
    s.text(pad, note_y, "SCOPE IS PART OF THE RESULT.", 18 if mobile else 22, PALETTE["blue"], "bold", spacing=.8)
    if not mobile:
        s.text(w - pad, note_y, "Phillip A. Holland Jr. / AI-assisted research", 19, PALETTE["muted"], anchor="end")
        s.text(pad, note_y + 40, data.get("source_label", "Read the accompanying task contract and verification record."), 19, PALETTE["muted"])
    else:
        s.text(pad, note_y + 44, "Phillip A. Holland Jr. / AI-assisted research", 20, PALETTE["muted"])
    return s


def source_file(relative: str) -> Path:
    path = (ROOT / relative).resolve()
    if path == ROOT or ROOT not in path.parents or not path.is_file():
        raise ValueError("Evidence source must be an existing file inside the checkout: " + str(relative))
    return path


def pointer(data: Any, value: str):
    if value == "":
        return data
    if not isinstance(value, str) or not value.startswith("/"):
        raise ValueError("Use a JSON pointer starting with / for each metric value.")
    for part in value[1:].split("/"):
        key = part.replace("~1", "/").replace("~0", "~")
        if isinstance(data, list):
            data = data[int(key)]
        elif isinstance(data, dict):
            data = data[key]
        else:
            raise ValueError("Pointer traverses a scalar: " + value)
    return data


def load_metrics(path: Path):
    data = json.loads(path.read_text())
    if data.get("schema") != "causalfill.release-cards.v1":
        raise ValueError("Expected schema causalfill.release-cards.v1")
    version = data.get("release", {}).get("version", "")
    metrics = []
    for row in data.get("metrics", []):
        safe_id(row["id"])
        if row["kind"] not in KINDS:
            raise ValueError("Unknown evidence class: " + str(row["kind"]))
        if not row.get("label") or not row.get("scope"):
            raise ValueError("Every result card must state a label and scope.")
        if "record_label" in row and not isinstance(row["record_label"], str):
            raise ValueError("Record labels must be text.")
        resolved = dict(row)
        if row["kind"] == "proposed":
            if not isinstance(row.get("value"), str):
                raise ValueError("Proposed cards use a short textual status, not a measured number.")
            resolved["display_value"] = row["value"]
        else:
            source = source_file(row["source"])
            source_sha = sha(source)
            if row.get("expected_source_sha256") and row["expected_source_sha256"] != source_sha:
                raise ValueError("Evidence source changed: " + row["source"])
            raw = json.loads(source.read_text())
            pointers = row.get("pointers", [])
            if not 1 <= len(pointers) <= 2:
                raise ValueError("Measured/formal cards must derive one value or a numerator/denominator pair from their JSON source.")
            values = [pointer(raw, item) for item in pointers]
            formatting = row.get("format", "integer")
            if formatting == "integer":
                if any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in values):
                    raise ValueError("Integer cards require nonnegative integer source values.")
                rendered = [f"{v:,}" for v in values]
            elif formatting == "decimal":
                if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in values):
                    raise ValueError("Decimal cards require finite numeric source values.")
                rendered = [f"{v:,.2f}".rstrip("0").rstrip(".") for v in values]
            elif formatting == "text":
                if any(not isinstance(v, str) or len(v) > 18 for v in values):
                    raise ValueError("Text status cards require short source strings.")
                rendered = values
            else:
                raise ValueError("Unsupported metric format.")
            resolved["display_value"] = " / ".join(rendered)
            resolved["source_sha256"] = source_sha
            resolved["source_values"] = values
        if len(resolved["display_value"]) > 24:
            raise ValueError("Metric value is too long for the card.")
        metrics.append(resolved)
    if len({row["id"] for row in metrics}) != len(metrics):
        raise ValueError("Duplicate card IDs.")
    return data, version, metrics


def contrast(a: str, b: str):
    def luminance(color):
        rgb = [int(color[i:i+2], 16) / 255 for i in (1, 3, 5)]
        linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in rgb]
        return sum(v * w for v, w in zip(linear, (.2126, .7152, .0722)))
    x, y = sorted((luminance(a), luminance(b)))
    return (y + .05) / (x + .05)


def render(source: Path, destination: Path, width: int | None = None):
    executable = shutil.which("inkscape")
    if not executable:
        raise ValueError("PNG preview rendering requires Inkscape on PATH.")
    command = [executable, str(source), "--export-type=png", "--export-filename=" + str(destination)]
    if width:
        command.append("--export-width=" + str(width))
    result = subprocess.run(command, capture_output=True, text=True, timeout=90)
    if result.returncode:
        raise ValueError("SVG render failed: " + source.name + "\n" + result.stderr[-1500:])
    return {"svg": source.name, "png": destination.as_posix(), "sha256": sha(destination), "width": Image.open(destination).width,
            "height": Image.open(destination).height}


def make_contact_sheet(pngs: list[Path], destination: Path, columns=2, width=1800):
    pad, gap = 40, 24
    tile_width = (width - 2 * pad - gap * (columns - 1)) // columns
    tiles = []
    for path in pngs:
        image = Image.open(path).convert("RGB")
        scale = tile_width / image.width
        target = image.resize((tile_width, round(image.height * scale)), Image.Resampling.LANCZOS)
        tiles.append((path.stem, target))
    row_heights = [max(tile[1].height for tile in tiles[start:start+columns]) + 35 for start in range(0, len(tiles), columns)]
    image = Image.new("RGB", (width, pad * 2 + sum(row_heights) + max(0, len(row_heights)-1) * gap), PALETTE["paper"])
    draw = ImageDraw.Draw(image)
    top = pad
    for row_index, row_height in enumerate(row_heights):
        for col, (name, tile) in enumerate(tiles[row_index*columns:(row_index+1)*columns]):
            xx = pad + col * (tile_width + gap)
            draw.text((xx, top), name, fill=PALETTE["muted"], font=font(19, "mono"))
            image.paste(tile, (xx, top + 32))
        top += row_height + gap
    image.save(destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metrics", type=Path, help="Root-authored card specification using source JSON pointers.")
    parser.add_argument("--output", type=Path, default=ROOT / "branding")
    parser.add_argument("--render", action="store_true", help="Generate PNG previews with Inkscape.")
    parser.add_argument("--design-preview", action="store_true", help="Render clearly labeled layout-only metric cards.")
    for name in FONT_CANDIDATES:
        parser.add_argument("--font-" + name, type=Path)
    args = parser.parse_args()
    for name in FONT_CANDIDATES:
        if value := getattr(args, "font_" + name):
            FONT_PATHS[name] = str(value)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    data, version, metrics = load_metrics(args.metrics) if args.metrics else ({}, "", [])
    assets: list[dict[str, Any]] = []
    paths: list[Path] = []

    def save(name: str, svg: SVG):
        path = output / name
        record = svg.write(path)
        record["path"] = path.relative_to(output).as_posix()
        assets.append(record)
        paths.append(path)

    for dark in (True, False):
        save("wordmark-" + ("dark" if dark else "light") + ".svg", wordmark(dark))
    for dark in (True, False):
        icon = SVG(160, 160, "CausalFill-Bench icon", "An open frame with a missing center and a separate filling tile.", PALETTE["ink_deep"] if dark else PALETTE["paper"])
        mark(icon, 28, 28, 104, dark)
        save("icon-" + ("dark" if dark else "light") + ".svg", icon)
    save("hero.svg", hero())
    save("hero-mobile.svg", hero(True))
    save("cover.svg", cover())
    save("social-card.svg", cover(True))
    save("evidence-legend.svg", evidence_legend())
    save("evidence-legend-mobile.svg", evidence_legend(True))
    for index, task in enumerate(TASKS, 1):
        save("tasks/" + task[0] + ".svg", task_card(task, index))
    save("features/robust-sensing.svg", signal_repair_card())
    for metric in metrics:
        save("results/" + metric["id"] + ".svg", metric_card(metric, version))
    if metrics:
        save("results-sheet.svg", metric_sheet(metrics, version))
        save("results-sheet-mobile.svg", metric_sheet(metrics, version, mobile=True))
    if args.design_preview:
        examples = []
        for kind in KINDS:
            row = {"kind": kind, "display_value": "—", "label": "A result with a clear scope",
                   "scope": "Layout preview only. No measurement or formal result is asserted."}
            examples.append(row)
            save("design-preview/" + kind + ".svg", metric_card(row, "", True))
        save("design-preview/results-sheet.svg", metric_sheet(examples, "", preview=True))
        save("design-preview/results-sheet-mobile.svg", metric_sheet(examples, "", mobile=True, preview=True))
    if "benchmark_card" in data:
        save("benchmark-card.svg", benchmark_card(data["benchmark_card"], version))
        save("benchmark-card-mobile.svg", benchmark_card(data["benchmark_card"], version, True))
    elif args.design_preview:
        sample = {"title": "The complete benchmark card", "subtitle": "A reusable author-facing layout. This is a design preview, not an evaluated task.",
                  "fields": [
                      {"label": "Missing component", "body": "State exactly what is absent and which downstream decision depends on it."},
                      {"label": "Public evidence", "body": "List the observations and documents a solver is allowed to use."},
                      {"label": "Actions and budget", "body": "Declare action costs, resource limits and irreversible effects."},
                      {"label": "Strict acceptance", "body": "State the complete success contract and allow valid alternative solutions."},
                      {"label": "Evidence and claims", "body": "Link the recorded runs or checked theorems. Keep distinct evidence classes visible."},
                      {"label": "Known boundaries", "body": "Name the model assumptions, isolation limits and conclusions not established."},
                  ]}
        save("design-preview/benchmark-card.svg", benchmark_card(sample, "", preview=True))
        save("design-preview/benchmark-card-mobile.svg", benchmark_card(sample, "", mobile=True, preview=True))
    pairs = {"body_on_paper": ("muted", "paper"), "body_on_white": ("muted", "white"),
             "ink_on_paper": ("ink", "paper"), "light_on_dark": ("light_text", "ink_deep"),
             "measured": ("blue", "blue_light"), "formal": ("teal", "teal_light"),
             "proposed": ("amber", "amber_light"), "mint_on_dark": ("mint", "ink_deep")}
    ratios = {name: round(contrast(PALETTE[a], PALETTE[b]), 3) for name, (a, b) in pairs.items()}
    if any(value < 4.5 for value in ratios.values()):
        raise ValueError("A body-text palette pair fails 4.5:1 contrast: " + str(ratios))
    previews = []
    if args.render:
        preview_dir = output / "previews"
        preview_dir.mkdir(exist_ok=True)
        for path in paths:
            relative = path.relative_to(output)
            name = "--".join(relative.with_suffix("").parts) + ".png"
            previews.append(render(path, preview_dir / name))
        for svg_name, label, width in [("hero.svg", "hero-github-900", 900), ("hero-mobile.svg", "hero-mobile-375", 375),
                                       ("evidence-legend-mobile.svg", "legend-mobile-375", 375)]:
            previews.append(render(output / svg_name, preview_dir / (label + ".png"), width))
        for svg_name, label, width in [("results-sheet.svg", "results-github-900", 900),
                                       ("results-sheet-mobile.svg", "results-mobile-375", 375),
                                       ("benchmark-card-mobile.svg", "benchmark-mobile-375", 375),
                                       ("design-preview/results-sheet-mobile.svg", "design-results-mobile-375", 375),
                                       ("design-preview/benchmark-card-mobile.svg", "design-benchmark-mobile-375", 375),
                                       ("tasks/robotics.svg", "task-mobile-375", 375),
                                       ("features/robust-sensing.svg", "signal-repair-mobile-375", 375)]:
            if (output / svg_name).is_file():
                previews.append(render(output / svg_name, preview_dir / (label + ".png"), width))
        selected = [Path(item["png"]) for item in previews if Path(item["png"]).name in
                    {"hero.png", "hero-mobile.png", "social-card.png", "cover.png", "wordmark-light.png", "wordmark-dark.png"}]
        make_contact_sheet(selected, preview_dir / "identity-sheet.png", 2)
        selected = [Path(item["png"]) for item in previews if "tasks--" in item["png"]]
        make_contact_sheet(selected, preview_dir / "task-sheet.png", 3)
        selected = [Path(item["png"]) for item in previews if "results--" in item["png"] or "design-preview--" in item["png"] and "benchmark-card" not in item["png"] and "results-sheet" not in item["png"]]
        if selected:
            make_contact_sheet(selected, preview_dir / "result-sheet.png", 2)
    manifest = {"schema": "causalfill.brand-build.v1", "created_utc": datetime.now(timezone.utc).isoformat(),
                "release_version": version or None, "builder_sha256": sha(Path(__file__)),
                "input": {"path": str(args.metrics), "sha256": sha(args.metrics)} if args.metrics else None,
                "palette": PALETTE, "contrast_ratios": ratios, "measuring_fonts": FONT_PATHS,
                "assets": assets, "resolved_metrics": metrics, "png_previews": previews,
                "scope": "Documentation graphics; source-pointer binding and text/contrast checks do not replace evaluator or theorem verification.",
                "visual_inspection": "Required separately; rendering alone is not visual QA."}
    (output / "build-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (output / "tokens.json").write_text(json.dumps({"palette": PALETTE, "font_family": FONT_FAMILY, "mono_family": MONO_FAMILY,
                                                 "evidence_kinds": {key: value[0] for key, value in KINDS.items()}}, indent=2) + "\n")
    print(json.dumps({"assets": len(assets), "result_cards": len(metrics), "png_previews": len(previews),
                      "text_bounds": "passed", "body_text_contrast": "passed", "output": str(output)}, indent=2))


if __name__ == "__main__":
    main()
