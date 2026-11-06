"""Original symbolic active-sensing tasks; no physics engine or robot integration.

Camera outputs are calibrated 2-D coordinates, not raster vision observations.
The evaluator owns the latent scene. Only ``query`` results cross the task's
observation boundary. ``reference_answer`` is an evidence-based debugging oracle,
not a learned or frontier-model baseline.
"""

from __future__ import annotations

from copy import deepcopy
from fractions import Fraction
import json
import math
from typing import Any

from causalfill.types import Task, Verdict


AXES = {"xy": (0, 1), "xz": (0, 2), "yz": (1, 2)}
FORCE_LIMITS = {"glass": 2.0, "foam": 1.0, "steel": 8.0}
MAX_WAYPOINTS = 16
EPSILON = 1e-8


def _number(value: Any, bound: float = 1000.0) -> float:
    if type(value) not in (int, float):
        raise ValueError("Expected a finite numeric value; booleans are invalid.")
    if abs(value) > bound or not math.isfinite(value):
        raise ValueError("Numeric value is nonfinite or outside the supported range.")
    return float(value)


def _point(value: Any) -> list[float]:
    if type(value) is not list or len(value) != 3:
        raise ValueError("A point must be a three-number JSON array.")
    return [_number(component) for component in value]


def _waypoints(value: Any) -> list[list[float]]:
    if type(value) is not list or len(value) > MAX_WAYPOINTS:
        raise ValueError("Waypoints must be a JSON array with at most 16 points.")
    return [_point(point) for point in value]


def _exact_fields(value: Any, fields: set[str]) -> None:
    if type(value) is not dict or set(value) != fields:
        raise ValueError("Missing, unknown, or malformed argument fields.")


def segment_intersects_box(
    start: list[float],
    end: list[float],
    lower: list[float],
    upper: list[float],
    clearance: float = 0.0,
) -> bool:
    """Closed segment versus clearance-expanded closed AABB, using slab tests.

    Touching the expanded surface counts as a collision. Inputs are expected to
    have passed the task's finite-number and shape validation. Geometry uses the
    exact decimal values of JSON numbers: a positive gap is not a collision, and
    no tolerance permits the gripper to cross a workspace boundary. Keeping the
    interval arithmetic rational also avoids a parameter-space epsilon whose
    physical size would depend on the segment length.
    """
    start_exact = [Fraction(str(value)) for value in start]
    end_exact = [Fraction(str(value)) for value in end]
    clearance_exact = Fraction(str(clearance))
    enter, leave = Fraction(0), Fraction(1)
    for axis in range(3):
        lo = Fraction(str(lower[axis])) - clearance_exact
        hi = Fraction(str(upper[axis])) + clearance_exact
        delta = end_exact[axis] - start_exact[axis]
        if delta == 0:
            if start_exact[axis] < lo or start_exact[axis] > hi:
                return False
            continue
        first = (lo - start_exact[axis]) / delta
        last = (hi - start_exact[axis]) / delta
        if first > last:
            first, last = last, first
        enter, leave = max(enter, first), min(leave, last)
        if enter > leave:
            return False
    return enter <= 1 and leave >= 0


def path_assessment(
    start: list[float],
    target: list[float],
    waypoints: list[list[float]],
    obstacles: list[dict[str, Any]],
    bounds: list[list[float]],
    clearance: float,
) -> tuple[bool, bool]:
    """Return (collision_free, inside_workspace), without any goal oracle."""
    points = [start, *waypoints, target]
    margin = Fraction(str(clearance))
    lower = [Fraction(str(value)) + margin for value in bounds[0]]
    upper = [Fraction(str(value)) - margin for value in bounds[1]]
    inside = all(
        lower[axis] <= Fraction(str(point[axis])) <= upper[axis]
        for point in points
        for axis in range(3)
    )
    collision = any(
        segment_intersects_box(a, b, box["lower"], box["upper"], clearance)
        for a, b in zip(points, points[1:])
        for box in obstacles
    )
    return not collision, inside


