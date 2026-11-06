#!/usr/bin/env python3
"""Independent finite audit of v0.5 image and decision-sufficiency mechanisms.

The image oracle uses exact Fraction geometry and an independently written
PNG reader. The decision oracle enumerates complete small query trees and
executes their raw world/observation paths; it does not use the production
belief recurrence. These are bounded engineering checks, not model scores,
formal proofs, statistical calibration, or physical-robot evidence.
"""
from __future__ import annotations

import argparse
import base64
import binascii
from collections import Counter
import copy
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import itertools
import json
from pathlib import Path
import pickle
import random
import secrets
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
from unittest.mock import patch
import zlib

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from causalfill.vision import (decode_envelope, decode_png, detect_components,
                              encode_png, image_envelope, pixel_to_world,
                              recover_calibration, render_scene)
from causalfill.decision_sufficiency import (SCHEMA, build_certificate,
                                           replay_certificate, verify_certificate)


class Audit:
    def __init__(self):
        self.counts = Counter()
        self.failures = []
        self.measurements = {}
        self.transcript = hashlib.sha256()

    def check(self, section, condition, case):
        self.counts[section] += 1
        event = [section, bool(condition), case]
        self.transcript.update(json.dumps(event, sort_keys=True, separators=(",", ":")).encode()+b"\n")
        if not condition:
            self.failures.append({"section": section, "case": case})

    def rejects(self, section, operation, case):
        try:
            operation()
        except (ValueError, TypeError, OverflowError):
            self.check(section, True, case)
        except Exception as exc:
            self.check(section, False, {"case": case, "unexpected_exception": type(exc).__name__})
        else:
            self.check(section, False, case)


def independent_png(png):
    """Read known-valid producer PNGs independently, without decoder helpers.

    This audit reader is used only on bounded producer output. It is not an
    alternative public parser and intentionally is not the attack target.
    """
    if png[:8] != b"\x89PNG\r\n\x1a\n":
        raise AssertionError("signature")
    offset, kinds, compressed = 8, [], bytearray()
    width = height = None
    while offset < len(png):
        length = int.from_bytes(png[offset:offset+4], "big")
        kind = png[offset+4:offset+8]
        data = png[offset+8:offset+8+length]
        crc = int.from_bytes(png[offset+8+length:offset+12+length], "big")
        if crc != binascii.crc32(kind+data) & 0xffffffff:
            raise AssertionError("CRC")
        kinds.append(kind.decode("ascii"))
        if kind == b"IHDR":
            width, height = int.from_bytes(data[:4], "big"), int.from_bytes(data[4:8], "big")
            if data[8:] != bytes([8, 2, 0, 0, 0]):
                raise AssertionError("profile")
        elif kind == b"IDAT":
            compressed.extend(data)
        offset += length+12
    raw = zlib.decompress(compressed)
    stride = width*3+1
    if len(raw) != height*stride or any(raw[y*stride] for y in range(height)):
        raise AssertionError("scanline")
    rgb = b"".join(raw[y*stride+1:(y+1)*stride] for y in range(height))
    return width, height, rgb, kinds


def exact_raster(shapes, camera, background=(235, 239, 244)):
    """Fraction-valued center-sampling oracle, independent of producer floats."""
    width, height = camera["width"], camera["height"]
    a, b, tx = map(Fraction, camera["matrix"][0])
    c, d, ty = map(Fraction, camera["matrix"][1])
    determinant = a*d-b*c
    output = bytearray()
    for row in range(height):
        for col in range(width):
            u, v = Fraction(2*col+1, 2)-tx, Fraction(2*row+1, 2)-ty
            x, y = (d*u-b*v)/determinant, (a*v-c*u)/determinant
            color = background
            for shape in shapes:
                if shape["shape"] == "rect":
                    x0, y0, x1, y1 = map(Fraction, shape["bounds"])
                    selected = x0 <= x < x1 and y0 <= y < y1
                else:
                    cx, cy = map(Fraction, shape["center"])
                    radius = Fraction(shape["radius"])
                    selected = (x-cx)*(x-cx)+(y-cy)*(y-cy) <= radius*radius
                if selected:
                    color = shape["rgb"]
            output.extend(color)
    return bytes(output)


def raster_checks(audit, cases=64):
    rng = random.Random(510042)
    matrices = [[[1, 0, 2], [0, 1, 3]], [[-1, 0, 19], [0, 1, 3]],
                [[0, -1, 20], [1, 0, 2]], [[1, 0.25, 2], [0.25, 1, 2]],
                [[2, 0, -3], [0, 1, 2]], [[1, -0.5, 6], [0, 1, 3]]]
    pixels = 0
    for i in range(cases):
        shapes = [
            {"shape": "rect", "bounds": [1, 1, 15, 15], "rgb": [30, 70, 110]},
            {"shape": "circle", "center": [rng.randrange(4, 13), rng.randrange(4, 13)],
             "radius": rng.choice([2, 2.5, 3]), "rgb": [220, 50, 70]},
            {"shape": "rect", "bounds": [8, 4, 12, 11], "rgb": [40, 200, 90]},
        ]
        camera = {"width": 24, "height": 24, "matrix": matrices[i % len(matrices)]}
        image = render_scene(shapes, camera)
        png = base64.b64decode(image["png_base64"])
        width, height, rgb, chunks = independent_png(png)
        audit.check("independent_raster_geometry", rgb == exact_raster(shapes, camera), i)
        audit.check("producer_wire_profile", chunks == ["IHDR", "IDAT", "IEND"], i)
        audit.check("independent_png_roundtrip", decode_envelope(image) == (width, height, rgb), i)
        pixels += width*height
    audit.measurements["raster"] = {"scenes": cases, "exact_pixel_samples": pixels,
                                   "oracle": "Fraction geometry plus independently parsed pixels"}


def png_with(chunks):
    data = bytearray(b"\x89PNG\r\n\x1a\n")
    for kind, payload in chunks:
        data.extend(struct.pack(">I", len(payload))+kind+payload)
        data.extend(struct.pack(">I", binascii.crc32(kind+payload) & 0xffffffff))
    return bytes(data)


