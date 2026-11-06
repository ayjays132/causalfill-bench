"""Small evaluator-side task interface. Never expose Task objects to evaluated agents."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import random
from dataclasses import dataclass, field
from typing import Any

SPLITS = ("train", "dev", "transfer")
# Version the meaning of evaluator results independently of the package version.
# v2 preserves committed-operation diagnostics on rejected/unfinished completions
# and groups equivalent Signal Repair mechanisms under one structural signature.
SCORING_VERSION = "causalfill.scoring.v2"


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def strict_int(value: Any, low: int, high: int, name: str = "value") -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be an integer in [{low}, {high}]")
    return value


def finite_number(value: Any, low: float, high: float, name: str = "value") -> float:
    if type(value) not in (int, float) or not low <= value <= high or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number in [{low}, {high}]")
    return float(value)


def fields(args: dict, expected: set[str]) -> None:
    if not isinstance(args, dict) or set(args) != expected:
        raise ValueError("required argument keys: " + ", ".join(sorted(expected)))


@dataclass
class Verdict:
    success: bool
    recovery: float = 0.0
    outcome: float = 0.0
    safety: float = 1.0
    details: dict = field(default_factory=dict)


class Task:
    family = "base"

    def __init__(self, seed: int, split: str = "dev", difficulty: int = 2, twin: int = 0):
        if split not in SPLITS:
            raise ValueError(f"split must be one of {SPLITS}")
        strict_int(seed, 0, 2**63 - 1, "seed")
        strict_int(difficulty, 1, 3, "difficulty")
        strict_int(twin, 0, 1, "twin")
        self.seed, self.split, self.difficulty, self.twin = seed, split, difficulty, twin
        # Exclude twin: the domain must alter exactly one chosen causal parameter.
        self.rng = random.Random(digest([type(self).__name__, seed, split, difficulty]))
        self.prompt = ""
        self.files: dict[str, str] = {}
        self.slots: dict = {}
        self.tools: dict = {}
        self.budget = 50
        self.max_calls = 70
        self.answerable = True
        self.structural_signature = f"{self.family}:{split}:v1"

    def public(self) -> dict:
        return copy.deepcopy({
            "family": self.family, "difficulty": self.difficulty,
            "prompt": self.prompt, "slots": self.slots,
            "files": sorted(self.files), "tools": self.tools,
            "budget": self.budget, "max_calls": self.max_calls,
        })

    def query(self, name: str, args: dict) -> dict:
        raise ValueError("unknown domain tool")

    def evaluate(self, fill: dict) -> Verdict:
        raise NotImplementedError

    def failure_verdict(self, details: dict) -> Verdict:
        """Report a failed completion, retaining task-specific state if applicable.

        Stateful tasks may override this evaluator-only hook to report an action
        that already happened before an abstention, invalid fill or termination.
        The default preserves the behavior of tasks without such diagnostics.
        """
        return Verdict(False, details=copy.deepcopy(details))

    def reference_answer(self) -> dict:
        raise NotImplementedError

    def reference_actions(self) -> list[tuple[str, dict]]:
        return []

