import copy
import json
import unittest
from unittest.mock import patch

from causalfill.domains.proof import ProofTask
from causalfill.logic_kernel import verify_model, verify_resolution
from causalfill.proof_search import resolution_refutation, solve_proof
from causalfill.session import Session, verify_trace


class ProofTrackTests(unittest.TestCase):
    def test_reference_certifies_each_structure_and_difficulty(self):
        for split in ("train","dev","transfer"):
            for difficulty in (1,2,3):
                for twin in (0,1):
                    task=ProofTask(17,split,difficulty,twin)
                    fill=task.reference_answer()
                    self.assertTrue(task.evaluate(fill).success,(split,difficulty,twin))
                    self.assertLessEqual(len(fill["proof_steps"]),12000)
                    self.assertLess(len(json.dumps(fill,separators=(",",":"))),120000)

    def test_public_callback_reference_is_budgeted_and_has_no_task_access(self):
        task=ProofTask(9,"transfer",3)
        session=Session(task)
        with patch.object(task,"reference_answer",side_effect=AssertionError("private oracle used")):
            fill=solve_proof(session.public(),session.call)
        out=session.call("submit",{"fill":fill,"confidence":1.0,"abstain":False,"evidence":["e0001"]})
        self.assertTrue(out["accepted"])
        self.assertNotIn("success",out)
        self.assertTrue(session.result["success"])
        self.assertEqual(session.cost,1)
        self.assertEqual(session.invalid,0)
        self.assertTrue(verify_trace(session.trace))

    def test_checker_does_not_rely_on_the_search_implementation(self):
        task=ProofTask(1,"transfer",2)
        fill=task.reference_answer()
        with patch("causalfill.proof_search.resolution_refutation",side_effect=AssertionError("search invoked by checker")):
            self.assertTrue(task.evaluate(fill).success)

    def test_statement_cannot_be_weakened_or_rebound(self):
        task=ProofTask(2,"dev",2)
        fill=task.reference_answer()
        changed=copy.deepcopy(fill)
        changed["statement_sha256"]="0"*64
        self.assertFalse(task.evaluate(changed).success)
        changed=copy.deepcopy(fill)
        changed["goal"]=1
        self.assertFalse(task.evaluate(changed).success)

    def test_true_prefix_does_not_count_as_complete_proof(self):
        task=ProofTask(0,"train",1)
        fill=task.reference_answer()
        fill["proof_steps"]=fill["proof_steps"][:-1]
        prefix=task.query("check_prefix",{"proof_steps":fill["proof_steps"]})
        self.assertTrue(prefix["prefix_valid"])
        self.assertFalse(prefix["derived_empty"])
        self.assertFalse(task.evaluate(fill).success)

    def test_model_is_mandatory_and_blocks_vacuity(self):
        task=ProofTask(8,"train",2)
        fill=task.reference_answer()
        self.assertTrue(verify_model(task.clauses,fill["consistency_model"],task.nvars))
        fill["consistency_model"][abs(task.goal)-1]=task.goal<0
        verdict=task.evaluate(fill)
        self.assertTrue(verdict.details["conclusion_proved"])
        self.assertFalse(verdict.details["premises_consistent"])
        self.assertFalse(verdict.success)

    def test_forged_axioms_forward_refs_and_nonbool_models_fail(self):
        task=ProofTask(3,"train",1)
        fill=task.reference_answer()
        for bad in ([[0,0,1]],[[99999,0,1]],[[True,0,1]],["admit"],"sorry"):
            candidate=copy.deepcopy(fill);candidate["proof_steps"]=bad
            self.assertFalse(task.evaluate(candidate).success)
        fill["consistency_model"]=[int(x) for x in fill["consistency_model"]]
        self.assertFalse(task.evaluate(fill).success)

    def test_polarity_twins_preserve_nongoal_structure_and_change_bound_statement(self):
        a=ProofTask(2,"transfer",2,0);b=ProofTask(2,"transfer",2,1)
        self.assertEqual(a._base,b._base)
        self.assertEqual(a.goal,-b.goal)
        self.assertEqual(a.nvars,b.nvars)
        self.assertEqual(a.twin_kind,"theorem_polarity")
        self.assertNotEqual(a.statement["statement_sha256"],b.statement["statement_sha256"])
        fill=a.reference_answer()
        self.assertFalse(b.evaluate(fill).success)
        self.assertTrue(b.evaluate(b.reference_answer()).success)

    def test_prefix_limit_and_invalid_calls_do_not_mutate_statement(self):
        task=ProofTask(7,"dev",1)
        before=copy.deepcopy(task.statement)
        with self.assertRaises(ValueError): task.query("check_prefix",{"proof_steps":[[0,1,1]]*257})
        with self.assertRaises(ValueError): task.query("check_prefix",{"proof_steps":[],"axioms":[[]]})
        self.assertEqual(before,task.statement)

    def test_search_rejects_satisfiable_input_and_proof_is_exact(self):
        with self.assertRaises(ValueError): resolution_refutation([[1,2],[-1,2]],2)
        steps=resolution_refutation([[1,2],[-1],[-2]],2)
        checked=verify_resolution([[1,2],[-1],[-2]],steps,2)
        self.assertTrue(checked["valid"] and checked["derived_empty"])


if __name__=="__main__": unittest.main()
