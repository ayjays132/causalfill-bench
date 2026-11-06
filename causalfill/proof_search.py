"""Untrusted certificate search, deliberately separate from the resolution kernel.

The generator/verifier never accepts this module's answer without checking it.
Search uses Davis-Putnam variable elimination with subsumption and proof-DAG
pruning. This is a small deterministic reference, not a new SAT algorithm.
"""
from __future__ import annotations

import json


def resolution_refutation(clauses, nvars, max_steps=12000, search_clause_limit=100000):
    """Return compact [parent_a, parent_b, pivot] triples deriving the empty clause.

    Clause indices refer to the original order, followed by derived clauses.
    Search is bounded and may fail even when a refutation exists. No execution
    or evaluator-private state is used.
    """
    if type(nvars) is not int or not 1 <= nvars <= 200:
        raise ValueError("nvars must be an integer in 1..200")
    if type(clauses) is not list or len(clauses) > 2000:
        raise ValueError("clauses must be a bounded list")
    original = []
    for clause in clauses:
        if type(clause) not in (list, tuple) or len(clause) > 2*nvars:
            raise ValueError("invalid clause")
        if any(type(lit) is not int or lit == 0 or abs(lit)>nvars for lit in clause):
            raise ValueError("invalid literal")
        original.append(frozenset(clause))
    all_clauses = list(original)
    steps = []
    active = {i for i,c in enumerate(original) if not any(-x in c for x in c)}
    known = {}
    for i,c in enumerate(original):
        known.setdefault(c,i)

    def add(a,b,pivot,result):
        if result in known:
            return known[result]
        if len(all_clauses) >= search_clause_limit:
            raise ValueError("reference search clause limit exceeded")
        index = len(all_clauses)
        steps.append([a,b,pivot])
        all_clauses.append(result)
        known[result] = index
        return index

    def prune_proof(final_index):
        ninitial = len(original)
        needed = set()
        todo = [final_index]
        while todo:
            index=todo.pop()
            if index<ninitial or index in needed:
                continue
            needed.add(index)
            a,b,_=steps[index-ninitial]
            todo.extend((a,b))
        ordered=sorted(needed)
        if len(ordered)>max_steps:
            raise ValueError("reference proof exceeds submission step limit")
        remap={old:ninitial+i for i,old in enumerate(ordered)}
        return [[remap.get(a,a),remap.get(b,b),v]
                for old in ordered for a,b,v in [steps[old-ninitial]]]

    for i,c in enumerate(original):
        if not c:
            return []
    while active:
        counts={}
        for index in active:
            for lit in all_clauses[index]:
                counts.setdefault(abs(lit),[[],[]])[lit<0].append(index)
        if not counts:
            break
        # Unit clauses first; otherwise min-fill elimination limits growth.
        units=[(abs(next(iter(all_clauses[i]))),i) for i in active if len(all_clauses[i])==1]
        if units:
            pivot=min(units)[0]
        else:
            pivot=min(counts,key=lambda v:(len(counts[v][0])*len(counts[v][1]),
                                            len(counts[v][0])+len(counts[v][1]),v))
        positives,negatives=counts[pivot]
        residual=active-set(positives)-set(negatives)
        candidates={}
        for a in sorted(positives):
            for b in sorted(negatives):
                resolvent=(all_clauses[a]-{pivot}) | (all_clauses[b]-{-pivot})
                if any(-lit in resolvent for lit in resolvent):
                    continue
                candidates.setdefault(resolvent,(a,b))
        # Keep shortest resolvents first. A retained stronger clause makes a
        # larger one unnecessary; all retained clauses still have real proofs.
        for clause,(a,b) in sorted(candidates.items(),key=lambda item:(len(item[0]),tuple(sorted(item[0])))):
            if any(all_clauses[i] <= clause for i in residual):
                continue
            index=add(a,b,pivot,clause)
            if not clause:
                return prune_proof(index)
            residual={i for i in residual if not clause < all_clauses[i]}
            residual.add(index)
        active=residual
    raise ValueError("no resolution refutation found; input may be satisfiable")


def solve_statement(statement):
    """Construct a fill from a public statement; no Task object is accepted."""
    if type(statement) is not dict:
        raise ValueError("statement must be an object")
    nvars=statement["nvars"]
    clauses=statement["clauses"]
    goal=statement["goal"]
    if type(goal) is not int or goal == 0 or abs(goal)>nvars:
        raise ValueError("goal must be a signed variable")
    # These benchmark assumptions explicitly gate every clause by the goal.
    # A concrete model is still supplied and independently checked by the kernel.
    witness=[False]*nvars
    witness[abs(goal)-1]=goal>0
    proof=resolution_refutation(clauses+[[-goal]],nvars)
    result={"statement_sha256":statement["statement_sha256"],
            "proof_steps":proof,"consistency_model":witness}
    if len(json.dumps(result,separators=(",",":")))>120000:
        raise ValueError("reference certificate exceeds protocol size allowance")
    return result


def solve_proof(public,call):
    """Evidence-only adapter, compatible with Session or HTTP tool callbacks."""
    if public.get("family")!="proof":
        raise ValueError("not a proof task")
    response=call("read_file",{"path":"/formal/statement.json"})
    if "error" in response:
        raise ValueError(response["error"])
    return solve_statement(json.loads(response["content"]))
