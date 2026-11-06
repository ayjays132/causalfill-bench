"""Exact finite-field operator recovery with a deliberately small task grammar.

The public interface is a black-box affine map.  The evaluator uses its planted
structural construction, while a submission is interpreted as a sparse matrix.
No submitted expression is executed.  This is a system-identification control
task, not evidence that a model reasons in a hundred spatial dimensions.
"""

from __future__ import annotations

import json
from typing import Any

from causalfill.types import Task, Verdict


MODULUS = 101
DIMENSIONS = {1: 8, 2: 32, 3: 100}
STRUCTURES = {
    "train": "diagonal-affine",
    "dev": "permuted-affine",
    "transfer": "permuted-cyclic-coupled-affine",
}


def _integer(value: Any, label: str, lower: int, upper: int) -> int:
    if type(value) is not int or not lower <= value <= upper:
        raise ValueError(f"{label} must be an integer in [{lower}, {upper}]")
    return value


def _vector(value: Any, dimension: int, modulus: int, label: str) -> list[int]:
    if type(value) is not list or len(value) != dimension:
        raise ValueError(f"{label} must be a list of length {dimension}")
    return [_integer(item, label, 0, modulus - 1) for item in value]


def basis_probe_plan(dimension: int) -> list[list[int]]:
    """A complete, nonadaptive identification plan for an affine operator."""
    _integer(dimension, "dimension", 1, 100)
    probes = [[0] * dimension]
    for column in range(dimension):
        vector = [0] * dimension
        vector[column] = 1
        probes.append(vector)
    return probes


def recover_affine_operator(
    observations: list[list[int]], dimension: int, modulus: int = MODULUS
) -> dict[str, Any]:
    """Recover from public outputs at zero and the ordered standard basis.

    This utility has no access to a task, seed, latent coefficients, or grader.
    The caller is responsible for obtaining the observations through its tools.
    """
    _integer(dimension, "dimension", 1, 100)
    _integer(modulus, "modulus", 2, 65521)
    if type(observations) is not list or len(observations) != dimension + 1:
        raise ValueError("need zero probe followed by every ordered basis probe")
    outputs = [
        _vector(item, dimension, modulus, "observation") for item in observations
    ]
    offset = outputs[0]
    rows = []
    for row in range(dimension):
        terms = []
        for column in range(dimension):
            coefficient = (outputs[column + 1][row] - offset[row]) % modulus
            if coefficient:
                terms.append({"column": column, "coefficient": coefficient})
        rows.append(terms)
    return {"offset": list(offset), "rows": rows}


def sparse_probe_plan(dimension: int) -> list[list[int]]:
    """Five public interventions for a map with at most two terms per row.

    Zero determines the affine offset. Four moment probes determine the two
    positions and their coefficients by classical Prony-style reconstruction.
    Coordinates are distinct elements of GF(101), including coordinate zero.
    """
    _integer(dimension, "dimension", 1, 100)
    return [[0] * dimension] + [
        [pow(column, degree, MODULUS) for column in range(dimension)]
        for degree in range(4)
    ]


def recover_sparse_operator(
    observations: list[list[int]], dimension: int, modulus: int = MODULUS
) -> dict[str, Any]:
    """Recover zero-, one-, or two-term rows from five public observations.

    Observation order is zero, ones, coordinate index, index squared, index
    cubed. Arithmetic is exact in GF(101). This utility knows no task/seed.
    """
    _integer(dimension, "dimension", 1, 100)
    if type(modulus) is not int or modulus != MODULUS:
        raise ValueError("sparse reconstruction requires field modulus 101")
    if type(observations) is not list or len(observations) != 5:
        raise ValueError("need exactly five ordered sparse-probe observations")
    outputs = [_vector(item, dimension, modulus, "observation") for item in observations]
    offset = outputs[0]
    rows = []
    for row in range(dimension):
        moments = [(outputs[degree + 1][row] - offset[row]) % modulus for degree in range(4)]
        m0, m1, m2, m3 = moments
        determinant = (m0 * m2 - m1 * m1) % modulus
        if determinant:
            inverse = pow(determinant, -1, modulus)
            root_sum = ((m0 * m3 - m1 * m2) * inverse) % modulus
            root_product = ((m1 * m3 - m2 * m2) * inverse) % modulus
            roots = [
                column for column in range(dimension)
                if (column * column - root_sum * column + root_product) % modulus == 0
            ]
            if len(roots) != 2:
                raise ValueError("observations are inconsistent with two supported coordinates")
            j, k = roots
            a = ((m1 - m0 * k) * pow((j - k) % modulus, -1, modulus)) % modulus
            b = (m0 - a) % modulus
            if not a or not b:
                raise ValueError("observations do not have the claimed two-term structure")
            terms = [{"column": j, "coefficient": a}, {"column": k, "coefficient": b}]
        elif m0:
            column = (m1 * pow(m0, -1, modulus)) % modulus
            if column >= dimension:
                raise ValueError("observed coordinate is outside the declared dimension")
            terms = [{"column": column, "coefficient": m0}]
        elif any(moments):
            raise ValueError("observations are inconsistent with the sparse grammar")
        else:
            terms = []
        reconstructed = [
            sum(term["coefficient"] * pow(term["column"], degree, modulus) for term in terms) % modulus
            for degree in range(4)
        ]
        if reconstructed != moments:
            raise ValueError("moment observations fail reconstruction consistency")
        rows.append(terms)
    return {"offset": list(offset), "rows": rows}


