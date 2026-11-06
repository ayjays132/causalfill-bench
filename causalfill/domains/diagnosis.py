"""Finite experiment planning with a certified optimal worst-case query budget."""
from __future__ import annotations

import copy
import json

from ..decision_certificates import (
    build_decision_certificate, elimination_certificate, extract_decision_tree,
    information_lower_bound, table_digest, validate_table,
    verify_decision_certificate, verify_decision_tree,
)
from ..types import Task, Verdict, fields, strict_int


def _response_table(rng, split: str, difficulty: int) -> list[list[int]]:
    bits = difficulty + 2
    worlds, width = 1 << bits, 4 + 2 * difficulty
    if split == "train":
        # Direct latent bits plus parity sensors: an explicit easy control.
        rows = [[(world >> bit) & 1 for bit in range(bits)] for world in range(worlds)]
        for _ in range(width - bits):
            selected = rng.sample(range(bits), rng.randrange(2, bits + 1))
            for row in rows:
                row.append(sum(row[bit] for bit in selected) % 2)
    elif split == "dev":
        # General response partitions. Draw distinct rows with an explicit cap.
        rows = []
        seen = set()
        for _ in range(4096):
            row = tuple(rng.randrange(2) for _ in range(width))
            if row not in seen:
                rows.append(list(row)); seen.add(row)
            if len(rows) == worlds:
                break
        if len(rows) != worlds:
            raise ValueError("bounded generation could not find distinct worlds")
    else:
        # Conditional sensors: determine the gate, then select relevant sensors.
        rows = []
        for world in range(worlds):
            gate = world & 1
            row = [gate]
            for bit in range(1, bits):
                value = (world >> bit) & 1
                row.extend([value if gate == 0 else 0, value if gate == 1 else 0])
            rows.append(row)
        while len(rows[0]) < width:
            exceptional = rng.randrange(worlds)
            for world, row in enumerate(rows):
                row.append(int(world == exceptional))
    # Opaque labels and polarity preserve the structural class, not the answer.
    rng.shuffle(rows)
    order = list(range(width)); rng.shuffle(order)
    flips = [rng.randrange(2) for _ in range(width)]
    result = [[row[q] ^ flips[j] for j, q in enumerate(order)] for row in rows]
    return [list(row) for row in validate_table(result)]


