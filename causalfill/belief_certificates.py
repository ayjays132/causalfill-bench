"""Independent checks for finite evolving-state planning certificates.

The bound checker uses tuple/set state collections and reconstructs *every*
legal alternative. It does not call the optimizer or its bit-set transition
code. A separate strategy checker replays the submitted public-observation
policy once from every possible initial state, without using the Bellman
recurrence. JSON/schema validation is shared and remains trusted Python code.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from .belief_games import (
    CERTIFICATE_SCHEMA, STRATEGY_SCHEMA, MODES, Game, MAX_BELIEF_NODES,
    MAX_CERTIFICATE_BYTES, MAX_INITIAL_STATES, MAX_OBSERVATION_CHARS,
    MAX_RANK, MAX_STRATEGY_NODES, MAX_TOTAL_COST, validate_game,
)


def _fields(value: Any, names: set[str], label: str) -> dict:
    if type(value) is not dict or set(value) != names:
        raise ValueError(f"{label} has missing, extra, or invalid fields")
    return value


def _int(value: Any, lower: int, upper: int, label: str) -> int:
    if type(value) is not int or not lower <= value <= upper:
        raise ValueError(f"{label} must be an integer in [{lower}, {upper}]")
    return value


def _mode(mode: Any) -> tuple[bool, bool]:
    if type(mode) is not str or mode not in MODES:
        raise ValueError("unsupported finite-game policy mode")
    return mode.startswith("open_loop"), mode in ("no_observe", "open_loop_no_observe")


def _bounded_encoding(value: Any) -> bytes:
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, UnicodeError, RecursionError, OverflowError) as exc:
        raise ValueError("certificate must be bounded strict JSON") from exc
    if len(encoded) > MAX_CERTIFICATE_BYTES:
        raise ValueError("certificate exceeds its serialized byte cap")
    return encoded


def _belief(raw: Any, count: int) -> tuple[int, ...]:
    if type(raw) is not list or not 1 <= len(raw) <= MAX_INITIAL_STATES:
        raise ValueError("invalid certificate belief size")
    values = tuple(_int(x, 0, count-1, "belief state") for x in raw)
    if list(values) != sorted(set(values)):
        raise ValueError("certificate beliefs must be sorted and duplicate-free")
    return values


def _alternatives(model: Game, possible: tuple[int, ...], mode: str) -> dict[str, tuple[int, dict[str, tuple[int, ...]]]]:
    """Checker-owned transition reconstruction, independent of the producer."""
    ignore_feedback, exclude_observe = _mode(mode)
    if any(model.states[s].outcome == "failure" for s in possible):
        return {}
    live_states = tuple(s for s in possible if model.states[s].outcome == "live")
    if not live_states:
        return {}
    common_actions: set[int] | None = None
    for s in live_states:
        enabled = {i for i, target in enumerate(model.states[s].successors) if target >= 0}
        common_actions = enabled if common_actions is None else common_actions.intersection(enabled)
    alternatives = {}
    current_rank = max(model.states[s].rank for s in possible)
    for action_index in sorted(common_actions or ()):
        action = model.actions[action_index]
        if exclude_observe and action.kind == "observe":
            continue
        grouped: dict[str, set[int]] = {}
        for source in possible:
            state = model.states[source]
            if state.outcome == "success":
                if not ignore_feedback:
                    raise ValueError("adaptive belief mixed live and terminal public states")
                target = source
            else:
                target = state.successors[action_index]
            token = "*" if ignore_feedback else model.states[target].observation
            grouped.setdefault(token, set()).add(target)
        children = {token: tuple(sorted(values)) for token, values in sorted(grouped.items())}
        if not children or any(max(model.states[s].rank for s in child) >= current_rank for child in children.values()):
            raise ValueError("belief transition is not strictly rank decreasing")
        alternatives[action.id] = (action.cost, children)
    return alternatives


def _claims(model: Game, certificate: Any) -> tuple[str, tuple[int, ...], dict[tuple[int, ...], tuple[int | None, str | None]]]:
    _fields(certificate, {"schema_version", "game_sha256", "mode", "root", "nodes"}, "game certificate")
    if certificate["schema_version"] != CERTIFICATE_SCHEMA:
        raise ValueError("unsupported game-certificate schema")
    if certificate["game_sha256"] != model.sha256:
        raise ValueError("certificate belongs to a different finite game")
    mode = certificate["mode"]
    _mode(mode)
    root = _belief(certificate["root"], len(model.states))
    if root != tuple(sorted(model.initial)):
        raise ValueError("certificate root is not the entire initial uncertainty set")
    raw = certificate["nodes"]
    if type(raw) is not list or not 1 <= len(raw) <= MAX_BELIEF_NODES:
        raise ValueError("invalid number of certificate nodes")
    identifiers = {action.id for action in model.actions}
    claims = {}
    for item in raw:
        _fields(item, {"belief", "value", "action"}, "certificate node")
        possible = _belief(item["belief"], len(model.states))
        if possible in claims:
            raise ValueError("duplicate certificate belief")
        value = item["value"]
        if value is not None:
            _int(value, 0, MAX_TOTAL_COST, "claimed policy cost")
        action = item["action"]
        if action is not None and (type(action) is not str or action not in identifiers):
            raise ValueError("certificate chooses an undeclared action")
        claims[possible] = (value, action)
    if root not in claims:
        raise ValueError("certificate root node is absent")
    _bounded_encoding(certificate)
    return mode, root, claims


def verify_game_certificate(game: Any, certificate: Any) -> dict:
    """Verify the exact minimum worst-case cost, including impossibility.

    None denotes an unachievable guaranteed-success policy. Merely checking an
    attaining policy would prove an upper bound; checking all alternatives at
    every reachable belief supplies the matching lower bound in this model.
    """
    try:
        model = validate_game(game)
        mode, root, claims = _claims(model, certificate)
        seen: set[tuple[int, ...]] = set()
        alternatives_checked = 0
        branches_checked = 0

        def check(possible: tuple[int, ...]) -> None:
            nonlocal alternatives_checked, branches_checked
            if possible in seen:
                return
            if possible not in claims:
                raise ValueError("an alternative-action/outcome child belief is absent")
            value, selected = claims[possible]
            outcomes = [model.states[s].outcome for s in possible]
            if all(outcome == "success" for outcome in outcomes):
                if value != 0 or selected is not None:
                    raise ValueError("a guaranteed goal belief needs zero cost and no action")
            elif "failure" in outcomes:
                if value is not None or selected is not None:
                    raise ValueError("an absorbing failure makes guaranteed success impossible")
            else:
                alternatives = _alternatives(model, possible, mode)
                candidates = {}
                for action, (cost, children) in alternatives.items():
                    alternatives_checked += 1
                    branches_checked += len(children)
                    for child in children.values():
                        check(child)
                    values = [claims[child][0] for child in children.values()]
                    candidates[action] = None if any(v is None for v in values) else cost + max(values)
                finite = [v for v in candidates.values() if v is not None]
                expected = min(finite) if finite else None
                if value != expected:
                    raise ValueError("claimed value violates the complete Bellman recurrence")
                if expected is None:
                    if selected is not None:
                        raise ValueError("an unwinning belief cannot claim an attaining action")
                elif selected not in candidates or candidates[selected] != expected:
                    raise ValueError("selected action does not attain the certified minimum")
            seen.add(possible)

        check(root)
        if seen != set(claims):
            raise ValueError("certificate contains beliefs unreachable under its declared policy mode")
        return {"valid": True, "winning": claims[root][0] is not None, "optimal_cost": claims[root][0],
                "mode": mode, "checked_beliefs": len(seen), "checked_alternatives": alternatives_checked,
                "checked_outcome_branches": branches_checked, "initial_states": len(model.initial),
                "game_sha256": model.sha256,
                "scope": "exact guaranteed-success minimax action cost in this finite ranked deterministic observation model"}
    except (ValueError, TypeError, KeyError, IndexError, RecursionError, OverflowError, UnicodeError) as exc:
        return {"valid": False, "error": str(exc)[:240]}


def extract_game_strategy(game: Any, certificate: Any) -> dict:
    """Construct an untrusted attaining observation policy from checked values."""
    checked = verify_game_certificate(game, certificate)
    if not checked["valid"]:
        raise ValueError(checked["error"])
    if not checked["winning"]:
        raise ValueError("there is no guaranteed-success strategy in this mode")
    model = validate_game(game)
    mode, root, claims = _claims(model, certificate)
    nodes: list[dict] = []
    identifiers: dict[tuple[int, ...], int] = {}

    def build(possible: tuple[int, ...]) -> int:
        if possible in identifiers:
            return identifiers[possible]
        index = len(nodes)
        identifiers[possible] = index
        nodes.append({})
        if all(model.states[s].outcome == "success" for s in possible):
            nodes[index] = {"stop": True}
        else:
            action = claims[possible][1]
            _, children = _alternatives(model, possible, mode)[action]
            nodes[index] = {"action": action, "branches": [
                {"observation": token, "next": build(child)} for token, child in children.items()]}
        return index

    root_index = build(root)
    if len(nodes) > MAX_STRATEGY_NODES:
        raise ValueError("attaining policy exceeds the finite strategy-node limit")
    return {"schema_version": STRATEGY_SCHEMA, "game_sha256": model.sha256,
            "mode": mode, "root": root_index, "nodes": nodes}


def verify_game_strategy(game: Any, strategy: Any) -> dict:
    """Replay the policy from every initial state, without a value recurrence.

    The policy branches only on public observation tokens. No world index, task
    object, reference action, optimizer value, or hidden-state selector is a
    policy input. A successful fixed-script world stops paying once it reaches
    a terminal goal, while its common script can continue for other worlds.
    """
    try:
        model = validate_game(game)
        _fields(strategy, {"schema_version", "game_sha256", "mode", "root", "nodes"}, "strategy")
        if strategy["schema_version"] != STRATEGY_SCHEMA or strategy["game_sha256"] != model.sha256:
            raise ValueError("strategy schema or finite-game binding differs")
        ignore_feedback, exclude_observe = _mode(strategy["mode"])
        raw = strategy["nodes"]
        if type(raw) is not list or not 1 <= len(raw) <= MAX_STRATEGY_NODES:
            raise ValueError("invalid strategy node count")
        root = _int(strategy["root"], 0, len(raw)-1, "strategy root")
        action_indices = {action.id: index for index, action in enumerate(model.actions)}
        parsed = []
        for node in raw:
            if type(node) is dict and set(node) == {"stop"}:
                if type(node["stop"]) is not bool or node["stop"] is not True:
                    raise ValueError("terminal strategy flag must be Boolean true")
                parsed.append(None)
                continue
            _fields(node, {"action", "branches"}, "strategy action node")
            name = node["action"]
            if type(name) is not str or name not in action_indices:
                raise ValueError("strategy chooses an undeclared action")
            action_index = action_indices[name]
            if exclude_observe and model.actions[action_index].kind == "observe":
                raise ValueError("strategy violates its no-observe restriction")
            branches = node["branches"]
            if type(branches) is not list or not 1 <= len(branches) <= MAX_INITIAL_STATES:
                raise ValueError("invalid strategy observation branch count")
            targets = {}
            for edge in branches:
                _fields(edge, {"observation", "next"}, "strategy branch")
                token = edge["observation"]
                if type(token) is not str or len(token) > MAX_OBSERVATION_CHARS:
                    raise ValueError("invalid strategy observation token")
                if token in targets or (ignore_feedback and token != "*"):
                    raise ValueError("duplicate branch or feedback-dependent open-loop strategy")
                targets[token] = _int(edge["next"], 0, len(raw)-1, "strategy successor")
            parsed.append((action_index, targets))
        _bounded_encoding(strategy)

        visited: set[int] = set()
        branch_use: dict[int, set[str]] = {}
        costs = []
        maximum_steps = 0
        for initial in model.initial:
            state_index, node_index, cost = initial, root, 0
            for steps in range(MAX_RANK + 1):
                visited.add(node_index)
                node = parsed[node_index]
                state = model.states[state_index]
                if node is None:
                    if state.outcome != "success":
                        raise ValueError("strategy stops before a goal for at least one initial world")
                    costs.append(cost)
                    maximum_steps = max(maximum_steps, steps)
                    break
                if state.outcome == "failure":
                    raise ValueError("strategy reaches an absorbing failure")
                action_index, targets = node
                if state.outcome == "success":
                    if not ignore_feedback:
                        raise ValueError("adaptive strategy continues after an observed terminal goal")
                    target = state_index
                else:
                    target = state.successors[action_index]
                    if target < 0:
                        raise ValueError("strategy takes an unavailable action in some possible world")
                    cost += model.actions[action_index].cost
                token = "*" if ignore_feedback else model.states[target].observation
                if token not in targets:
                    raise ValueError("strategy omits a realized public observation")
                branch_use.setdefault(node_index, set()).add(token)
                state_index, node_index = target, targets[token]
            else:
                raise ValueError("strategy does not terminate inside the ranked horizon")
        if visited != set(range(len(parsed))):
            raise ValueError("strategy contains unreachable nodes")
        for node_index, node in enumerate(parsed):
            if node is not None and branch_use.get(node_index, set()) != set(node[1]):
                raise ValueError("strategy contains an impossible observation branch")
        return {"valid": True, "mode": strategy["mode"], "worst_case_cost": max(costs),
                "initial_states_checked": len(model.initial), "nodes_checked": len(parsed),
                "maximum_action_steps": maximum_steps, "per_initial_costs": costs,
                "scope": "complete replay of this observation-only strategy in every listed deterministic initial world"}
    except (ValueError, TypeError, KeyError, IndexError, RecursionError, OverflowError, UnicodeError) as exc:
        return {"valid": False, "error": str(exc)[:240]}


def expand_game_certificate(game: Any, certificate: Any) -> dict:
    """Export the checked belief arena for independent formal tooling.

    This export is a Python-constructed projection of the raw game. A theorem
    about the resulting AND/OR arena does not by itself prove this projection
    equivalent to the raw transition model, much less to an external simulator.
    """
    verdict = verify_game_certificate(game, certificate)
    if not verdict["valid"]:
        raise ValueError(verdict["error"])
    model = validate_game(game)
    mode, root, claims = _claims(model, certificate)
    order = sorted(claims, key=lambda b: (max(model.states[s].rank for s in b), b))
    indices = {belief: index for index, belief in enumerate(order)}
    nodes = []
    for possible in order:
        goal = all(model.states[s].outcome == "success" for s in possible)
        failure = any(model.states[s].outcome == "failure" for s in possible)
        alternatives = {} if goal or failure else _alternatives(model, possible, mode)
        nodes.append({"belief": list(possible), "rank": max(model.states[s].rank for s in possible),
                      "goal": goal, "failure_cut": failure, "value": claims[possible][0],
                      "selected_action": claims[possible][1],
                      "choices": [{"action": action, "cost": cost,
                                   "observations": list(children),
                                   "children": [indices[child] for child in children.values()]}
                                  for action, (cost, children) in alternatives.items()]})
    return {"schema_version": "finite-belief-arena-v1", "game_sha256": model.sha256,
            "certificate_sha256": hashlib.sha256(_bounded_encoding(certificate)).hexdigest(),
            "mode": mode, "root": indices[root], "nodes": nodes}

