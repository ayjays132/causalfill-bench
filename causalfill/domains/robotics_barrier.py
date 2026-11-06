"""Versioned symbolic route sensing with a checkable paired-world witness.

The two worlds share all camera observations and public files. A wall shifts in
y: one world leaves an upper passage, the other a lower passage. Their forbidden
sets cover a separating workspace cross-section, so no continuous path is safe
in both. This proves a need for a geometry-dependent observation, not model
hardness, real-image understanding, contact physics, or lidar exclusivity.
"""
from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
import json
import math
from typing import Any

from causalfill.domains.robotics import (
    AXES, MAX_WAYPOINTS, RoboticsTask, path_assessment,
    recover_target_from_camera_readings,
)
from causalfill.types import canonical, digest


PROFILE_VERSION = "robotics_barrier_v1"
CERTIFICATE_VERSION = "separating_workspace_section_v1"
MAX_CERTIFICATE_BYTES = 262144


def solve_robotics_barrier_from_observations(
    workspace: dict[str, Any],
    camera_readings: list[dict[str, Any]],
    lidar_reading: dict[str, Any],
) -> dict[str, Any]:
    """Reference plan using only the three supplied public observations.

    No Task, seed, latent geometry, counterfactual world, or certificate is an
    input. This planner is specialized to a single full-height box with an open
    y passage; it does not claim general motion planning.
    """
    if workspace.get("profile_version") != PROFILE_VERSION:
        raise ValueError("Expected the robotics_barrier_v1 public workspace.")
    target, material = recover_target_from_camera_readings(workspace, camera_readings)
    start, bounds = workspace["start"], workspace["bounds"]
    clearance = workspace["gripper_clearance"]
    obstacles = lidar_reading["occupied_boxes"]
    if type(obstacles) is not list or len(obstacles) != 1:
        raise ValueError("The barrier reference supports exactly one observed wall.")
    candidates: list[list[list[float]]] = [[]]
    wall = obstacles[0]
    free_lower = Fraction(str(bounds[0][1])) + Fraction(str(clearance))
    free_upper = Fraction(str(bounds[1][1])) - Fraction(str(clearance))
    wall_lower = Fraction(str(wall["lower"][1])) - Fraction(str(clearance))
    wall_upper = Fraction(str(wall["upper"][1])) + Fraction(str(clearance))
    for lower, upper in ((free_lower, wall_lower), (wall_upper, free_upper)):
        if lower < upper:
            passage_y = float((lower+upper)/2)
            candidates.append([[start[0], passage_y, start[2]],
                               [target[0], passage_y, target[2]]])
    for waypoints in candidates:
        clear, inside = path_assessment(start, target, waypoints, obstacles, bounds, clearance)
        if clear and inside:
            return {"target_world_position": target, "safe_waypoints": waypoints,
                    "grasp_precondition": {"gripper": "open",
                        "force_limit_n": workspace["material_force_limits_n"][material]}}
    raise ValueError("Observed wall has no route supported by the barrier reference.")


