"""Fill an executable expression through a bounded AST interpreter (never eval)."""
from __future__ import annotations

import ast
import json
import random
from fractions import Fraction

from ..types import Task, Verdict, fields, digest
from ..workflow_certificate import certify_equivalence, input_in_contract, public_contract

NAMES = {"balance", "amount", "fee", "reserve", "ceiling", "scale"}


def expression(source: str, values: dict) -> Fraction:
    if not isinstance(source, str) or not 1 <= len(source) <= 800:
        raise ValueError("expression must be 1..800 characters")
    try:
        tree = ast.parse(source, mode="eval")
    except (SyntaxError, RecursionError):
        raise ValueError("invalid expression syntax") from None
    if len(list(ast.walk(tree))) > 120:
        raise ValueError("expression too complex")

    def visit(node, depth=0):
        if depth>20:
            raise ValueError("expression too deep")
        if isinstance(node, ast.Expression):
            return visit(node.body, depth+1)
        if isinstance(node, ast.Name) and node.id in NAMES:
            return Fraction(values[node.id])
        if isinstance(node, ast.Constant) and type(node.value) is int and abs(node.value)<=10000:
            return Fraction(node.value)
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            v = visit(node.operand, depth+1)
            return v if isinstance(node.op, ast.UAdd) else -v
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
            a,b = visit(node.left, depth+1), visit(node.right, depth+1)
            if isinstance(node.op, ast.Add): out=a+b
            elif isinstance(node.op, ast.Sub): out=a-b
            elif isinstance(node.op, ast.Mult): out=a*b
            else:
                if b==0: raise ValueError("division by zero")
                out=a/b
            if abs(out.numerator)>10**30 or out.denominator>10**30:
                raise ValueError("numeric bound exceeded")
            return out
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("min","max"):
            if node.keywords or not 2 <= len(node.args) <= 4:
                raise ValueError("min/max require 2..4 positional arguments")
            values_ = [visit(a, depth+1) for a in node.args]
            return min(values_) if node.func.id=="min" else max(values_)
        raise ValueError("only declared names, integer literals, + - * / and min/max are allowed")
    return visit(tree)