class DiagnosisTask(Task):
    family = "diagnosis"

    def __init__(self, seed: int, split: str = "dev", difficulty: int = 2, twin: int = 0):
        super().__init__(seed, split, difficulty, twin)
        self.twin_kind = "diagnostic_state"
        self._table = _response_table(self.rng, split, difficulty)
        self._world = (self.rng.randrange(len(self._table)) + twin) % len(self._table)
        self._certificate = build_decision_certificate(self._table)
        checked = verify_decision_certificate(self._table, self._certificate)
        if not checked["valid"]:
            raise ValueError("generated minimax certificate failed independent validation")
        self._tree = extract_decision_tree(self._table, self._certificate)
        tree_check = verify_decision_tree(self._table, self._tree)
        if not tree_check["valid"] or tree_check["depth"] != checked["optimal_depth"]:
            raise ValueError("strategy tree does not match the certified optimum")
        self.query_budget = checked["optimal_depth"]
        self.query_count = 0
        self.observations: list[tuple[int, int]] = []
        self.budget = self.query_budget + 2  # public table and optional manual.
        self.max_calls = self.query_budget + 8
        structure = {"train": "direct-parity", "dev": "random-partitions", "transfer": "conditional-sensors"}[split]
        self.structural_signature = f"diagnosis:{structure}:v1"
        self.prompt = (
            "Complete a missing diagnosis and certify it from experiments. Exactly one listed world is current. "
            "The public table lists every possible world's deterministic binary response to each experiment; "
            "it does not identify the current world. Choose experiments, identify the world, and for every "
            "other world cite an experiment you actually performed whose observed response excludes it. "
            "A lucky world guess without these elimination witnesses does not pass. "
            f"At most {self.query_budget} experiments are permitted, even if unused file-read cost remains. "
            "This is the independently checked minimum worst-case deterministic adaptive query depth for this table. "
            "Read /formal/diagnosis.json."
        )
        self.slots = {
            "world": {"type": "integer", "description": f"Current candidate-world index 0..{len(self._table)-1}."},
            "eliminations": {"type": "array[object]", "description":
                "Exactly one {world: competitor_index, experiment: observed_experiment_id} for every competing world."},
        }
        self.tools = {"experiment": {
            "description": "Observe one binary response from the current world; repeated experiments still count.",
            "arguments": {"id": f"integer 0..{len(self._table[0])-1}"}, "cost": 1,
        }}
        self.files = {
            "/formal/diagnosis.json": json.dumps({
                "world_count": len(self._table), "experiment_count": len(self._table[0]),
                "responses": self._table, "table_sha256": table_digest(self._table),
                "query_budget": self.query_budget,
                "binary_information_lower_bound": information_lower_bound(len(self._table)),
                "world_indices": "zero-based rows", "experiment_indices": "zero-based columns",
            }, separators=(",", ":")),
            "/docs/diagnosis.txt": (
                "The complete table defines the finite hypothesis class. All rows are distinct. "
                "An experiment has a deterministic, noiseless, binary response. You may synthesize an "
                "adaptive decision strategy using only the advertised column queries. No hidden experiment is allowed.\n"
                "Keep all worlds consistent with actual responses. Each elimination entry must name a competing "
                "world and a previously executed experiment on which that world's table response disagrees "
                "with the observed response. Cover every other world exactly once. The chosen world must agree "
                "with every observed response. Query IDs are column indices, not trace event IDs; the outer "
                "submission evidence field separately cites observed trace events.\n"
                "An optimal strategy minimizes the worst-case number of experiments. For a candidate set S, "
                "D(S)=0 if it is a singleton; otherwise D(S)=1+min_q max(D(S0),D(S1)) over informative columns. "
                "The evaluator independently checks a complete recurrence certificate and a strategy tree. "
                "A particular world's identification may terminate before the worst-case cap.\n"
                "The twin changes only the current categorical world, preserving this response table. This is "
                "diagnostic-state robustness, not a physical intervention experiment."
            ),
        }

    def decision_certificate(self) -> dict:
        """Evaluator/research export only; no target world is present in the artifact."""
        return copy.deepcopy(self._certificate)

    def query(self, name: str, args: dict) -> dict:
        if name != "experiment":
            raise ValueError("unknown diagnosis tool")
        fields(args, {"id"})
        query = strict_int(args["id"], 0, len(self._table[0])-1, "experiment id")
        if self.query_count >= self.query_budget:
            raise ValueError("certified experiment budget exhausted")
        outcome = self._table[self._world][query]
        self.query_count += 1
        self.observations.append((query, outcome))
        return {"experiment": query, "outcome": outcome,
                "remaining_experiments": self.query_budget-self.query_count}

    def evaluate(self, fill: dict) -> Verdict:
        try:
            fields(fill, {"world", "eliminations"})
            n, width = len(self._table), len(self._table[0])
            world = strict_int(fill["world"], 0, n-1, "world")
            entries = fill["eliminations"]
            if type(entries) is not list or len(entries) != n-1:
                raise ValueError("one elimination entry is required for each competing world")
            observed = dict(self.observations)
            seen = set()
            valid = 0
            for entry in entries:
                fields(entry, {"world", "experiment"})
                other = strict_int(entry["world"], 0, n-1, "competitor")
                query = strict_int(entry["experiment"], 0, width-1, "experiment")
                if other == world or other in seen:
                    raise ValueError("competitors must be distinct and exclude the chosen world")
                seen.add(other)
                if query in observed and self._table[other][query] != observed[query]:
                    valid += 1
            consistent = all(self._table[world][q] == value for q, value in self.observations)
            success = (world == self._world and consistent and valid == n-1 and
                       self.query_count <= self.query_budget)
            return Verdict(success, valid/(n-1), float(success), 1.0, {
                "candidate_consistent": consistent, "valid_eliminations": valid,
                "required_eliminations": n-1, "experiments_used": self.query_count,
                "optimal_worst_case_queries": self.query_budget,
                "binary_information_lower_bound": information_lower_bound(n),
                "certificate_states_checked": len(self._certificate["nodes"]),
                "verification_scope": "exact finite-table identification with observed elimination witnesses",
            })
        except (ValueError, TypeError, KeyError, IndexError) as exc:
            return Verdict(False, details={"invalid_fill": str(exc)[:240]})

    def reference_actions(self) -> list[tuple[str, dict]]:
        node = self._tree
        actions = []
        while "query" in node:
            query = node["query"]
            actions.append(("experiment", {"id": query}))
            node = node["one" if self._table[self._world][query] else "zero"]
        return actions

    def reference_answer(self) -> dict:
        # As in a stateful domain, reference actions must have been replayed.
        return {"world": self._world,
                "eliminations": elimination_certificate(self._table, self.observations, self._world)}