def decoder_attacks(audit):
    header = (b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    data = (b"IDAT", zlib.compress(b"\x00\x11\x22\x33"))
    end = (b"IEND", b"")
    good = png_with([header, data, end])
    audit.check("decoder_accepts_valid_control", decode_png(good) == (1, 1, b"\x11\x22\x33"), "one_pixel")
    attacks = {
        "metadata": png_with([header, (b"tEXt", b"answer\x00WEST"), data, end]),
        "duplicate_header": png_with([header, header, data, end]),
        "missing_header": png_with([data, end]),
        "missing_end": png_with([header, data]),
        "trailing_bytes": good+b"hidden_state",
        "truncated_chunk": good[:-1],
        "corrupt_crc": good[:-1]+bytes([good[-1] ^ 1]),
        "empty_idat": png_with([header, (b"IDAT", b""), end]),
        "bad_filter": png_with([header, (b"IDAT", zlib.compress(b"\x01\x11\x22\x33")), end]),
        "short_scanline": png_with([header, (b"IDAT", zlib.compress(b"\x00\x11\x22")), end]),
        "long_scanline": png_with([header, (b"IDAT", zlib.compress(b"\x00\x11\x22\x33\x44")), end]),
        "extra_zlib_stream": png_with([header, (b"IDAT", data[1]+zlib.compress(b"\x00")), end]),
        "trailing_zlib_garbage": png_with([header, (b"IDAT", data[1]+b"hidden"), end]),
        "truncated_zlib": png_with([header, (b"IDAT", data[1][:-1]), end]),
        "bounded_expansion": png_with([header, (b"IDAT", zlib.compress(b"\x00"*1_000_000)), end]),
        "nonempty_end": png_with([header, data, (b"IEND", b"x")]),
        "invalid_profile": png_with([(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 16, 2, 0, 0, 0)), data, end]),
        "zero_dimension": png_with([(b"IHDR", struct.pack(">IIBBBBB", 0, 1, 8, 2, 0, 0, 0)), data, end]),
        "oversized_dimension": png_with([(b"IHDR", struct.pack(">IIBBBBB", 1025, 1, 8, 2, 0, 0, 0)), data, end]),
        "chunk_explosion": png_with([header]+[(b"IDAT", b"x")]*65+[end]),
    }
    for name, image in attacks.items():
        audit.rejects("malformed_png_rejection", lambda image=image: decode_png(image), name)
    # Correctly split IDAT is a valid alternative serialization.
    middle = len(data[1])//2
    split = png_with([header, (b"IDAT", data[1][:middle]), (b"IDAT", data[1][middle:]), end])
    audit.check("decoder_accepts_valid_control", decode_png(split) == decode_png(good), "multiple_idat")
    valid = image_envelope(good)
    changes = [{"width": True}, {"height": 2}, {"mime_type": "image/jpeg"},
               {"sha256": "0"*64}, {"png_base64": valid["png_base64"]+"!"},
               {"answer": "WEST"}, {"png_base64": None}]
    for i, change in enumerate(changes):
        candidate = {**valid, **change}
        audit.rejects("malformed_envelope_rejection", lambda candidate=candidate: decode_envelope(candidate), i)
    audit.measurements["decoder"] = {"malformed_png_cases": len(attacks),
                                     "malformed_envelopes": len(changes),
                                     "independent_valid_controls": 2,
                                     "maximum_bomb_uncompressed_bytes": 1_000_000}


def pixel_noise_and_calibration(audit, cases=32):
    camera = {"width": 48, "height": 48, "matrix": [[1, 0, 0], [0, 1, 0]]}
    target = {"shape": "circle", "center": [18, 20], "radius": 5, "rgb": [230, 20, 50]}
    occluder = {"shape": "rect", "bounds": [6, 8, 43, 38], "rgb": [45, 60, 75]}
    twin = {**target, "center": [34, 20]}
    clean = decode_envelope(render_scene([target], camera))[2]
    clean_twin = decode_envelope(render_scene([twin], camera))[2]
    for i in range(cases):
        bound = 1+i % 32
        first = render_scene([target], camera, noise=bound, noise_seed=3000+i)
        noisy = decode_envelope(first)[2]
        other = decode_envelope(render_scene([twin], camera, noise=bound, noise_seed=3000+i))[2]
        audit.check("bounded_rgb_noise", max(abs(x-y) for x, y in zip(clean, noisy)) <= bound, i)
        audit.check("repeated_capture_correlation", first == render_scene([target], camera, noise=bound, noise_seed=3000+i), i)
        audit.check("occluded_counterfactual_equality",
                    render_scene([target, occluder], camera, noise=bound, noise_seed=3000+i) ==
                    render_scene([twin, occluder], camera, noise=bound, noise_seed=3000+i), i)
        audit.check("noise_outside_intervention_unchanged",
                    all(x == y for x, y, before, after in zip(noisy, other, clean, clean_twin) if before == after), i)
    landmarks = [{"world": [10, 10], "rgb": [220, 20, 30]},
                 {"world": [70, 10], "rgb": [20, 200, 60]},
                 {"world": [10, 60], "rgb": [40, 60, 220]}]
    shapes = [{"shape": "circle", "center": x["world"], "radius": 3, "rgb": x["rgb"]} for x in landmarks]
    matrices = [[[1, 0, 4], [0, 1, 8]], [[-1, 0, 90], [0, 1, 8]],
                [[0, -1, 80], [1, 0, 4]], [[1, 0.25, 4], [0.25, 1, 8]]]
    for i, matrix in enumerate(matrices):
        image = render_scene(shapes, {"width": 110, "height": 105, "matrix": matrix}, noise=8, noise_seed=i)
        recovered = recover_calibration(image, landmarks, tolerance=8)
        audit.check("independent_landmark_calibration", max(abs(a-b) for row_a, row_b in zip(matrix, recovered)
                                                            for a, b in zip(row_a, row_b)) < 1e-12, i)
        point = [35, 28]
        pixel = [sum(matrix[j][k]*point[k] for k in (0, 1))+matrix[j][2] for j in (0, 1)]
        restored = pixel_to_world(recovered, pixel)
        audit.check("calibration_inverse", max(abs(a-b) for a, b in zip(point, restored)) < 1e-12, i)
    image = render_scene(shapes, {"width": 110, "height": 105, "matrix": matrices[0]})
    absent = copy.deepcopy(landmarks)
    absent[0]["rgb"] = [1, 2, 3]
    audit.rejects("invalid_calibration_rejection", lambda: recover_calibration(image, absent), "missing_fiducial")
    collinear = copy.deepcopy(landmarks)
    collinear[2]["world"] = [40, 10]
    audit.rejects("invalid_calibration_rejection", lambda: recover_calibration(image, collinear), "collinear_world")
    duplicate = render_scene(shapes+[dict(shapes[0], center=[50, 50])],
                             {"width": 110, "height": 105, "matrix": matrices[0]})
    audit.rejects("invalid_calibration_rejection", lambda: recover_calibration(duplicate, landmarks), "duplicate_fiducial")