def _parse_fill(
    fill: Any, dimension: int, modulus: int
) -> tuple[list[int], list[list[tuple[int, int]]]]:
    if type(fill) is not dict or set(fill) != {"offset", "rows"}:
        raise ValueError("fill must contain exactly offset and rows")
    offset = _vector(fill["offset"], dimension, modulus, "offset")
    raw_rows = fill["rows"]
    if type(raw_rows) is not list or len(raw_rows) != dimension:
        raise ValueError(f"rows must be a list of length {dimension}")
    rows = []
    for raw_row in raw_rows:
        if type(raw_row) is not list or len(raw_row) > dimension:
            raise ValueError("each sparse row must be a bounded list")
        seen = set()
        terms = []
        for term in raw_row:
            if type(term) is not dict or set(term) != {"column", "coefficient"}:
                raise ValueError("each term needs exactly column and coefficient")
            column = _integer(term["column"], "column", 0, dimension - 1)
            coefficient = _integer(term["coefficient"], "coefficient", 0, modulus - 1)
            if column in seen:
                raise ValueError("duplicate columns are not allowed within a row")
            seen.add(column)
            terms.append((column, coefficient))
        rows.append(terms)
    return offset, rows


def _candidate_output(
    offset: list[int], rows: list[list[tuple[int, int]]], vector: list[int], modulus: int
) -> list[int]:
    # Sparse candidate interpreter is intentionally separate from _target().
    return [
        (bias + sum(coefficient * vector[column] for column, coefficient in row)) % modulus
        for bias, row in zip(offset, rows)
    ]


