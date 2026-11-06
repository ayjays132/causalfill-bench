"""Exact, finite decision sufficiency with set-valued noisy observations.

An experiment can emit any member of its declared support in a fixed world.
Supports may overlap. A controller must succeed for every compatible world and
every allowed observation; repeated sampling is not assumed independent. Each
listed experiment is available at most once. Successful terminal actions need
not identify the world. Costs are nonnegative integers (experiments positive).

This is a bounded Python certificate, not a new planning algorithm, statistical
coverage guarantee, physical safety proof, or refinement proof for a renderer.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache

MAX_WORLDS = 24
MAX_EXPERIMENTS = 10
MAX_ACTIONS = 64
MAX_STATES = 100_000
MAX_REPLAY_STEPS = 1_000_000
SCHEMA = "causalfill.noisy-decision.v1"
CERTIFICATE_SCHEMA = "causalfill.decision-sufficiency-certificate.v1"


def _integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{label} must be an integer in [{low}, {high}]")
    return value


def _name(value):
    if type(value) is not str or not 1 <= len(value) <= 64:
        raise ValueError("identifiers must be strings of length 1..64")
    return value


def _keys(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError("invalid fields")


def validate_problem(problem):
    """Return a fresh canonical model; reject Python bool/integer aliases."""
    _keys(problem, {"schema", "worlds", "actions", "experiments"})
    if problem["schema"] != SCHEMA:
        raise ValueError("unsupported problem schema")
    worlds = problem["worlds"]
    if type(worlds) is not list or not 1 <= len(worlds) <= MAX_WORLDS:
        raise ValueError("world count outside supported bounds")
    worlds = [_name(w) for w in worlds]
    if len(set(worlds)) != len(worlds):
        raise ValueError("duplicate worlds")
    actions = problem["actions"]
    if type(actions) is not list or not 1 <= len(actions) <= MAX_ACTIONS:
        raise ValueError("action count outside supported bounds")
    clean_actions = []
    for a in actions:
        _keys(a, {"id", "cost", "success_worlds"})
        success = a["success_worlds"]
        if type(success) is not list or any(type(w) is not str or w not in worlds for w in success):
            raise ValueError("unknown successful world")
        if len(set(success)) != len(success):
            raise ValueError("duplicate successful worlds")
        clean_actions.append({"id": _name(a["id"]), "cost": _integer(a["cost"], 0, 10**6, "action cost"),
                              "success_worlds": sorted(success)})
    experiments = problem["experiments"]
    if type(experiments) is not list or len(experiments) > MAX_EXPERIMENTS:
        raise ValueError("experiment count outside supported bounds")
    clean_experiments = []
    for q in experiments:
        _keys(q, {"id", "cost", "supports"})
        supports = q["supports"]
        if type(supports) is not dict or set(supports) != set(worlds):
            raise ValueError("every experiment needs a support for every world")
        clean = {}
        for w in worlds:
            values = supports[w]
            if type(values) is not list or not 1 <= len(values) <= 16:
                raise ValueError("observation support size must be 1..16")
            values = [_name(o) for o in values]
            if len(set(values)) != len(values):
                raise ValueError("duplicate support observation")
            clean[w] = sorted(values)
        if len(set(o for row in clean.values() for o in row)) > 64:
            raise ValueError("observation alphabet too large")
        clean_experiments.append({"id": _name(q["id"]),
                                  "cost": _integer(q["cost"], 1, 10**6, "experiment cost"),
                                  "supports": clean})
    for group in (clean_actions, clean_experiments):
        if len({x["id"] for x in group}) != len(group):
            raise ValueError("duplicate action or experiment identifiers")
    return {"schema": SCHEMA, "worlds": list(worlds), "actions": clean_actions,
            "experiments": clean_experiments}


def problem_digest(problem):
    data = json.dumps(validate_problem(problem), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(data.encode()).hexdigest()


def _objective(value):
    if value not in ("action", "identification"):
        raise ValueError("objective must be action or identification")
    return value


def build_certificate(problem, objective="action"):
    """Untrusted optimizer: export all needed alternative-query subproblems."""
    model = validate_problem(problem)
    _objective(objective)
    worlds, experiments = model["worlds"], model["experiments"]
    actions = [(a["id"], a["cost"], sum(1 << worlds.index(w) for w in a["success_worlds"]))
               for a in model["actions"]]
    supports = []
    for q in experiments:
        alphabet = sorted({o for row in q["supports"].values() for o in row})
        supports.append([(o, sum(1 << i for i, w in enumerate(worlds) if o in q["supports"][w]))
                         for o in alphabet])
    nodes = {}

    @lru_cache(maxsize=None)
    def solve(belief, remaining):
        if len(nodes) >= MAX_STATES:
            raise ValueError("certificate state cap exceeded; no optimum claimed")
        candidates = []
        if objective == "identification":
            if belief.bit_count() == 1:
                candidates.append((0, "identify", worlds[belief.bit_length() - 1]))
        else:
            candidates.extend((cost, "act", aid) for aid, cost, mask in actions if belief & mask == belief)
        # Zero is an immediate universal lower bound, so no positive query can
        # improve it. This is the only pruning rule.
        if not any(v == 0 for v, _, _ in candidates):
            for index, q in enumerate(experiments):
                if not remaining & (1 << index):
                    continue
                child_values = [solve(belief & mask, remaining ^ (1 << index))
                                for _, mask in supports[index] if belief & mask]
                if child_values and all(v is not None for v in child_values):
                    candidates.append((q["cost"] + max(child_values), "query", q["id"]))
        selected = min(candidates) if candidates else None
        value = None if selected is None else selected[0]
        choice = None if selected is None else {"kind": selected[1], "id": selected[2]}
        nodes[(belief, remaining)] = [belief, remaining, value, choice]
        return value

    root = [(1 << len(worlds)) - 1, (1 << len(experiments)) - 1]
    value = solve(*root)
    return {"schema": CERTIFICATE_SCHEMA, "problem_sha256": problem_digest(model),
            "objective": objective, "root": root, "value": value,
            "nodes": [nodes[key] for key in sorted(nodes, key=lambda x: (x[1].bit_count(), x[0], x[1]))]}


def verify_certificate(problem, certificate):
    """Check exact minima using a separate set-based implementation.

    Every legal query and possible support branch must have a checked child,
    even when it is not on the selected policy. Remaining queries strictly
    decrease, including when a noisy observation leaves the belief unchanged.
    """
    try:
        model = validate_problem(problem)
        _keys(certificate, {"schema", "problem_sha256", "objective", "root", "value", "nodes"})
        if certificate["schema"] != CERTIFICATE_SCHEMA or certificate["problem_sha256"] != problem_digest(model):
            raise ValueError("certificate schema or trusted problem digest mismatch")
        objective = _objective(certificate["objective"])
        nw, nq = len(model["worlds"]), len(model["experiments"])
        full, remaining = (1 << nw) - 1, (1 << nq) - 1
        if type(certificate["root"]) is not list or len(certificate["root"]) != 2:
            raise ValueError("invalid root")
        for value, expected in zip(certificate["root"], (full, remaining)):
            if type(value) is not int or value != expected:
                raise ValueError("incorrect root")
        rows = certificate["nodes"]
        if type(rows) is not list or not 1 <= len(rows) <= MAX_STATES:
            raise ValueError("invalid node count")
        max_cost = sum(q["cost"] for q in model["experiments"]) + max(a["cost"] for a in model["actions"])
        claims = {}
        for row in rows:
            if type(row) is not list or len(row) != 4:
                raise ValueError("each node must be [belief, remaining, value, choice]")
            b = _integer(row[0], 1, full, "belief")
            r = _integer(row[1], 0, remaining, "remaining")
            v, choice = row[2:]
            if v is not None:
                _integer(v, 0, max_cost, "value")
                _keys(choice, {"kind", "id"})
                _name(choice["id"])
                if choice["kind"] not in ("act", "identify", "query"):
                    raise ValueError("unknown selected choice")
            elif choice is not None:
                raise ValueError("impossible node cannot select a choice")
            if (b, r) in claims:
                raise ValueError("duplicate node")
            claims[(b, r)] = (v, choice)
        if certificate["value"] is not None:
            _integer(certificate["value"], 0, max_cost, "root value")
        checked = set()

        def check(b, r):
            if (b, r) in checked:
                return
            if (b, r) not in claims:
                raise ValueError("missing alternative-query child")
            current_worlds = {w for i, w in enumerate(model["worlds"]) if b & (1 << i)}
            candidates = []
            if objective == "identification":
                if len(current_worlds) == 1:
                    candidates.append((0, {"kind": "identify", "id": next(iter(current_worlds))}))
            else:
                for a in model["actions"]:
                    if current_worlds <= set(a["success_worlds"]):
                        candidates.append((a["cost"], {"kind": "act", "id": a["id"]}))
            if not any(v == 0 for v, _ in candidates):
                for qi, q in enumerate(model["experiments"]):
                    if not r & (1 << qi):
                        continue
                    observations = sorted({o for w in current_worlds for o in q["supports"][w]})
                    child_values = []
                    for observation in observations:
                        possible = {w for w in current_worlds if observation in q["supports"][w]}
                        child = sum(1 << i for i, w in enumerate(model["worlds"]) if w in possible)
                        child_remaining = r & ~(1 << qi)
                        check(child, child_remaining)
                        child_values.append(claims[(child, child_remaining)][0])
                    if child_values and all(v is not None for v in child_values):
                        candidates.append((q["cost"] + max(child_values), {"kind": "query", "id": q["id"]}))
            expected = min((v for v, _ in candidates), default=None)
            claimed, selected = claims[(b, r)]
            if claimed != expected or (expected is not None and (claimed, selected) not in candidates):
                raise ValueError("full minimax recurrence or attaining choice mismatch")
            checked.add((b, r))

        check(full, remaining)
        if checked != set(claims):
            raise ValueError("unreachable certificate nodes")
        if certificate["value"] != claims[(full, remaining)][0]:
            raise ValueError("root summary does not match checked claim")
        return {"valid": True, "objective": objective, "value": certificate["value"],
                "checked_states": len(checked), "guaranteed": certificate["value"] is not None,
                "assurance": "finite Python recurrence check; not a Lean proof or renderer refinement"}
    except (ValueError, TypeError, KeyError, IndexError, RecursionError) as exc:
        return {"valid": False, "error": str(exc)}


def replay_certificate(problem, certificate):
    """Separate fixed-world traversal of every supported selected-policy branch."""
    check = verify_certificate(problem, certificate)
    if not check["valid"] or certificate["value"] is None:
        return {"valid": False, "error": "no verified attaining policy"}
    model = validate_problem(problem)
    nodes = {(r[0], r[1]): (r[2], r[3]) for r in certificate["nodes"]}
    experiments = {q["id"]: (i, q) for i, q in enumerate(model["experiments"])}
    actions = {a["id"]: a for a in model["actions"]}
    leaves, costs, steps = 0, [], 0
    # Merge histories with the same fixed world, belief and remaining sensors.
    # Track exact path multiplicity plus minimum/maximum accumulated costs.
    # Equal-support labels otherwise create exponentially many redundant paths.
    for world in model["worlds"]:
        initial = tuple(certificate["root"])
        frontier = {initial: (0, 0, 1)}
        for rank in range(len(model["experiments"]), -1, -1):
            level = [key for key in frontier if key[1].bit_count() == rank]
            for mask, rem in level:
                steps += 1
                if steps > MAX_REPLAY_STEPS:
                    return {"valid": False, "error": "replay state cap exceeded; no full replay claim"}
                low_cost, high_cost, multiplicity = frontier.pop((mask, rem))
                choice = nodes[(mask, rem)][1]
                if choice["kind"] == "query":
                    qi, query = experiments[choice["id"]]
                    belief = {w for i, w in enumerate(model["worlds"]) if mask & (1 << i)}
                    for o in query["supports"][world]:
                        child = sum(1 << i for i, w in enumerate(model["worlds"])
                                    if w in belief and o in query["supports"][w])
                        key = (child, rem & ~(1 << qi))
                        new_low, new_high = low_cost + query["cost"], high_cost + query["cost"]
                        if key in frontier:
                            old_low, old_high, old_n = frontier[key]
                            frontier[key] = (min(old_low, new_low), max(old_high, new_high), old_n + multiplicity)
                        else:
                            frontier[key] = (new_low, new_high, multiplicity)
                else:
                    if choice["kind"] == "identify":
                        if choice["id"] != world:
                            return {"valid": False, "error": "wrong identified world"}
                    else:
                        action = actions[choice["id"]]
                        if world not in action["success_worlds"]:
                            return {"valid": False, "error": "terminal action fails"}
                        low_cost += action["cost"]
                        high_cost += action["cost"]
                    if high_cost > certificate["value"]:
                        return {"valid": False, "error": "policy exceeds bound"}
                    costs.extend((low_cost, high_cost))
                    leaves += multiplicity
        if frontier:
            return {"valid": False, "error": "unfinished policy frontier"}
    return {"valid": True, "worlds": len(model["worlds"]), "supported_policy_leaves": leaves,
            "replay_states": steps, "worst_cost": max(costs), "best_cost": min(costs)}



def demo_problem(profile="decision"):
    """Small, fully specified fixtures; no correspondence to real hardware."""
    if profile not in ("decision", "robust", "ambiguous", "noisy_resolvable", "adaptive", "action_ambiguity"):
        raise ValueError("unknown demonstration profile")
    if profile == "action_ambiguity":
        return {"schema": SCHEMA, "worlds": ["left_only", "shared", "right_only"],
                "actions": [
                    {"id": "left", "cost": 0, "success_worlds": ["left_only", "shared"]},
                    {"id": "right", "cost": 0, "success_worlds": ["shared", "right_only"]}],
                "experiments": [{"id": "camera", "cost": 1,
                    "supports": {"left_only": ["L"], "shared": ["L", "R"], "right_only": ["R"]}}]}
    worlds = ["left_dry", "left_wet", "right_dry", "right_wet"]
    model = {"schema": SCHEMA, "worlds": worlds,
             "actions": [{"id": "left_slow", "cost": 0, "success_worlds": worlds[:2]},
                         {"id": "right_slow", "cost": 0, "success_worlds": worlds[2:]}],
             "experiments": [{"id": "camera", "cost": 1,
                 "supports": {w: [w.split("_")[0]] for w in worlds}},
                 {"id": "surface", "cost": 3,
                  "supports": {w: [w.split("_")[1]] for w in worlds}}]}
    if profile == "robust":
        model["actions"].append({"id": "bypass", "cost": 0, "success_worlds": worlds})
    elif profile == "ambiguous":
        model["experiments"][0]["supports"] = {w: [w.split("_")[0], "blur"] for w in worlds}
    elif profile == "noisy_resolvable":
        model["experiments"][0]["supports"] = {w: [w.split("_")[0], "blur"] for w in worlds}
        model["experiments"].append({"id": "side_camera", "cost": 2,
            "supports": {w: [w.split("_")[0]+"_a", w.split("_")[0]+"_b"] for w in worlds}})
    elif profile == "adaptive":
        # Branch-specific sensors: a fixed one-sensor choice cannot resolve all
        # cases. Irrelevant latent surface information is no longer required.
        model["actions"] = [{"id": w, "cost": 0, "success_worlds": [w]} for w in worlds]
        model["experiments"][1] = {"id": "left_probe", "cost": 2,
            "supports": {w: [w if w.startswith("left") else "unused"] for w in worlds}}
        model["experiments"].append({"id": "right_probe", "cost": 2,
            "supports": {w: [w if w.startswith("right") else "unused"] for w in worlds}})
    return model