def exhaustive_transfer_calibration(audit, limit=192):
    """Enumerate the represented subpixel support using exact pixel centroids.

    Four orientations, two shear signs, four pixel phases and six target
    centers give 192 canonical scenes. The independent oracle uses one-pass
    exact RGB masks and Fraction-valued affine interpolation. Integer image
    translations cancel when no object clips; color/noise separation preserves
    these masks. This is a finite raster bound, not a sensor coverage guarantee.
    """
    from causalfill.domains.visual import PALETTE
    orientations = [((0, -1), (1, 0)), ((-1, 0), (0, -1)),
                    ((0, 1), (1, 0)), ((1, 0), (0, -1))]
    colors = [tuple(c) for c in PALETTE]
    decorative = [(235, 239, 244), (210, 220, 231), (241, 244, 248),
                  (222, 229, 237), (255, 255, 255), (70, 82, 101), (99, 115, 134), (48, 61, 81)]
    minimum_separation = min(max(abs(a-b) for a, b in zip(c, other))
                             for c in colors for other in colors+decorative if c != other)
    audit.check("transfer_color_noise_separation", minimum_separation > 12, minimum_separation)
    configurations = list(itertools.product(range(4), (-0.25, 0.25), (0.25, 0.75), (0.25, 0.75),
                                            (28, 68), (44, 48, 52)))
    if limit < len(configurations):
        configurations = [configurations[i*len(configurations)//limit] for i in range(limit)]
    worst = Fraction(0)
    worst_case = None
    for index, (orientation_index, shear, phase_x, phase_y, target_x, target_y) in enumerate(configurations):
        orientation = orientations[orientation_index]
        base = [[2, shear], [0, 2]]
        linear = [[sum(orientation[i][k]*base[k][j] for k in range(2)) for j in range(2)] for i in range(2)]
        phases = (phase_x, phase_y)
        matrix = [[linear[i][0], linear[i][1], 120+phases[i]-48*sum(linear[i])] for i in range(2)]
        # Check the entire advertised square at both extreme integer shifts.
        corners = [[sum(matrix[i][k]*point[k] for k in (0, 1))+matrix[i][2]+shift for i in (0, 1)]
                   for point in ((0, 0), (0, 96), (96, 0), (96, 96)) for shift in (-4, 4)]
        audit.check("transfer_integer_translation_no_clipping", all(0 <= v < 240 for point in corners for v in point), index)
        positions = [[8, 8], [88, 8], [8, 88], [target_x, target_y]]
        primitives = [{"shape": "circle", "center": p, "radius": 2.5 if i < 3 else 3.5,
                       "rgb": list(colors[i])} for i, p in enumerate(positions)]
        image = render_scene(primitives, {"width": 240, "height": 240, "matrix": matrix})
        width, height, rgb, _ = independent_png(base64.b64decode(image["png_base64"]))
        index_by_color = {bytes(colors[i]): i for i in range(4)}
        sums = [[0, 0, 0] for _ in range(4)]
        for pixel in range(width*height):
            label = index_by_color.get(rgb[3*pixel:3*pixel+3])
            if label is not None:
                sums[label][0] += 2*(pixel % width)+1
                sums[label][1] += 2*(pixel // width)+1
                sums[label][2] += 1
        observed = [[Fraction(sx, 2*n), Fraction(sy, 2*n)] for sx, sy, n in sums]
        p0, p1, p2, pt = observed
        ux, uy = p1[0]-p0[0], p1[1]-p0[1]
        vx, vy = p2[0]-p0[0], p2[1]-p0[1]
        zx, zy = pt[0]-p0[0], pt[1]-p0[1]
        det = ux*vy-uy*vx
        restored = [8+80*(zx*vy-zy*vx)/det, 8+80*(ux*zy-uy*zx)/det]
        errors = [abs(x-Fraction(y)) for x, y in zip(restored, positions[-1])]
        error = max(errors)
        if error > worst:
            worst, worst_case = error, [orientation_index, shear, phase_x, phase_y, target_x, target_y]
        audit.check("transfer_exhaustive_quantization_bound", error <= Fraction(3, 5), index)
        landmarks = [{"world": positions[i], "rgb": list(colors[i])} for i in range(3)]
        production = pixel_to_world(recover_calibration(image, landmarks, tolerance=0),
                                    detect_components(image, colors[3], tolerance=0)[0]["center"])
        audit.check("transfer_fraction_centroid_reference", max(abs(float(x)-y) for x, y in zip(restored, production)) < 1e-11, index)
    audit.measurements["finite_transfer_calibration"] = {
        "canonical_camera_target_configurations": len(configurations),
        "full_represented_subpixel_support_enumerated": len(configurations) == 192,
        "factorization": "4 orientations × 2 shear signs × 4 subpixel phase pairs × 6 target centers",
        "maximum_exact_error_world": str(worst), "maximum_error_world": float(worst),
        "worst_case": worst_case, "acceptance_tolerance_world": "3/5",
        "minimum_semantic_color_linf_separation": minimum_separation,
        "maximum_rgb_noise": 6,
        "scope": "Finite 2D renderer support. Integer-translation invariance requires no clipping; palette/noise invariance follows from nonoverlapping bounded RGB supports. Not a physical sensor calibration guarantee.",
    }


def all_small_trees(query_names=("q0", "q1"), terminals=("a0", "a1")):
    """Enumerate full syntactic policies without considering any beliefs."""
    leaves = [("terminal", name) for name in terminals]
    policies = list(leaves)
    for query in query_names:
        descendants = all_small_trees(tuple(x for x in query_names if x != query), terminals)
        for zero, one in itertools.product(descendants, repeat=2):
            policies.append(("query", query, zero, one))
    return policies


def raw_policy_leaves(tree, world, supports, query_costs, spent=0):
    """Traverse a fixed world's allowed raw observations; no belief operations."""
    if tree[0] == "terminal":
        return [(tree[1], spent)]
    _, query, zero, one = tree
    leaves = []
    for observation in supports[query][world]:
        leaves.extend(raw_policy_leaves(zero if observation == "0" else one,
                                       world, supports, query_costs, spent+query_costs[query]))
    return leaves


def enumeration_optimum(problem, objective="action"):
    terminals = tuple(problem["worlds"] if objective == "identification" else [a["id"] for a in problem["actions"]])
    policies = all_small_trees(tuple(q["id"] for q in problem["experiments"]), terminals)
    supports = {q["id"]: q["supports"] for q in problem["experiments"]}
    costs = {q["id"]: q["cost"] for q in problem["experiments"]}
    action_cost = {a["id"]: a["cost"] for a in problem["actions"]}
    success = {a["id"]: a["success_worlds"] for a in problem["actions"]}
    values = []
    for policy in policies:
        all_good, worst = True, 0
        for world in problem["worlds"]:
            for terminal, query_cost in raw_policy_leaves(policy, world, supports, costs):
                if objective == "identification":
                    good, total = terminal == world, query_cost
                else:
                    good, total = world in success[terminal], query_cost+action_cost[terminal]
                all_good = all_good and good
                worst = max(worst, total)
        if all_good:
            values.append(worst)
    return min(values, default=None), len(policies)


def small_problems(table_limit=81):
    support_rows = [("0",), ("1",), ("0", "1")]
    successes = [[], ["w0"], ["w1"], ["w0", "w1"]]
    for index, rows in enumerate(itertools.product(support_rows, repeat=4)):
        if index >= table_limit:
            break
        base = {"schema": SCHEMA, "worlds": ["w0", "w1"], "actions": [],
                "experiments": [{"id": "q0", "cost": 1, "supports": {"w0": list(rows[0]), "w1": list(rows[1])}},
                                {"id": "q1", "cost": 2, "supports": {"w0": list(rows[2]), "w1": list(rows[3])}}]}
        for left, right in itertools.product(successes, repeat=2):
            problem = copy.deepcopy(base)
            problem["actions"] = [{"id": "a0", "cost": index % 3, "success_worlds": list(left)},
                                  {"id": "a1", "cost": (index+1) % 4, "success_worlds": list(right)}]
            yield index, problem


def decision_enumeration(audit, table_limit=81):
    models = policy_evaluations = traversals = 0
    identified_tables = set()
    for index, problem in small_problems(table_limit):
        for objective in ("action", "identification"):
            if objective == "identification" and index in identified_tables:
                continue
            if objective == "identification":
                identified_tables.add(index)
            expected, policies = enumeration_optimum(problem, objective)
            certificate = build_certificate(problem, objective)
            verified = verify_certificate(problem, certificate)
            case = [models, index, objective]
            audit.check("enumerated_complete_policy_optimum", certificate["value"] == expected, case)
            audit.check("decision_certificate_valid", verified.get("valid") and verified.get("value") == expected, case)
            if expected is not None:
                replay = replay_certificate(problem, certificate)
                audit.check("selected_policy_attains_bound", replay.get("valid") and replay.get("worst_cost") == expected, case)
                traversals += replay.get("supported_policy_leaves", 0)
            models += 1
            policy_evaluations += policies
    audit.measurements["small_policy_oracle"] = {
        "observation_support_tables": table_limit, "model_objective_comparisons": models,
        "complete_syntactic_policies_per_model": 74, "whole_policy_evaluations": policy_evaluations,
        "selected_policy_replay_leaves": traversals,
        "scope": "2 worlds, 2 one-use experiments with supports {0}, {1}, {0,1}, 2 actions; all 16 action success-set pairs",
        "independence": "full syntactic tree enumeration and raw world-path execution, no production belief recursion",
    }


def decision_forgery_checks(audit):
    # Both queries distinguish, so the checker must retain cheaper and more
    # expensive alternative branches, not merely a successful selected tree.
    problem = {"schema": SCHEMA, "worlds": ["w0", "w1"],
               "actions": [{"id": "a0", "cost": 0, "success_worlds": ["w0"]},
                           {"id": "a1", "cost": 0, "success_worlds": ["w1"]}],
               "experiments": [{"id": "q0", "cost": 1, "supports": {"w0": ["0"], "w1": ["1"]}},
                               {"id": "q1", "cost": 2, "supports": {"w0": ["0"], "w1": ["1"]}}]}
    certificate = build_certificate(problem)
    attacks = {}
    altered = copy.deepcopy(certificate)
    altered["value"] = 0
    for node in altered["nodes"]:
        if node[:2] == altered["root"]:
            node[2] = 0
    attacks["false_lower_bound"] = altered
    altered = copy.deepcopy(certificate)
    altered["nodes"] = [n for n in altered["nodes"] if n[:2] != [1, 1]]
    attacks["omitted_unselected_alternative"] = altered
    altered = copy.deepcopy(certificate)
    altered["problem_sha256"] = "0"*64
    attacks["untrusted_statement"] = altered
    for field in ("root", "value", "node_value", "node_belief", "node_remaining"):
        altered = copy.deepcopy(certificate)
        if field == "root": altered["root"][0] = True
        elif field == "value": altered["value"] = True
        elif field == "node_value": altered["nodes"][0][2] = False
        elif field == "node_belief": altered["nodes"][0][0] = True
        else: altered["nodes"][0][1] = True
        attacks["bool_alias_"+field] = altered
    for name, forged in attacks.items():
        audit.check("decision_forgery_rejection", not verify_certificate(problem, forged)["valid"], name)
    for name, mutation in (
        ("empty_support", []), ("duplicate_support", ["0", "0"]), ("boolean_support", [True]),
        ("numeric_support", [0]), ("oversized_support", [str(i) for i in range(17)])):
        altered = copy.deepcopy(problem)
        altered["experiments"][0]["supports"]["w0"] = mutation
        audit.rejects("invalid_decision_model_rejection", lambda altered=altered: build_certificate(altered), name)
        audit.check("invalid_decision_model_checker", not verify_certificate(altered, certificate)["valid"], name)
    alternative = copy.deepcopy(certificate)
    alternative["nodes"].reverse()
    audit.check("valid_certificate_order_alternative", verify_certificate(problem, alternative)["valid"], "reversed_rows")


def replay_alias_checks(audit):
    """A compact policy has billions of label paths but only 76 replay states.

    This directly targets a development finding: traversing every synonymous
    label path used exponential time. The revised replay aggregates exact
    multiplicities of equal semantic states, and has an explicit state cap.
    Counts here are represented paths, not that many executed tests.
    """
    worlds = ["w"+str(i) for i in range(11)]
    problem = {"schema": SCHEMA, "worlds": worlds,
               "actions": [{"id": w, "cost": 0, "success_worlds": [w]} for w in worlds],
               "experiments": []}
    for i in range(10):
        problem["experiments"].append({
            "id": "q"+str(i), "cost": 1,
            "supports": {w: [("hit" if w == worlds[i] else "miss")+str(j) for j in range(8)] for w in worlds},
        })
    certificate = build_certificate(problem)
    replay = replay_certificate(problem, certificate)
    expected_leaves = sum(8**depth for depth in range(1, 11))+8**10
    audit.check("alias_replay_optimum", certificate["value"] == 10, "11_worlds_10_sensors")
    audit.check("alias_replay_exact_multiplicity", replay.get("valid") and replay.get("supported_policy_leaves") == expected_leaves,
                {"expected": expected_leaves, "actual": replay.get("supported_policy_leaves")})
    audit.check("alias_replay_compact_states", replay.get("replay_states") == 76, replay.get("replay_states"))
    audit.check("alias_replay_cost_extrema", replay.get("best_cost") == 1 and replay.get("worst_cost") == 10,
                [replay.get("best_cost"), replay.get("worst_cost")])
    with patch("causalfill.decision_sufficiency.MAX_REPLAY_STEPS", 1):
        capped = replay_certificate(problem, certificate)
        audit.check("alias_replay_resource_cap", capped.get("valid") is False and "cap" in capped.get("error", ""), "explicit_incomplete_result")
    audit.measurements["alias_replay"] = {
        "worlds": 11, "experiments": 10, "labels_per_world_sensor": 8,
        "represented_supported_policy_leaves": expected_leaves,
        "executed_replay_states": replay.get("replay_states"),
        "exact_cost_range": [replay.get("best_cost"), replay.get("worst_cost")],
        "count_warning": "The leaf count is an exact multiplicity sum, not billions of individually executed trials.",
    }


def visual_domain_checks(audit, seed_count=4):
    from causalfill.domains.visual import VisualTask, solve_visual
    from causalfill.session import Session, verify_trace
    scenes = successes = 0
    maximum_error = 0.0
    for split, difficulty, seed in itertools.product(("train", "dev", "transfer"), (1, 2, 3), range(seed_count)):
        pair = [VisualTask(seed, split, difficulty, twin) for twin in (0, 1)]
        key = [split, difficulty, seed]
        audit.check("visual_public_twin_equivalence", pair[0].public() == pair[1].public() and pair[0].files == pair[1].files, key)
        if split != "train":
            audit.check("visual_occluded_twin_byte_equivalence", pair[0].query("capture", {"view": "overview"}) ==
                        pair[1].query("capture", {"view": "overview"}), key)
        audit.check("visual_counterfactual_changes_pixels", pair[0].image("inspection") != pair[1].image("inspection"), key)
        audit.check("visual_counterfactual_changes_decision", pair[0].reference_answer()["dispatch"] != pair[1].reference_answer()["dispatch"], key)
        for twin, task in enumerate(pair):
            session = Session(task)
            answer = solve_visual(session.public(), session.call)
            session.call("submit", {"fill": answer, "confidence": 1, "abstain": False,
                                    "evidence": [e["event_id"] for e in session.trace]})
            audit.check("visual_public_pixel_reference", session.result["success"], key+[twin])
            audit.check("visual_trace_integrity", verify_trace(session.trace), key+[twin])
            audit.check("visual_budget_replay", session.cost == 4 and session.invalid == 0, key+[twin])
            # A calibrated image reference may use only public contract data.
            expected = task.reference_answer()
            maximum_error = max(maximum_error, *(abs(a-b) for a, b in zip(answer["target_world"], expected["target_world"])))
            successes += int(session.result["success"])
            scenes += 1
            wrong = copy.deepcopy(expected)
            wrong["dispatch"] = "EAST" if expected["dispatch"] == "WEST" else "WEST"
            audit.check("visual_executed_rule_scoring", not task.evaluate(wrong).success, key+[twin])
    audit.measurements["visual_domain"] = {"episodes": scenes, "scripted_public_pixel_successes": successes,
                                          "maximum_position_error_world": maximum_error,
                                          "natural_images_or_model_trials": False}


def visual_scoring_boundaries(audit):
    from causalfill.domains.visual import VisualTask
    task = VisualTask(41, "transfer", 3)
    expected = task.reference_answer()
    for axis, sign in itertools.product((0, 1), (-1, 1)):
        candidate = copy.deepcopy(expected)
        candidate["target_world"][axis] += sign*0.6
        audit.check("exact_visual_tolerance", task.evaluate(candidate).success, [axis, sign, "at_boundary"])
        candidate["target_world"][axis] += sign*1e-10
        audit.check("exact_visual_tolerance", not task.evaluate(candidate).success, [axis, sign, "outside_boundary"])
    for value in (True, False, float("nan"), float("inf"), "28", None):
        candidate = copy.deepcopy(expected)
        candidate["target_world"][0] = value
        audit.check("invalid_visual_fill", not task.evaluate(candidate).success, str(value))
    for value in (True, False, 1.0, "1"):
        candidate = copy.deepcopy(expected)
        candidate["tokens_left_of_target"] = value
        audit.check("invalid_visual_fill", not task.evaluate(candidate).success, ["count", str(value)])
    before = copy.deepcopy(task.__dict__)
    for name, arguments in [("unknown", {}), ("capture", {}), ("capture", {"view": []}),
                            ("capture", {"view": True}), ("capture", {"view": "inspection", "seed": 1})]:
        audit.rejects("invalid_visual_call", lambda name=name, arguments=arguments: task.query(name, arguments), str(arguments))
        after = copy.deepcopy(task.__dict__)
        # random.Random objects compare by identity; compare their states.
        a_rng, b_rng = before.pop("rng", None), after.pop("rng", None)
        audit.check("invalid_visual_call_atomicity", before == after and a_rng.getstate() == b_rng.getstate(), str(arguments))
        before["rng"] = a_rng


def image_http_client_checks(audit):
    """Exercise the copied public client against a real loopback evaluator."""
    import importlib.util
    import os
    from causalfill.domains.visual import VisualTask
    from causalfill.server import create_server
    from causalfill.session import Session, verify_trace
    source = ROOT/"clients/image_client.py"
    spec = importlib.util.spec_from_file_location("audit_image_client", source)
    client = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(client)
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        task = VisualTask(37, "transfer", 3)
        session = Session(task)
        token = secrets.token_urlsafe(32)
        server = create_server(session, "127.0.0.1", 0, token=token, output_dir=root/"evaluator")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        solver = root/"solver"
        solver.mkdir()
        copied = solver/"image_client.py"
        shutil.copyfile(source, copied)
        environment = {**os.environ, "CFB_URL": "http://127.0.0.1:"+str(server.server_port),
                       "CFB_TOKEN": token, "PYTHONPATH": ""}
        def call(command, body=None):
            raw = b"" if body is None else json.dumps(body).encode()
            result = subprocess.run([sys.executable, str(copied), command, "--output-dir", str(solver/"observations")],
                                    input=raw, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=solver,
                                    env=environment, timeout=30)
            audit.check("image_client_exits_cleanly", result.returncode == 0, [command, None if body is None else body["tool"]])
            audit.check("image_client_credential_separation", token.encode() not in result.stdout+result.stderr, command)
            return json.loads(result.stdout)
        try:
            public = call("episode")
            audit.check("image_http_public_contract", public["family"] == "visual" and "image" not in public, "episode")
            blocked = call("tool", {"tool": "read_file", "arguments": {"path": "/etc/passwd"}})
            audit.check("image_http_virtual_files_only", "error" in blocked and "content" not in blocked, "host_path")
            result = call("tool", {"tool": "capture", "arguments": {"view": "inspection"}})
            payload = result["image"]
            path = Path(payload["local_image_path"])
            raw = path.read_bytes()
            audit.check("image_client_saved_exact_public_pixels", raw == base64.b64decode(task.image("inspection")["png_base64"]), "captured_bytes")
            audit.check("image_client_integrity_metadata", payload["sha256"] == hashlib.sha256(raw).hexdigest(), "digest")
            audit.check("image_client_no_private_annotations", set(payload) == {"mime_type", "width", "height", "sha256", "local_image_path"}, "envelope_fields")
            audit.check("image_client_public_png_chunks", independent_png(raw)[3] == ["IHDR", "IDAT", "IEND"], "chunks")
            audit.check("image_client_opaque_filenames", path.name == hashlib.sha256(raw).hexdigest()+".png", "name")
            submission = call("tool", {"tool": "submit", "arguments": {"fill": {}, "confidence": 0,
                                                                          "abstain": False, "evidence": []}})
            audit.check("image_http_grade_withheld", set(submission) == {"accepted", "episode_closed", "event_id", "cost_used"}, "final_response")
            audit.check("image_http_trace_integrity", verify_trace(session.trace), "trace")
            audit.measurements["image_http_client"] = {
                "transport": "real authenticated loopback HTTP plus copied standalone public client",
                "png_bytes": len(raw),
                "inline_observation_response_bytes": len(json.dumps(session.trace[1]["response"]).encode()),
                "copied_client_imports_evaluator": False,
                "os_isolation_certified": False,
            }
            # Invalid metadata must fail before any artifact is created.
            envelope = task.image("inspection")
            for key, value in (("width", True), ("height", 1), ("sha256", "0"*64), ("png_base64", "!")):
                invalid = {**envelope, key: value}
                target = root/("bad_"+key)
                audit.rejects("image_client_invalid_payload", lambda invalid=invalid, target=target: client.materialize_images(invalid, target), key)
                audit.check("image_client_invalid_payload_atomicity", not target.exists(), key)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


def robot_outcome_oracle(open_route, initial_friction, wear, route, mode, elapsed, energy, spec):
    """Declared physics evaluated in exact decimal Fractions, without runtime helper."""
    contact = spec["contact"]
    mu = max(Fraction(str(contact["minimum_friction"])),
             Fraction(str(initial_friction))-Fraction(str(contact["wear_decrement"]))*wear)
    events = {
        "collision": route != "detour" and route != open_route,
        "slip": route != "detour" and mode == "roll" and mu*Fraction(str(contact["gravity"])) < 3,
        "stalled": route != "detour" and mode == "grip" and mu > Fraction(str(contact["grip_maximum_friction"])),
        "deadline_exceeded": elapsed > spec["deadline"],
        "energy_exceeded": energy > spec["energy_cap"],
    }
    return {"completed": not any(events.values()), **events}


def robot_ledger_checks(audit, session, spec, case):
    """Reconstruct all public action charges independently of returned counters."""
    elapsed = energy = wear = steps = sensor_cost = camera_moves = captures = probes = tool_cost = 0
    terminal = False
    for event in session.trace:
        name, arguments, response = event["tool"], event["arguments"], event["response"]
        if name == "submit":
            continue
        advertised = session.task.tools.get(name, {}).get("cost", {"read_file": 1, "list_files": 1,
                                      "search_files": 2, "session_status": 1}.get(name, 1))
        if "budget_exhausted" not in response.get("error", ""):
            tool_cost += advertised
        audit.check("robot_tool_budget_replay", response["cost_used"] == tool_cost, case+[event["event_id"]])
        if "error" in response or not name.startswith("robot_"):
            continue
        if name == "robot_move_camera":
            action = spec["actions"]["move_camera"]
            camera_moves += 1
        elif name == "robot_capture":
            action = spec["actions"]["capture"]
            captures += 1
            sensor_cost += advertised
        elif name == "robot_probe":
            action = spec["actions"]["probe_"+arguments["force"]]
            wear += action["wear"]
            probes += 1
            sensor_cost += advertised
        else:
            key = "detour_slow" if arguments["route"] == "detour" else "primary_"+arguments["mode"]
            action = spec["actions"][key]
            terminal = True
        elapsed += action["time"]
        energy += action["energy"]
        steps += 1
        expected = {"elapsed": elapsed, "energy_used": energy, "wear": wear,
                    "deadline": spec["deadline"], "energy_cap": spec["energy_cap"],
                    "terminal": terminal, "primitive_steps": steps}
        audit.check("robot_resource_receipt_replay", response["resources"] == expected, case+[event["event_id"]])
    task = session.task
    audit.check("robot_resource_final_replay", (task.elapsed, task.energy_used, task.wear, task.primitive_steps,
                                                task.observation_cost, task.camera_moves, task.captures, task.probes) ==
                (elapsed, energy, wear, steps, sensor_cost, camera_moves, captures, probes), case)


def robot_integrity_checks(audit):
    from causalfill.domains.robotics_vision import RoboticsVisionTask
    from causalfill.runner import run_episode
    from causalfill.session import Session, verify_trace
    malformed = [
        ("unknown", {}), ("robot_move_camera", {}), ("robot_move_camera", {"view": True}),
        ("robot_move_camera", {"view": "inspection", "extra": 1}), ("robot_capture", {"seed": 2}),
        ("robot_capture", []), ("robot_probe", {"force": True}), ("robot_probe", {"force": float("nan")}),
        ("robot_probe", {"force": []}), ("robot_probe", {"force": "gentle", "state": "dry"}),
        ("robot_execute", {"route": True, "mode": "roll"}), ("robot_execute", {"route": "upper", "mode": True}),
        ("robot_execute", {"route": "detour", "mode": "roll"}),
        ("robot_execute", {"route": "lower", "mode": "grip", "completed": True}),
    ]
    for seed in (0, 1, 2, 3):
        task = RoboticsVisionTask(seed, "transfer", 3)
        before = pickle.dumps(task.__dict__)
        task.reference_answer()
        task.reference_actions()
        audit.check("robot_reference_helpers_are_pure", pickle.dumps(task.__dict__) == before, seed)
        audit.check("robot_fill_cannot_replace_execution", not task.evaluate({"delivered": True}).success, seed)
        for index, (name, arguments) in enumerate(malformed):
            before = pickle.dumps(task.__dict__)
            audit.rejects("robot_invalid_action_rejection", lambda name=name, arguments=arguments: task.query(name, arguments), [seed, index])
            audit.check("robot_invalid_action_atomicity", pickle.dumps(task.__dict__) == before, [seed, index])
        session = Session(task)
        response = session.call("robot_probe", {"force": True})
        audit.check("robot_invalid_action_still_costs_tool_budget", "error" in response and session.cost == 4 and task.wear == 0, seed)
        task.query("robot_execute", {"route": "detour", "mode": "slow"})
        for index, (name, arguments) in enumerate([
            ("robot_move_camera", {"view": "inspection"}), ("robot_capture", {}),
            ("robot_probe", {"force": "firm"}), ("robot_execute", {"route": "upper", "mode": "roll"})]):
            before = pickle.dumps(task.__dict__)
            audit.rejects("robot_terminal_rejection", lambda name=name, arguments=arguments: task.query(name, arguments), [seed, index])
            audit.check("robot_terminal_irreversibility", pickle.dumps(task.__dict__) == before, [seed, index])
        for value in (1, 0, "true", None, [], False):
            audit.check("robot_completion_claim_typing", not task.evaluate({"delivered": value}).success, [seed, str(value)])
        record, trace, public = run_episode("robotics_vision", seed, "transfer", 3, policy="oracle")
        expected_cost = 2 if seed % 3 == 0 else 11
        audit.check("robot_oracle_operations_are_logged", record["success"] and record["tool_cost"] == expected_cost and
                    sum(e["tool"] == "robot_execute" for e in trace) == 1 and verify_trace(trace), seed)


def robot_transition_checks(audit, seed_count=8):
    """All seven legal commits after four named sensing/contact prefixes.

    Prefixes are empty, gentle, firm, and firm+gentle, following one actual
    camera move and capture. This is not enumeration of all possible histories.
    """
    from causalfill.domains.robotics_vision import RoboticsVisionTask
    from causalfill.robotics_vision_policy import recover_open_route, solve_robotics_vision
    from causalfill.session import Session, verify_trace
    actions = [(r, m) for r in ("upper", "lower") for m in ("roll", "grip", "slow")]+[("detour", "slow")]
    prefixes = [(), ("gentle",), ("firm",), ("firm", "gentle")]
    cases = frames = 0
    conditioning_counts = {}
    max_opening_error = 0.0
    for split, difficulty, seed in itertools.product(("train", "dev", "transfer"), (1, 2, 3), range(seed_count)):
        pair = [RoboticsVisionTask(seed, split, difficulty, twin) for twin in (0, 1)]
        key = [split, difficulty, seed]
        audit.check("robot_public_twin_equivalence", pair[0].public() == pair[1].public() and pair[0].files == pair[1].files, key)
        audit.check("robot_overview_pixel_equivalence", pair[0].image("overview") == pair[1].image("overview"), key)
        inspection = [task.image("inspection") for task in pair]
        audit.check("robot_declared_intervention_pixel_effect", (inspection[0] == inspection[1]) == (pair[0].twin_kind == "surface_friction"), key)
        for twin, base in enumerate(pair):
            spec = json.loads(base.files["/scene/robotics_vision.json"])
            route, support = recover_open_route(spec, inspection[twin])
            expected_y = spec["lanes"][base._open_route]["center_y"]
            error = max(abs(support["estimated_center_world"][0]-spec["opening"]["center_x"]),
                        abs(support["estimated_center_world"][1]-expected_y))
            max_opening_error = max(max_opening_error, error)
            audit.check("robot_public_pixel_gate_recovery", route == base._open_route and error <= 1.0, key+[twin])
            frames += 2
            before = copy.deepcopy(base)
            initial_success = []
            for route0, mode0 in actions:
                raw = copy.deepcopy(before)
                raw.query("robot_execute", {"route": route0, "mode": mode0})
                if raw.evaluate({"delivered": True}).success:
                    initial_success.append((route0, mode0))
            audit.check("robot_each_initial_world_feasible", bool(initial_success), key+[twin])
            base.query("robot_move_camera", {"view": "inspection"})
            base.query("robot_capture", {})
            for prefix in prefixes:
                contacted = copy.deepcopy(base)
                expected_elapsed, expected_energy, expected_wear = 2, 1, 0
                for force in prefix:
                    measurement = contacted.query("robot_probe", {"force": force})
                    action = spec["actions"]["probe_"+force]
                    expected_elapsed += action["time"]
                    expected_energy += action["energy"]
                    expected_wear += action["wear"]
                    low, high = measurement["friction_interval"]
                    audit.check("robot_probe_contains_post_contact_state", low <= contacted.friction <= high, key+[twin, list(prefix), force])
                for route0, mode0 in actions:
                    task = copy.deepcopy(contacted)
                    action = spec["actions"]["detour_slow" if route0 == "detour" else "primary_"+mode0]
                    elapsed, energy = expected_elapsed+action["time"], expected_energy+action["energy"]
                    expected = robot_outcome_oracle(task._open_route, task._initial_friction, expected_wear,
                                                    route0, mode0, elapsed, energy, spec)
                    result = task.query("robot_execute", {"route": route0, "mode": mode0})
                    case = key+[twin, list(prefix), route0, mode0]
                    audit.check("robot_exact_fraction_transition_oracle", result["outcome"] == expected and
                                all(type(v) is bool for v in result["outcome"].values()), case)
                    audit.check("robot_execution_ledger", (task.elapsed, task.energy_used, task.wear) ==
                                (elapsed, energy, expected_wear), case)
                    audit.check("robot_actual_execution_scoring", task.evaluate({"delivered": True}).success == expected["completed"], case)
                    cases += 1
            # A blinded-reading callback tests information use independently of
            # the contact intervention itself. No model trial is claimed.
            task = RoboticsVisionTask(seed, split, difficulty, twin)
            session = Session(task)
            def without_probe_reading(name, args):
                response = session.call(name, args)
                if name == "robot_probe":
                    response.pop("friction_interval", None)
                return response
            fill = solve_robotics_vision(session.public(), without_probe_reading, "conditioning_grip")
            session.call("submit", {"fill": fill, "confidence": float(bool(fill["delivered"])),
                                    "abstain": False, "evidence": [event["event_id"] for event in session.trace]})
            expected_success = max(Fraction(str(spec["contact"]["minimum_friction"])),
                                   Fraction(str(task._initial_friction))-2*Fraction(str(spec["contact"]["wear_decrement"]))) <= Fraction("0.45")
            actual = task.evaluate(fill).success
            audit.check("robot_conditioning_without_reading", actual == expected_success and task.action == {"route": task._open_route, "mode": "grip"}, key+[twin])
            audit.check("robot_conditioning_no_collision_or_slip", not task.outcome["collision"] and not task.outcome["slip"], key+[twin])
            robot_ledger_checks(audit, session, spec, key+[twin])
            audit.check("robot_control_trace_integrity", verify_trace(session.trace), key+[twin])
            label = task.contact_profile+"/"+task.profile
            row = conditioning_counts.setdefault(label, {"episodes": 0, "successes": 0, "stalls": 0})
            row["episodes"] += 1
            row["successes"] += int(actual)
            row["stalls"] += int(task.outcome["stalled"])
    audit.measurements["robot_transitions"] = {
        "base_episodes": seed_count*3*3*2, "rendered_gate_frames_checked": frames,
        "committed_transition_cases": cases, "prefixes": [list(p) for p in prefixes],
        "legal_terminal_actions_per_prefix": len(actions),
        "maximum_opening_center_error_world": max_opening_error,
        "probe_reading_blinded_conditioning_grip": conditioning_counts,
        "oracle": "exact decimal Fraction physical conditions plus independent time/energy/wear accounting",
        "scope": "four selected prefixes, not every possible history; scripted controls only",
    }


def robot_common_action_checks(audit):
    """Enumerate action intersections before and after declared contact actions."""
    from causalfill.domains.robotics_vision import RoboticsVisionTask
    actions = [(r, m) for r in ("upper", "lower") for m in ("roll", "grip", "slow")]+[("detour", "slow")]
    findings = []
    for seed in (1, 7):  # strict/conditionable and strict/resistant, friction twins
        spec = json.loads(RoboticsVisionTask(seed).files["/scene/robotics_vision.json"])
        for prefix in ((), ("gentle",), ("firm",), ("firm", "gentle")):
            successes = []
            for mu in spec["contact"]["initial_friction_support"]:
                valid = set()
                for route, mode in actions:
                    task = RoboticsVisionTask(seed)
                    task._open_route = "upper"
                    task._initial_friction = mu
                    # One recorded move/capture accounts for the observed lane.
                    task.query("robot_move_camera", {"view": "inspection"})
                    task.query("robot_capture", {})
                    for force in prefix:
                        task.query("robot_probe", {"force": force})
                    task.query("robot_execute", {"route": route, "mode": mode})
                    if task.evaluate({"delivered": True}).success:
                        valid.add((route, mode))
                successes.append(valid)
            common = set.intersection(*successes)
            expected = {("upper", "grip")} if seed == 1 and prefix == ("firm",) else set()
            audit.check("robot_common_terminal_action_enumeration", common == expected, [seed, list(prefix), sorted(common)])
            findings.append({"contact_profile": spec["contact"]["profile"], "prefix": list(prefix),
                             "successful_action_sets": [sorted(x) for x in successes], "common": sorted(common)})
    # Geometry remains consequential for strict gate twins even after firm
    # conditioning; no single route can cross both distinct openings.
    for seed in (2, 4, 8, 10):
        successes = []
        for twin in (0, 1):
            valid = set()
            for route, mode in actions:
                task = RoboticsVisionTask(seed, twin=twin)
                task.query("robot_probe", {"force": "firm"})
                task.query("robot_execute", {"route": route, "mode": mode})
                if task.evaluate({"delivered": True}).success:
                    valid.add((route, mode))
            successes.append(valid)
        audit.check("robot_geometry_pair_no_common_commit", bool(successes[0]) and bool(successes[1]) and not (successes[0] & successes[1]), seed)
    audit.measurements["robot_action_intersections"] = {
        "strict_known_lane_profiles": findings,
        "interpretation": "Firm contact creates a common grip action only in the deliberately conditionable profile; resistant profiles require information or more contact than the strict deadline permits. Geometry sensing is still consequential for strict gate pairs.",
        "scope": "Exhaustive seven terminal actions after listed prefixes, not an exact optimum over all sensing histories.",
    }


def source_hashes():
    candidates = ["causalfill/vision.py", "causalfill/domains/visual.py", "causalfill/types.py",
                  "causalfill/session.py", "causalfill/server.py", "causalfill/protocol_json.py",
                  "causalfill/decision_sufficiency.py", "clients/image_client.py", "tools/stress_vision_audit_v05.py",
                  "causalfill/domains/robotics_vision.py", "causalfill/robotics_vision_policy.py",
                  "causalfill/runner.py", "causalfill/registry.py", "causalfill/policies.py"]
    return {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in candidates if (ROOT/name).is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed-count", type=int, default=8)
    parser.add_argument("--table-limit", type=int, default=81)
    parser.add_argument("--sections", nargs="+", choices=("pixels", "calibration", "decision", "visual", "http", "robotics"), default=["pixels", "calibration", "decision", "visual", "http", "robotics"])
    args = parser.parse_args()
    if not 1 <= args.seed_count <= 100 or not 1 <= args.table_limit <= 81:
        parser.error("seed-count must be 1..100; table-limit must be 1..81")
    audit = Audit()
    started, before = time.monotonic(), source_hashes()
    if "pixels" in args.sections:
        raster_checks(audit)
        decoder_attacks(audit)
        pixel_noise_and_calibration(audit)
    if "calibration" in args.sections:
        exhaustive_transfer_calibration(audit)
    if "decision" in args.sections:
        decision_enumeration(audit, args.table_limit)
        decision_forgery_checks(audit)
        replay_alias_checks(audit)
    if "visual" in args.sections:
        visual_domain_checks(audit, args.seed_count)
        visual_scoring_boundaries(audit)
    if "http" in args.sections:
        image_http_client_checks(audit)
    if "robotics" in args.sections:
        robot_integrity_checks(audit)
        robot_transition_checks(audit, args.seed_count)
        robot_common_action_checks(audit)
    after = source_hashes()
    audit.check("source_stability", before == after, "no_files_changed_during_run")
    report = {"schema": "causalfill.independent-vision-audit.v05", "created_utc": datetime.now(timezone.utc).isoformat(),
              "role": "author/evaluator development audit", "sections": args.sections,
              "source_sha256_before": before, "source_sha256_after": after,
              "counts": dict(audit.counts), "checks": sum(audit.counts.values()),
              "failure_count": len(audit.failures), "failures": audit.failures,
              "measurements": audit.measurements, "elapsed_seconds": time.monotonic()-started,
              "transcript_sha256": audit.transcript.hexdigest(),
              "claims": {"finite_engineering_checks": True, "model_performance": False,
                         "formal_proof": False, "physical_robot_validation": False}}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False)+"\n")
    print(json.dumps({"checks": report["checks"], "failure_count": report["failure_count"],
                      "measurements": report["measurements"], "output": str(args.output)}, indent=2))
    return int(bool(audit.failures))


if __name__ == "__main__":
    raise SystemExit(main())