class LatentTask(Task):
    """Recover a masked affine operator over GF(101) with bounded interventions."""

    def __init__(self, seed: int, split: str = "dev", difficulty: int = 2, twin: int = 0):
        if split not in STRUCTURES:
            raise ValueError("split must be train, dev, or transfer")
        if type(difficulty) is not int or difficulty not in DIMENSIONS:
            raise ValueError("difficulty must be 1, 2, or 3")
        if type(twin) is not int or twin not in (0, 1):
            raise ValueError("twin must be 0 or 1")
        super().__init__(seed, split, difficulty, twin)
        self.family = "latent"
        self.dimension = DIMENSIONS[difficulty]
        self.modulus = MODULUS
        self._structure = STRUCTURES[split]
        self.structural_signature = f"latent:{self._structure}:v1"
        self.answerable = True
        self.budget = self.dimension + 8
        self.max_calls = self.dimension + 12

        self._permutation = list(range(self.dimension))
        if split != "train":
            self.rng.shuffle(self._permutation)
            # Ensure that dev actually differs from the diagonal class, even
            # for the rare seed that happens to draw the identity permutation.
            if self._permutation == list(range(self.dimension)):
                self._permutation = self._permutation[1:] + self._permutation[:1]
        self._scale = [self.rng.randrange(1, MODULUS) for _ in range(self.dimension)]
        self._offset = [self.rng.randrange(MODULUS) for _ in range(self.dimension)]
        self._coupling = (
            [self.rng.randrange(1, MODULUS) for _ in range(self.dimension)]
            if split == "transfer" else [0] * self.dimension
        )
        self._pivot = self.rng.randrange(self.dimension)
        if twin:
            # Exactly one causal coefficient changes; zero is excluded so the
            # structural class and sparsity remain fixed in a pair.
            self._scale[self._pivot] = 1 + self._scale[self._pivot] % (MODULUS - 1)
        self._heldout = [
            [self.rng.randrange(MODULUS) for _ in range(self.dimension)] for _ in range(12)
        ]

        self.prompt = (
            f"Recover the masked affine operator f: GF({MODULUS})^{self.dimension} "
            f"-> GF({MODULUS})^{self.dimension}. You may intervene with the probe tool. "
            "Submit offset and sparse rows, where output[i] = "
            "(offset[i] + sum(term.coefficient * input[term.column] for term in rows[i])) "
            f"modulo {MODULUS}. Indices start at zero. Infer a map that works on new inputs, "
            "not just your observed examples. All coefficients and coordinates are canonical "
            f"integers 0 through {MODULUS - 1}."
        )
        self.slots = {
            "offset": {"type": "integer_vector", "description": f"Exactly {self.dimension} residues."},
            "rows": {
                "type": "sparse_matrix_rows",
                "description": (
                    f"Exactly {self.dimension} lists of {{column: int, coefficient: int}}. "
                    "No duplicate columns within a row; omitted entries mean zero."
                ),
            },
        }
        self.tools = {
            "probe": {
                "description": "Evaluate the operator on one intervention vector; no state is changed.",
                "arguments": {"vector": f"list of {self.dimension} integers in [0, {MODULUS - 1}]"},
                "cost": 1,
            }
        }
        terms_per_row = 2 if split == "transfer" else 1
        masked_rows = [
            {
                "offset": f"[MASK:b_{row}]",
                "terms": [
                    {"column": f"[MASK:j_{row}_{term}]", "coefficient": f"[MASK:a_{row}_{term}]"}
                    for term in range(terms_per_row)
                ],
            }
            for row in range(self.dimension)
        ]
        self.files = {
            "/docs/field.txt": (
                f"Arithmetic is exact modulo the prime {MODULUS}. Dimension: {self.dimension}.\n"
                "Probe vectors must be JSON lists of canonical integer residues. Booleans, floats, "
                "negative coordinates, and unknown fields are invalid.\n"
                "The public task grammar is affine. To identify any such map, observe f(0), then "
                "f(e_j) for every standard basis vector e_j. Column j is f(e_j)-f(0) modulo p.\n"
                f"This needs {self.dimension + 1} probes and fits the advertised budget. You may "
                "use a more economical plan. The evaluator accepts every behaviorally equivalent map.\n"
                "The sparse template indicates the number of planted terms, but your answer may "
                "use any equivalent bounded sparse matrix. There are no hidden nonlinear branches.\n"
                "Train uses diagonal affine maps; dev adds coordinate permutation; transfer adds "
                "cyclic coupling after permutation. These are three finite procedural grammars, "
                "not a claim of broad held-out reasoning generalization.\n"
            ),
            "/workspace/operator.masked.json": json.dumps(
                {"modulus": MODULUS, "dimension": self.dimension, "rows": masked_rows},
                separators=(",", ":"),
            ),
        }

    def _target(self, vector: list[int]) -> list[int]:
        """Planted construction; independent of the candidate sparse interpreter."""
        answer = []
        for row in range(self.dimension):
            primary = self._scale[row] * vector[self._permutation[row]]
            adjacent = self._coupling[row] * vector[self._permutation[(row + 1) % self.dimension]]
            answer.append((self._offset[row] + primary + adjacent) % MODULUS)
        return answer

    def query(self, name: str, args: dict) -> dict:
        if name != "probe":
            raise ValueError("unknown latent tool")
        if type(args) is not dict or set(args) != {"vector"}:
            raise ValueError("probe requires exactly vector")
        vector = _vector(args["vector"], self.dimension, MODULUS, "vector")
        return {"output": self._target(vector), "modulus": MODULUS}

    def evaluate(self, fill: dict) -> Verdict:
        try:
            offset, rows = _parse_fill(fill, self.dimension, MODULUS)
        except ValueError as exc:
            return Verdict(False, details={"invalid_submission": str(exc)})

        # A zero + full basis certificate is complete for the stated affine
        # hypothesis class.  It does not merely sample a few convenient inputs.
        row_correct = [True] * self.dimension
        certificate_passes = 0
        for vector in basis_probe_plan(self.dimension):
            expected = self._target(vector)
            actual = _candidate_output(offset, rows, vector, MODULUS)
            certificate_passes += actual == expected
            for row, (got, want) in enumerate(zip(actual, expected)):
                row_correct[row] = row_correct[row] and got == want
        heldout_passes = sum(
            _candidate_output(offset, rows, vector, MODULUS) == self._target(vector)
            for vector in self._heldout
        )
        certificate_ok = certificate_passes == self.dimension + 1
        outcome = heldout_passes / len(self._heldout)
        # Averaging over mostly-zero matrix entries would unfairly reward an
        # all-zero submission; recovery instead measures complete output rows.
        recovery = sum(row_correct) / self.dimension
        return Verdict(
            certificate_ok and heldout_passes == len(self._heldout),
            recovery=recovery,
            outcome=outcome,
            safety=1.0,
            details={
                "certificate": "exact-affine-zero-and-basis",
                "certificate_passes": certificate_passes,
                "certificate_total": self.dimension + 1,
                "heldout_interventions_passed": heldout_passes,
                "heldout_interventions_total": len(self._heldout),
                "dimension": self.dimension,
                "field_modulus": MODULUS,
            },
        )

    def reference_answer(self) -> dict:
        """Engineering solvability witness, obtained exclusively via probe().

        Direct method calls do not pay the runner's budget. A measured baseline
        must issue the same plan through the runner and account for every call.
        """
        outputs = [
            self.query("probe", {"vector": vector})["output"]
            for vector in basis_probe_plan(self.dimension)
        ]
        return recover_affine_operator(outputs, self.dimension, MODULUS)


