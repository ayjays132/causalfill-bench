"""Independent numerical and adversarial checks of the sufficient workflow proof system."""
import ast
from fractions import Fraction
import itertools
import json
import random
import unittest
from unittest.mock import patch

from causalfill.domains.workflow import WorkflowTask, expression
from causalfill.policies import evidence_reference
from causalfill.session import Session
from causalfill.workflow_certificate import (
    INPUT_MAGNITUDE, NUMERIC_LIMIT, certify_equivalence, input_in_contract, public_contract,
)


def direct_values(source, values):
    """Direct Fraction semantics with each original intermediate retained.

    No production interpreter, normalizer, polynomial, lattice or resource-bound
    function participates in this numeric oracle.
    """
    tree = ast.parse(source, mode="eval") if isinstance(source, str) else source
    recorded = []

    def visit(node):
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Name):
            value = Fraction(values[node.id])
        elif isinstance(node, ast.Constant):
            value = Fraction(node.value)
        elif isinstance(node, ast.UnaryOp):
            value = visit(node.operand)
            if isinstance(node.op, ast.USub):
                value = -value
        elif isinstance(node, ast.BinOp):
            left, right = visit(node.left), visit(node.right)
            if isinstance(node.op, ast.Add): value = left + right
            elif isinstance(node.op, ast.Sub): value = left - right
            elif isinstance(node.op, ast.Mult): value = left * right
            else: value = left / right
        elif isinstance(node, ast.Call):
            arguments = [visit(argument) for argument in node.args]
            value = min(arguments) if node.func.id == "min" else max(arguments)
        else:
            raise AssertionError(type(node).__name__)
        recorded.append((type(node).__name__, getattr(node, "col_offset", 0), value))
        return value

    return visit(tree), recorded


