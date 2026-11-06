"""Scripted controllers restricted to public JSON and tool responses.

These are engineered baselines, not measured general model performance. No task
object, hidden camera, generator seed, or evaluator outcome is read by a policy.
"""
from __future__ import annotations

import json

from .vision import detect_components, pixel_to_world, recover_calibration

POLICY_MODES = ("adaptive", "fixed", "fixed_minimal", "blind", "query_free", "robust", "conditioning", "conditioning_grip")


def recover_open_route(spec, image):
    """Recover world-relative opening pose from pixels, then classify a lane.

    A failure to find unique landmarks/opening, or a pose outside the public
    geometric margin, is insufficient evidence and raises ValueError. The
    one-unit allowance is an explicitly tested renderer-family assumption, not
    a distribution-free confidence interval.
    """
    tolerance = spec["perception"]["rgb_noise_bound"]
    matrix = recover_calibration(image, spec["landmarks"], tolerance=tolerance)
    components = detect_components(image, spec["palette"]["opening"],
                                   tolerance=tolerance, min_pixels=8)
    if len(components) != 1:
        raise ValueError("opening is not uniquely visible")
    point = pixel_to_world(matrix, components[0]["center"])
    allowance = spec["perception"]["center_error_allowance_world"]
    opening = spec["opening"]
    if abs(point[0]-opening["center_x"]) > allowance:
        raise ValueError("recovered opening is outside its calibrated support")
    candidates = [name for name, lane in spec["lanes"].items()
                  if abs(point[1]-lane["center_y"]) <= allowance]
    if len(candidates) != 1:
        raise ValueError("lane evidence is ambiguous")
    return candidates[0], {"estimated_center_world": point,
                           "center_allowance_world": allowance,
                           "source": "public PNG and three visible fiducials"}


def solve_robotics_vision(public, call, mode="adaptive"):
    """Return a completion after acting through the supplied public callback.

    adaptive: skip sensing when the robust detour fits the known resources;
              otherwise image-calibrate, gently probe, and use interval-safe mode.
    fixed: overview image, inspection move/image, gentle probe, then execute.
    fixed_minimal: inspection move/image, gentle probe, then execute.
    conditioning: image-calibrate, firmly condition the surface, and use grip
                  without consulting the returned friction measurement.
    conditioning_grip: firmly condition and always grip; accepts possible stall
                       on resistant dry surfaces instead of choosing slow.
    blind/query_free: upper rolling route with no sensor calls.
    robust: unconditional slow detour, which intentionally misses strict deadlines.
    """
    if mode not in POLICY_MODES:
        raise ValueError("unknown robotics policy mode")
    def use(name, args):
        response = call(name, args)
        if "error" in response:
            raise ValueError(response["error"])
        return response

    spec = json.loads(use("read_file", {"path": "/scene/robotics_vision.json"})["content"])
    def execute(route, contact_mode):
        result = use("robot_execute", {"route": route, "mode": contact_mode})
        return {"delivered": bool(result["outcome"]["completed"])}

    if mode in ("blind", "query_free"):
        return execute("upper", "roll")
    detour = spec["actions"]["detour_slow"]
    robust_fits = detour["time"] <= spec["deadline"] and detour["energy"] <= spec["energy_cap"]
    if mode == "robust" or (mode == "adaptive" and robust_fits):
        return execute("detour", "slow")
    if mode == "fixed":
        use("robot_capture", {})
    use("robot_move_camera", {"view": "inspection"})
    image = use("robot_capture", {})["image"]
    try:
        route, _support = recover_open_route(spec, image)
    except (ValueError, KeyError, TypeError):
        # A corrupted/occluded image never licenses a confident primary route.
        # This fallback remains a measured failure if the detour misses deadline.
        return execute("detour", "slow")
    if mode in ("conditioning", "conditioning_grip"):
        use("robot_probe", {"force": "firm"})
        if mode == "conditioning_grip":
            return execute(route, "grip")
        # Prove sufficiency from the public action law, not the returned reading.
        contact = spec["contact"]
        conditioned_max = max(contact["minimum_friction"],
                              max(contact["initial_friction_support"])
                              - contact["wear_decrement"]*spec["actions"]["probe_firm"]["wear"])
        safe_mode = "grip" if conditioned_max <= contact["grip_maximum_friction"] else "slow"
        return execute(route, safe_mode)
    measurement = use("robot_probe", {"force": "gentle"})
    low, high = measurement["friction_interval"]
    contact = spec["contact"]
    if low >= contact["roll_minimum_friction"]:
        contact_mode = "roll"
    elif high <= contact["grip_maximum_friction"]:
        contact_mode = "grip"
    else:
        contact_mode = "slow"
    return execute(route, contact_mode)
