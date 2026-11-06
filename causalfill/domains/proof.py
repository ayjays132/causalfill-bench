"""Proof-carrying completion for finite propositional controller statements.

The search procedure is untrusted. Final certificates are checked by a separate
resolution kernel against fixed, digest-bound premises and a signed conclusion.
An explicit satisfying model rules out vacuous proofs from inconsistent premises.
"""
from __future__ import annotations

import json

from ..types import Task, Verdict, fields
from ..logic_kernel import statement_digest, verify_model, verify_resolution


def _chain(length):
    return [[1]] + [[-i,i+1] for i in range(1,length)] + [[-length]], length


def _parity(inputs, values):
    clauses=[[i if value else -i] for i,value in enumerate(values,1)]
    previous=1
    parity=values[0]
    for variable in range(2,inputs+1):
        result=inputs+variable-1
        # result <-> previous XOR variable.
        clauses.extend([[previous,variable,-result],[-previous,-variable,-result],
                        [previous,-variable,result],[-previous,variable,result]])
        previous=result
        parity=parity != values[variable-1]
    clauses.append([-previous if parity else previous])
    return clauses,2*inputs-1


def _pigeonhole(pigeons):
    holes=pigeons-1
    v=lambda p,h:p*holes+h+1
    clauses=[[v(p,h) for h in range(holes)] for p in range(pigeons)]
    clauses.extend([-v(p,h),-v(q,h)] for h in range(holes)
                   for p in range(pigeons) for q in range(p+1,pigeons))
    clauses.extend([-v(p,h),-v(p,k)] for p in range(pigeons)
                   for h in range(holes) for k in range(h+1,holes))
    return clauses,pigeons*holes


