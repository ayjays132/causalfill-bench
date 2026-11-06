"""A second workflow audit using a generated-tree Fraction oracle.

The numerical oracle below does not parse Python ASTs, import production
normalizers, or reuse the workflow interpreter.  Only the public certificate
entry point is used as the implementation under review.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from fractions import Fraction
import hashlib
import itertools
import json
from pathlib import Path
import random
import unittest

from causalfill.domains.workflow import expression
from causalfill.workflow_certificate import certify_equivalence


BOX = 1_000_000
LIMIT = 10**30
VARIABLES = ("balance", "amount", "fee", "reserve", "ceiling", "scale")


@dataclass(frozen=True)
class Expr:
    operation: str
    children: tuple["Expr", ...] = ()
    literal: str | int | None = None

    def source(self) -> str:
        if self.operation in ("variable", "integer"):
            return str(self.literal)
        if self.operation == "negative":
            return "(-" + self.children[0].source() + ")"
        if self.operation in ("min", "max"):
            return self.operation + "(" + ",".join(child.source() for child in self.children) + ")"
        return "(" + self.children[0].source() + self.operation + self.children[1].source() + ")"


def var(name: str) -> Expr:
    return Expr("variable", literal=name)


def integer(value: int) -> Expr:
    if value < 0:
        return Expr("negative", (integer(-value),))
    return Expr("integer", literal=value)


def op(operation: str, *children: Expr) -> Expr:
    return Expr(operation, tuple(children))


def fraction(numerator: int, denominator: int) -> Expr:
    return op("/", integer(numerator), integer(denominator))


def apply_operation(operation: str, arguments: tuple[Fraction, ...]) -> Fraction:
    if operation == "+":
        return arguments[0] + arguments[1]
    if operation == "-":
        return arguments[0] - arguments[1]
    if operation == "*":
        return arguments[0] * arguments[1]
    if operation == "/":
        return arguments[0] / arguments[1]
    if operation == "negative":
        return -arguments[0]
    # The generated-tree oracle deliberately selects from a sorted sequence,
    # independently of the production min/max interpreter and lattice code.
    ordered = sorted(arguments)
    if operation == "min":
        return ordered[0]
    if operation == "max":
        return ordered[-1]
    raise AssertionError(operation)


def numeric_oracle(tree: Expr, values: dict[str, int], trace: list[Fraction] | None = None) -> Fraction:
    if tree.operation == "variable":
        result = Fraction(values[tree.literal])
    elif tree.operation == "integer":
        result = Fraction(tree.literal)
    else:
        result = apply_operation(tree.operation, tuple(numeric_oracle(child, values, trace)
                                                      for child in tree.children))
    if trace is not None:
        trace.append(result)
    return result


def semantic_vector(tree: Expr, points: list[dict[str, int]], cache: dict) -> tuple[Fraction, ...]:
    if tree in cache:
        return cache[tree]
    if tree.operation == "variable":
        result = tuple(Fraction(point[tree.literal]) for point in points)
    elif tree.operation == "integer":
        result = (Fraction(tree.literal),) * len(points)
    else:
        arguments = [semantic_vector(child, points, cache) for child in tree.children]
        result = tuple(apply_operation(tree.operation, tuple(values)) for values in zip(*arguments))
    cache[tree] = result
    return result


def lattice_corpus() -> list[Expr]:
    leaves = [op("/", var("balance"), integer(2)), var("reserve"), var("ceiling"),
              fraction(1, 3), fraction(-2, 3), op("+", var("balance"), integer(1))]
    shallow = leaves + [op(kind, a, b) for kind in ("min", "max")
                        for a, b in itertools.combinations_with_replacement(leaves, 2)]
    all_trees = shallow + [op(kind, a, b) for kind in ("min", "max")
                           for a, b in itertools.combinations_with_replacement(shallow, 2)]
    # Force nonbinary calls, median distributions, and arithmetic-wrapped atoms
    # into the corpus as well as exhaustive binary trees of depth at most two.
    a, b, c = leaves[:3]
    all_trees += [op("max", op("min", a, b), op("min", b, c), op("min", c, a)),
                  op("min", op("max", a, b), op("max", b, c), op("max", c, a)),
                  op("min", a, b, c), op("max", a, b, c)]
    random.Random(230519).shuffle(all_trees)
    return all_trees


def audit_lattices(limit: int | None = None) -> dict:
    trees = lattice_corpus()
    if limit is not None:
        trees = trees[:limit]
    all_points = [dict(balance=b, reserve=r, ceiling=c, amount=0, fee=0, scale=1)
                  for b, r, c in itertools.product((-5, -1, 0, 1, 4), repeat=3)]
    result = {}
    for constrained in (False, True):
        points = [point for point in all_points if not constrained or point["reserve"] <= point["ceiling"]]
        cache, representatives = {}, {}
        collision_pairs = 0
        values_checked = 0
        for tree in trees:
            source = tree.source()
            checked = certify_equivalence(source, source, reserve_le_ceiling=constrained, include_proof=True)
            if not checked["certified"]:
                raise AssertionError(("small lattice failed certification", source, checked))
            form = json.dumps(checked["proof"]["candidate"]["normal_form"], separators=(",", ":"))
            vector = semantic_vector(tree, points, cache)
            values_checked += len(points)
            if form in representatives:
                previous_source, previous_vector = representatives[form]
                if vector != previous_vector:
                    index = next(i for i, (a, b) in enumerate(zip(vector, previous_vector)) if a != b)
                    raise AssertionError(("false normal-form equality", source, previous_source, points[index],
                                          str(vector[index]), str(previous_vector[index]), constrained))
                pair = certify_equivalence(source, previous_source, reserve_le_ceiling=constrained)
                if not pair["certified"]:
                    raise AssertionError(("same-form pair not accepted", pair))
                collision_pairs += 1
            else:
                representatives[form] = (source, vector)
        result["ordered_box" if constrained else "unconstrained_box"] = {
            "expressions": len(trees), "integer_valuations": len(points),
            "exact_expression_values": values_checked,
            "distinct_normal_forms": len(representatives),
            "accepted_cross_expression_pairs_checked": collision_pairs,
            "false_certifications": 0,
        }
    return result


def random_tree(rng: random.Random, depth: int) -> Expr:
    leaves = [*(var(name) for name in VARIABLES), integer(0), integer(1), integer(-2), fraction(2, 3)]
    if depth <= 0 or rng.random() < 0.28:
        return rng.choice(leaves)
    kind = rng.choice(("+", "-", "*", "/", "min", "max", "negative"))
    left = random_tree(rng, depth - 1)
    if kind == "negative":
        return op(kind, left)
    if kind == "/":
        right = rng.choice((integer(2), integer(-3), fraction(2, 3), fraction(-7, 11),
                            op("min", integer(2), integer(3)), op("max", integer(-3), integer(-2))))
        if rng.random() < 0.35:
            atom = var(rng.choice(VARIABLES))
            right = op("+", op("-", atom, atom), right)
    else:
        right = random_tree(rng, depth - 1)
    return op(kind, left, right)


def audit_mixed_bounds(count: int = 320, points_count: int = 28) -> dict:
    rng = random.Random(991827)
    points = []
    for scale in (1, BOX):
        for signs in ((1, 1, 1, 1, 1), (-1, -1, -1, -1, -1), (1, -1, 1, -1, 1),
                      (-1, 1, -1, 1, -1), (0, 0, 0, 0, 0)):
            point = dict(zip(VARIABLES[:-1], (sign * BOX for sign in signs)))
            points.append({**point, "scale": scale})
    while len(points) < points_count:
        point = {name: rng.randrange(-BOX, BOX + 1) for name in VARIABLES[:-1]}
        points.append({**point, "scale": rng.randrange(1, BOX + 1)})
    trees = [random_tree(rng, rng.choice((2, 3, 4, 5))) for _ in range(count)]
    certified = 0
    intermediate_values = 0
    runtime_values = 0
    reasons = Counter()
    root_signatures = {}
    accepted_collision_pairs = 0
    for tree in trees:
        source = tree.source()
        checked = certify_equivalence(source, source, include_proof=True)
        if not checked["certified"]:
            reasons[checked["reason_code"]] += 1
            continue
        certified += 1
        trace = checked["proof"]["candidate"]["intermediate_bounds"]
        root_values = []
        for point in points:
            values = []
            root = numeric_oracle(tree, point, values)
            root_values.append(root)
            if len(values) != len(trace):
                raise AssertionError(("AST numeric-node trace differs from generated tree", source))
            for value, bound in zip(values, trace):
                magnitude = Fraction(bound["absolute_value_bound"])
                divisor = bound["denominator_divisor"]
                numerator_bound = Fraction(bound["numerator_absolute_bound"])
                if not (abs(value) <= magnitude and divisor % value.denominator == 0 and
                        abs(value.numerator) <= numerator_bound <= LIMIT and value.denominator <= divisor <= LIMIT):
                    raise AssertionError(("unsound M/D bound", source, point, str(value), bound))
                intermediate_values += 1
            if expression(source, point) != root:
                raise AssertionError(("interpreter/generated-tree disagreement", source, point))
            runtime_values += 1
        form = json.dumps(checked["proof"]["candidate"]["normal_form"], separators=(",", ":"))
        if form in root_signatures:
            previous_source, previous_values = root_signatures[form]
            if tuple(root_values) != previous_values:
                raise AssertionError(("mixed-arithmetic false certification", source, previous_source))
            if not certify_equivalence(source, previous_source)["certified"]:
                raise AssertionError("same normal form was not accepted")
            accepted_collision_pairs += 1
        else:
            root_signatures[form] = (source, tuple(root_values))
        # An additive perturbation of one is never equal in exact rationals.
        # The full equality gate must reject it even when both sides are safe.
        if certify_equivalence(source, "(" + source + ")+1")["certified"]:
            raise AssertionError(("accepted unequal additive perturbation", source))
    if certified < count // 2:
        raise AssertionError(("audit did not cover enough accepted mixed trees", certified, count))
    return {"generated_expressions": count, "certified_expressions": certified,
            "not_certified_reason_counts": dict(sorted(reasons.items())),
            "integer_valuations_per_expression": len(points),
            "exact_intermediate_values_checked": intermediate_values,
            "production_interpreter_comparisons": runtime_values,
            "accepted_cross_expression_pairs_checked": accepted_collision_pairs,
            "unequal_plus_one_candidates_rejected": certified,
            "bound_violations": 0, "false_certifications": 0}


def audit_aliases_and_conditional_divisors() -> dict:
    def wide(text):
        return "".join(chr(ord(character) + 0xFEE0) if "a" <= character <= "z" else character for character in text)

    values = dict(balance=37, amount=-11, fee=5, reserve=-2, ceiling=9, scale=3)
    aliases = [(wide("balance") + "+" + wide("amount"), "balance+amount", Fraction(26)),
               (wide("min") + "(" + wide("balance") + "," + wide("fee") + ")", "min(balance,fee)", Fraction(5)),
               ("(balance # comment\n)", "balance", Fraction(37))]
    for candidate, target, expected in aliases:
        if not certify_equivalence(candidate, target)["certified"]:
            raise AssertionError(("Python-normalized source alias rejected unexpectedly", candidate))
        if expression(candidate, values) != expected or expression(target, values) != expected:
            raise AssertionError(("alias changed semantics", candidate))
    invalid = ["b\u0430lance", "m\u0456n(balance,fee)", "v_balance", "Lbalance", "'v:balance'",
               "min.__call__(balance,fee)", "NaN", "Infinity", "0e0", "True", "1j", "min"]
    for candidate in invalid:
        if certify_equivalence(candidate, "balance")["certified"]:
            raise AssertionError(("crafted atom/source alias certified", candidate))

    conditional = "balance/(min(reserve,ceiling)-reserve+1)"
    if not certify_equivalence(conditional, "balance", reserve_le_ceiling=True)["certified"]:
        raise AssertionError("the explicitly constrained constant divisor was not recognized")
    if certify_equivalence(conditional, "balance")["certified"]:
        raise AssertionError("a conditional order assumption leaked into the unconstrained box")
    # An actual excluded-domain pole demonstrates why the constraint matters.
    witness = {**values, "reserve": 1, "ceiling": 0}
    with_pole = op("/", var("balance"), op("+", op("-", op("min", var("reserve"), var("ceiling")),
                                                        var("reserve")), integer(1)))
    try:
        numeric_oracle(with_pole, witness)
    except ZeroDivisionError:
        pass
    else:
        raise AssertionError("the crafted excluded-domain pole was not reproduced")
    for reserve, ceiling in itertools.product(range(-4, 5), repeat=2):
        if reserve <= ceiling:
            point = {**values, "reserve": reserve, "ceiling": ceiling}
            if numeric_oracle(with_pole, point) != Fraction(point["balance"]):
                raise AssertionError(("conditional divisor is not constant on its claimed box", point))
    for assumption in (None, 0, 1, "true", []):
        checked = certify_equivalence("min(reserve,ceiling)", "reserve", reserve_le_ceiling=assumption)
        if checked["certified"] or checked["reason_code"] != "invalid_assumption_flag":
            raise AssertionError(("non-Boolean assumption accepted", assumption))
    return {"legitimate_parser_aliases_checked": len(aliases), "crafted_aliases_rejected": len(invalid),
            "invalid_assumption_flags_rejected": 5, "conditional_divisor_ordered_points_checked": 45,
            "excluded_domain_pole_reproduced": True, "false_certifications": 0}


class WorkflowIndependentAuditTests(unittest.TestCase):
    def test_constraint_aware_rational_lattice_collisions(self):
        audit_lattices(limit=280)

    def test_generated_tree_fraction_intermediate_bounds(self):
        audit_mixed_bounds(count=160, points_count=20)

    def test_aliases_and_constraint_dependent_denominator(self):
        audit_aliases_and_conditional_divisors()


def write_audit(destination: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    sources = [root / "causalfill/workflow_certificate.py", root / "causalfill/domains/workflow.py", Path(__file__).resolve()]
    report = {"schema": "causalfill.workflow-independent-audit.v1", "started_at_utc": datetime.now(timezone.utc).isoformat(),
              "method": "generated expression trees evaluated with exact Fraction semantics; no production normalizer or AST interpreter in numeric oracle",
              "source_sha256": {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in sources},
              "lattices": audit_lattices(), "mixed_ast_bounds": audit_mixed_bounds(count=960, points_count=44),
              "aliases_and_conditional_divisors": audit_aliases_and_conditional_divisors(),
              "findings": [],
              "limits": ["Finite differential testing supports but does not formally prove implementation soundness.",
                         "The source-level M/D induction and lattice dominance rules were separately reviewed; this module is not Lean-verified.",
                         "The numeric resource guarantee bounds original DSL Fraction values on the stated input domain; it is not a wall-clock or operating-system memory guarantee."]}
    report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    report["status"] = "passed"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit-output", type=Path)
    arguments, remaining = parser.parse_known_args()
    if arguments.audit_output:
        write_audit(arguments.audit_output)
    else:
        unittest.main(argv=[__file__, *remaining])