class SparseLatentTask(LatentTask):
    """Sparse affine recovery under a budget too small for coordinate scanning.

    Shares the control family's planted structures and complete affine
    verifier. Its public task contract exposes sparsity, not a solving recipe.
    """

    def __init__(self, seed: int, split: str = "dev", difficulty: int = 2, twin: int = 0):
        super().__init__(seed, split, difficulty, twin)
        self.family = "latent_sparse"
        self.structural_signature = f"latent_sparse:{self._structure}:v1"
        self.budget = 9
        self.max_calls = 14
        self.prompt = (
            f"Recover a masked affine operator f: GF({MODULUS})^{self.dimension} "
            f"-> GF({MODULUS})^{self.dimension} under a budget of nine cost units. "
            "Each output coordinate depends on at most two input coordinates plus an offset. "
            "You may choose bounded intervention vectors for the probe tool. Submit offset and "
            "sparse rows: output[i] = (offset[i] + sum(term.coefficient * input[term.column] "
            f"for term in rows[i])) modulo {MODULUS}. All entries are integers 0..100; "
            "columns are indexed from zero. Your map must work on all inputs, not only your probes."
        )
        self.files["/docs/field.txt"] = (
            f"Field: GF({MODULUS}). Dimension: {self.dimension}. Exact arithmetic, no noise.\n"
            "Hidden operator: affine with at most two nonzero coefficients in each output row. "
            "Nonzero coefficients need not be positive as signed integers: 100 represents -1, "
            "so two coefficients can sum to zero in the field.\n"
            "Probe accepts exactly {vector: [integer, ...]}; length must equal dimension. "
            "Each coordinate is a canonical residue 0..100. Booleans, floats, unknown fields, "
            "negative values, and oversized inputs are invalid. Each probe costs one unit.\n"
            "Submit {offset: [...], rows: [[{column: int, coefficient: int}, ...], ...]}. "
            "There must be exactly dimension offsets and rows. Omitted row terms mean zero. "
            "Each column may occur at most once per row. Equivalent affine maps are accepted.\n"
            "The entire episode has nine cost units, including common tools such as reading this "
            "file. Use informative interventions that can constrain multiple coordinates at once.\n"
            "Train has diagonal affine maps; dev has permuted affine maps; transfer adds one "
            "cyclic neighbor coupling per row after permutation. The candidate hypothesis class "
            "is affine throughout. There are no unannounced nonlinear branches.\n"
        )

    def reference_answer(self) -> dict:
        outputs = [
            self.query("probe", {"vector": vector})["output"]
            for vector in sparse_probe_plan(self.dimension)
        ]
        return recover_sparse_operator(outputs, self.dimension, MODULUS)