def invert_camera_point(
    image: list[float], fiducials: list[dict[str, Any]], axes: list[int]
) -> list[float]:
    """Infer an orthographic 2-D affine calibration from three visible anchors.

    This helper uses only values present in the camera observation. It supports
    translation, scaling, reflection, and the transfer split's affine shear.
    """
    origin, u_anchor, v_anchor = fiducials
    u_span = u_anchor["world"][axes[0]] - origin["world"][axes[0]]
    v_span = v_anchor["world"][axes[1]] - origin["world"][axes[1]]
    if abs(u_span) <= EPSILON or abs(v_span) <= EPSILON:
        raise ValueError("Degenerate fiducial geometry.")
    a = (u_anchor["image"][0] - origin["image"][0]) / u_span
    c = (u_anchor["image"][1] - origin["image"][1]) / u_span
    b = (v_anchor["image"][0] - origin["image"][0]) / v_span
    d = (v_anchor["image"][1] - origin["image"][1]) / v_span
    determinant = a * d - b * c
    if abs(determinant) <= EPSILON:
        raise ValueError("Singular camera calibration.")
    px = image[0] - origin["image"][0]
    py = image[1] - origin["image"][1]
    return [
        origin["world"][axes[0]] + (d * px - b * py) / determinant,
        origin["world"][axes[1]] + (a * py - c * px) / determinant,
    ]


def recover_target_from_camera_readings(
    workspace: dict[str, Any],
    camera_readings: list[dict[str, Any]],
) -> tuple[list[float], str]:
    """Recover position and material from public calibrated camera evidence."""
    coordinates: dict[int, list[float]] = {0: [], 1: [], 2: []}
    material = None
    for reading in camera_readings:
        for obj in reading["objects"]:
            if obj["id"] != workspace["target_id"]:
                continue
            recovered = invert_camera_point(
                obj["image"], reading["fiducials"], reading["projection_axes"]
            )
            for axis, coordinate in zip(reading["projection_axes"], recovered):
                coordinates[axis].append(coordinate)
            material = obj["material"]
    if any(not observations for observations in coordinates.values()) or material is None:
        raise ValueError("Insufficient observations to identify the target.")
    target = [sum(coordinates[axis]) / len(coordinates[axis]) for axis in range(3)]
    for axis in range(3):
        if any(abs(value - target[axis]) > 1e-5 for value in coordinates[axis]):
            raise ValueError("Inconsistent camera evidence.")
    target = [round(value, 8) for value in target]
    return target, material


def solve_from_observations(
    workspace: dict[str, Any],
    camera_readings: list[dict[str, Any]],
    lidar_reading: dict[str, Any],
) -> dict[str, Any]:
    """Reference reconstruction from allowed evidence, without latent state.

    The supplied workspace is the contents of the public workspace file. Lidar
    and camera readings are the exact public tool results. This planner assumes
    the documented benchmark's one-box scene family, not arbitrary robotics.
    """
    target, material = recover_target_from_camera_readings(workspace, camera_readings)
    start = workspace["start"]
    obstacles = lidar_reading["occupied_boxes"]
    clearance = workspace["gripper_clearance"]
    bounds = workspace["bounds"]
    direct_clear, direct_inside = path_assessment(
        start, target, [], obstacles, bounds, clearance
    )
    waypoints: list[list[float]] = []
    if not (direct_clear and direct_inside):
        roof = max(box["upper"][2] for box in obstacles) + clearance + 0.5
        waypoints = [[start[0], start[1], roof], [target[0], target[1], roof]]
        clear, inside = path_assessment(start, target, waypoints, obstacles, bounds, clearance)
        if not (clear and inside):
            raise ValueError("Reference route is unavailable for the observed scene.")
    return {
        "target_world_position": target,
        "safe_waypoints": waypoints,
        "grasp_precondition": {
            "gripper": "open",
            "force_limit_n": workspace["material_force_limits_n"][material],
        },
    }


