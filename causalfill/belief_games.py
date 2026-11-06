"""Bounded deterministic partially observed games and an untrusted optimizer.

An unknown initial state is fixed for an episode. Actions change the state;
successor observation tokens are the complete feedback modeled here. Strictly
decreasing ranks make the finite minimax problem well founded. The independent
certificate and policy checkers live in :mod:`belief_certificates`.

This is classical finite belief-space planning, not a new planning algorithm or
a claim about the difficulty of these tasks for language models.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any


GAME_SCHEMA = "finite-belief-game-v1"
CERTIFICATE_SCHEMA = "finite-belief-certificate-v1"
STRATEGY_SCHEMA = "finite-belief-strategy-v1"
MODES = ("adaptive", "no_observe", "open_loop", "open_loop_no_observe")
MAX_STATES = 8192
MAX_ACTIONS = 32
MAX_INITIAL_STATES = 32
MAX_RANK = 64
MAX_ACTION_COST = 1000
MAX_TRANSITIONS = 65536
MAX_OBSERVATION_CHARS = 4096
MAX_GAME_BYTES = 8 * 1024 * 1024
MAX_BELIEF_NODES = 20000
MAX_CERTIFICATE_BYTES = 16 * 1024 * 1024
MAX_STRATEGY_NODES = MAX_INITIAL_STATES * MAX_RANK + 1
MAX_TOTAL_COST = MAX_RANK * MAX_ACTION_COST


@dataclass(frozen=True)
class Action:
    id: str
    cost: int
    kind: str


@dataclass(frozen=True)
class State:
    rank: int
    observation: str
    outcome: str
    # One successor per global action index, or -1 when unavailable.
    successors: tuple[int, ...]


@dataclass(frozen=True)
class Game:
    actions: tuple[Action, ...]
    states: tuple[State, ...]
    initial: tuple[int, ...]
    sha256: str


def _integer(value: Any, low: int, high: int, label: str) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{label} must be an integer in [{low}, {high}]")
    return value


def _fields(value: Any, fields: set[str], label: str) -> dict:
    if type(value) is not dict or set(value) != fields:
        raise ValueError(f"{label} has missing, extra, or invalid fields")
    return value


def _text(value: Any, maximum: int, label: str, empty: bool = False) -> str:
    if type(value) is not str or not (0 if empty else 1) <= len(value) <= maximum:
        raise ValueError(f"{label} must be bounded text")
    # Surrogates are not legal scalar Unicode values and have no strict UTF-8
    # representation, even though a Python str may contain them.
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeError as exc:
        raise ValueError(f"{label} is not strict UTF-8 text") from exc
    return value


def validate_game(raw: Any) -> Game:
    """Validate the complete JSON statement and return immutable parsed data.

    No floating-point costs, Boolean integer aliases, omitted transitions, or
    hidden current-state marker are permitted by this schema. Undefined action
    transitions are unavailable actions, not information-producing experiments.
    A real task must expose no additional hidden-state-dependent error feedback
    if it claims conformance to this complete observation model.
    """
    _fields(raw, {"schema_version", "actions", "states", "initial"}, "game")
    if raw["schema_version"] != GAME_SCHEMA:
        raise ValueError("unsupported finite-game schema")
    actions_raw = raw["actions"]
    if type(actions_raw) is not list or not 1 <= len(actions_raw) <= MAX_ACTIONS:
        raise ValueError("invalid game action count")
    actions: list[Action] = []
    action_indices: dict[str, int] = {}
    for item in actions_raw:
        _fields(item, {"id", "cost", "kind"}, "action")
        identifier = _text(item["id"], 64, "action ID")
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]*", identifier) is None:
            raise ValueError("action ID must use the published ASCII identifier grammar")
        if identifier in action_indices:
            raise ValueError("duplicate action ID")
        cost = _integer(item["cost"], 1, MAX_ACTION_COST, "action cost")
        if type(item["kind"]) is not str or item["kind"] not in ("observe", "act"):
            raise ValueError("action kind must be observe or act")
        action_indices[identifier] = len(actions)
        actions.append(Action(identifier, cost, item["kind"]))

    states_raw = raw["states"]
    if type(states_raw) is not list or not 1 <= len(states_raw) <= MAX_STATES:
        raise ValueError("invalid finite-game state count")
    states: list[State] = []
    edge_count = 0
    observation_interfaces: dict[str, tuple[bool, tuple[int, ...]]] = {}
    for item in states_raw:
        _fields(item, {"rank", "observation", "outcome", "transitions"}, "state")
        rank = _integer(item["rank"], 0, MAX_RANK, "state rank")
        observation = _text(item["observation"], MAX_OBSERVATION_CHARS, "observation", empty=True)
        outcome = item["outcome"]
        if type(outcome) is not str or outcome not in ("live", "success", "failure"):
            raise ValueError("state outcome must be live, success, or failure")
        transitions = item["transitions"]
        if type(transitions) is not list or len(transitions) > len(actions):
            raise ValueError("invalid state transition list")
        if outcome != "live" and (transitions or rank != 0):
            raise ValueError("terminal states must have rank zero and no outgoing transitions")
        if outcome == "live" and rank == 0:
            raise ValueError("live states need a positive rank")
        successors = [-1] * len(actions)
        for edge in transitions:
            _fields(edge, {"action", "next"}, "transition")
            identifier = edge["action"]
            if type(identifier) is not str or identifier not in action_indices:
                raise ValueError("transition names an undeclared action")
            action = action_indices[identifier]
            if successors[action] != -1:
                raise ValueError("duplicate state/action transition")
            successors[action] = _integer(edge["next"], 0, len(states_raw)-1, "successor state")
            edge_count += 1
            if edge_count > MAX_TRANSITIONS:
                raise ValueError("game exceeds the transition cap")
        interface = (outcome == "live", tuple(i for i, target in enumerate(successors) if target >= 0))
        if observation in observation_interfaces and observation_interfaces[observation] != interface:
            raise ValueError("equal observations must expose the same liveness and available actions")
        observation_interfaces[observation] = interface
        states.append(State(rank, observation, outcome, tuple(successors)))
    for state in states:
        for target in state.successors:
            if target >= 0 and states[target].rank >= state.rank:
                raise ValueError("every transition must strictly decrease the state rank")

    initial_raw = raw["initial"]
    if type(initial_raw) is not list or not 1 <= len(initial_raw) <= MAX_INITIAL_STATES:
        raise ValueError("invalid number of possible initial states")
    initial = tuple(_integer(x, 0, len(states)-1, "initial state") for x in initial_raw)
    if len(set(initial)) != len(initial):
        raise ValueError("initial states must be distinct")
    if len({states[x].observation for x in initial}) != 1:
        raise ValueError("initial states must have the same public observation")
    encoded = json.dumps(raw, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if len(encoded) > MAX_GAME_BYTES:
        raise ValueError("finite-game statement exceeds its byte limit")
    return Game(tuple(actions), tuple(states), initial, hashlib.sha256(encoded).hexdigest())


def game_digest(game: Any) -> str:
    return validate_game(game).sha256


def _mode(mode: Any) -> tuple[bool, bool]:
    if type(mode) is not str or mode not in MODES:
        raise ValueError("unsupported finite-game policy mode")
    return mode in ("open_loop", "open_loop_no_observe"), mode in ("no_observe", "open_loop_no_observe")


def _bits(mask: int) -> tuple[int, ...]:
    result = []
    while mask:
        bit = mask & -mask
        result.append(bit.bit_length()-1)
        mask ^= bit
    return tuple(result)


def _mask(states: tuple[int, ...] | list[int]) -> int:
    result = 0
    for state in states:
        result |= 1 << state
    return result


def _choices(game: Game, belief: int, mode: str) -> list[tuple[int, tuple[tuple[str, int], ...]]]:
    """Optimizer transition construction using bit-set beliefs.

    A successful terminal state is absorbing only when ignored observations
    keep it grouped with live states. Its world has already completed and pays
    no more execution cost. The last live world realizes the total fixed-script
    cost, so positive common action costs still obey the scalar recurrence.
    """
    ignore_feedback, exclude_observe = _mode(mode)
    possible = _bits(belief)
    if any(game.states[s].outcome == "failure" for s in possible):
        return []
    live = [s for s in possible if game.states[s].outcome == "live"]
    if not live:
        return []
    result = []
    for a, action in enumerate(game.actions):
        if exclude_observe and action.kind == "observe":
            continue
        if any(game.states[s].successors[a] < 0 for s in live):
            continue
        partitions: dict[str, int] = {}
        for state in possible:
            target = game.states[state].successors[a] if state in live else state
            token = "*" if ignore_feedback else game.states[target].observation
            partitions[token] = partitions.get(token, 0) | (1 << target)
        result.append((a, tuple(sorted(partitions.items()))))
    return result


def build_game_certificate(game: Any, mode: str = "adaptive") -> dict:
    """Compute the exact robust cost and all reachable Bellman obligations.

    None is infinity: no legal policy guarantees success from that belief in
    the selected mode. This producer is untrusted until the separate checker
    validates its output, including alternatives to the chosen action.
    """
    parsed = validate_game(game)
    _mode(mode)
    root = _mask(parsed.initial)
    memo: dict[int, tuple[int | None, str | None]] = {}
    active: set[int] = set()

    def solve(belief: int) -> int | None:
        if belief in memo:
            return memo[belief][0]
        if len(memo) + len(active) >= MAX_BELIEF_NODES:
            raise ValueError("reachable belief graph exceeds the certificate cap")
        active.add(belief)
        possible = _bits(belief)
        outcomes = [parsed.states[s].outcome for s in possible]
        if all(outcome == "success" for outcome in outcomes):
            memo[belief] = (0, None)
        elif "failure" in outcomes:
            memo[belief] = (None, None)
        else:
            candidates = []
            for action_index, partitions in _choices(parsed, belief, mode):
                values = [solve(child) for _, child in partitions]
                if all(value is not None for value in values):
                    action = parsed.actions[action_index]
                    candidates.append((action.cost + max(values), action.id))
            memo[belief] = min(candidates) if candidates else (None, None)
        active.remove(belief)
        return memo[belief][0]

    solve(root)
    order = sorted(memo, key=lambda b: (max(parsed.states[s].rank for s in _bits(b)), _bits(b)))
    return {"schema_version": CERTIFICATE_SCHEMA, "game_sha256": parsed.sha256,
            "mode": mode, "root": list(_bits(root)),
            "nodes": [{"belief": list(_bits(b)), "value": memo[b][0], "action": memo[b][1]} for b in order]}


def successor_beliefs(game: Any, belief: list[int], action: str, mode: str = "adaptive") -> dict[str, list[int]]:
    """Public planning helper; it receives no current hidden state or task."""
    parsed = validate_game(game)
    _mode(mode)
    if type(belief) is not list or not 1 <= len(belief) <= MAX_INITIAL_STATES:
        raise ValueError("invalid belief size")
    possible = tuple(_integer(x, 0, len(parsed.states)-1, "belief state") for x in belief)
    if list(possible) != sorted(set(possible)):
        raise ValueError("belief must be sorted and duplicate-free")
    if type(action) is not str:
        raise ValueError("action ID must be text")
    for action_index, children in _choices(parsed, _mask(possible), mode):
        if parsed.actions[action_index].id == action:
            return {token: list(_bits(child)) for token, child in children}
    raise ValueError("action is unavailable in the selected belief/policy mode")

