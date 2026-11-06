"""Choose dependency-relevant gaps while preserving an explicit evidence path.

Selection difficulty is a design proxy, never a measured frontier-model score.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
import random


@dataclass(frozen=True)
class Component:
    name: str
    depends_on: tuple[str, ...] = ()
    token_count: int = 1
    evidence_cost: int | None = None
    consequence_weight: float = 1.0


class MaskPlanner:
    def __init__(self, components: list[Component]):
        if not 1 <= len(components) <= 20:
            raise ValueError("a graph must have 1..20 components")
        self.nodes = {c.name: c for c in components}
        if len(self.nodes) != len(components):
            raise ValueError("duplicate component")
        for c in components:
            if c.token_count < 1 or c.consequence_weight < 0:
                raise ValueError("invalid component cost or weight")
            if c.evidence_cost is not None and c.evidence_cost < 0:
                raise ValueError("negative evidence cost")
            if any(d not in self.nodes for d in c.depends_on):
                raise ValueError("unknown dependency")
        self._topological()

    def _topological(self) -> list[str]:
        remaining = set(self.nodes)
        ordered = []
        while remaining:
            ready = sorted(n for n in remaining if not set(self.nodes[n].depends_on)&remaining)
            if not ready:
                raise ValueError("dependency graph must be acyclic")
            ordered.extend(ready)
            remaining.difference_update(ready)
        return ordered

    def descendants(self, name: str) -> set[str]:
        reached = {name}
        for n in self._topological():
            if set(self.nodes[n].depends_on)&reached:
                reached.add(n)
        return reached

    def choose(self, count: int, evidence_budget: int, strategy: str = "causal", seed: int = 0,
               token_target: int | None = None) -> dict:
        if type(count) is not int or not 1 <= count <= min(6, len(self.nodes)):
            raise ValueError("mask count must be 1..6 and no greater than graph size")
        if strategy not in ("causal", "random"):
            raise ValueError("strategy must be causal or random")
        candidates = []
        for subset in combinations(sorted(self.nodes), count):
            nodes = [self.nodes[n] for n in subset]
            # Conservative independent-observation model; shared tools require custom certificates.
            if any(n.evidence_cost is None for n in nodes):
                continue
            cost = sum(n.evidence_cost for n in nodes)
            tokens = sum(n.token_count for n in nodes)
            if cost > evidence_budget or (token_target is not None and tokens != token_target):
                continue
            influenced = set().union(*(self.descendants(n) for n in subset))
            impact = sum(self.nodes[n].consequence_weight for n in influenced)
            candidates.append({"masked": list(subset), "evidence_cost_bound": cost,
                               "tokens_masked": tokens, "influence_proxy": impact,
                               "affected_components": sorted(influenced)})
        if not candidates:
            raise ValueError("no mask satisfies evidence and size constraints")
        result = (max(candidates, key=lambda c: (c["influence_proxy"], -c["evidence_cost_bound"]))
                  if strategy == "causal" else random.Random(seed).choice(candidates))
        return {**result, "strategy": strategy, "candidate_count": len(candidates),
                "qualification": "graph proxy; recoverability assumptions require domain validation"}