class RoboticsBarrierTask(RoboticsTask):
    """A separate profile: original RoboticsTask generation remains unchanged."""

    family = "robotics_barrier"

    def __init__(self, seed: int, split: str = "dev", difficulty: int = 2, twin: int = 0):
        super().__init__(seed, split, difficulty, twin)
        self.family = "robotics_barrier"
        # Every draw is shared across twins. The only changed causal parameter
        # is a y translation of one wall; its size and all other state stay fixed.
        wall_left = self.rng.randrange(18, 23)/4       # 4.50 .. 5.50
        wall_width = self.rng.randrange(3, 6)/4      # 0.75 .. 1.25
        wall_height_y = self.rng.randrange(28, 37)/4 # 7.00 .. 9.00
        self._wall_y_offset = (12.0-wall_height_y) if twin else 0.0
        self._obstacles = [{"id": "barrier-a",
            "lower": [wall_left, self._wall_y_offset, 0.0],
            "upper": [wall_left+wall_width, self._wall_y_offset+wall_height_y, 12.0]}]
        workspace = json.loads(self.files["/scene/workspace.json"])
        workspace["profile_version"] = PROFILE_VERSION
        self.files["/scene/workspace.json"] = json.dumps(workspace, indent=2)
        self.files["/docs/barrier-profile.txt"] = (
            "ROBOTICS BARRIER PROFILE v1\n"
            "This is a symbolic numeric-coordinate simulation, not real-image perception or physical robotics.\n"
            "One axis-aligned wall extends from the workspace floor to its ceiling. The target is on the "
            "opposite x side of the wall from the start. A positive-width passage exists at one y end. "
            "Do not assume which end is open: the wall's y position is observed by lidar or by geometric "
            "path probes, while camera outputs contain only object and calibration coordinates.\n"
            "Recover the target from cameras and submit any safe continuous piecewise-linear route under "
            "the ordinary collision, workspace, force, and goal constraints. No route pattern or "
            "particular sensor is required for scoring. The profile has paired worlds with identical "
            "public files and camera readings but incompatible safe routes.\n"
            "The budget includes all public tool calls. A fixed route need not be valid in both worlds.\n"
        )
        self.prompt = (
            "Complete the masked manipulation plan in robotics_barrier_v1: "
            "target_world_position=<MASK>, safe_waypoints=<MASK>, grasp_precondition=<MASK>. "
            "Recover the target from calibrated numeric camera evidence and sense the full-height wall "
            "to choose an open passage. Read the workspace, robotics manual and barrier profile. "
            "The final route is checked in a symbolic 3D simulator; any behaviorally valid plan is accepted."
        )
        transform = {"train": "positive-diagonal", "dev": "signed-diagonal", "transfer": "affine-shear"}[split]
        self.structural_signature = f"robotics_barrier:orthographic-{transform}:opposite-y-passages:v1"
        self.twin_kind = "wall_y_translation"

    def reference_answer(self) -> dict:
        workspace = json.loads(self.files["/scene/workspace.json"])
        cameras = [self.query("camera", {"view": view}) for view in workspace["camera_views"]]
        return solve_robotics_barrier_from_observations(workspace, cameras, self.query("lidar", {}))

    def separation_certificate(self) -> dict:
        """Evaluator-only paired artifact; never exposed as an episode tool."""
        other = RoboticsBarrierTask(self.seed, self.split, self.difficulty, 1-self.twin)
        first, second = (self, other) if self.twin == 0 else (other, self)
        return build_barrier_pair_certificate(first, second)


def build_barrier_pair_certificate(first: RoboticsBarrierTask, second: RoboticsBarrierTask) -> dict:
    """Construct a statement-bound witness from two observed generated worlds."""
    worlds = []
    routes = []
    for task in (first, second):
        if not isinstance(task, RoboticsBarrierTask):
            raise ValueError("A barrier pair consists of RoboticsBarrierTask worlds.")
        workspace = json.loads(task.files["/scene/workspace.json"])
        cameras = [task.query("camera", {"view": view}) for view in workspace["camera_views"]]
        lidar = task.query("lidar", {})
        worlds.append({"public": task.public(), "files": deepcopy(task.files),
                       "cameras": cameras, "lidar": lidar})
        routes.append(solve_robotics_barrier_from_observations(workspace, cameras, lidar))
    first_box = worlds[0]["lidar"]["occupied_boxes"][0]
    coordinate = float((Fraction(str(first_box["lower"][0]))+
                        Fraction(str(first_box["upper"][0])))/2)
    statement = {"profile_version": PROFILE_VERSION, "worlds": worlds}
    certificate = {"certificate_version": CERTIFICATE_VERSION,
                   "statement_sha256": digest(statement),
                   "separator": {"axis": 0, "coordinate": coordinate}, "routes": routes}
    return {"statement": statement, "certificate": certificate}


# The verifier below deliberately does not call path_assessment,
# segment_intersects_box, recover_target_from_camera_readings, the reference
# planner, a task constructor, or generator-private members. It treats the
# artifact as untrusted bounded JSON and recomputes its geometry and calibration.


def _fields(value: Any, expected: set[str], label: str) -> dict:
    if type(value) is not dict or set(value) != expected:
        raise ValueError(f"{label}: missing, extra, or malformed fields")
    return value


def _rational(value: Any, label: str) -> Fraction:
    if type(value) not in (int, float) or abs(value) > 1000 or not math.isfinite(value):
        raise ValueError(f"{label}: finite nonboolean numeric value within +/-1000 required")
    return Fraction(str(value))


def _vector(value: Any, length: int, label: str) -> list[Fraction]:
    if type(value) is not list or len(value) != length:
        raise ValueError(f"{label}: incorrect vector shape")
    return [_rational(component, label) for component in value]