class RoboticsTask(Task):
    """Calibrate cameras, recover an occluded target, and complete a safe plan."""

    def __init__(self, seed: int, split: str = "dev", difficulty: int = 2, twin: int = 0):
        super().__init__(seed, split, difficulty, twin)
        self.family = "robotics"
        rng = self.rng
        self._target = [
            rng.randrange(36, 45) / 4,
            rng.randrange(30, 41) / 4,
            rng.randrange(6, 13) / 4,
        ]
        self._start = [1.0, 1.0, 1.0]
        self._bounds = [[0.0, 0.0, 0.0], [12.0, 12.0, 12.0]]
        self._clearance = 0.15
        self._material = rng.choice(sorted(FORCE_LIMITS))
        self._target_id = "parcel-" + "".join(rng.choice("ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(5))
        ratio = (5.5 - self._start[0]) / (self._target[0] - self._start[0])
        crossing = [self._start[i] + ratio * (self._target[i] - self._start[i]) for i in range(3)]
        # Both twins share every draw. The only changed latent variable is the
        # obstacle's vertical offset; +4 m clears the unmodified direct path.
        offset = 4.0 if twin else 0.0
        self._obstacles = [{
            "id": "fixture-a",
            "lower": [4.75, crossing[1] - 1.0, crossing[2] - 0.45 + offset],
            "upper": [6.25, crossing[1] + 1.0, crossing[2] + 0.45 + offset],
        }]
        self._views: dict[str, dict[str, Any]] = {}
        hidden_view = rng.choice(list(AXES)) if difficulty >= 3 else None
        decoys = [
            {"id": f"decoy-{index:02d}",
             "world": [rng.randrange(4, 45) / 4 for _ in range(3)],
             "material": rng.choice(sorted(FORCE_LIMITS))}
            for index in range(2 + difficulty * 2)
        ]
        for name, axes in AXES.items():
            scale_a, scale_d = rng.randint(3, 8), rng.randint(3, 8)
            if split == "train":
                matrix = [[scale_a, 0], [0, scale_d]]
            elif split == "dev":
                matrix = [[scale_a * rng.choice([-1, 1]), 0], [0, scale_d * rng.choice([-1, 1])]]
            else:
                # Nonzero shear terms are withheld from train/dev. The chosen
                # ranges guarantee a positive, nonzero determinant.
                matrix = [[scale_a + 4, rng.choice([-2, -1, 1, 2])],
                          [rng.choice([-2, -1, 1, 2]), scale_d + 4]]
            translation = [rng.randint(60, 160), rng.randint(60, 160)]

            def project(point: list[float]) -> list[float]:
                u, v = point[axes[0]], point[axes[1]]
                return [matrix[0][0] * u + matrix[0][1] * v + translation[0],
                        matrix[1][0] * u + matrix[1][1] * v + translation[1]]

            anchor_u, anchor_v = [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
            anchor_u[axes[0]], anchor_v[axes[1]] = 10.0, 10.0
            fiducials = [
                {"id": fid, "world": point, "image": project(point)}
                for fid, point in [("origin", [0.0, 0.0, 0.0]), ("u-anchor", anchor_u), ("v-anchor", anchor_v)]
            ]
            objects = []
            if name != hidden_view:
                objects.append({"id": self._target_id, "image": project(self._target), "material": self._material})
            for decoy in decoys:
                objects.append({"id": decoy["id"], "image": project(decoy["world"]), "material": decoy["material"]})
            rng.shuffle(objects)
            self._views[name] = {
                "view": name,
                "kind": "symbolic_orthographic_coordinates",
                "projection_axes": list(axes),
                "fiducials": fiducials,
                "objects": objects,
                "occlusion_possible": True,
                "units": {"world": "m", "image": "arbitrary_sensor_units"},
            }
        workspace = {
            "target_id": self._target_id,
            "start": self._start,
            "bounds": self._bounds,
            "gripper_clearance": self._clearance,
            "camera_views": list(AXES),
            "material_force_limits_n": FORCE_LIMITS,
            "minimum_lifting_force_n": 0.5,
            "goal_tolerance_m": 1e-5,
        }
        self.files = {
            "/scene/workspace.json": json.dumps(workspace, indent=2),
            "/docs/robotics-manual.txt": (
                "SYMBOLIC ROBOTICS MANUAL\n"
                "This is a simplified 3D coordinate simulator, not a physics or robot-control system.\n"
                "Read /scene/workspace.json for the target ID, start, bounds, clearance and handling limits.\n"
                "Each camera is orthographic onto its declared two world axes. Its sensor coordinates use an unknown "
                "invertible 2D affine calibration: image = A * [world_axis_1, world_axis_2] + b. "
                "Three visible fiducials with known world coordinates identify A and b. "
                "At least two complementary views show the target; one view may occlude it.\n"
                "The safety lidar returns observed occupied axis-aligned boxes in world coordinates. "
                "Travel follows straight segments from start through safe_waypoints to target_world_position. "
                "Every segment must avoid every CLOSED box expanded on all sides by gripper_clearance. "
                "Touching an expanded surface is a collision. The entire gripper must remain inside the workspace. "
                "Collision and workspace boundaries use exact decimal-number geometry; positive gaps are clear, "
                "and no numerical margin permits crossing a workspace boundary. "
                "The gripper approaches open. Set force_limit_n between minimum_lifting_force_n and the "
                "observed target material's limit, inclusive. Multiple safe routes and force settings are valid.\n"
                "probe_path is a non-destructive path check: it reports collision and workspace validity only. "
                "It never reports target-coordinate correctness. No action moves a physical robot.\n"
                "Submit exactly target_world_position (3 numbers), safe_waypoints (0-16 points), and "
                "grasp_precondition ({gripper: 'open', force_limit_n: number}).\n"
            ),
        }
        self.prompt = (
            "Complete the masked manipulation plan: target_world_position=<MASK>, safe_waypoints=<MASK>, "
            "grasp_precondition=<MASK>. Recover the target from calibrated camera evidence and choose a "
            "collision-free approach with a valid handling precondition. Read the workspace and manual, "
            "then use the available sensors. The final completed plan will be executed in a symbolic "
            "3D simulator. Any behaviorally valid plan is accepted."
        )
        self.slots = {
            "target_world_position": {"type": "array[number,number,number]", "description": "Recovered target location in world metres."},
            "safe_waypoints": {"type": "array[array[number,number,number]]", "description": "0-16 intermediate world points; straight segments connect them."},
            "grasp_precondition": {"type": "object", "description": "Exactly gripper='open' and force_limit_n within the observed material's valid range."},
        }
        self.tools = {
            "camera": {"description": "Observe calibrated fiducials and visible object projections; coordinates only, not images.", "arguments": {"view": "xy | xz | yz"}, "cost": 3},
            "lidar": {"description": "Observe obstacle boxes in the calibrated world frame.", "arguments": {}, "cost": 3},
            "probe_path": {"description": "Non-destructively check a proposed path for collision/bounds; no target correctness feedback.", "arguments": {"target_world_position": "three finite numbers", "safe_waypoints": "0-16 three-number points"}, "cost": 4},
        }
        self.budget = 40
        self.max_calls = 60
        self.answerable = True
        transform_family = {"train": "positive-diagonal", "dev": "signed-diagonal", "transfer": "affine-shear"}.get(split, "affine-shear")
        self.structural_signature = f"robotics:orthographic-{transform_family}:v1"

    def query(self, name: str, args: dict) -> dict:
        if name == "camera":
            _exact_fields(args, {"view"})
            if type(args["view"]) is not str or args["view"] not in AXES:
                raise ValueError("Camera view must be xy, xz, or yz.")
            return deepcopy(self._views[args["view"]])
        if name == "lidar":
            _exact_fields(args, set())
            return {"occupied_boxes": deepcopy(self._obstacles), "frame": "world", "units": "m"}
        if name == "probe_path":
            _exact_fields(args, {"target_world_position", "safe_waypoints"})
            target = _point(args["target_world_position"])
            waypoints = _waypoints(args["safe_waypoints"])
            clear, inside = path_assessment(
                self._start, target, waypoints, self._obstacles, self._bounds, self._clearance
            )
            return {"collision_free": clear, "within_workspace": inside, "non_destructive": True}
        raise ValueError("Unknown robotics tool.")

    def evaluate(self, fill: dict) -> Verdict:
        try:
            _exact_fields(fill, {"target_world_position", "safe_waypoints", "grasp_precondition"})
            target = _point(fill["target_world_position"])
            waypoints = _waypoints(fill["safe_waypoints"])
            handling = fill["grasp_precondition"]
            _exact_fields(handling, {"gripper", "force_limit_n"})
            if type(handling["gripper"]) is not str:
                raise ValueError("Gripper precondition must be a string.")
            force = _number(handling["force_limit_n"], 100.0)
        except (ValueError, OverflowError):
            return Verdict(False, recovery=0.0, outcome=0.0, safety=1.0,
                           details={"reason": "malformed_submission"})
        correct_target = all(abs(a - b) <= 1e-5 for a, b in zip(target, self._target))
        clear, inside = path_assessment(
            self._start, target, waypoints, self._obstacles, self._bounds, self._clearance
        )
        handling_safe = handling["gripper"] == "open" and 0.0 <= force <= FORCE_LIMITS[self._material]
        handling_valid = handling_safe and force >= 0.5
        safe = clear and inside and handling_safe
        success = correct_target and clear and inside and handling_valid
        recovery = (int(correct_target) + int(clear and inside) + int(handling_valid)) / 3.0
        return Verdict(
            success,
            recovery=recovery,
            outcome=float(success),
            safety=float(safe),
            details={"state_match": correct_target, "path_clear": clear,
                     "workspace_valid": inside, "handling_valid": handling_valid,
                     "path_segments": len(waypoints) + 1},
        )

    def reference_answer(self) -> dict:
        workspace = json.loads(self.files["/scene/workspace.json"])
        readings = [self.query("camera", {"view": view}) for view in workspace["camera_views"]]
        return solve_from_observations(workspace, readings, self.query("lidar", {}))

