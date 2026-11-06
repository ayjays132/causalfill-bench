"""A sufficient, bounded symbolic certificate for the workflow expression DSL.

Equal rational-polynomial normal forms, with canonical min/max lattice atoms,
prove equality. Unequal normal forms do NOT prove inequivalence. Every original
AST node must first obtain a conservative all-input Fraction resource bound;
algebraic cancellation cannot hide a pole or an oversized intermediate.

This module does not call the workflow interpreter, task generator, sampling
tests, eval, or an external CAS. Its trusted operations are ordinary Python
integers, Fraction arithmetic, AST parsing, and the stated algebraic rules.
It is not a Lean formalization or a complete equivalence decision procedure.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
import math
from typing import Any

SCHEMA = "causalfill.workflow-symbolic.v1"
NAMES = frozenset(("balance", "amount", "fee", "reserve", "ceiling", "scale"))
INPUT_MAGNITUDE = 1_000_000
NUMERIC_LIMIT = 10**30
MAX_SOURCE_CHARS = 800
MAX_AST_NODES = 120
MAX_AST_DEPTH = 20
MAX_CONSTANT = 10_000
MAX_POLYNOMIAL_TERMS = 256
MAX_MONOMIAL_FACTORS = 24
MAX_LATTICE_TERMS = 128
MAX_CANONICAL_BYTES = 16_384
MAX_NORMALIZATION_WORK = 50_000
MAX_COEFFICIENT_BITS = 256

# Atom names are canonical ASCII strings. The empty monomial denotes 1.
Polynomial = dict[tuple[str, ...], Fraction]
PolyKey = tuple[tuple[tuple[str, ...], int, int], ...]
Lattice = tuple[tuple[PolyKey, ...], ...]  # max of min-terms


class NotCertified(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Bound:
    magnitude: Fraction
    denominator_divisor: int


@dataclass
class Symbolic:
    polynomial: Polynomial
    bound: Bound


def public_contract(reserve_le_ceiling: bool = False) -> dict:
    """The finite input domain and sufficient proof rules are public task data."""
    return {
        "schema_version": SCHEMA,
        "input_domain": {
            name: {"type": "integer", "minimum": 1 if name == "scale" else -INPUT_MAGNITUDE,
                   "maximum": INPUT_MAGNITUDE}
            for name in sorted(NAMES)
        },
        "constraints": ["reserve <= ceiling"] if reserve_le_ceiling else [],
        "arithmetic": "Exact rational arithmetic; no rounding.",
        "fraction_numerator_absolute_limit": NUMERIC_LIMIT,
        "fraction_denominator_limit": NUMERIC_LIMIT,
        "limits": {"source_characters": MAX_SOURCE_CHARS, "ast_nodes": MAX_AST_NODES,
                   "ast_depth": MAX_AST_DEPTH, "integer_literal_absolute_value": MAX_CONSTANT,
                   "polynomial_terms": MAX_POLYNOMIAL_TERMS,
                   "monomial_factors": MAX_MONOMIAL_FACTORS,
                   "lattice_terms": MAX_LATTICE_TERMS,
                   "canonical_bytes": MAX_CANONICAL_BYTES,
                   "coefficient_integer_bits": MAX_COEFFICIENT_BITS,
                   "normalization_work_units": MAX_NORMALIZATION_WORK},
        "grammar": "Declared names, integer literals, unary +/-, +, -, *, /, and min/max with 2..4 positional arguments.",
        "division_certification": "Every divisor must normalize to a nonzero rational constant. Variable divisors are not certified, even if some could be proved nonzero by a stronger system.",
        "accepted_identities": [
            "Exact rational polynomial identities, including distributivity and cancellation of total bounded subexpressions.",
            "min/max commutativity, associativity, idempotence, absorption and lattice distributivity.",
            "Ordering of rational constants; reserve <= ceiling only when listed as a task constraint.",
        ],
        "strict_success": "Symbolic equivalence and conservative totality/resource bounds over this input domain, plus all behavioral diagnostics passing.",
        "incompleteness": "This is a sufficient proof system. Unsupported expressions, nonmatching normal forms, or conservative bound failures are not_certified, not a claim that mathematical equivalence is false.",
    }


def input_in_contract(values: Any, reserve_le_ceiling: bool = False) -> bool:
    if type(values) is not dict or set(values) != NAMES:
        return False
    for name, value in values.items():
        low = 1 if name == "scale" else -INPUT_MAGNITUDE
        if type(value) is not int or not low <= value <= INPUT_MAGNITUDE:
            return False
    return not reserve_le_ceiling or values["reserve"] <= values["ceiling"]


def _key(polynomial: Polynomial) -> PolyKey:
    return tuple((monomial, coefficient.numerator, coefficient.denominator)
                 for monomial, coefficient in sorted(polynomial.items()) if coefficient)


def _from_key(key: PolyKey) -> Polynomial:
    return {monomial: Fraction(numerator, denominator) for monomial, numerator, denominator in key}


def _constant(polynomial: Polynomial) -> Fraction | None:
    if not polynomial:
        return Fraction(0)
    if set(polynomial) == {()}:
        return polynomial[()]
    return None


def _key_constant(key: PolyKey) -> Fraction | None:
    if not key:
        return Fraction(0)
    if len(key) == 1 and key[0][0] == ():
        return Fraction(key[0][1], key[0][2])
    return None


def _quoted_ascii_size(value: str) -> int:
    # All internal atom strings are ASCII without control characters.
    return 2 + len(value) + value.count('"') + value.count("\\")


def _encode_key(key: PolyKey) -> str:
    # Check output size BEFORE json.dumps can expand nested atom strings.
    size = 2 + max(0, len(key) - 1)
    for monomial, numerator, denominator in key:
        mono_size = 2 + max(0, len(monomial) - 1) + sum(_quoted_ascii_size(atom) for atom in monomial)
        size += 4 + mono_size + len(str(numerator)) + len(str(denominator))
        if size > MAX_CANONICAL_BYTES:
            raise NotCertified("canonical_size_limit", "canonical expression exceeds the bounded proof representation")
    encoded = json.dumps(key, separators=(",", ":"), ensure_ascii=True)
    if len(encoded) > MAX_CANONICAL_BYTES:
        raise NotCertified("canonical_size_limit", "canonical expression exceeds the bounded proof representation")
    return encoded


class _Normalizer:
    def __init__(self, reserve_le_ceiling: bool):
        self.reserve_le_ceiling = reserve_le_ceiling
        self.work = 0
        self.nodes_checked = 0
        self.max_depth = 0
        self.max_numerator_bound = Fraction(0)
        self.max_denominator_divisor = 1
        self.max_magnitude_bound = Fraction(0)
        self.lattice_atoms: dict[str, Lattice] = {}
        self.bound_trace: list[dict] = []

    def charge(self, amount: int = 1) -> None:
        self.work += amount
        if self.work > MAX_NORMALIZATION_WORK:
            raise NotCertified("normalization_work_limit", "symbolic expansion exceeds the bounded proof work limit")

    def checked_polynomial(self, polynomial: Polynomial) -> Polynomial:
        if len(polynomial) > MAX_POLYNOMIAL_TERMS:
            raise NotCertified("polynomial_term_limit", "polynomial expansion exceeds the proof term limit")
        for monomial, coefficient in polynomial.items():
            self.charge()
            if len(monomial) > MAX_MONOMIAL_FACTORS:
                raise NotCertified("monomial_factor_limit", "monomial exceeds the proof factor limit")
            if max(abs(coefficient.numerator).bit_length(), coefficient.denominator.bit_length()) > MAX_COEFFICIENT_BITS:
                raise NotCertified("coefficient_limit", "symbolic coefficient exceeds the proof integer limit")
        _encode_key(_key(polynomial))
        return polynomial

    def add(self, left: Polynomial, right: Polynomial, sign: int = 1) -> Polynomial:
        result = dict(left)
        for monomial, coefficient in right.items():
            self.charge()
            new = result.get(monomial, Fraction(0)) + sign * coefficient
            if new:
                result[monomial] = new
            else:
                result.pop(monomial, None)
        return self.checked_polynomial(result)

    def multiply(self, left: Polynomial, right: Polynomial) -> Polynomial:
        result: Polynomial = {}
        for a, x in left.items():
            for b, y in right.items():
                self.charge()
                if len(a) + len(b) > MAX_MONOMIAL_FACTORS:
                    raise NotCertified("monomial_factor_limit", "monomial exceeds the proof factor limit")
                monomial = tuple(sorted(a + b))
                new = result.get(monomial, Fraction(0)) + x * y
                if new:
                    result[monomial] = new
                else:
                    result.pop(monomial, None)
                if len(result) > MAX_POLYNOMIAL_TERMS:
                    raise NotCertified("polynomial_term_limit", "polynomial expansion exceeds the proof term limit")
        return self.checked_polynomial(result)

    def scale(self, polynomial: Polynomial, coefficient: Fraction) -> Polynomial:
        return self.checked_polynomial({m: c * coefficient for m, c in polynomial.items() if c * coefficient})

    def leaf_le(self, left: PolyKey, right: PolyKey) -> bool:
        """Only explicitly justified order relations; no sampling or guessing."""
        self.charge()
        if left == right:
            return True
        a, b = _key_constant(left), _key_constant(right)
        if a is not None and b is not None:
            return a <= b
        reserve = ((("v:reserve",), 1, 1),)
        ceiling = ((("v:ceiling",), 1, 1),)
        return self.reserve_le_ceiling and left == reserve and right == ceiling

    def canonical_lattice(self, terms: list[tuple[PolyKey, ...]]) -> Lattice:
        """Canonical max-of-mins; removing dominated terms is sound in R."""
        if len(terms) > MAX_LATTICE_TERMS:
            raise NotCertified("lattice_term_limit", "min/max distribution exceeds the proof term limit")
        unique = set()
        for term in terms:
            leaves = sorted(set(term))
            # If a <= b, min(a,b,...) = min(a,...). Preserve the earlier
            # representative if two leaves have a proved equality.
            kept = []
            for i, leaf in enumerate(leaves):
                dominated = any(self.leaf_le(other, leaf) and
                                (not self.leaf_le(leaf, other) or j < i)
                                for j, other in enumerate(leaves) if i != j)
                if not dominated:
                    kept.append(leaf)
            unique.add(tuple(kept))
        ordered = sorted(unique)

        def term_le(a: tuple[PolyKey, ...], b: tuple[PolyKey, ...]) -> bool:
            # min(a) <= min(b) whenever, for every b_i, some a_j <= b_i.
            return all(any(self.leaf_le(left, right) for left in a) for right in b)

        answer = []
        for i, term in enumerate(ordered):
            dominated = any(term_le(term, other) and (not term_le(other, term) or j < i)
                            for j, other in enumerate(ordered) if i != j)
            if not dominated:
                answer.append(term)
        return tuple(answer)

    def as_lattice(self, polynomial: Polynomial) -> Lattice:
        if len(polynomial) == 1:
            monomial, coefficient = next(iter(polynomial.items()))
            if coefficient == 1 and len(monomial) == 1 and monomial[0] in self.lattice_atoms:
                return self.lattice_atoms[monomial[0]]
        return ((_key(polynomial),),)

    def lattice(self, operation: str, arguments: list[Polynomial]) -> Polynomial:
        dnfs = [self.as_lattice(argument) for argument in arguments]
        if operation == "max":
            terms = [term for dnf in dnfs for term in dnf]
            result = self.canonical_lattice(terms)
        else:
            result: Lattice = ((),)
            for dnf in dnfs:
                if len(result) * len(dnf) > MAX_LATTICE_TERMS:
                    raise NotCertified("lattice_term_limit", "min/max distribution exceeds the proof term limit")
                self.charge(len(result) * len(dnf))
                result = self.canonical_lattice([left + right for left in result for right in dnf])
        if len(result) == 1 and len(result[0]) == 1:
            return _from_key(result[0][0])
        encoded_terms = [[_encode_key(leaf) for leaf in term] for term in result]
        size = 3 + max(0, len(encoded_terms) - 1)
        for term in encoded_terms:
            size += 2 + max(0, len(term) - 1) + sum(_quoted_ascii_size(leaf) for leaf in term)
            if size > MAX_CANONICAL_BYTES:
                raise NotCertified("canonical_size_limit", "min/max normal form exceeds the proof representation limit")
        atom = "L" + json.dumps(encoded_terms, separators=(",", ":"))
        if len(atom) > MAX_CANONICAL_BYTES:
            raise NotCertified("canonical_size_limit", "min/max normal form exceeds the proof representation limit")
        self.lattice_atoms[atom] = result
        return self.checked_polynomial({(atom,): Fraction(1)})

    def check_bound(self, node: ast.AST, bound: Bound) -> Bound:
        self.nodes_checked += 1
        m, d = bound.magnitude, bound.denominator_divisor
        numerator = m * d
        if d > NUMERIC_LIMIT or numerator > NUMERIC_LIMIT:
            raise NotCertified("resource_bound_not_proved", "a conservative intermediate Fraction numerator/denominator bound exceeds 10**30 on the public input box")
        self.max_numerator_bound = max(self.max_numerator_bound, numerator)
        self.max_denominator_divisor = max(self.max_denominator_divisor, d)
        self.max_magnitude_bound = max(self.max_magnitude_bound, m)
        self.bound_trace.append({"node": type(node).__name__, "column": getattr(node, "col_offset", 0),
                                 "absolute_value_bound": str(m), "denominator_divisor": d,
                                 "numerator_absolute_bound": str(numerator)})
        return bound

    def visit(self, node: ast.AST, depth: int = 0) -> Symbolic:
        self.charge()
        self.max_depth = max(self.max_depth, depth)
        if depth > MAX_AST_DEPTH:
            raise NotCertified("ast_depth_limit", "expression exceeds the runtime AST depth bound")
        if isinstance(node, ast.Expression):
            return self.visit(node.body, depth + 1)
        if isinstance(node, ast.Name) and node.id in NAMES:
            bound = self.check_bound(node, Bound(Fraction(INPUT_MAGNITUDE), 1))
            return Symbolic({("v:" + node.id,): Fraction(1)}, bound)
        if isinstance(node, ast.Constant) and type(node.value) is int and abs(node.value) <= MAX_CONSTANT:
            bound = self.check_bound(node, Bound(Fraction(abs(node.value)), 1))
            return Symbolic({(): Fraction(node.value)} if node.value else {}, bound)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            child = self.visit(node.operand, depth + 1)
            bound = self.check_bound(node, child.bound)
            polynomial = child.polynomial if isinstance(node.op, ast.UAdd) else self.scale(child.polynomial, Fraction(-1))
            return Symbolic(polynomial, bound)
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
            left, right = self.visit(node.left, depth + 1), self.visit(node.right, depth + 1)
            a, b = left.bound, right.bound
            if isinstance(node.op, (ast.Add, ast.Sub)):
                bound = self.check_bound(node, Bound(a.magnitude + b.magnitude,
                                                     math.lcm(a.denominator_divisor, b.denominator_divisor)))
                polynomial = self.add(left.polynomial, right.polynomial, -1 if isinstance(node.op, ast.Sub) else 1)
            elif isinstance(node.op, ast.Mult):
                bound = self.check_bound(node, Bound(a.magnitude * b.magnitude,
                                                     a.denominator_divisor * b.denominator_divisor))
                polynomial = self.multiply(left.polynomial, right.polynomial)
            else:
                divisor = _constant(right.polynomial)
                if divisor is None:
                    raise NotCertified("variable_divisor_not_certified", "division requires a symbolically nonzero rational constant")
                if divisor == 0:
                    raise NotCertified("zero_divisor", "the divisor is symbolically zero")
                bound = self.check_bound(node, Bound(a.magnitude / abs(divisor),
                                                     a.denominator_divisor * abs(divisor.numerator)))
                polynomial = self.scale(left.polynomial, 1 / divisor)
            return Symbolic(polynomial, bound)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("min", "max"):
            if node.keywords or not 2 <= len(node.args) <= 4:
                raise NotCertified("unsupported_syntax", "min/max require 2..4 positional arguments")
            arguments = [self.visit(argument, depth + 1) for argument in node.args]
            divisor = math.lcm(*(argument.bound.denominator_divisor for argument in arguments))
            bound = self.check_bound(node, Bound(max(argument.bound.magnitude for argument in arguments), divisor))
            return Symbolic(self.lattice(node.func.id, [argument.polynomial for argument in arguments]), bound)
        raise NotCertified("unsupported_syntax", "only declared names, bounded integer literals, + - * / and min/max are supported")

    def analyze(self, source: Any) -> tuple[PolyKey, dict]:
        if type(source) is not str or not 1 <= len(source) <= MAX_SOURCE_CHARS:
            raise NotCertified("source_size_or_type", "expression must be a string of 1..800 characters")
        try:
            tree = ast.parse(source, mode="eval")
        except (SyntaxError, RecursionError, ValueError):
            raise NotCertified("invalid_syntax", "invalid expression syntax") from None
        ast_nodes = sum(1 for _ in ast.walk(tree))
        if ast_nodes > MAX_AST_NODES:
            raise NotCertified("ast_node_limit", "expression exceeds the runtime AST node bound")
        result = self.visit(tree)
        normal_form = _key(self.checked_polynomial(result.polynomial))
        encoded = _encode_key(normal_form)
        summary = {
            "ast_nodes": ast_nodes, "ast_max_depth": self.max_depth,
            "original_ast_values_bounded": self.nodes_checked,
            "normalization_work_units": self.work,
            "normal_form_terms": len(normal_form), "normal_form_bytes": len(encoded),
            "normal_form_sha256": hashlib.sha256(encoded.encode("ascii")).hexdigest(),
            "maximum_numerator_absolute_bound": str(self.max_numerator_bound),
            "maximum_denominator_divisor": self.max_denominator_divisor,
            "maximum_absolute_value_bound": str(self.max_magnitude_bound),
            "root_absolute_value_bound": str(result.bound.magnitude),
            "root_denominator_divisor": result.bound.denominator_divisor,
        }
        return normal_form, summary


def certify_equivalence(candidate: Any, specification: Any, *, reserve_le_ceiling: bool = False,
                        include_proof: bool = False) -> dict:
    """Return a recomputed certificate; unsupported cases fail closed.

    The specification is evaluator-held, while the candidate is untrusted.
    The only order assumption available to this checker is the explicitly
    selected reserve<=ceiling contract. A positive result proves equality and
    bounded total evaluation on the fixed integer input box. A negative result
    is ``not_certified`` and does not assert mathematical inequivalence.
    """
    result: dict[str, Any] = {"schema_version": SCHEMA, "status": "not_certified", "certified": False,
        "equivalence_proved": False, "totality_and_resource_bounds_proved": False,
        "normal_forms_match": None, "input_magnitude": INPUT_MAGNITUDE,
        "scale_range": [1, INPUT_MAGNITUDE], "reserve_le_ceiling": bool(reserve_le_ceiling),
        "numeric_limit": NUMERIC_LIMIT,
        "verification_scope": "sufficient symbolic equality and bounded total rational evaluation on the declared integer input box"}
    if type(reserve_le_ceiling) is not bool:
        result.update(reason_code="invalid_assumption_flag", reason="reserve_le_ceiling must be a Boolean")
        return result
    normalizers = []
    normal_forms = []
    try:
        for label, source in (("candidate", candidate), ("specification", specification)):
            normalizer = _Normalizer(reserve_le_ceiling)
            normal_form, summary = normalizer.analyze(source)
            summary["source_sha256"] = hashlib.sha256(source.encode("utf-8")).hexdigest()
            result[label] = summary
            normalizers.append(normalizer)
            normal_forms.append(normal_form)
        result["totality_and_resource_bounds_proved"] = True
        matches = normal_forms[0] == normal_forms[1]
        result["normal_forms_match"] = matches
        if matches:
            result.update(status="certified", certified=True, equivalence_proved=True,
                          reason_code="matching_normal_forms", reason="equal sound normal forms and all original AST values conservatively bounded")
        else:
            result.update(reason_code="normal_forms_differ", reason="normal forms differ under this sufficient proof system; equivalence is not certified")
        if include_proof:
            result["proof"] = {
                label: {"normal_form": json.loads(_encode_key(form)), "intermediate_bounds": normalizer.bound_trace}
                for label, form, normalizer in zip(("candidate", "specification"), normal_forms, normalizers)
            }
    except NotCertified as exc:
        result.update(reason_code=exc.code, reason=str(exc)[:240])
    except (ArithmeticError, RecursionError, TypeError, ValueError) as exc:
        result.update(reason_code="bounded_checker_failure", reason=f"{type(exc).__name__}: {str(exc)[:200]}")
    return result
