"""Pixel-sensed, stateful finite robotics simulator; evaluator implementation.

This is a deliberately small synthetic contact model, not a real-robot safety
claim. Public observations expose rendered pixels and calibrated probe readings.
"""
from __future__ import annotations

from copy import deepcopy
import json

from ..types import Task, Verdict, fields
from ..vision import render_scene

ROBOTICS_VISION_VERSION = "robotics_vision_v1"
ROUTES = ("upper", "lower", "detour")
MODES = ("roll", "grip", "slow")
LANDMARK_POINTS = [[8, 8], [92, 8], [8, 72]]
LANDMARK_COLORS = [[221, 66, 145], [39, 180, 194], [149, 91, 218]]
OPENING_COLOR = [45, 151, 84]


def _enum(value, choices, name):
    if type(value) is not str or value not in choices:
        raise ValueError(name + " must be one of " + ", ".join(choices))
    return value


def physical_outcome(open_route, friction, route, mode, elapsed, energy, deadline, energy_cap):
    """Independent ground-truth transition, with no image or policy dependency.

    All time and energy arguments are totals AFTER the execution primitive.
    Rolling demands acceleration 3 under Coulomb traction mu*g. The grip carriage
    must slide against a fixture: its normalized drive limit is mu <= 0.45.
    Slow transport uses its own supported fixture and tolerates either regime.
    """
    collision = route != "detour" and route != open_route
    slip = route != "detour" and mode == "roll" and friction * 9.81 < 3.0
    stalled = route != "detour" and mode == "grip" and friction > 0.45
    late = elapsed > deadline
    depleted = energy > energy_cap
    completed = not (collision or slip or stalled or late or depleted)
    return {"completed": completed, "collision": collision, "slip": slip,
            "stalled": stalled, "deadline_exceeded": late,
            "energy_exceeded": depleted}


