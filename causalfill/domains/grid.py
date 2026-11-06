"""Original small-grid induction tasks with a bounded transformation language.

No ARC tasks are included.  The tiny, public generation grammar is designed
for controllable experiments and has an explicit identification witness.
"""

from __future__ import annotations

import itertools
import json
from typing import Any

from causalfill.types import Task, Verdict


MAX_SIDE = 8
COLORS = 5
MAX_OPERATIONS = 4
STRUCTURES = {
    "train": "recolor",
    "dev": "rotate-recolor",
    "transfer": "select-crop-rotate-recolor",
}


def _integer(value: Any, name: str, low: int, high: int) -> int:
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"{name} must be an integer in [{low}, {high}]")
    return value


def validate_grid(value: Any) -> list[list[int]]:
    if type(value) is not list or not 1 <= len(value) <= MAX_SIDE:
        raise ValueError("grid must have 1..8 rows")
    if type(value[0]) is not list or not 1 <= len(value[0]) <= MAX_SIDE:
        raise ValueError("grid must have 1..8 columns")
    width = len(value[0])
    result = []
    for row in value:
        if type(row) is not list or len(row) != width:
            raise ValueError("grid must be rectangular")
        result.append([_integer(cell, "cell", 0, COLORS - 1) for cell in row])
    return result


def validate_program(value: Any) -> list[dict]:
    if type(value) is not list or len(value) > MAX_OPERATIONS:
        raise ValueError("program must contain at most four operations")
    program = []
    for step in value:
        if type(step) is not dict or type(step.get("op")) is not str:
            raise ValueError("each operation must be an object with an op string")
        op = step["op"]
        if op == "recolor":
            if set(step) != {"op", "source", "target"}:
                raise ValueError("recolor needs exactly op, source, target")
            source = _integer(step["source"], "source", 1, 4)
            target = _integer(step["target"], "target", 1, 4)
            program.append({"op": op, "source": source, "target": target})
        elif op == "rotate90":
            if set(step) != {"op", "turns"}:
                raise ValueError("rotate90 needs exactly op and turns")
            program.append({"op": op, "turns": _integer(step["turns"], "turns", 0, 3)})
        elif op == "keep_color":
            if set(step) != {"op", "color"}:
                raise ValueError("keep_color needs exactly op and color")
            program.append({"op": op, "color": _integer(step["color"], "color", 1, 4)})
        elif op in {"crop", "flip_h"}:
            if set(step) != {"op"}:
                raise ValueError(f"{op} needs exactly op")
            program.append({"op": op})
        else:
            raise ValueError("unknown grid operation")
    return program


def _rotate(grid: list[list[int]]) -> list[list[int]]:
    return [list(row) for row in zip(*grid[::-1])]


def _crop(grid: list[list[int]]) -> list[list[int]]:
    occupied = [(r, c) for r, row in enumerate(grid) for c, value in enumerate(row) if value]
    if not occupied:
        return [[0]]
    top = min(r for r, _ in occupied)
    bottom = max(r for r, _ in occupied)
    left = min(c for _, c in occupied)
    right = max(c for _, c in occupied)
    return [row[left:right + 1] for row in grid[top:bottom + 1]]


def apply_program(grid: Any, program: Any) -> list[list[int]]:
    """Interpret the bounded DSL as data; never execute submitted source code."""
    output = validate_grid(grid)
    steps = validate_program(program)
    for step in steps:
        op = step["op"]
        if op == "rotate90":
            for _ in range(step["turns"]):
                output = _rotate(output)
        elif op == "flip_h":
            output = [row[::-1] for row in output]
        elif op == "crop":
            output = _crop(output)
        elif op == "keep_color":
            output = [[value if value == step["color"] else 0 for value in row] for row in output]
        elif op == "recolor":
            output = [[step["target"] if value == step["source"] else value for value in row] for row in output]
    return output


