"""Complete and execute a decision under a global sensor-corruption budget.

The current world and faulty probe IDs belong to the evaluator. Certificates
cover every fixed world and every allowed corruption pattern, not just the
planted episode. Public policies see only the contract and actual responses.
"""
from __future__ import annotations

import copy
from functools import lru_cache
import json

from ..robust_decisions import (
    build_robust_certificate, extract_robust_policy, problem_digest,
    validate_problem, verify_robust_certificate, verify_robust_policy,
)
from ..types import Task, Verdict, canonical, fields


def _parity(value: int) -> int:
    return value.bit_count() % 2


def _make_contract(rng, split: str, difficulty: int) -> tuple[dict, str]:
    """Original finite fixtures, using classical repetition/linear codes."""
    overlap = False
    bypass = None
    faults = 1
    if split == "train":
        dimension = difficulty
        masks = [1 << bit for bit in range(dimension) for _ in range(3)]
        costs = [1] * len(masks)
        structure = f"repetition-{dimension}-bits-one-global-fault"
    elif split == "dev":
        if difficulty == 1:
            dimension, masks = 1, [1, 1, 1]
            structure = "repetition-one-bit"
        elif difficulty == 2:
            dimension, masks = 3, [1, 2, 3, 4, 5, 6]
            structure = "punctured-simplex-eight-worlds"
        else:
            dimension, masks = 4, [1, 2, 4, 8, 11, 13, 14]
            structure = "hamming-sixteen-worlds"
        costs = [1] * len(masks)
    elif difficulty < 3:
        dimension, masks = 3, [1, 2, 3, 4, 5, 6, 7]
        overlap = True
        costs = [1] * 7 if difficulty == 1 else [1, 2, 2, 3, 3, 4, 4]
        structure = "overlapping-action-regions"
        if difficulty == 2:
            bypass = rng.choice([5, 6, 7])
            structure = "weighted-overlap-with-robust-bypass"
    else:
        dimension, masks = 3, [1, 2, 3, 4, 5, 6, 7, 1, 2, 4]
        costs = [1] * 10
        faults = 2
        structure = "extended-simplex-two-global-faults"

    concrete = list(range(1 << dimension))
    rng.shuffle(concrete)
    worlds = [f"w{i:02d}" for i in range(len(concrete))]
    columns = list(zip(masks, costs))
    rng.shuffle(columns)
    experiments = []
    for index, (mask, cost) in enumerate(columns):
        polarity = rng.randrange(2)
        experiments.append({
            "id": f"q{index:02d}", "cost": cost,
            "responses": {label: _parity(value & mask) ^ polarity
                          for label, value in zip(worlds, concrete)},
        })
    actions = []
    if overlap:
        for group in range(4):
            actions.append({
                "cost": 1 if difficulty == 1 else [2, 3, 1, 2][group],
                "success_worlds": [label for label, value in zip(worlds, concrete)
                                   if value % 4 != group],
            })
    else:
        actions = [{"cost": 2 if faults == 2 else 1, "success_worlds": [label]}
                   for label in worlds]
    if bypass is not None:
        actions.append({"cost": bypass, "success_worlds": list(worlds)})
    rng.shuffle(actions)
    for index, action in enumerate(actions):
        action["id"] = f"a{index:02d}"
    problem = {"schema": "causalfill.robust-decision.v1", "worlds": worlds,
               "max_corruptions": faults, "actions": actions,
               "experiments": experiments}
    validate_problem(problem)
    return problem, structure


@lru_cache(maxsize=8)
def _certified_public_contract(serialized: str) -> tuple[dict, dict]:
    """Cache only public model-derived artifacts; never store a selected world."""
    problem = json.loads(serialized)
    certificate = build_robust_certificate(problem, objective="action")
    checked = verify_robust_certificate(problem, certificate, expected_objective="action")
    if not checked["valid"] or certificate["value"] is None:
        raise ValueError("generated robust task lacks a checked finite solution")
    policy = extract_robust_policy(problem, certificate)
    replay = verify_robust_policy(problem, policy, expected_objective="action")
    if not replay["valid"]:
        raise ValueError("generated robust policy failed independent replay")
    return certificate, policy