class ProofTask(Task):
    family="proof"

    def __init__(self,seed,split="dev",difficulty=2,twin=0):
        super().__init__(seed,split,difficulty,twin)
        if split=="train":
            base,nbase=_chain(3+3*difficulty)
            structure="implication-chain"
        elif split=="dev":
            ninputs=3+difficulty
            values=[self.rng.choice((False,True)) for _ in range(ninputs)]
            base,nbase=_parity(ninputs,values)
            structure="xor-ladder"
        else:
            # This finite contradiction family is established prior art, not a
            # new theorem. The gated controller statement is original here.
            pigeons={1:4,2:5,3:7}[difficulty]
            base,nbase=_pigeonhole(pigeons)
            structure=f"pigeonhole-{pigeons}-into-{pigeons-1}"
        self.nvars=nbase+1
        labels=list(range(1,self.nvars+1))
        self.rng.shuffle(labels)
        polarity=[self.rng.choice((-1,1)) for _ in range(self.nvars)]
        def relabel(literal):
            return (1 if literal>0 else -1)*polarity[abs(literal)-1]*labels[abs(literal)-1]
        self._base=[sorted(relabel(x) for x in clause) for clause in base]
        # A single signed-output convention changes across twins. This is a
        # theorem-polarity intervention, not a physical causal intervention.
        self.goal=relabel(self.nvars)*(-1 if twin else 1)
        self.clauses=[sorted(clause+[self.goal]) for clause in self._base]
        self.statement={"nvars":self.nvars,"clauses":self.clauses,"goal":self.goal,
            "statement_sha256":statement_digest(self.clauses,self.nvars,self.goal)}
        self.twin_kind="theorem_polarity"
        self.structural_signature=f"proof:{structure}:v1"
        self.budget=20
        self.max_calls=24
        self.slots={
            "statement_sha256":{"type":"string","description":"Exact SHA256 from the fixed public formal statement."},
            "proof_steps":{"type":"array[array[int,int,int]]","description":"Resolution steps [left_index,right_index,pivot]; max 12000 steps and protocol size bound."},
            "consistency_model":{"type":"array[bool]","description":f"Exactly {self.nvars} Boolean values satisfying the ORIGINAL premises F."},
        }
        self.prompt=(
            "Fill the missing proof of a controller's signed output condition. Read the immutable formal statement F, "
            "its variable count and goal literal. Supply a resolution refutation of F plus the negated goal, AND "
            "a concrete satisfying model of F. This establishes the stated conclusion without exploiting "
            "inconsistent assumptions. Use the exact statement digest; changing or weakening the theorem is invalid. "
            "Only compact proof-index triples are accepted; no source code, new premises, admitted axioms or prose proofs. "
            "The task is finite propositional logic and is not a Lean or physical-control evaluation."
        )
        self.files={
            "/formal/statement.json":json.dumps(self.statement,separators=(",",":")),
            "/workspace/controller.txt":(
                "Certified controller output\n"
                "Assumptions: the fixed clauses F in /formal/statement.json.\n"
                "Conclusion: the exact signed goal literal in that file.\n"
                "Proof: <MASK:resolution_steps>\n"
                "Assumption-consistency witness: <MASK:consistency_model>\n"
                "The output polarity is a specification parameter, not an editable claim.\n"
            ),
            "/docs/resolution.txt":(
                "Variables are numbered 1..nvars. A positive integer denotes a variable; a negative integer its negation.\n"
                "Each clause is a disjunction. The list of clauses is their conjunction F. Empty clause is false.\n"
                "The initial proof clauses are all F clauses in their original order, followed by the ONE clause [-goal].\n"
                "A proof step [a,b,p] references earlier clause indices, zero-based. p is a positive variable number.\n"
                "One parent must contain +p and the other -p. Remove the chosen pivot sign from each parent and union the remaining literals.\n"
                "That resolvent becomes the next clause. The final derived clause must be empty.\n"
                "No arbitrary clauses, deleted premises, forward references or extra axioms are allowed.\n"
                "Submit a list of nvars booleans whose index i-1 gives variable i. It must satisfy F, not F plus [-goal].\n"
                "The statement digest binds nvars, every normalized F clause and its order, and the signed goal. Copy the public digest exactly.\n"
                "The prefix checker verifies at most 256 submitted steps without completing them. A valid prefix need not prove the goal.\n"
                "The full certificate allows at most 12000 steps, at most 500000 total literal entries, and must fit the 128 KiB tool request.\n"
                "These are finite implication-chain, XOR-ladder or resource-capacity statements. Exact proof checking does not establish frontier difficulty.\n"
            ),
        }
        self.tools={"check_prefix":{"description":"Check at most 256 proposed resolution steps; never solve or complete the proof",
            "arguments":{"proof_steps":"list of compact [a,b,p] triples"},"cost":2}}

    def query(self,name,args):
        if name!="check_prefix":
            raise ValueError("unknown proof tool")
        fields(args,{"proof_steps"})
        steps=args["proof_steps"]
        if type(steps) is not list or len(steps)>256:
            raise ValueError("prefix must contain at most 256 steps")
        result=verify_resolution(self.clauses+[[-self.goal]],steps,self.nvars,max_steps=256)
        return {"prefix_valid":result["valid"],"derived_empty":result["derived_empty"],
                "checked_steps":result["checked_steps"],"error":result["error"]}

    def evaluate(self,fill):
        try:
            fields(fill,{"statement_sha256","proof_steps","consistency_model"})
            bound=type(fill["statement_sha256"]) is str and fill["statement_sha256"]==self.statement["statement_sha256"]
            proof=verify_resolution(self.clauses+[[-self.goal]],fill["proof_steps"],self.nvars)
            consistent=verify_model(self.clauses,fill["consistency_model"],self.nvars)
            proved=bool(proof["valid"] and proof["derived_empty"])
            success=bool(bound and proved and consistent)
            return Verdict(success,float(bound and proved),float(success),1.0,
                {"statement_bound":bound,"refutation_valid":proof["valid"],"conclusion_proved":proved,
                 "premises_consistent":consistent,"checked_steps":proof["checked_steps"],
                 "kernel_error":proof["error"],"verification_scope":"finite-propositional-resolution",
                 "twin_kind":self.twin_kind,"variables":self.nvars,"premises":len(self.clauses)})
        except (TypeError,ValueError,KeyError):
            return Verdict(False,details={"invalid_fill":True})

    def reference_answer(self):
        from ..proof_search import solve_statement
        return solve_statement(json.loads(self.files["/formal/statement.json"]))