def _gaussian(matrix: list[list[Fraction]], rhs: list[Fraction]) -> list[Fraction]:
    augmented = [row[:]+[answer] for row, answer in zip(matrix, rhs)]
    for column in range(len(augmented)):
        candidates = [row for row in range(column, len(augmented)) if augmented[row][column] != 0]
        if not candidates:
            raise ValueError("singular camera calibration")
        pivot = candidates[0]
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        augmented[column] = [value/divisor for value in augmented[column]]
        for row in range(len(augmented)):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [a-factor*b for a, b in zip(augmented[row], augmented[column])]
    return [row[-1] for row in augmented]


def _camera_target(workspace: dict, readings: Any) -> tuple[list[Fraction], str]:
    if type(readings) is not list or len(readings) != 3:
        raise ValueError("certificate must include all three camera observations")
    views, recovered, materials = set(), [[], [], []], set()
    for reading in readings:
        _fields(reading, {"view", "kind", "projection_axes", "fiducials", "objects",
                          "occlusion_possible", "units"}, "camera")
        view = reading["view"]
        if type(view) is not str or view not in AXES or view in views:
            raise ValueError("camera views must be distinct xy, xz, yz")
        views.add(view)
        axes = reading["projection_axes"]
        if (type(axes) is not list or any(type(axis) is not int for axis in axes)
                or axes != list(AXES[view])):
            raise ValueError("camera projection axes do not match its view")
        if reading["kind"] != "symbolic_orthographic_coordinates":
            raise ValueError("incorrect camera observation kind")
        if type(reading["occlusion_possible"]) is not bool:
            raise ValueError("camera occlusion metadata must be boolean")
        _fields(reading["units"], {"world", "image"}, "camera units")
        if reading["units"] != {"world": "m", "image": "arbitrary_sensor_units"}:
            raise ValueError("incorrect camera units")
        fiducials = reading["fiducials"]
        if type(fiducials) is not list or len(fiducials) != 3:
            raise ValueError("three calibration fiducials are required")
        worlds, images = [], []
        for fiducial in fiducials:
            _fields(fiducial, {"id", "world", "image"}, "fiducial")
            if type(fiducial["id"]) is not str or not 1 <= len(fiducial["id"]) <= 100:
                raise ValueError("fiducial id must be a bounded string")
            worlds.append(_vector(fiducial["world"], 3, "fiducial world"))
            images.append(_vector(fiducial["image"], 2, "fiducial image"))
        design = [[world[axes[0]], world[axes[1]], Fraction(1)] for world in worlds]
        image_x = _gaussian(design, [image[0] for image in images])
        image_y = _gaussian(design, [image[1] for image in images])
        objects = reading["objects"]
        if type(objects) is not list or not 1 <= len(objects) <= 64:
            raise ValueError("bounded camera object list required")
        visible_target = False
        for obj in objects:
            _fields(obj, {"id", "image", "material"}, "object")
            if type(obj["id"]) is not str or not 1 <= len(obj["id"]) <= 100:
                raise ValueError("object id must be a bounded string")
            if type(obj["material"]) is not str or obj["material"] not in workspace["material_force_limits_n"]:
                raise ValueError("unknown object material")
            image = _vector(obj["image"], 2, "object image")
            if obj["id"] != workspace["target_id"]:
                continue
            if visible_target:
                raise ValueError("duplicate target object in a camera")
            visible_target = True
            material = obj["material"]
            if type(material) is not str or material not in workspace["material_force_limits_n"]:
                raise ValueError("unknown target material")
            materials.add(material)
            position = _gaussian([image_x[:2], image_y[:2]],
                                 [image[0]-image_x[2], image[1]-image_y[2]])
            for axis, value in zip(axes, position):
                recovered[axis].append(value)
    if any(not values or len(set(values)) != 1 for values in recovered) or len(materials) != 1:
        raise ValueError("camera evidence must consistently identify every target coordinate and material")
    return [values[0] for values in recovered], next(iter(materials))


def _box(value: Any) -> tuple[list[Fraction], list[Fraction]]:
    _fields(value, {"id", "lower", "upper"}, "obstacle")
    if type(value["id"]) is not str or not 1 <= len(value["id"]) <= 100:
        raise ValueError("obstacle id must be a bounded string")
    lower, upper = _vector(value["lower"], 3, "box lower"), _vector(value["upper"], 3, "box upper")
    if any(lo >= hi for lo, hi in zip(lower, upper)):
        raise ValueError("barrier boxes must have positive extent")
    return lower, upper