def completion_for_history(problem: dict, observations: list[dict], action_id: str) -> dict:
    """Construct witnesses using only public data and actually observed bits."""
    action = next(a for a in problem["actions"] if a["id"] == action_id)
    table = {q["id"]: q["responses"] for q in problem["experiments"]}
    excluded = []
    for world in problem["worlds"]:
        if world not in action["success_worlds"]:
            conflicts = [o["experiment"] for o in observations
                         if table[o["experiment"]][world] != o["outcome"]]
            excluded.append({"world": world,
                             "conflicts": conflicts[:problem["max_corruptions"] + 1]})
    return {"problem_sha256": problem_digest(problem), "action": action_id,
            "exclusions": excluded}


class RobustSensingTask(Task):
    family = "robust_sensing"

    def __init__(self, seed: int, split: str = "dev", difficulty: int = 2, twin: int = 0):
        super().__init__(seed, split, difficulty, twin)
        self.twin_kind = "sensor_corruption"
        self._problem, structure = _make_contract(self.rng, split, difficulty)
        self._certificate, self._policy = _certified_public_contract(canonical(self._problem))
        self._problem_sha256 = problem_digest(self._problem)
        self._queries = {q["id"]: q for q in self._problem["experiments"]}
        self._actions = {a["id"]: a for a in self._problem["actions"]}
        self._world = self.rng.choice(self._problem["worlds"])
        sampled_faults = self.rng.sample(list(self._queries), self._problem["max_corruptions"])
        self._faults = frozenset(sampled_faults if twin else [])
        self._reset_runtime()
        self.operational_budget = self._certificate["value"]
        # One contract read and one optional explanatory read are outside the
        # finite operational optimum. No other setup optimum is claimed.
        self.budget = self.operational_budget + 2
        self.max_calls = len(self._queries) + 12
        self.structural_signature = f"robust_sensing:{structure}:v1"
        self.prompt = (
            "Signal Repair: complete a controller's missing routing decision and execute it. "
            "Exactly one listed operating world is current. The truthful binary probe table and "
            "successful worlds for every action are public. Across the entire episode, at most "
            f"{self._problem['max_corruptions']} distinct probe readings may be flipped. "
            "This is one shared corruption limit, not a new allowance for each probe. Each probe "
            "can be used once. Choose evidence and then commit an action irreversibly. Success "
            "requires the actual operation to succeed AND that the pre-commit observations justify "
            "that action in every world compatible with the corruption limit. Full world "
            "identification is unnecessary when one action succeeds in all remaining worlds. "
            "The operational budget limits probe costs plus the committed action separately "
            "from setup-read credits; unused setup credits cannot increase that limit. "
            "Complete the action and evidence holes after committing. For each world where the "
            "chosen action would fail, cite at least k+1 distinct observed probes contradicting "
            "that world's truthful table. Read /formal/robust-sensing.json."
        )
        self.slots = {
            "problem_sha256": {"type": "string", "description": "Exact digest in the public contract."},
            "action": {"type": "string", "description": "ID of the action actually committed."},
            "exclusions": {"type": "array[object]", "description":
                "One {world, conflicts:[experiment IDs]} for every world outside the chosen action's success set; each needs k+1 distinct observed contradictions."},
        }
        self.tools = {}
        for query in self._problem["experiments"]:
            self.tools["probe_" + query["id"]] = {
                "description": f"Read probe {query['id']} once; the response may be corrupted within the shared limit.",
                "arguments": {}, "cost": query["cost"],
            }
        for action in self._problem["actions"]:
            self.tools["commit_" + action["id"]] = {
                "description": f"Irreversibly execute action {action['id']}; later probing is unavailable. Outcome stays evaluator-only.",
                "arguments": {}, "cost": action["cost"],
            }
        self.files = {
            "/formal/robust-sensing.json": json.dumps({
                "problem": self._problem, "problem_sha256": self._problem_sha256,
                "operational_budget": self.operational_budget,
                "budget_scope": "probe costs plus one terminal action; setup reads excluded",
                "setup_credit_rule": "unused setup credits cannot increase the operational budget",
                "query_rule": "each listed probe is available once",
                "fault_rule": "at most max_corruptions flipped responses in the whole episode",
                "fill_rule": "witnesses must refer to distinct observations made before commitment",
            }, separators=(",", ":")),
            "/docs/robust-sensing.txt": (
                "For each candidate world, count how many observed bits disagree with its truthful "
                "table. Retain it while that count is at most k. A single disagreement cannot "
                "eliminate a world when k is positive. Do not reset disagreement counts when "
                "choosing another probe. An action is justified when it succeeds in every "
                "remaining world. A successful common bypass needs no identifying evidence.\n"
                "Probes are one-use devices. Repeated or malformed calls are errors and still "
                "consume Session budget, without changing the hidden case. Commitment is final; "
                "a certificate without executing the action does not complete the task.\n"
                "The advertised operational limit is an independently checked minimum worst-case "
                "cost in this finite model. Planning computation, file reads and final submission "
                "are separate. Public generators and solved examples are development material.\n"
                "The clean/corrupted twin changes only the selected faulty probe set. An assigned "
                "fault may not be exposed if that probe is never called; assignment and observed "
                "corruption counts are reported separately in evaluator results."
            ),
        }

    def _reset_runtime(self):
        self.observations: list[dict] = []
        self.used: set[str] = set()
        self.committed: str | None = None
        self.commit_observations: list[dict] = []
        self.operational_cost = 0
        self._observed_faults = 0

    def clone_for_case(self, world: str, faults: list[str] | tuple[str, ...]) -> "RobustSensingTask":
        """Evaluator audit only. Clone a fresh runtime without regenerating its model."""
        if (world not in self._problem["worlds"] or len(faults) != len(set(faults))
                or len(faults) > self._problem["max_corruptions"]
                or any(q not in self._queries for q in faults)):
            raise ValueError("invalid evaluator case")
        clone = copy.copy(self)
        clone._world, clone._faults = world, frozenset(faults)
        clone._reset_runtime()
        return clone

    def public_problem(self) -> dict:
        """Evaluator export of the same contract delivered through read_file."""
        return copy.deepcopy(self._problem)

    def robust_certificate(self) -> dict:
        """Author/evaluator artifact; not part of a scored solver's public files."""
        return copy.deepcopy(self._certificate)

    def robust_policy(self) -> dict:
        """Author/evaluator artifact, never an episode observation."""
        return copy.deepcopy(self._policy)

    def query(self, name: str, args: dict) -> dict:
        fields(args, set())
        if self.committed is not None:
            raise ValueError("operation already committed; submit its completion")
        if name.startswith("probe_") and name[6:] in self._queries:
            query = name[6:]
            if query in self.used:
                raise ValueError("probe already consumed")
            if self.operational_cost + self._queries[query]["cost"] > self.operational_budget:
                raise ValueError("operational budget exhausted; unused setup credits cannot buy probes")
            self.used.add(query)
            bit = self._queries[query]["responses"][self._world] ^ int(query in self._faults)
            self.observations.append({"experiment": query, "outcome": bit})
            self.operational_cost += self._queries[query]["cost"]
            self._observed_faults += int(query in self._faults)
            return {"experiment": query, "outcome": bit,
                    "remaining_probes": len(self._queries) - len(self.used)}
        if name.startswith("commit_") and name[7:] in self._actions:
            action = name[7:]
            if self.operational_cost + self._actions[action]["cost"] > self.operational_budget:
                raise ValueError("operational budget exhausted; unused setup credits cannot buy an action")
            self.committed = action
            self.commit_observations = copy.deepcopy(self.observations)
            self.operational_cost += self._actions[action]["cost"]
            return {"action": action, "committed": True,
                    "next_step": "Submit the action and observed exclusion witnesses."}
        raise ValueError("unknown robust-sensing tool")

    def _mismatch_counts(self, observations: list[dict]) -> dict[str, int]:
        # Direct runtime calculation, separate from the planner/checker state code.
        return {w: sum(self._queries[o["experiment"]]["responses"][w] != o["outcome"]
                       for o in observations) for w in self._problem["worlds"]}

    def evaluate(self, fill: dict) -> Verdict:
        try:
            fields(fill, {"problem_sha256", "action", "exclusions"})
            if type(fill["problem_sha256"]) is not str or fill["problem_sha256"] != self._problem_sha256:
                raise ValueError("completion is not bound to the public problem")
            action_id = fill["action"]
            if type(action_id) is not str or action_id not in self._actions:
                raise ValueError("unknown action")
            action = self._actions[action_id]
            if self.committed != action_id:
                raise ValueError("completion must name the action actually committed")
            k = self._problem["max_corruptions"]
            unsafe = set(self._problem["worlds"]) - set(action["success_worlds"])
            entries = fill["exclusions"]
            if type(entries) is not list or len(entries) != len(unsafe):
                raise ValueError("one exclusion is required for each unsafe world")
            observed = {o["experiment"]: o["outcome"] for o in self.commit_observations}
            seen, valid = set(), 0
            for item in entries:
                fields(item, {"world", "conflicts"})
                world, conflicts = item["world"], item["conflicts"]
                if type(world) is not str or world not in unsafe or world in seen:
                    raise ValueError("unsafe worlds must be covered exactly once")
                seen.add(world)
                if (type(conflicts) is not list or not k + 1 <= len(conflicts) <= len(self._queries)
                        or any(type(q) is not str for q in conflicts)
                        or len(set(conflicts)) != len(conflicts)):
                    raise ValueError("exclusion needs distinct observed conflicting probe IDs")
                if all(q in observed and self._queries[q]["responses"][world] != observed[q]
                       for q in conflicts):
                    valid += 1
            counts = self._mismatch_counts(self.commit_observations)
            possible = [w for w, count in counts.items() if count <= k]
            justified = bool(possible) and all(w in action["success_worlds"] for w in possible)
            outcome = self._world in action["success_worlds"]
            within_budget = self.operational_cost <= self.operational_budget
            witnesses_complete = valid == len(unsafe)
            success = outcome and justified and witnesses_complete and within_budget
            return Verdict(success, valid / len(unsafe) if unsafe else 1.0, float(outcome),
                           float(justified), {
                "actual_operation_succeeded": outcome, "action_justified_before_commit": justified,
                "valid_exclusions": valid, "required_exclusions": len(unsafe),
                "compatible_worlds_at_commit": len(possible), "full_identification_required": False,
                "assigned_corruptions": len(self._faults), "observed_corruptions": self._observed_faults,
                "global_corruption_limit": k, "queries_used": len(self.used),
                "operational_cost": self.operational_cost, "certified_operational_budget": self.operational_budget,
                "within_operational_budget": within_budget,
                "scope": "finite symbolic operation with evidence valid under a global bounded corruption model",
            })
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            return Verdict(False, details={"invalid_fill": str(exc)[:240]})

    def reference_actions(self) -> list[tuple[str, dict]]:
        node = self._policy["root"]
        actions = []
        while self._policy["nodes"][node]["kind"] == "query":
            item = self._policy["nodes"][node]
            query = item["id"]
            actions.append(("probe_" + query, {}))
            bit = self._queries[query]["responses"][self._world] ^ int(query in self._faults)
            node = item["branches"][str(bit)]
        leaf = self._policy["nodes"][node]
        actions.append(("commit_" + leaf["id"], {}))
        return actions

    def reference_answer(self) -> dict:
        if self.committed is None:
            raise ValueError("reference actions must execute before completion")
        return completion_for_history(self._problem, self.commit_observations, self.committed)


def solve_robust_sensing(public: dict, call) -> dict:
    """Task-aware scripted control using only a public model and tool callback."""
    raw = call("read_file", {"path": "/formal/robust-sensing.json"})
    contract = json.loads(raw["content"])
    problem = contract["problem"]
    if problem_digest(problem) != contract["problem_sha256"]:
        raise ValueError("public contract digest mismatch")
    _, policy = _certified_public_contract(canonical(problem))
    node, observations = policy["root"], []
    while policy["nodes"][node]["kind"] == "query":
        item = policy["nodes"][node]
        result = call("probe_" + item["id"], {})
        observations.append({"experiment": item["id"], "outcome": result["outcome"]})
        node = item["branches"][str(result["outcome"])]
    action = policy["nodes"][node]["id"]
    result = call("commit_" + action, {})
    if not result.get("committed"):
        raise ValueError("action did not execute")
    return completion_for_history(problem, observations, action)