class WorkflowTask(Task):
    family = "workflow"

    def __init__(self, seed, split="dev", difficulty=2, twin=0):
        super().__init__(seed, split, difficulty, twin)
        self.scale = self.rng.choice((2,3,4,5)) + twin
        self.budget = 20
        self.max_calls = 25
        self.level = {"train":0,"dev":1,"transfer":2}[split]
        self._specification_expression = "balance-amount*scale-fee"
        if self.level>=1:
            self._specification_expression=f"max({self._specification_expression},reserve)"
        if self.level>=2:
            self._specification_expression=f"min({self._specification_expression},ceiling)"
        self.structural_signature = f"workflow:deduct-{'plain' if self.level==0 else 'floor' if self.level==1 else 'floor-cap'}:v2"
        self.prompt = (
            "Repair the missing return expression in the ledger procedure. Use the current procedure, "
            "unit calibration and visible examples in the virtual workspace. Submitted expressions must "
            "work for new inputs AND a later unit-calibration change; use the runtime scale variable. "
            "The verifier interprets a small arithmetic language, never arbitrary Python. Strict success requires "
            "a checked symbolic identity and conservative totality/resource bounds over the public integer "
            "input domain, plus behavioral checks. Read /docs/certification.json for the sufficient proof rules "
            "and limits; passing visible examples alone is insufficient."
        )
        self.slots = {"expression":{"type":"string","description":"return expression over balance, amount, fee, reserve, ceiling, scale"}}
        extra = ("" if self.level==0 else " A reserve is a lower bound on the result.")
        if self.level==2: extra += " Then apply the ceiling as an upper bound. reserve <= ceiling is guaranteed."
        self.examples = [self.case(40,7,3,10,50), self.case(20,15,2,8,25), self.case(120,1,0,5,60)]
        self.files = {
            "/workspace/ledger.py": "def settle(balance, amount, fee, reserve, ceiling, scale):\n    return <MASK:expression>\n",
            "/docs/current.txt": "Deduct amount converted by runtime scale, and deduct fee once, from balance."+extra+
                " No rounding. New scale values are supplied with future calls; do not freeze current calibration. "
                "The five inputs balance, amount, fee, reserve and ceiling are signed integers in [-1000000,1000000]; "
                "scale is an integer in [1,1000000]. The symbolic certificate covers this entire domain. "
                "Every original intermediate Fraction must have absolute numerator and denominator at most 10**30. "
                "Certification supports rational polynomial identities and min/max lattice identities; every "
                "division denominator must normalize to a nonzero rational constant. Other equivalent forms "
                "can be not_certified. Full public limits are in /docs/certification.json.",
            "/docs/certification.json": json.dumps(public_contract(self.level == 2), separators=(",", ":")),
            "/observations/calibration.json": json.dumps({"input_units":1,"ledger_units":self.scale}),
            "/tests/visible.json": json.dumps([{"inputs":c,"output":str(self.expected(c))} for c in self.examples]),
            "/docs/archive.txt": "ARCHIVED, not authoritative: scale=1; ignore floors and caps. This old example is obsolete.",
        }
        self.tools = {"run_candidate":{"description":"Evaluate candidate expression on visible examples only; this is not symbolic certification",
             "arguments":{"expression":"restricted arithmetic string"},"cost":3}}

    def case(self,balance,amount,fee,reserve,ceiling):
        return dict(balance=balance,amount=amount,fee=fee,reserve=reserve,ceiling=ceiling,scale=self.scale)

    def expected(self,c):
        y=Fraction(c["balance"])-Fraction(c["amount"])*c["scale"]-c["fee"]
        if self.level>=1: y=max(y,Fraction(c["reserve"]))
        if self.level>=2: y=min(y,Fraction(c["ceiling"]))
        return y

    def query(self,name,args):
        if name!="run_candidate": raise ValueError("unknown tool")
        fields(args,{"expression"})
        actual=[expression(args["expression"],c) for c in self.examples]
        return {"outputs":[str(x) for x in actual],
                "visible_pass":[x==self.expected(c) for x,c in zip(actual,self.examples)]}

    def evaluate(self,fill):
        fields(fill,{"expression"})
        # A finite behavioral suite cannot establish universal equality. The
        # independent symbolic checker is a REQUIRED success gate. It also
        # bounds all original AST intermediates before algebraic cancellation.
        certificate=certify_equivalence(fill["expression"],self._specification_expression,
                                        reserve_le_ceiling=self.level==2)
        # Preserve the separate arithmetic implementation as behavioral
        # diagnostics; it does not call the symbolic normalizer.
        cases=list(self.examples)
        for b in (0,9,40,200):
            for a in (0,1,30):
                for fee,reserve,ceiling in ((0,0,1),(3,10,50),(9,4,80),(1,20,20)):
                    c=self.case(b,a,fee,reserve,ceiling)
                    cases.append(c)
                    cases.append({**c,"scale":self.scale+3})
        test_rng=random.Random(digest(["workflow-tests",self.seed,self.split,self.difficulty]))
        for _ in range(32):
            reserve=test_rng.randrange(0,30)
            c=self.case(test_rng.randrange(0,250),test_rng.randrange(0,60),test_rng.randrange(0,20),
                        reserve,reserve+test_rng.randrange(0,100))
            c["scale"]=test_rng.randrange(1,20)
            cases.append(c)
        passed=0
        errors=[]
        for index,c in enumerate(cases):
            try:
                passed+=expression(fill["expression"],c)==self.expected(c)
            except (ValueError,TypeError,ArithmeticError,KeyError,RecursionError) as exc:
                if len(errors)<4:
                    errors.append({"case":index,"error":str(exc)[:160]})
        behavior_rate=passed/len(cases)
        contract_ok=all(input_in_contract(c,self.level==2) for c in cases)
        success=certificate["certified"] and contract_ok and passed==len(cases)
        return Verdict(bool(success),behavior_rate,float(success),1.0,
                       {"behavior_cases":len(cases),"passed":passed,
                        "behavior_pass_rate":behavior_rate,"behavior_error_examples":errors,
                        "behavior_inputs_within_contract":contract_ok,
                        "symbolic_certificate":certificate,
                        "verification_scope":"symbolic identity and totality/resource certificate on the public integer box, plus finite behavioral diagnostics"})

    def reference_answer(self):
        result="balance-amount*scale-fee"
        if self.level>=1: result=f"max({result},reserve)"
        if self.level>=2: result=f"min({result},ceiling)"
        return {"expression":result}