def candidate_programs(split: str) -> list[list[dict]]:
    """Public finite generation grammar, not a list of episode answers."""
    if split not in STRUCTURES:
        raise ValueError("split must be train, dev, or transfer")
    candidates = []
    for source in range(1, COLORS):
        for target in range(1, COLORS):
            if source == target:
                continue
            for turns in ((0,) if split == "train" else range(4)):
                program = []
                if split == "transfer":
                    program.extend([{"op": "keep_color", "color": source}, {"op": "crop"}])
                if split != "train":
                    program.append({"op": "rotate90", "turns": turns})
                program.append({"op": "recolor", "source": source, "target": target})
                candidates.append(program)
    return candidates


def diagnostic_grid() -> list[list[int]]:
    """One valid experiment that distinguishes the full public grammar.

    Each color has a different area and an oriented L shape with four distinct
    rotations. Thus selection, orientation, and target color are recoverable.
    """
    grid = [[0] * 8 for _ in range(8)]
    shapes = {
        1: [(0, 0), (1, 0), (1, 1)],
        2: [(0, 4), (1, 4), (2, 4), (2, 5)],
        3: [(4, 0), (5, 0), (6, 0), (6, 1), (6, 2)],
        4: [(4, 4), (5, 4), (6, 4), (7, 4), (7, 5), (7, 6)],
    }
    for color, cells in shapes.items():
        for row, column in cells:
            grid[row][column] = color
    return grid


def infer_program(split: str, observations: list[dict]) -> list[dict]:
    """Solve from supplied input/output evidence, without task or grader access."""
    if type(observations) is not list or not observations:
        raise ValueError("at least one input/output observation is required")
    pairs = []
    for observation in observations:
        if type(observation) is not dict or set(observation) != {"input", "output"}:
            raise ValueError("each observation needs exactly input and output")
        pairs.append((validate_grid(observation["input"]), validate_grid(observation["output"])))
    matches = [
        program for program in candidate_programs(split)
        if all(apply_program(grid, program) == output for grid, output in pairs)
    ]
    if len(matches) != 1:
        raise ValueError("observations do not identify exactly one grammar candidate")
    return matches[0]