class WorkflowCertificateTests(unittest.TestCase):
    def test_public_integer_contract_and_conditional_order_assumption(self):
        box = public_contract(True)
        self.assertEqual(box["constraints"], ["reserve <= ceiling"])
        self.assertEqual(box["input_domain"]["scale"]["minimum"], 1)
        self.assertEqual(box["input_domain"]["balance"]["minimum"], -INPUT_MAGNITUDE)
        good = dict(balance=-INPUT_MAGNITUDE, amount=INPUT_MAGNITUDE, fee=-1,
                    reserve=-INPUT_MAGNITUDE, ceiling=INPUT_MAGNITUDE, scale=INPUT_MAGNITUDE)
        self.assertTrue(input_in_contract(good, True))
        for field, value in (("scale", 0), ("scale", -1), ("balance", INPUT_MAGNITUDE+1),
                             ("amount", True), ("fee", Fraction(1, 2))):
            self.assertFalse(input_in_contract({**good, field: value}, True))
        reversed_order = {**good, "reserve": 10, "ceiling": 0}
        self.assertTrue(input_in_contract(reversed_order))
        self.assertFalse(input_in_contract(reversed_order, True))

    def test_all_split_dimension_twin_references_and_public_reference_policy(self):
        for split, difficulty, twin in itertools.product(("train", "dev", "transfer"), (1, 2, 3), (0, 1)):
            task = WorkflowTask(31, split, difficulty, twin)
            self.assertTrue(task.evaluate(task.reference_answer()).success)
            session = Session(task)
            # Verification must not consult an oracle/reference-answer method.
            task.reference_answer = lambda: (_ for _ in ()).throw(AssertionError("reference oracle consulted"))
            fill, abstain = evidence_reference(session.public(), session.call)
            self.assertFalse(abstain)
            result = session.call("submit", {"fill": fill, "confidence": 1.0, "abstain": False,
                                             "evidence": [event["event_id"] for event in session.trace]})
            self.assertTrue(result["accepted"])
            self.assertTrue(session.result["success"])
            self.assertEqual(session.invalid, 0)

    def test_threshold_attacks_pass_sample_suite_but_fail_strict_certificate(self):
        for split in ("train", "dev", "transfer"):
            task = WorkflowTask(5, split)
            correct = task.reference_answer()["expression"]
            for threshold in (19, 9999):
                candidate = f"({correct})+max(0,scale-{threshold})"
                verdict = task.evaluate({"expression": candidate})
                self.assertEqual(verdict.details["passed"], verdict.details["behavior_cases"])
                self.assertEqual(verdict.details["behavior_pass_rate"], 1.0)
                self.assertFalse(verdict.success)
                self.assertEqual(verdict.outcome, 0.0)
                certificate = verdict.details["symbolic_certificate"]
                self.assertTrue(certificate["totality_and_resource_bounds_proved"])
                self.assertEqual(certificate["status"], "not_certified")
                self.assertEqual(certificate["reason_code"], "normal_forms_differ")
                witness = dict(balance=40, amount=7, fee=3, reserve=10, ceiling=50, scale=threshold+1)
                self.assertTrue(input_in_contract(witness, split == "transfer"))
                self.assertNotEqual(expression(candidate, witness), task.expected(witness))

    def test_legitimate_rational_polynomial_alternatives(self):
        base = "balance-amount*scale-fee"
        alternatives = ["balance-fee-scale*amount", "balance+(-scale)*amount-fee",
                        "(2*balance-2*fee-2*amount*scale)/2",
                        "(balance-fee-amount*scale)/(amount-amount+1)",
                        "(balance/2+balance/2)-amount*scale-fee",
                        base+"+max(balance,amount)-max(amount,balance)"]
        for source in alternatives:
            result = certify_equivalence(source, base)
            self.assertTrue(result["certified"], (source, result))
        for source, expected in (("balance/(amount-amount+2)", "balance/2"),
                                 ("balance/(2/3)", "3*balance/2"),
                                 ("(balance+amount)*fee", "balance*fee+amount*fee")):
            self.assertTrue(certify_equivalence(source, expected)["certified"])

    def test_lattice_identities_and_clamp_reordering_require_correct_assumptions(self):
        identities = [
            ("max(balance,amount)", "max(amount,balance)"),
            ("min(balance,balance)", "balance"),
            ("max(balance,min(balance,amount))", "balance"),
            ("min(balance,max(amount,fee))", "max(min(balance,amount),min(balance,fee))"),
            ("max(balance,min(amount,fee))", "min(max(balance,amount),max(balance,fee))"),
            ("min(balance,min(amount,fee))", "min(fee,amount,balance)"),
            ("max(1/3,1/2)", "1/2"),
        ]
        for left, right in identities:
            self.assertTrue(certify_equivalence(left, right)["certified"], (left, right))
        a = "min(max(balance-amount*scale-fee,reserve),ceiling)"
        b = "max(reserve,min(ceiling,balance-fee-scale*amount))"
        self.assertFalse(certify_equivalence(a, b)["certified"])
        self.assertTrue(certify_equivalence(a, b, reserve_le_ceiling=True)["certified"])
        witness = dict(balance=5, amount=0, fee=0, reserve=10, ceiling=0, scale=1)
        self.assertNotEqual(direct_values(a, witness)[0], direct_values(b, witness)[0])

    def test_pole_zero_and_variable_divisor_cancellation_fail_closed(self):
        for source in ("0/(balance-balance)", "0/(scale-20)",
                       "(scale-20)/(scale-20)-1", "0*(1/(scale-20))"):
            result = certify_equivalence(source, "0")
            self.assertFalse(result["certified"], source)
            self.assertFalse(result["totality_and_resource_bounds_proved"])
        # This IS mathematically equivalent on the declared scale>=1 domain.
        # The deliberately sufficient proof system does not certify it.
        incomplete = certify_equivalence("balance/scale*scale", "balance")
        self.assertFalse(incomplete["certified"])
        self.assertEqual(incomplete["reason_code"], "variable_divisor_not_certified")
        for split in ("train", "dev", "transfer"):
            task = WorkflowTask(9, split)
            source = task.reference_answer()["expression"]+"+0/(scale-20)"
            verdict = task.evaluate({"expression": source})
            self.assertEqual(verdict.details["behavior_pass_rate"], 1.0)
            self.assertFalse(verdict.success)

    def test_original_intermediate_overflow_cannot_be_cancelled_away(self):
        huge = "balance*balance*balance*balance*balance*balance"
        task = WorkflowTask(7, "train")
        source = task.reference_answer()["expression"]+f"+({huge})-({huge})"
        verdict = task.evaluate({"expression": source})
        self.assertEqual(verdict.details["behavior_pass_rate"], 1.0)
        self.assertFalse(verdict.success)
        self.assertEqual(verdict.details["symbolic_certificate"]["reason_code"], "resource_bound_not_proved")
        witness = dict(balance=INPUT_MAGNITUDE, amount=0, fee=0, reserve=0, ceiling=0, scale=1)
        with self.assertRaises(ValueError):
            expression(source, witness)

    def test_exact_fraction_resource_boundary_and_conservative_incompleteness(self):
        exact_integer = "*".join(["10000"]*7+["100"])
        exact_denominator = "1/"+"/".join(["10000"]*7+["100"])
        for source in (exact_integer, exact_denominator):
            result = certify_equivalence(source, source, include_proof=True)
            self.assertTrue(result["certified"], result)
        for source in (exact_integer+"*2", exact_denominator+"/2"):
            result = certify_equivalence(source, source)
            self.assertFalse(result["certified"])
            self.assertEqual(result["reason_code"], "resource_bound_not_proved")
        # Each actual Fraction here is exactly zero. The denominator-divisor
        # bound deliberately overapproximates and may refuse this valid form.
        source = "0/"+"/".join(["10000"]*8)
        self.assertEqual(direct_values(source, {})[0], 0)
        result = certify_equivalence(source, "0")
        self.assertFalse(result["certified"])
        self.assertEqual(result["reason_code"], "resource_bound_not_proved")

    def test_every_reported_intermediate_bound_matches_independent_extreme_inputs(self):
        sources = ["balance/6+amount/10", "(balance/6)*(amount/10)", "balance/(2/3)",
                   "min(balance/6,amount/10)", "max(min(balance/6,amount/10),fee/14)",
                   "(balance-fee)*(amount+scale)/12", "min(max(balance-amount*scale-fee,reserve),ceiling)"]
        points = (-INPUT_MAGNITUDE, 0, INPUT_MAGNITUDE)
        for source in sources:
            result = certify_equivalence(source, source, include_proof=True)
            self.assertTrue(result["certified"], result)
            trace = result["proof"]["candidate"]["intermediate_bounds"]
            tree = ast.parse(source, mode="eval")
            for vector in itertools.product(points, repeat=5):
                for scale in (1, INPUT_MAGNITUDE):
                    values = dict(zip(("balance", "amount", "fee", "reserve", "ceiling"), vector))
                    values["scale"] = scale
                    _, intermediates = direct_values(tree, values)
                    self.assertEqual(len(trace), len(intermediates))
                    for checked, (kind, column, value) in zip(trace, intermediates):
                        self.assertEqual((checked["node"], checked["column"]), (kind, column))
                        m, d = Fraction(checked["absolute_value_bound"]), checked["denominator_divisor"]
                        self.assertLessEqual(abs(value), m)
                        self.assertEqual(d % value.denominator, 0)
                        self.assertLessEqual(abs(value.numerator), Fraction(checked["numerator_absolute_bound"]))
                        self.assertLessEqual(Fraction(checked["numerator_absolute_bound"]), NUMERIC_LIMIT)
                        self.assertLessEqual(d, NUMERIC_LIMIT)

    def test_exhaustive_small_lattice_forms_agree_with_direct_truth_semantics(self):
        leaves = ["balance", "amount", "fee"]
        shallow = leaves+[f"{op}({a},{b})" for op in ("min", "max") for a in leaves for b in leaves]
        expressions = shallow+[f"{op}({a},{b})" for op in ("min", "max") for a in shallow for b in shallow]
        expressions += ["max(min(balance,amount),min(balance,fee),min(amount,fee))",
                        "min(max(balance,amount),max(balance,fee),max(amount,fee))"]
        meanings_by_form, forms_by_meaning = {}, {}
        for source in expressions:
            checked = certify_equivalence(source, source, include_proof=True)
            self.assertTrue(checked["certified"], (source, checked))
            form = json.dumps(checked["proof"]["candidate"]["normal_form"], separators=(",", ":"))
            tree = ast.parse(source, mode="eval")
            meanings = tuple(direct_values(tree, dict(zip(leaves, values)))[0]
                             for values in itertools.product((-1, 0, 1), repeat=3))
            meanings_by_form.setdefault(form, set()).add(meanings)
            forms_by_meaning.setdefault(meanings, set()).add(form)
        self.assertEqual(len(expressions), 905)
        self.assertEqual(len(meanings_by_form), 18)
        self.assertTrue(all(len(meanings) == 1 for meanings in meanings_by_form.values()))
        self.assertTrue(all(len(forms) == 1 for forms in forms_by_meaning.values()))

    def test_randomized_polynomial_identities_over_lattice_atoms(self):
        rng = random.Random(78031)
        atoms = ["balance", "amount", "fee", "min(balance,amount)", "max(amount,fee)", "1/3", "-2"]
        for _ in range(200):
            a, b, c = [rng.choice(atoms) for _ in range(3)]
            left, right = f"(({a})+({b}))*({c})", f"({a})*({c})+({b})*({c})"
            self.assertTrue(certify_equivalence(left, right)["certified"], (left, right))
            self.assertTrue(certify_equivalence(f"({a})-({a})+({b})", b)["certified"])
            for values in itertools.product((-2, 0, 3), repeat=3):
                inputs = dict(zip(("balance", "amount", "fee"), values))
                self.assertEqual(direct_values(left, inputs)[0], direct_values(right, inputs)[0])

    def test_malformed_and_expanding_expressions_return_not_certified(self):
        invalid = [None, True, [], {}, "", "balance"*200, "True", "1.5", "10001", "balance**2",
                   "min(balance)", "max(balance,amount,fee,reserve,ceiling)", "max(balance,amount,key=abs)",
                   "__import__('os')", "balance.__class__", "[balance][0]", "lambda: balance",
                   "("*350+"balance"+")"*350, "+".join(["balance"]*100)]
        for source in invalid:
            result = certify_equivalence(source, "balance")
            self.assertFalse(result["certified"], source)
            self.assertEqual(result["status"], "not_certified")
        expanding = "*".join(["(balance+amount+fee+reserve+ceiling+scale)"]*8)
        self.assertFalse(certify_equivalence(expanding, "0")["certified"])
        # Concrete resource caps are also exercised independently of AST size.
        with patch("causalfill.workflow_certificate.MAX_POLYNOMIAL_TERMS", 2):
            result = certify_equivalence("balance+amount+fee", "balance")
            self.assertEqual(result["reason_code"], "polynomial_term_limit")
        with patch("causalfill.workflow_certificate.MAX_LATTICE_TERMS", 2):
            result = certify_equivalence("max(balance,amount,fee)", "balance")
            self.assertEqual(result["reason_code"], "lattice_term_limit")
        with patch("causalfill.workflow_certificate.MAX_NORMALIZATION_WORK", 3):
            result = certify_equivalence("balance+amount", "balance")
            self.assertEqual(result["reason_code"], "normalization_work_limit")


if __name__ == "__main__":
    unittest.main()