def _face_intersection(start, end, lower, upper) -> bool:
    """Independent exact endpoint / six-face intersection, without slab tests."""
    def inside(point):
        return all(lo <= value <= hi for lo, value, hi in zip(lower, point, upper))

    if inside(start) or inside(end):
        return True
    direction = [b-a for a, b in zip(start, end)]
    for axis in range(3):
        if direction[axis] == 0:
            continue
        for face in (lower[axis], upper[axis]):
            parameter = (face-start[axis])/direction[axis]
            if 0 <= parameter <= 1:
                point = [a+parameter*delta for a, delta in zip(start, direction)]
                if inside(point):
                    return True
    return False


def _route_valid(fill, start, target, material, workspace, boxes, free_lower, free_upper) -> bool:
    _fields(fill, {"target_world_position", "safe_waypoints", "grasp_precondition"}, "route")
    endpoint = _vector(fill["target_world_position"], 3, "route target")
    tolerance = _rational(workspace["goal_tolerance_m"], "goal tolerance")
    if any(abs(actual-expected) > tolerance for actual, expected in zip(endpoint, target)):
        return False
    raw_waypoints = fill["safe_waypoints"]
    if type(raw_waypoints) is not list or len(raw_waypoints) > MAX_WAYPOINTS:
        raise ValueError("route must have 0..16 waypoints")
    waypoints = [_vector(point, 3, "waypoint") for point in raw_waypoints]
    handling = _fields(fill["grasp_precondition"], {"gripper", "force_limit_n"}, "handling")
    force = _rational(handling["force_limit_n"], "force")
    minimum = _rational(workspace["minimum_lifting_force_n"], "minimum force")
    maximum = _rational(workspace["material_force_limits_n"][material], "material force")
    if handling["gripper"] != "open" or not minimum <= force <= maximum:
        return False
    points = [start, *waypoints, endpoint]
    if not all(lo <= coordinate <= hi for point in points
               for lo, coordinate, hi in zip(free_lower, point, free_upper)):
        return False
    return not any(_face_intersection(a, b, lower, upper)
                   for a, b in zip(points, points[1:]) for lower, upper in boxes)


def _rectangles_cover(rectangles, lower, upper) -> tuple[bool, int]:
    """Exact rectangle-union coverage by interval checks at cuts and strips."""
    clipped = []
    cuts = {lower[0], upper[0]}
    for lo, hi in rectangles:
        lo = [max(lo[axis], lower[axis]) for axis in range(2)]
        hi = [min(hi[axis], upper[axis]) for axis in range(2)]
        if any(a > b for a, b in zip(lo, hi)):
            continue
        clipped.append((lo, hi))
        cuts.update((lo[0], hi[0]))
    cuts = sorted(cuts)
    probes = cuts+[(a+b)/2 for a, b in zip(cuts, cuts[1:]) if a < b]
    for coordinate in probes:
        intervals = sorted((lo[1], hi[1]) for lo, hi in clipped if lo[0] <= coordinate <= hi[0])
        covered = lower[1]
        for lo, hi in intervals:
            if lo > covered:
                break
            covered = max(covered, hi)
        if covered < upper[1]:
            return False, len(probes)
    return True, len(probes)