class GridTask(Task):
    def __init__(self, seed: int, split: str = "dev", difficulty: int = 2, twin: int = 0):
        super().__init__(seed, split, difficulty, twin)
        self.family = "grid"
        self.structural_signature = f"grid:{STRUCTURES[split]}:v1"
        self.answerable = True
        self.budget = {1: 10, 2: 7, 3: 5}[difficulty]
        self.max_calls = self.budget + 5
        self._source = self.rng.randrange(1, COLORS)
        targets = [color for color in range(1, COLORS) if color != self._source]
        target_index = self.rng.randrange(len(targets))
        self._target_color = targets[(target_index + twin) % len(targets)]
        self._turns = self.rng.randrange(4)
        self._program = []
        if split == "transfer":
            self._program.extend([{"op": "keep_color", "color": self._source}, {"op": "crop"}])
        if split != "train":
            self._program.append({"op": "rotate90", "turns": self._turns})
        self._program.append({"op": "recolor", "source": self._source, "target": self._target_color})

        demo_inputs = [
            [[1, 2], [3, 4]],
            [[0, 1, 0], [2, 3, 4], [0, 0, 0]],
            [[0, 1, 1, 0], [2, 0, 3, 0], [2, 0, 3, 4], [0, 0, 0, 4]],
        ][: {1: 3, 2: 2, 3: 1}[difficulty]]
        self._demonstrations = [
            {"input": grid, "output": apply_program(grid, self._program)} for grid in demo_inputs
        ]
        # Small-grid exhaustive checks are evaluator-side. Random larger grids
        # are independent of target/twin and include rectangles and zeros.
        self._challenge_inputs = [diagnostic_grid(), [[0]], [[0] * 8 for _ in range(8)]]
        for height, width in ((1, 1), (1, 2), (2, 1), (2, 2)):
            for cells in itertools.product(range(COLORS), repeat=height * width):
                self._challenge_inputs.append([list(cells[r * width:(r + 1) * width]) for r in range(height)])
        self._random_inputs = []
        for _ in range(32):
            height, width = self.rng.randrange(1, 9), self.rng.randrange(1, 9)
            self._random_inputs.append([[self.rng.randrange(COLORS) for _ in range(width)] for _ in range(height)])

        self.prompt = (
            "Infer the missing grid transformation program from demonstrations and optional active "
            "experiments. Grids are rectangular, 1..8 cells per side, colors 0..4; 0 is background. "
            "Fill program with at most four operations from the documented DSL. Your program is "
            "evaluated on new grids, including rectangular and empty-background cases. "
            "These are original procedural tasks, not ARC dataset items."
        )
        self.slots = {"program": {"type": "grid_dsl", "description": "List of at most four typed operation objects."}}
        self.tools = {
            "transform": {
                "description": "Evaluate the hidden grid rule on a chosen valid grid; the task is stateless.",
                "arguments": {"grid": "rectangular list of integer rows, sides 1..8, colors 0..4"},
                "cost": 1,
            }
        }
        self.files = {
            "/docs/grid-dsl.txt": (
                "Execute operations left to right. Submission: {program: [operation, ...]}.\n"
                "{op: recolor, source: 1..4, target: 1..4}: replace that color everywhere.\n"
                "{op: rotate90, turns: 0..3}: rotate clockwise by 90 degrees times turns.\n"
                "{op: keep_color, color: 1..4}: set every other color to zero.\n"
                "{op: crop}: retain the smallest bounding rectangle of nonzero cells; all-zero becomes [[0]].\n"
                "{op: flip_h}: reverse each row, preserving row order.\n"
                "Unknown keys, extra fields, booleans, floats, and out-of-range integers are invalid.\n"
                "A candidate may contain 0..4 operations, including an equivalent alternative composition.\n"
                "Public generation grammar: train = recolor(s,t); dev = rotate90(r), recolor(s,t); "
                "transfer = keep_color(s), crop, rotate90(r), recolor(s,t). s,t are distinct in 1..4; r is 0..3.\n"
                f"This episode uses the {split} grammar.\n"
                "An informative active experiment can separate the candidates: place differently sized "
                "asymmetric shapes of all four nonzero colors in one grid. Different areas reveal which "
                "color was selected; orientation reveals rotation; output values reveal recoloring.\n"
                "The supplied reference uses one 8x8 diagnostic experiment to distinguish all public "
                "grammar candidates. This is an explicit solvability witness, not an unknown secret.\n"
            ),
            "/data/demonstrations.json": json.dumps(self._demonstrations, separators=(",", ":")),
            "/workspace/pipeline.txt": "\n".join(f"[MASK:operation_{i}]" for i in range(len(self._program))),
        }

    def query(self, name: str, args: dict) -> dict:
        if name != "transform":
            raise ValueError("unknown grid tool")
        if type(args) is not dict or set(args) != {"grid"}:
            raise ValueError("transform requires exactly grid")
        return {"output": apply_program(args["grid"], self._program)}

    def evaluate(self, fill: dict) -> Verdict:
        try:
            if type(fill) is not dict or set(fill) != {"program"}:
                raise ValueError("fill must contain exactly program")
            program = validate_program(fill["program"])
        except ValueError as exc:
            return Verdict(False, details={"invalid_submission": str(exc)})
        certificate_passed = sum(
            apply_program(grid, program) == apply_program(grid, self._program)
            for grid in self._challenge_inputs
        )
        random_passed = sum(
            apply_program(grid, program) == apply_program(grid, self._program)
            for grid in self._random_inputs
        )
        return Verdict(
            certificate_passed == len(self._challenge_inputs) and random_passed == len(self._random_inputs),
            recovery=certificate_passed / len(self._challenge_inputs),
            outcome=random_passed / len(self._random_inputs),
            safety=1.0,
            details={
                "small_grid_and_edge_checks_passed": certificate_passed,
                "small_grid_and_edge_checks_total": len(self._challenge_inputs),
                "larger_interventions_passed": random_passed,
                "larger_interventions_total": len(self._random_inputs),
                "verification_scope": "finite behavioral suite; not exhaustive over every valid grid",
            },
        )

    def reference_answer(self) -> dict:
        grid = diagnostic_grid()
        output = self.query("transform", {"grid": grid})["output"]
        return {"program": infer_program(self.split, [{"input": grid, "output": output}])}