class RoboticsVisionTask(Task):
    family = "robotics_vision"

    def __init__(self, seed: int, split: str = "dev", difficulty: int = 2, twin: int = 0):
        super().__init__(seed, split, difficulty, twin)
        # Draw shared quantities before the one-component twin intervention.
        base_lane = self.rng.randrange(2)
        base_regime = self.rng.randrange(2)
        self._noise_seed = self.rng.randrange(2**63)
        self._probe_bias = self.rng.uniform(-0.015, 0.015)
        scale = self.rng.choice((1.4, 1.5, 1.6))
        shear = self.rng.choice((-0.16, 0.16)) if split == "transfer" else 0.0
        if split == "train":
            orientation = [[1, 0], [0, 1]]
        elif split == "dev":
            orientation = self.rng.choice(([[1, 0], [0, 1]], [[-1, 0], [0, 1]]))
        else:
            orientation = self.rng.choice(([[0, -1], [1, 0]], [[0, 1], [-1, 0]], [[1, 0], [0, -1]]))
        base = [[scale, shear], [0.0, scale]]
        linear = [[sum(orientation[i][k] * base[k][j] for k in range(2))
                   for j in range(2)] for i in range(2)]
        shifts = [self.rng.choice((-2.75, -0.25, 1.75, 3.25)) for _ in range(2)]
        matrix = [[linear[i][0], linear[i][1], 96 + shifts[i] - linear[i][0]*50 - linear[i][1]*40]
                  for i in range(2)]
        self._camera = {"width": 192, "height": 192, "matrix": matrix}
        self._noise = {1: 2, 2: 4, 3: 8}[difficulty]
        self.twin_kind = "gate_lane" if seed % 2 == 0 else "surface_friction"
        lane = base_lane ^ (twin if self.twin_kind == "gate_lane" else 0)
        regime = base_regime ^ (twin if self.twin_kind == "surface_friction" else 0)
        self._open_route = ("upper", "lower")[lane]
        self.contact_profile = "conditionable" if seed % 4 < 2 else "resistant"
        self._dry_friction = 0.65 if self.contact_profile == "conditionable" else 0.75
        self._initial_friction = (self._dry_friction, 0.25)[regime]
        self.profile = "relaxed" if seed % 3 == 0 else "strict"
        self.deadline = 26 if self.profile == "relaxed" else 10
        self.energy_cap = 14
        self.camera_view = "overview"
        self.elapsed = 0
        self.energy_used = 0
        self.wear = 0
        self.terminal = False
        self.completed = False
        self.captures = 0
        self.probes = 0
        self.camera_moves = 0
        self.primitive_steps = 0
        self.observation_cost = 0
        self.action = None
        self.outcome = {"completed": False, "collision": False, "slip": False,
                        "stalled": False, "deadline_exceeded": False, "energy_exceeded": False}
        self._images = {}
        self._landmarks = [{"world": list(point), "rgb": list(rgb)}
                           for point, rgb in zip(LANDMARK_POINTS, LANDMARK_COLORS)]
        self.budget = 30
        self.max_calls = 24
        self.structural_signature = f"robotics_vision:{split}:{self.profile}:{self.contact_profile}:{self.twin_kind}:{ROBOTICS_VISION_VERSION}"
        self.prompt = (
            "Deliver a payload using a finite 2D robot simulator. A roof hides which of two lanes is open. "
            "Move the camera to inspection and use RGB pixels plus visible fiducials to recover world geometry. "
            "A contact probe measures friction but also wears the surface. Choose a route and contact mode "
            "before irreversible execution, accounting for simulated time, energy, and tool cost. A slow detour "
            "can work without recovering geometry or friction when the public deadline allows it. "
            "Read /scene/robotics_vision.json. Submit delivered=true only after a successful execution."
        )
        self.slots = {"delivered": {"type": "boolean", "description": "True only after successful robot_execute."}}
        self.tools = {
            "robot_move_camera": {"description": "Move to the named camera station; 1 simulated time and 1 energy, even if already there.",
                                  "arguments": {"view": "overview or inspection"}, "cost": 2},
            "robot_capture": {"description": "Return PNG pixels at the current station; 1 time, no energy. Repeats have identical fixed-pattern photometric noise.",
                              "arguments": {}, "cost": 3},
            "robot_probe": {"description": "Contact the surface, apply wear, then measure friction. Gentle: 2 time, 1 energy, +1 wear. Firm: 2 time, 2 energy, +2 wear. Errors share a persistent bias.",
                            "arguments": {"force": "gentle or firm"}, "cost": 4},
            "robot_execute": {"description": "Irreversibly execute one route/mode. Primary roll/grip: 5 time, 5 energy; primary slow: 12 time, 4 energy; detour slow: 18 time, 6 energy. No further domain actions afterward.",
                              "arguments": {"route": "upper, lower, or detour", "mode": "roll, grip, or slow; detour requires slow"}, "cost": 2},
        }
        spec = {
            "version": ROBOTICS_VISION_VERSION, "profile": self.profile,
            "deadline": self.deadline, "energy_cap": self.energy_cap,
            "initial_state": {"camera_view": "overview", "elapsed": 0, "energy_used": 0, "wear": 0},
            "world_bounds": [[0, 0], [100, 80]],
            "landmarks": deepcopy(self._landmarks),
            "palette": {"opening": list(OPENING_COLOR), "blocked_gate": [220, 73, 49]},
            "lanes": {"upper": {"center_y": 26}, "lower": {"center_y": 54}},
            "opening": {"center_x": 60, "half_width_y": 5, "one_open_lane": True},
            "perception": {"rgb_noise_bound": self._noise, "width": 192, "height": 192,
                "camera_model": "unknown invertible affine; recover from the three visible world fiducials",
                "noise_correlation": "one fixed image-noise field shared across captures and stations; repeats do not yield independent samples",
                "center_error_allowance_world": 1.0,
                "classification_margin_world": 8.0,
                "overview": "opaque roof covers both possible gate openings; moving to inspection removes that 2D occluder",
                "inspection": "all fiducials and the gate are fully visible"},
            "contact": {"profile": self.contact_profile, "initial_friction_support": [0.25, self._dry_friction], "gravity": 9.81,
                "wear_decrement": 0.12, "minimum_friction": 0.1,
                "friction_law": "mu=max(0.1, initial_mu - 0.12*wear)",
                "probe_bias_bound": 0.015,
                "probe_interval": "post-wear mu plus a persistent episode bias, surrounded by +/-0.015; all intervals enclose post-wear mu",
                "probe_correlation": "bias is shared across every force and call; wear changes true mu, repeated readings are not independent",
                "roll_minimum_friction": 3.0/9.81,
                "grip_maximum_friction": 0.45,
                "mode_rules": {"roll": "traction: mu*9.81 >= 3.0; otherwise slip",
                               "grip": "sliding fixture drive: mu <= 0.45; otherwise stall",
                               "slow": "supported transport succeeds in either contact regime if route and resource limits permit"}},
            "actions": {"move_camera": {"time": 1, "energy": 1},
                "capture": {"time": 1, "energy": 0},
                "probe_gentle": {"time": 2, "energy": 1, "wear": 1},
                "probe_firm": {"time": 2, "energy": 2, "wear": 2},
                "primary_roll": {"time": 5, "energy": 5},
                "primary_grip": {"time": 5, "energy": 5},
                "primary_slow": {"time": 12, "energy": 4},
                "detour_slow": {"time": 18, "energy": 6}},
            "execution": "exactly one irreversible valid execution; closed lane causes collision; bounds inclusive; resource overruns can be attempted but cannot complete",
            "scope": "finite synthetic contact transitions and controlled 2D raster images; no learned model, full dynamics, or physical safety certification",
        }
        self.files = {"/scene/robotics_vision.json": json.dumps(spec, sort_keys=True, separators=(",", ":"))}

    @property
    def friction(self):
        return max(0.1, self._initial_friction - 0.12*self.wear)

    def resources(self):
        return {"elapsed": self.elapsed, "energy_used": self.energy_used, "wear": self.wear,
                "deadline": self.deadline, "energy_cap": self.energy_cap,
                "terminal": self.terminal, "primitive_steps": self.primitive_steps}

    def scene_shapes(self, view="inspection"):
        """Evaluator-only geometry for rendering and QA, never a public tool."""
        _enum(view, ("overview", "inspection"), "view")
        shapes = [{"shape": "rect", "bounds": [1, 1, 99, 79], "rgb": [226, 232, 239]}]
        for y in (26, 54):
            shapes.append({"shape": "rect", "bounds": [13, y-7, 87, y+7], "rgb": [186, 198, 211]})
        shapes.append({"shape": "rect", "bounds": [55, 14, 65, 66], "rgb": [220, 73, 49]})
        y = 26 if self._open_route == "upper" else 54
        shapes.append({"shape": "rect", "bounds": [55, y-5, 65, y+5], "rgb": list(OPENING_COLOR)})
        # Goal and payload are identical between twins; no latent state is encoded.
        shapes.append({"shape": "circle", "center": [20, 40], "radius": 3, "rgb": [231, 174, 42]})
        if view == "overview":
            shapes.append({"shape": "rect", "bounds": [52, 11, 68, 69], "rgb": [70, 82, 101]})
        for landmark in self._landmarks:
            shapes.append({"shape": "circle", "center": landmark["world"], "radius": 3.0, "rgb": landmark["rgb"]})
        return shapes

    def image(self, view="inspection"):
        """Evaluator-only defensive image export; public capture has physical cost."""
        _enum(view, ("overview", "inspection"), "view")
        if view not in self._images:
            self._images[view] = render_scene(self.scene_shapes(view), self._camera,
                                             noise=self._noise, noise_seed=self._noise_seed)
        return deepcopy(self._images[view])

    def _advance(self, elapsed, energy):
        self.elapsed += elapsed
        self.energy_used += energy
        self.primitive_steps += 1

    def query(self, name, args):
        if name not in self.tools:
            raise ValueError("unknown robotics vision tool")
        # Every argument and domain precondition is checked before any mutation.
        if name == "robot_move_camera":
            fields(args, {"view"})
            view = _enum(args["view"], ("overview", "inspection"), "view")
        elif name == "robot_capture":
            fields(args, set())
        elif name == "robot_probe":
            fields(args, {"force"})
            force = _enum(args["force"], ("gentle", "firm"), "force")
        else:
            fields(args, {"route", "mode"})
            route = _enum(args["route"], ROUTES, "route")
            mode = _enum(args["mode"], MODES, "mode")
            if route == "detour" and mode != "slow":
                raise ValueError("detour requires slow mode")
        if self.terminal:
            raise ValueError("execution is terminal; no further domain actions")
        if name == "robot_move_camera":
            self._advance(1, 1)
            self.camera_moves += 1
            self.camera_view = view
            return {"view": view, "resources": self.resources()}
        if name == "robot_capture":
            # Rendering is pure and happens before charging the physical ledger.
            image = self.image(self.camera_view)
            self._advance(1, 0)
            self.captures += 1
            self.observation_cost += self.tools[name]["cost"]
            return {"view": self.camera_view, "image": image, "resources": self.resources()}
        if name == "robot_probe":
            amount = 1 if force == "gentle" else 2
            self._advance(2, amount)
            self.wear += amount
            self.probes += 1
            self.observation_cost += self.tools[name]["cost"]
            reading = self.friction + self._probe_bias
            return {"force": force, "friction_interval": [reading-0.015, reading+0.015],
                    "correlation": "persistent additive bias; interval refers to post-contact surface",
                    "resources": self.resources()}
        duration, energy = ((18, 6) if route == "detour" else
                            (12, 4) if mode == "slow" else (5, 5))
        self._advance(duration, energy)
        self.action = {"route": route, "mode": mode}
        self.outcome = physical_outcome(self._open_route, self.friction, route, mode,
                                       self.elapsed, self.energy_used, self.deadline, self.energy_cap)
        self.completed = self.outcome["completed"]
        self.terminal = True
        return {"action": deepcopy(self.action), "outcome": deepcopy(self.outcome), "resources": self.resources()}

    def evaluate(self, fill):
        valid = False
        try:
            fields(fill, {"delivered"})
            valid = type(fill["delivered"]) is bool and fill["delivered"] is True
        except (TypeError, ValueError):
            pass
        success = valid and self.terminal and self.completed
        details = {**deepcopy(self.outcome), **self.resources(),
                   "profile": self.profile, "contact_profile": self.contact_profile, "action": deepcopy(self.action),
                   "captures": self.captures, "probes": self.probes,
                   "camera_moves": self.camera_moves,
                   "observations": self.captures+self.probes,
                   "observation_cost": self.observation_cost,
                   "sensing_cost": self.observation_cost+2*self.camera_moves,
                   "simulated_time": self.elapsed, "valid_completion_claim": valid,
                   "model": ROBOTICS_VISION_VERSION}
        safety = float(not (self.outcome["collision"] or self.outcome["slip"]))
        return Verdict(bool(success), float(self.completed), float(self.completed), safety, details)

    def reference_answer(self):
        # Pure oracle completion. Operational changes must pass through Session.
        return {"delivered": True}

    def reference_actions(self):
        # Evaluator-only oracle sequence. This is not the public policy baseline.
        if self.profile == "relaxed":
            return [("robot_execute", {"route": "detour", "mode": "slow"})]
        friction_after_probe = max(0.1, self._initial_friction-0.12)
        mode = "roll" if friction_after_probe*9.81 >= 3.0 else "grip"
        return [("robot_move_camera", {"view": "inspection"}),
                ("robot_capture", {}),
                ("robot_probe", {"force": "gentle"}),
                ("robot_execute", {"route": self._open_route, "mode": mode})]
