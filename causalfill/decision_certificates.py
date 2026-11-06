"""Exact finite diagnosis strategies and independently checked certificates.

The optimizer is untrusted.  The certificate checker validates every relevant
Bellman recurrence, including every alternative informative query.  The tree
checker uses a separate set-based traversal.  These are finite Python checks,
not a Lean formalization or a claim about computational hardness of an LLM.
"""
from __future__ import annotations

import copy
import hashlib
import json
from functools import lru_cache
from typing import Any


MAX_WORLDS = 32
MAX_EXPERIMENTS = 12
MAX_CERTIFICATE_STATES = 100_000


def _int(value: Any, low: int, high: int, name: str) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be an integer in [{low}, {high}]")
    return value


def validate_table(table: Any) -> tuple[tuple[int, ...], ...]:
    if type(table) not in (list, tuple) or not 2 <= len(table) <= MAX_WORLDS:
        raise ValueError("table must contain 2..32 worlds")
    if type(table[0]) not in (list, tuple) or not 1 <= len(table[0]) <= MAX_EXPERIMENTS:
        raise ValueError("table must contain 1..12 experiments")
    width = len(table[0])
    normalized = []
    for row in table:
        if type(row) not in (list, tuple) or len(row) != width:
            raise ValueError("table must be rectangular")
        normalized.append(tuple(_int(x, 0, 1, "response") for x in row))
    if len(set(normalized)) != len(normalized):
        raise ValueError("worlds must have distinct complete response rows")
    return tuple(normalized)


def table_digest(table: Any) -> str:
    normalized = validate_table(table)
    encoded = json.dumps(normalized, separators=(",", ":")).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def information_lower_bound(world_count: int) -> int:
    """At least ceil(log2 N) binary queries are necessary in the worst case."""
    _int(world_count, 2, MAX_WORLDS, "world_count")
    return (world_count - 1).bit_length()


@lru_cache(maxsize=128)
def _optimize(table: tuple[tuple[int, ...], ...]) -> tuple[tuple[int, int, int | None], ...]:
    n, width = len(table), len(table[0])
    columns = [sum((1 << world) for world in range(n) if table[world][q]) for q in range(width)]
    depths: dict[int, int] = {}
    choices: dict[int, int | None] = {}

    def solve(state: int) -> int:
        if state in depths:
            return depths[state]
        if len(depths) >= MAX_CERTIFICATE_STATES:
            raise ValueError("version-space certificate exceeds configured state limit")
        if state.bit_count() == 1:
            depths[state], choices[state] = 0, None
            return 0
        alternatives = []
        for q, column in enumerate(columns):
            one = state & column
            zero = state ^ one
            if not one or not zero:
                continue
            alternatives.append((1 + max(solve(zero), solve(one)), q))
        if not alternatives:
            raise ValueError("non-identifiable state")
        depth, query = min(alternatives)
        depths[state], choices[state] = depth, query
        return depth

    solve((1 << n) - 1)
    return tuple((mask, depths[mask], choices[mask]) for mask in sorted(depths, key=lambda x: (x.bit_count(), x)))


def build_decision_certificate(table: Any) -> dict:
    normalized = validate_table(table)
    entries = _optimize(normalized)
    return {
        "schema_version": "finite-diagnosis-dp-v1",
        "table_sha256": table_digest(normalized),
        "root_mask": (1 << len(normalized)) - 1,
        "nodes": [[mask, depth, query] for mask, depth, query in entries],
    }


def verify_decision_certificate(table: Any, certificate: Any) -> dict:
    """Check both upper and lower minimax bounds without calling the optimizer.

    For every reachable non-singleton state, all informative experiment
    partitions must be present.  Its claimed depth must equal the minimum of
    one plus the worst child depth.  Strictly smaller states make the argument
    well-founded.  Verifying only the selected strategy would prove no lower
    bound; this checker explicitly checks all alternatives.
    """
    try:
        responses = validate_table(table)
        n, width = len(responses), len(responses[0])
        full = (1 << n) - 1
        if type(certificate) is not dict or set(certificate) != {"schema_version", "table_sha256", "root_mask", "nodes"}:
            raise ValueError("invalid certificate fields")
        if certificate["schema_version"] != "finite-diagnosis-dp-v1":
            raise ValueError("unsupported certificate schema")
        if certificate["table_sha256"] != table_digest(responses):
            raise ValueError("certificate belongs to a different response table")
        if type(certificate["root_mask"]) is not int or certificate["root_mask"] != full:
            raise ValueError("incorrect root state")
        raw = certificate["nodes"]
        if type(raw) is not list or not 1 <= len(raw) <= MAX_CERTIFICATE_STATES:
            raise ValueError("invalid certificate state count")
        claims = {}
        for item in raw:
            if type(item) is not list or len(item) != 3:
                raise ValueError("each certificate node is [state_mask, depth, query]")
            state = _int(item[0], 1, full, "state mask")
            depth = _int(item[1], 0, width, "depth")
            query = item[2]
            if query is not None:
                _int(query, 0, width - 1, "query")
            if state in claims:
                raise ValueError("duplicate certificate state")
            claims[state] = (depth, query)
        if full not in claims:
            raise ValueError("root state absent")

        checked: set[int] = set()

        def check(state: int) -> None:
            if state in checked:
                return
            if state not in claims:
                raise ValueError("required alternative-query child state absent")
            depth, chosen = claims[state]
            worlds = [world for world in range(n) if state & (1 << world)]
            if len(worlds) == 1:
                if depth != 0 or chosen is not None:
                    raise ValueError("a singleton must have zero depth and no query")
                checked.add(state)
                return
            candidates = []
            for q in range(width):
                partitions = [[world for world in worlds if responses[world][q] == bit] for bit in (0, 1)]
                if not partitions[0] or not partitions[1]:
                    continue
                child_masks = [sum(1 << world for world in part) for part in partitions]
                for child in child_masks:
                    if child.bit_count() >= state.bit_count():
                        raise ValueError("non-decreasing recurrence")
                    check(child)
                candidates.append((1 + max(claims[child][0] for child in child_masks), q))
            if not candidates:
                raise ValueError("non-singleton has no identifying experiment")
            optimum = min(value for value, _ in candidates)
            if depth != optimum or (depth, chosen) not in candidates:
                raise ValueError("claimed depth or selected experiment violates the full minimax recurrence")
            checked.add(state)

        check(full)
        if checked != set(claims):
            raise ValueError("certificate contains unreachable states")
        return {"valid": True, "optimal_depth": claims[full][0], "checked_states": len(checked),
                "information_lower_bound": information_lower_bound(n),
                "scope": "exact deterministic adaptive identification in this finite noiseless binary table"}
    except (ValueError, TypeError, KeyError, IndexError, RecursionError) as exc:
        return {"valid": False, "error": str(exc)[:240]}


