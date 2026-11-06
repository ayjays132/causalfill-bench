"""Finite decision completion under a shared adversarial corruption budget.

The true world is fixed. Every listed binary experiment can be used once, and
at most ``max_corruptions`` of the readings actually requested may be flipped.
The bound applies to the entire transcript, not independently to each sensor.
A terminal action can succeed without identifying the world.

The optimizer uses disjoint bitmask layers of required faults. The separate
certificate checker reconstructs integer discrepancy vectors and checks every
alternative. The policy verifier traverses fixed worlds and actual fault choices;
it does not invoke the optimizer, certificate checker or belief update.

These are bounded Python certificates. They do not establish a statistical
noise model, a physical fault bound, a Lean theorem or model/runtime refinement.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache

SCHEMA = "causalfill.robust-decision.v1"
CERTIFICATE_SCHEMA = "causalfill.robust-certificate.v1"
POLICY_SCHEMA = "causalfill.robust-policy.v1"
MAX_WORLDS = 32
MAX_EXPERIMENTS = 12
MAX_ACTIONS = 64
MAX_CORRUPTIONS = 2
MAX_STATES = 100_000
MAX_REPLAY_STATES = 1_000_000
MAX_COST = 1_000_000
MAX_PROBLEM_BYTES = 1_048_576
MAX_CERTIFICATE_BYTES = 33_554_432
MAX_JSON_DEPTH = 32


def _integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{label} must be an integer in [{low}, {high}]")
    return value


def _name(value):
    if type(value) is not str or not 1 <= len(value) <= 64:
        raise ValueError("identifiers must be strings of length 1..64")
    return value


def _keys(value, keys):
    if type(value) is not dict or len(value) != len(keys) or set(value) != set(keys):
        raise ValueError("invalid fields")


def _objective(value):
    if type(value) is not str or value not in ("action", "identification"):
        raise ValueError("objective must be action or identification")
    return value


def _digest_text(value):
    if (type(value) is not str or len(value) != 64
            or any(c not in "0123456789abcdef" for c in value)):
        raise ValueError("invalid SHA-256 digest")
    return value


def _json_text(value, limit):
    try:
        text = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, RecursionError) as exc:
        raise ValueError("value is not a bounded JSON artifact") from exc
    if len(text.encode("utf-8")) > limit:
        raise ValueError("artifact byte cap exceeded; no verification claim")
    return text


def load_robust_json(raw, *, max_bytes=MAX_CERTIFICATE_BYTES):
    """Strict offline JSON reader, including duplicate keys and nonfinite values.

    Object-taking APIs cannot recover duplicate keys already discarded by a
    different parser. Use this reader, or the benchmark's strict public parser,
    at the bytes-to-object boundary. Limits are engineering caps, not OS limits.
    """
    _integer(max_bytes, 1, MAX_CERTIFICATE_BYTES, "JSON byte limit")
    if type(raw) is str:
        try:
            raw = raw.encode("utf-8")
        except UnicodeError as exc:
            raise ValueError("JSON must be valid UTF-8") from exc
    if type(raw) is not bytes or len(raw) > max_bytes:
        raise ValueError("JSON input is not bytes/text within the byte cap")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON object key")
            result[key] = value
        return result

    def constant(_):
        raise ValueError("nonfinite JSON number")

    def integer(value):
        if len(value.lstrip("-")) > 20:
            raise ValueError("JSON integer has too many digits")
        return int(value)

    def floating(value):
        # This format has no floating-point fields. Reject them even when a
        # numeral such as 1.0 would otherwise compare equal to an integer.
        raise ValueError("floating-point numbers are outside this artifact format")

    try:
        result = json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                            parse_constant=constant, parse_int=integer, parse_float=floating)
        stack = [(result, 0)]
        while stack:
            value, depth = stack.pop()
            if depth > MAX_JSON_DEPTH:
                raise ValueError("JSON nesting limit exceeded")
            if type(value) is dict:
                stack.extend((child, depth + 1) for child in value.values())
            elif type(value) is list:
                stack.extend((child, depth + 1) for child in value)
        return result
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("invalid bounded JSON") from exc


def validate_problem(problem):
    """Return a fresh normalized model, rejecting unsupported fields and aliases."""
    _keys(problem, {"schema", "worlds", "max_corruptions", "actions", "experiments"})
    if type(problem["schema"]) is not str or problem["schema"] != SCHEMA:
        raise ValueError("unsupported robust decision schema")
    original_worlds = problem["worlds"]
    if type(original_worlds) is not list or not 1 <= len(original_worlds) <= MAX_WORLDS:
        raise ValueError("world count outside supported bounds")
    worlds = [_name(w) for w in original_worlds]
    if len(set(worlds)) != len(worlds):
        raise ValueError("duplicate world identifiers")
    world_set = set(worlds)
    faults = _integer(problem["max_corruptions"], 0, MAX_CORRUPTIONS, "corruption budget")
    original_actions = problem["actions"]
    if type(original_actions) is not list or len(original_actions) > MAX_ACTIONS:
        raise ValueError("action count outside supported bounds")
    actions = []
    for action in original_actions:
        _keys(action, {"id", "cost", "success_worlds"})
        good = action["success_worlds"]
        if (type(good) is not list or len(good) > len(worlds)
                or any(type(w) is not str or w not in world_set for w in good)):
            raise ValueError("unknown or oversized successful-world set")
        if len(set(good)) != len(good):
            raise ValueError("duplicate successful worlds")
        actions.append({"id": _name(action["id"]),
                        "cost": _integer(action["cost"], 0, MAX_COST, "action cost"),
                        "success_worlds": sorted(good)})
    original_queries = problem["experiments"]
    if type(original_queries) is not list or len(original_queries) > MAX_EXPERIMENTS:
        raise ValueError("experiment count outside supported bounds")
    experiments = []
    for query in original_queries:
        _keys(query, {"id", "cost", "responses"})
        responses = query["responses"]
        if type(responses) is not dict or len(responses) != len(worlds) or set(responses) != world_set:
            raise ValueError("every experiment needs one response for every world")
        experiments.append({"id": _name(query["id"]),
                            "cost": _integer(query["cost"], 1, MAX_COST, "experiment cost"),
                            "responses": {w: _integer(responses[w], 0, 1, "binary response") for w in worlds}})
    for group in (actions, experiments):
        if len({item["id"] for item in group}) != len(group):
            raise ValueError("duplicate action or experiment identifiers")
    result = {"schema": SCHEMA, "worlds": worlds, "max_corruptions": faults,
              "actions": actions, "experiments": experiments}
    _json_text(result, MAX_PROBLEM_BYTES)
    return result


def _model_digest(model):
    return hashlib.sha256(_json_text(model, MAX_PROBLEM_BYTES).encode("utf-8")).hexdigest()


def problem_digest(problem):
    """Commit the normalized public problem, including its global fault bound."""
    return _model_digest(validate_problem(problem))


def _cost_bound(model):
    return sum(q["cost"] for q in model["experiments"]) + max(
        (a["cost"] for a in model["actions"]), default=0)


def build_robust_certificate(problem, objective="action"):
    """Untrusted optimizer using disjoint bitmask layers of required corruptions."""
    model = validate_problem(problem)
    _objective(objective)
    worlds, queries, k = model["worlds"], model["experiments"], model["max_corruptions"]
    n, full = len(worlds), (1 << len(worlds)) - 1
    positions = {w: i for i, w in enumerate(worlds)}
    actions = [(a["cost"], a["id"], sum(1 << positions[w] for w in a["success_worlds"]))
               for a in model["actions"]]
    truth_masks = [sum(1 << i for i, w in enumerate(worlds) if q["responses"][w]) for q in queries]
    values, choices, reserved = {}, {}, set()

    def solve(layers, remaining):
        key = (layers, remaining)
        if key in values:
            return values[key]
        if len(reserved) >= MAX_STATES:
            raise ValueError("certificate state cap exceeded; no optimum claimed")
        reserved.add(key)
        possible = 0
        for layer in layers:
            possible |= layer
        candidates = []
        if objective == "identification":
            if possible.bit_count() == 1:
                candidates.append((0, "identify", worlds[possible.bit_length() - 1]))
        else:
            candidates.extend((cost, "act", aid) for cost, aid, success in actions
                              if possible & success == possible)
        # Zero is the universal cost lower bound. Only this terminal case prunes
        # alternatives; every positive-value node covers every remaining query.
        if not any(value == 0 for value, _, _ in candidates):
            for qi, query in enumerate(queries):
                if not remaining & (1 << qi):
                    continue
                children = []
                for outcome in (0, 1):
                    agree = truth_masks[qi] if outcome else full ^ truth_masks[qi]
                    disagree = full ^ agree
                    updated = (layers[0] & agree,) + tuple(
                        (layers[j] & agree) | (layers[j-1] & disagree) for j in range(1, k+1))
                    if any(updated):
                        children.append(solve(updated, remaining ^ (1 << qi)))
                if children and all(value is not None for value in children):
                    candidates.append((query["cost"] + max(children), "query", query["id"]))
        best = min(candidates) if candidates else None
        values[key] = None if best is None else best[0]
        choices[key] = None if best is None else {"kind": best[1], "id": best[2]}
        return values[key]

    remaining = (1 << len(queries)) - 1
    value = solve((full,) + (0,) * k, remaining)
    rows = []
    for (layers, rest), claimed in values.items():
        counts = [k+1] * n
        for errors, mask in enumerate(layers):
            while mask:
                bit = mask & -mask
                counts[bit.bit_length()-1] = errors
                mask ^= bit
        rows.append([counts, rest, claimed, choices[(layers, rest)]])
    rows.sort(key=lambda row: (row[1].bit_count(), row[0], row[1]))
    certificate = {"schema": CERTIFICATE_SCHEMA, "problem_sha256": _model_digest(model),
                   "objective": objective, "root": [[0] * n, remaining],
                   "value": value, "nodes": rows}
    _json_text(certificate, MAX_CERTIFICATE_BYTES)
    return certificate


def verify_robust_certificate(problem, certificate, *, expected_objective=None):
    """Independently reconstruct discrepancy vectors and all minimax alternatives."""
    try:
        model = validate_problem(problem)
        _keys(certificate, {"schema", "problem_sha256", "objective", "root", "value", "nodes"})
        if type(certificate["schema"]) is not str or certificate["schema"] != CERTIFICATE_SCHEMA:
            raise ValueError("unsupported certificate schema")
        if _digest_text(certificate["problem_sha256"]) != _model_digest(model):
            raise ValueError("certificate does not bind the trusted problem")
        objective = _objective(certificate["objective"])
        if expected_objective is not None and objective != _objective(expected_objective):
            raise ValueError("certificate objective differs from the externally pinned objective")
        worlds, queries, k = model["worlds"], model["experiments"], model["max_corruptions"]
        n, nq = len(worlds), len(queries)
        all_remaining = (1 << nq) - 1
        root = certificate["root"]
        if type(root) is not list or len(root) != 2 or type(root[0]) is not list or len(root[0]) != n:
            raise ValueError("invalid certificate root")
        if any(type(x) is not int or x != 0 for x in root[0]):
            raise ValueError("root mismatch counts must all be zero")
        if type(root[1]) is not int or root[1] != all_remaining:
            raise ValueError("root must include every experiment")
        rows = certificate["nodes"]
        if type(rows) is not list or not 1 <= len(rows) <= MAX_STATES:
            raise ValueError("invalid certificate state count")
        max_cost = _cost_bound(model)
        claims = {}
        for row in rows:
            if type(row) is not list or len(row) != 4:
                raise ValueError("each node must be [mismatch_counts, remaining, value, choice]")
            counts, remaining, value, selected = row
            if type(counts) is not list or len(counts) != n:
                raise ValueError("one mismatch count is required for each world")
            rest = _integer(remaining, 0, all_remaining, "remaining experiments")
            count_limit = min(k+1, nq - rest.bit_count())
            state = tuple(_integer(c, 0, count_limit, "mismatch count") for c in counts)
            if all(c > k for c in state):
                raise ValueError("empty possible-world state")
            if value is None:
                if selected is not None:
                    raise ValueError("an impossible state cannot select a choice")
            else:
                _integer(value, 0, max_cost, "state cost")
                _keys(selected, {"kind", "id"})
                if type(selected["kind"]) is not str or selected["kind"] not in ("act", "identify", "query"):
                    raise ValueError("unknown choice kind")
                _name(selected["id"])
            if (state, rest) in claims:
                raise ValueError("duplicate certificate state")
            claims[(state, rest)] = (value, selected)
        if certificate["value"] is not None:
            _integer(certificate["value"], 0, max_cost, "root cost")
        _json_text(certificate, MAX_CERTIFICATE_BYTES)
        checked = set()
        alternatives = 0
        branches = 0
        terminal_checks = 0

        def check(counts, remaining):
            nonlocal alternatives, branches, terminal_checks
            key = (counts, remaining)
            if key in checked:
                return
            if key not in claims:
                raise ValueError("missing alternative-query child")
            possible = {w for i, w in enumerate(worlds) if counts[i] <= k}
            candidates = []
            if objective == "identification":
                if len(possible) == 1:
                    candidates.append((0, {"kind": "identify", "id": next(iter(possible))}))
            else:
                for action in model["actions"]:
                    terminal_checks += 1
                    if possible <= set(action["success_worlds"]):
                        candidates.append((action["cost"], {"kind": "act", "id": action["id"]}))
            if not any(value == 0 for value, _ in candidates):
                for qi, query in enumerate(queries):
                    if not remaining & (1 << qi):
                        continue
                    alternatives += 1
                    child_values = []
                    for reading in (0, 1):
                        # No bitmask-layer operations from the optimizer are
                        # reused here. A mismatch spends one globally bounded
                        # fault; eliminated worlds remain eliminated.
                        child = tuple(min(k+1, counts[i] + int(query["responses"][w] != reading))
                                      for i, w in enumerate(worlds))
                        if not any(c <= k for c in child):
                            continue
                        branches += 1
                        rest = remaining & ~(1 << qi)
                        check(child, rest)
                        child_values.append(claims[(child, rest)][0])
                    if child_values and all(v is not None for v in child_values):
                        candidates.append((query["cost"] + max(child_values),
                                           {"kind": "query", "id": query["id"]}))
            expected = min((value for value, _ in candidates), default=None)
            claimed, selected = claims[key]
            if claimed != expected or (expected is not None and (claimed, selected) not in candidates):
                raise ValueError("complete minimax recurrence or attaining choice mismatch")
            checked.add(key)

        initial = (tuple(root[0]), root[1])
        check(*initial)
        if checked != set(claims):
            raise ValueError("unreachable certificate states")
        if certificate["value"] != claims[initial][0]:
            raise ValueError("root summary differs from the checked root")
        return {"valid": True, "objective": objective, "value": certificate["value"],
                "guaranteed": certificate["value"] is not None, "max_corruptions": k,
                "problem_sha256": certificate["problem_sha256"], "checked_states": len(checked),
                "checked_query_alternatives": alternatives, "checked_outcome_branches": branches,
                "checked_terminal_actions": terminal_checks,
                "scope": "exact finite worst-case query plus terminal-action cost under a shared flip budget"}
    except (ValueError, TypeError, KeyError, IndexError, RecursionError, OverflowError) as exc:
        return {"valid": False, "error": str(exc)[:240]}


def extract_robust_policy(problem, certificate):
    """Extract an observation-only DAG after verifying a finite cost certificate."""
    result = verify_robust_certificate(problem, certificate)
    if not result["valid"] or certificate["value"] is None:
        raise ValueError("no verified finite attaining policy")
    model = validate_problem(problem)
    worlds, k = model["worlds"], model["max_corruptions"]
    queries = {q["id"]: (i, q) for i, q in enumerate(model["experiments"])}
    claims = {(tuple(row[0]), row[1]): row[3] for row in certificate["nodes"]}
    nodes, indices = [], {}

    def emit(counts, remaining):
        key = (counts, remaining)
        if key in indices:
            return indices[key]
        index = len(nodes)
        indices[key] = index
        nodes.append(None)
        choice = dict(claims[key])
        if choice["kind"] == "query":
            qi, query = queries[choice["id"]]
            branches = {}
            for reading in (0, 1):
                updated = tuple(min(k+1, count + int(query["responses"][w] != reading))
                                for count, w in zip(counts, worlds))
                if any(count <= k for count in updated):
                    branches[str(reading)] = emit(updated, remaining & ~(1 << qi))
            choice["branches"] = branches
        nodes[index] = choice
        return index

    initial = certificate["root"]
    root = emit(tuple(initial[0]), initial[1])
    policy = {"schema": POLICY_SCHEMA, "problem_sha256": _model_digest(model),
              "objective": certificate["objective"], "budget": certificate["value"],
              "root": root, "nodes": nodes}
    _json_text(policy, MAX_CERTIFICATE_BYTES)
    return policy


def verify_robust_policy(problem, policy, *, expected_objective=None):
    """Replay every allowed corruption history in each fixed world.

    No certificate, minimax recurrence, optimizer, or belief-state update is
    consulted. Successful action membership is tested directly in the fixed
    world. Memoization merges equal (world, node, used queries, faults used)
    continuations while preserving exact path multiplicities and cost extrema.
    """
    try:
        model = validate_problem(problem)
        _keys(policy, {"schema", "problem_sha256", "objective", "budget", "root", "nodes"})
        if type(policy["schema"]) is not str or policy["schema"] != POLICY_SCHEMA:
            raise ValueError("unsupported policy schema")
        if _digest_text(policy["problem_sha256"]) != _model_digest(model):
            raise ValueError("policy does not bind the trusted problem")
        objective = _objective(policy["objective"])
        if expected_objective is not None and objective != _objective(expected_objective):
            raise ValueError("policy objective differs from the externally pinned objective")
        budget = _integer(policy["budget"], 0, _cost_bound(model), "policy budget")
        nodes = policy["nodes"]
        if type(nodes) is not list or not 1 <= len(nodes) <= MAX_STATES:
            raise ValueError("invalid policy node count")
        root = _integer(policy["root"], 0, len(nodes)-1, "policy root")
        queries = {q["id"]: (i, q) for i, q in enumerate(model["experiments"])}
        actions = {a["id"]: a for a in model["actions"]}
        declared_edges = set()
        for index, node in enumerate(nodes):
            if type(node) is not dict or type(node.get("kind")) is not str:
                raise ValueError("invalid policy node")
            kind = node["kind"]
            if kind == "query":
                _keys(node, {"kind", "id", "branches"})
                if _name(node["id"]) not in queries:
                    raise ValueError("unknown policy experiment")
                branches = node["branches"]
                if type(branches) is not dict or not branches or not set(branches) <= {"0", "1"}:
                    raise ValueError("policy branches must use binary string keys")
                for reading, child in branches.items():
                    _integer(child, 0, len(nodes)-1, "policy child")
                    declared_edges.add((index, reading))
            else:
                _keys(node, {"kind", "id"})
                _name(node["id"])
                if kind == "act":
                    if objective != "action" or node["id"] not in actions:
                        raise ValueError("invalid terminal action for objective")
                elif kind == "identify":
                    if objective != "identification" or node["id"] not in model["worlds"]:
                        raise ValueError("invalid identified world for objective")
                else:
                    raise ValueError("unknown policy node kind")
        _json_text(policy, MAX_CERTIFICATE_BYTES)
        visits = 0
        used_nodes, used_edges = set(), set()
        k = model["max_corruptions"]
        per_world = []

        @lru_cache(maxsize=None)
        def replay(world, index, used_queries, faults_used):
            nonlocal visits
            visits += 1
            if visits > MAX_REPLAY_STATES:
                raise ValueError("policy replay state cap exceeded; no complete replay claim")
            used_nodes.add(index)
            node = nodes[index]
            if node["kind"] == "act":
                action = actions[node["id"]]
                if world not in action["success_worlds"]:
                    raise ValueError("terminal action fails in a permitted world/history")
                return action["cost"], action["cost"], 1, 0
            if node["kind"] == "identify":
                if node["id"] != world:
                    raise ValueError("identified world is wrong in a permitted history")
                return 0, 0, 1, 0
            qi, query = queries[node["id"]]
            if used_queries & (1 << qi):
                raise ValueError("policy repeats an experiment or contains a reachable cycle")
            truthful = query["responses"][world]
            outcomes = [(truthful, faults_used)]
            if faults_used < k:
                outcomes.append((1-truthful, faults_used+1))
            values = []
            for reading, consumed in outcomes:
                label = str(reading)
                if label not in node["branches"]:
                    raise ValueError("policy omits an allowed corruption outcome")
                used_edges.add((index, label))
                values.append(replay(world, node["branches"][label], used_queries | (1 << qi), consumed))
            return (query["cost"] + min(v[0] for v in values),
                    query["cost"] + max(v[1] for v in values),
                    sum(v[2] for v in values), 1 + max(v[3] for v in values))

        for world in model["worlds"]:
            low, high, leaves, steps = replay(world, root, 0, 0)
            if high > budget:
                raise ValueError("policy exceeds its declared cost budget")
            per_world.append({"world": world, "best_cost": low, "worst_cost": high,
                              "corruption_histories": leaves, "max_queries": steps})
        if used_nodes != set(range(len(nodes))) or used_edges != declared_edges:
            raise ValueError("policy contains unreachable nodes or observation branches")
        return {"valid": True, "objective": objective, "budget": budget,
                "worst_cost": max(row["worst_cost"] for row in per_world),
                "best_cost": min(row["best_cost"] for row in per_world),
                "worlds_checked": len(per_world), "max_corruptions": k,
                "corruption_histories_checked": sum(row["corruption_histories"] for row in per_world),
                "replay_states": visits, "policy_nodes_checked": len(used_nodes),
                "per_world": per_world,
                "scope": "all allowed corruption paths of this policy in every fixed listed world; upper bound only"}
    except (ValueError, TypeError, KeyError, IndexError, RecursionError, OverflowError) as exc:
        return {"valid": False, "error": str(exc)[:240]}


def _observed_evidence(model, observations):
    queries = {q["id"]: (i, q) for i, q in enumerate(model["experiments"])}
    if type(observations) is not list or len(observations) > len(queries):
        raise ValueError("invalid observation count")
    seen = set()
    conflicts = {w: [] for w in model["worlds"]}
    remaining, spent = (1 << len(queries)) - 1, 0
    for observed in observations:
        _keys(observed, {"experiment", "outcome"})
        experiment = _name(observed["experiment"])
        if experiment not in queries or experiment in seen:
            raise ValueError("unknown or repeated observed experiment")
        reading = _integer(observed["outcome"], 0, 1, "observed binary outcome")
        seen.add(experiment)
        qi, query = queries[experiment]
        remaining &= ~(1 << qi)
        spent += query["cost"]
        for world in model["worlds"]:
            if query["responses"][world] != reading:
                conflicts[world].append(experiment)
    return conflicts, remaining, spent


def evidence_state(problem, observations):
    """Reconstruct public evidence without choosing or revealing the actual world.

    Observations are distinct ``{experiment: ID, outcome: 0|1}`` records. Actual
    mismatch counts are returned; ``state`` clips eliminated counts at k+1, as
    in certificates. An empty possible-world set flags violated assumptions.
    """
    model = validate_problem(problem)
    conflicts, remaining, spent = _observed_evidence(model, observations)
    counts = {w: len(conflicts[w]) for w in model["worlds"]}
    k = model["max_corruptions"]
    return {"problem_sha256": _model_digest(model), "mismatch_counts": counts,
            "possible_worlds": [w for w in model["worlds"] if counts[w] <= k],
            "state": [[min(k+1, counts[w]) for w in model["worlds"]], remaining],
            "remaining_experiments": [q["id"] for i, q in enumerate(model["experiments"])
                                      if remaining & (1 << i)],
            "query_cost": spent, "observations": len(observations),
            "max_corruptions": k, "conflicts": conflicts}


def verify_completion_evidence(problem, observations, action_id, exclusions=None):
    """Check sufficient *observed* evidence for one terminal action.

    If ``exclusions`` is supplied, it must have exactly one
    ``{world, conflicts: [experiment IDs]}`` entry per world in which that action
    fails, each naming k+1 distinct actually observed contradictions. Worlds
    sharing a valid action need not be distinguished or excluded. The runtime
    must separately execute and score any required irreversible action.
    """
    try:
        model = validate_problem(problem)
        evidence = evidence_state(model, observations)
        _name(action_id)
        actions = {a["id"]: a for a in model["actions"]}
        if action_id not in actions:
            raise ValueError("unknown completion action")
        action = actions[action_id]
        possible = set(evidence["possible_worlds"])
        if not possible:
            raise ValueError("no listed world fits the stated corruption bound")
        safe = set(action["success_worlds"])
        if not possible <= safe:
            raise ValueError("completion fails in a still-possible world")
        unsafe = set(model["worlds"]) - safe
        required_conflicts = model["max_corruptions"] + 1
        if exclusions is not None:
            if type(exclusions) is not list or len(exclusions) != len(unsafe):
                raise ValueError("one exclusion witness is required for each unsafe world")
            covered = set()
            for entry in exclusions:
                _keys(entry, {"world", "conflicts"})
                world = _name(entry["world"])
                if world not in unsafe or world in covered:
                    raise ValueError("witness worlds must be distinct and unsafe for the action")
                witnesses = entry["conflicts"]
                if (type(witnesses) is not list or len(witnesses) != required_conflicts
                        or any(type(q) is not str for q in witnesses)
                        or len(set(witnesses)) != len(witnesses)):
                    raise ValueError("each exclusion needs k+1 distinct experiment identifiers")
                if not set(witnesses) <= set(evidence["conflicts"][world]):
                    raise ValueError("exclusion does not cite observed contradictions")
                covered.add(world)
            if covered != unsafe:
                raise ValueError("incomplete unsafe-world coverage")
        return {"valid": True, "action": action_id, "problem_sha256": _model_digest(model),
                "possible_worlds": evidence["possible_worlds"], "unsafe_worlds_excluded": len(unsafe),
                "witnesses_checked": exclusions is not None, "conflicts_required_per_unsafe_world": required_conflicts,
                "query_cost": evidence["query_cost"], "terminal_cost": action["cost"],
                "total_cost": evidence["query_cost"] + action["cost"],
                "scope": "observed evidence suffices under the declared fault bound; action execution is separate"}
    except (ValueError, TypeError, KeyError, IndexError, RecursionError, OverflowError) as exc:
        return {"valid": False, "error": str(exc)[:240]}


def completion_exclusions(problem, observations, action_id):
    """Construct minimal k+1-conflict witnesses from already observed evidence."""
    checked = verify_completion_evidence(problem, observations, action_id)
    if not checked["valid"]:
        raise ValueError(checked["error"])
    model = validate_problem(problem)
    state = evidence_state(model, observations)
    action = next(a for a in model["actions"] if a["id"] == action_id)
    return [{"world": w, "conflicts": state["conflicts"][w][:model["max_corruptions"]+1]}
            for w in model["worlds"] if w not in action["success_worlds"]]