def verify_barrier_certificate(statement: Any, certificate: Any) -> dict[str, Any]:
    """Validate paired observation equivalence, a separator, and safe witnesses.

    A valid result establishes no *single* admissible continuous path can solve
    both supplied worlds, even allowing any endpoint within the goal tolerance.
    It is an exact symbolic geometry claim about the supplied statement, which
    the SHA-256 binding associates with the certificate. It is not an authenticity
    signature, general robot-safety guarantee, or proof of frontier-model hardness.
    """
    try:
        for payload in (statement, certificate):
            if len(canonical(payload).encode()) > MAX_CERTIFICATE_BYTES:
                raise ValueError("certificate artifact exceeds 256 KiB")
        _fields(statement, {"profile_version", "worlds"}, "statement")
        _fields(certificate, {"certificate_version", "statement_sha256", "separator", "routes"}, "certificate")
        if statement["profile_version"] != PROFILE_VERSION or certificate["certificate_version"] != CERTIFICATE_VERSION:
            raise ValueError("unsupported profile or certificate version")
        if certificate["statement_sha256"] != digest(statement):
            raise ValueError("statement hash mismatch")
        worlds = statement["worlds"]
        if type(worlds) is not list or len(worlds) != 2:
            raise ValueError("exactly two worlds are required")
        for world in worlds:
            _fields(world, {"public", "files", "cameras", "lidar"}, "world")
            public = _fields(world["public"], {"family", "difficulty", "prompt", "slots", "files",
                                               "tools", "budget", "max_calls"}, "public contract")
            if public["family"] != "robotics_barrier":
                raise ValueError("incorrect public task family")
            if type(public["difficulty"]) is not int or not 1 <= public["difficulty"] <= 3:
                raise ValueError("public difficulty must be an integer from 1 to 3")
            if any(type(public[field]) is not int or not 1 <= public[field] <= 100000
                   for field in ("budget", "max_calls")):
                raise ValueError("public budgets must be positive bounded integers")
            if type(public["prompt"]) is not str or not 1 <= len(public["prompt"]) <= 32768:
                raise ValueError("public prompt must be a bounded string")
            _fields(public["slots"], {"target_world_position", "safe_waypoints", "grasp_precondition"}, "public slots")
            for slot in public["slots"].values():
                _fields(slot, {"type", "description"}, "public slot")
                if any(type(value) is not str or len(value) > 4096 for value in slot.values()):
                    raise ValueError("public slot fields must be bounded strings")
            _fields(public["tools"], {"camera", "lidar", "probe_path"}, "public tools")
            for tool in public["tools"].values():
                _fields(tool, {"description", "arguments", "cost"}, "public tool")
                if type(tool["cost"]) is not int or not 1 <= tool["cost"] <= 10000:
                    raise ValueError("tool costs must be positive bounded integers")
                if type(tool["description"]) is not str or len(tool["description"]) > 4096:
                    raise ValueError("tool description must be a bounded string")
                if type(tool["arguments"]) is not dict or any(type(key) is not str or type(value) is not str
                                                              for key, value in tool["arguments"].items()):
                    raise ValueError("tool arguments must declare string fields")
            if type(world["files"]) is not dict or not 1 <= len(world["files"]) <= 16:
                raise ValueError("bounded public file mapping required")
            if any(type(path) is not str or type(body) is not str or len(body) > 32768
                   for path, body in world["files"].items()):
                raise ValueError("invalid public file entry")
            if (type(public["files"]) is not list or any(type(path) is not str for path in public["files"])
                    or public["files"] != sorted(world["files"])):
                raise ValueError("public file inventory does not match supplied files")
        for field in ("public", "files", "cameras"):
            # Python equality conflates JSON true with 1 and false with 0.
            # Observation equivalence must preserve the serialized JSON types.
            if canonical(worlds[0][field]) != canonical(worlds[1][field]):
                raise ValueError(f"paired {field} observations differ before geometry sensing")
        workspace = json.loads(worlds[0]["files"]["/scene/workspace.json"])
        _fields(workspace, {"target_id", "start", "bounds", "gripper_clearance", "camera_views",
                            "material_force_limits_n", "minimum_lifting_force_n", "goal_tolerance_m",
                            "profile_version"}, "workspace")
        if workspace["profile_version"] != PROFILE_VERSION:
            raise ValueError("incorrect workspace profile")
        if type(workspace["target_id"]) is not str or not 1 <= len(workspace["target_id"]) <= 100:
            raise ValueError("bounded target id required")
        if workspace["camera_views"] != list(AXES):
            raise ValueError("workspace camera views differ from the profile")
        if type(workspace["bounds"]) is not list or len(workspace["bounds"]) != 2:
            raise ValueError("workspace bounds shape")
        lower = _vector(workspace["bounds"][0], 3, "workspace lower")
        upper = _vector(workspace["bounds"][1], 3, "workspace upper")
        clearance = _rational(workspace["gripper_clearance"], "clearance")
        tolerance = _rational(workspace["goal_tolerance_m"], "goal tolerance")
        if clearance <= 0 or tolerance <= 0:
            raise ValueError("positive clearance and goal tolerance required")
        minimum = _rational(workspace["minimum_lifting_force_n"], "minimum force")
        limits = workspace["material_force_limits_n"]
        if type(limits) is not dict or set(limits) != {"foam", "glass", "steel"}:
            raise ValueError("material force contract is malformed")
        if minimum <= 0 or any(_rational(value, "material force") < minimum for value in limits.values()):
            raise ValueError("invalid symbolic force window")
        free_lower, free_upper = [x+clearance for x in lower], [x-clearance for x in upper]
        if any(a >= b for a, b in zip(free_lower, free_upper)):
            raise ValueError("workspace has no clearance-safe interior")
        start = _vector(workspace["start"], 3, "start")
        target, material = _camera_target(workspace, worlds[0]["cameras"])
        if not all(lo <= x <= hi for lo, x, hi in zip(free_lower, start, free_upper)):
            raise ValueError("start lies outside clearance-safe workspace")
        if not all(lo <= x-tolerance and x+tolerance <= hi for lo, x, hi in zip(free_lower, target, free_upper)):
            raise ValueError("entire goal tolerance region must be inside the workspace")
        all_boxes, raw_boxes = [], []
        for world in worlds:
            lidar = _fields(world["lidar"], {"occupied_boxes", "frame", "units"}, "lidar")
            if lidar["frame"] != "world" or lidar["units"] != "m":
                raise ValueError("lidar must use the declared world frame and metres")
            boxes = lidar["occupied_boxes"]
            if type(boxes) is not list or len(boxes) != 1:
                raise ValueError("exactly one wall in each profile world required")
            box_lower, box_upper = _box(boxes[0])
            raw_boxes.append((box_lower, box_upper))
            all_boxes.append([([value-clearance for value in box_lower],
                               [value+clearance for value in box_upper])])
        first, second = raw_boxes
        if worlds[0]["lidar"]["occupied_boxes"][0]["id"] != worlds[1]["lidar"]["occupied_boxes"][0]["id"]:
            raise ValueError("paired wall identities differ")
        if any(first[corner][axis] != second[corner][axis] for corner in (0, 1) for axis in (0, 2)):
            raise ValueError("only the wall's y translation may change")
        translation = second[0][1]-first[0][1]
        if translation == 0 or second[1][1]-first[1][1] != translation:
            raise ValueError("wall change is not a single nonzero y translation")
        separator = _fields(certificate["separator"], {"axis", "coordinate"}, "separator")
        axis = separator["axis"]
        if type(axis) is not int or not 0 <= axis <= 2:
            raise ValueError("separator axis must be 0, 1, or 2")
        coordinate = _rational(separator["coordinate"], "separator coordinate")
        if not (start[axis] < coordinate < target[axis]-tolerance
                or target[axis]+tolerance < coordinate < start[axis]):
            raise ValueError("separator does not strictly separate start from the entire goal region")
        transverse = [other for other in range(3) if other != axis]
        rectangles = [([box_lower[j] for j in transverse], [box_upper[j] for j in transverse])
                      for boxes in all_boxes for box_lower, box_upper in boxes
                      if box_lower[axis] <= coordinate <= box_upper[axis]]
        covered, slices = _rectangles_cover(rectangles, [free_lower[j] for j in transverse],
                                            [free_upper[j] for j in transverse])
        if not covered:
            raise ValueError("paired forbidden sets do not cover the separating workspace section")
        routes = certificate["routes"]
        if type(routes) is not list or len(routes) != 2:
            raise ValueError("one constructive route per world is required")
        for route, boxes in zip(routes, all_boxes):
            if not _route_valid(route, start, target, material, workspace, boxes, free_lower, free_upper):
                raise ValueError("a constructive per-world route is invalid")
        return {"valid": True, "certificate_version": CERTIFICATE_VERSION,
                "statement_sha256": certificate["statement_sha256"],
                "shared_public_and_camera_observations": True,
                "single_wall_y_translation": True, "separating_section_covered": True,
                "separator_axis": axis, "separator_coordinate": float(coordinate),
                "exact_section_slices_checked": slices, "constructive_routes_checked": 2,
                "guarantee": "no common admissible continuous path solves both supplied worlds",
                "scope": "symbolic geometry; a suitable geometry-dependent observation can distinguish worlds"}
    except (ValueError, TypeError, KeyError, IndexError, OverflowError, ZeroDivisionError, RecursionError) as exc:
        return {"valid": False, "reason": str(exc)[:300]}