def extract_decision_tree(table: Any, certificate: Any) -> dict:
    verdict = verify_decision_certificate(table, certificate)
    if not verdict["valid"]:
        raise ValueError(verdict["error"])
    responses = validate_table(table)
    nodes = {mask: (depth, query) for mask, depth, query in certificate["nodes"]}

    def build(worlds: list[int]) -> dict:
        if len(worlds) == 1:
            return {"world": worlds[0]}
        mask = sum(1 << world for world in worlds)
        query = nodes[mask][1]
        return {"query": query,
                "zero": build([world for world in worlds if responses[world][query] == 0]),
                "one": build([world for world in worlds if responses[world][query] == 1])}

    return build(list(range(len(responses))))


def verify_decision_tree(table: Any, tree: Any) -> dict:
    """A separate strategy checker: exact leaf identity and worst-case depth."""
    try:
        table_ = validate_table(table)
        count = 0

        def walk(node: Any, possible: list[int], depth: int) -> int:
            nonlocal count
            count += 1
            if count > 2 * len(table_) - 1 or depth > len(table_[0]):
                raise ValueError("tree exceeds its finite full-binary bound")
            if type(node) is not dict:
                raise ValueError("invalid tree node")
            if set(node) == {"world"}:
                world = _int(node["world"], 0, len(table_) - 1, "world")
                if possible != [world]:
                    raise ValueError("leaf does not uniquely identify its world")
                return depth
            if set(node) != {"query", "zero", "one"}:
                raise ValueError("invalid internal tree fields")
            q = _int(node["query"], 0, len(table_[0]) - 1, "query")
            left = [world for world in possible if table_[world][q] == 0]
            right = [world for world in possible if table_[world][q] == 1]
            if not left or not right:
                raise ValueError("tree contains an uninformative experiment")
            return max(walk(node["zero"], left, depth + 1), walk(node["one"], right, depth + 1))

        depth = walk(tree, list(range(len(table_))), 0)
        return {"valid": True, "depth": depth, "leaves": len(table_), "nodes": count}
    except (ValueError, TypeError, KeyError, IndexError, RecursionError) as exc:
        return {"valid": False, "error": str(exc)[:240]}


def elimination_certificate(table: Any, observations: list[tuple[int, int]], world: int) -> list[dict]:
    responses = validate_table(table)
    _int(world, 0, len(responses) - 1, "world")
    observed = {}
    for query, outcome in observations:
        _int(query, 0, len(responses[0]) - 1, "query")
        _int(outcome, 0, 1, "outcome")
        if query in observed and observed[query] != outcome:
            raise ValueError("contradictory observations")
        observed[query] = outcome
    if any(responses[world][q] != value for q, value in observed.items()):
        raise ValueError("chosen world contradicts observations")
    certificate = []
    for other in range(len(responses)):
        if other == world:
            continue
        witness = next((q for q, value in observed.items() if responses[other][q] != value), None)
        if witness is None:
            raise ValueError("observations do not uniquely identify the world")
        certificate.append({"world": other, "experiment": witness})
    return certificate


def solve_diagnosis(public: dict, call) -> dict:
    """Evidence-only scripted reference; no task object, seed or grader access."""
    if not isinstance(public, dict) or public.get("family") != "diagnosis":
        raise ValueError("expected a diagnosis episode")
    response = call("read_file", {"path": "/formal/diagnosis.json"})
    if "error" in response:
        raise ValueError(response["error"])
    contract = json.loads(response["content"])
    table = validate_table(contract["responses"])
    if table_digest(table) != contract["table_sha256"]:
        raise ValueError("public response-table digest mismatch")
    certificate = build_decision_certificate(table)
    checked = verify_decision_certificate(table, certificate)
    if not checked["valid"] or checked["optimal_depth"] != contract["query_budget"]:
        raise ValueError("advertised budget disagrees with the checked minimax certificate")
    node = extract_decision_tree(table, certificate)
    observations = []
    while "query" in node:
        query = node["query"]
        response = call("experiment", {"id": query})
        if "error" in response:
            raise ValueError(response["error"])
        outcome = _int(response["outcome"], 0, 1, "observed outcome")
        observations.append((query, outcome))
        node = node["one" if outcome else "zero"]
    world = node["world"]
    return {"world": world, "eliminations": elimination_certificate(table, observations, world)}
