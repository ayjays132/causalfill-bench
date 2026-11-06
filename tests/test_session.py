import copy
import unittest

from causalfill.session import Session,verify_trace
from causalfill.domains.words import WordsTask,AmbiguousWordsTask
from causalfill.domains.workflow import WorkflowTask
from causalfill.masking import Component,MaskPlanner


class SessionTests(unittest.TestCase):
    def test_final_response_never_leaks_grade_and_cannot_resubmit(self):
        t=WordsTask(1)
        s=Session(t)
        out=s.call("submit",{"fill":t.reference_answer(),"confidence":1,"abstain":False,"evidence":[]})
        self.assertTrue(s.result["success"])
        self.assertNotIn("success",out)
        self.assertNotIn("verdict",out)
        self.assertEqual(s.call("list_files",{}),{"error":"episode_closed"})

    def test_virtual_paths_never_access_host_or_private_task(self):
        s=Session(WordsTask(2))
        for path in ("/etc/passwd","../private.json","/oracle","/proc/self/environ"):
            self.assertIn("error",s.call("read_file",{"path":path}))
        self.assertEqual(s.invalid,4)
        self.assertEqual(s.cost,4)

    def test_invalid_calls_are_charged_and_trace_is_complete(self):
        s=Session(WordsTask(3))
        s.call(None,[])
        s.call("experiment",{"inputs":[float("nan")]})
        s.call("experiment",{"inputs":[0,0,0]})
        self.assertEqual(s.invalid,3)
        self.assertEqual(len(s.trace),3)
        self.assertEqual(s.cost,3)
        self.assertTrue(verify_trace(s.trace))

    def test_call_budget_terminates_without_free_error_search(self):
        t=WordsTask(0)
        t.max_calls=3
        s=Session(t)
        for _ in range(4):s.call("nonexistent",{})
        self.assertTrue(s.closed)
        self.assertEqual(s.trace[-1]["tool"],"__termination__")
        self.assertFalse(s.result["success"])

    def test_trace_detects_modified_response_but_is_not_signature(self):
        s=Session(WordsTask(0));s.call("list_files",{})
        original=copy.deepcopy(s.trace)
        self.assertTrue(verify_trace(original))
        original[0]["response"]["cost_used"]=99
        self.assertFalse(verify_trace(original))

    def test_unknown_evidence_is_invalid_and_charged(self):
        s=Session(WordsTask(1))
        out=s.call("submit",{"fill":{},"confidence":0.5,"abstain":False,"evidence":["e9000"]})
        self.assertIn("error",out)
        self.assertEqual(s.cost,1)

    def test_abstention_does_not_earn_capability_success(self):
        for t in (WordsTask(0),AmbiguousWordsTask(0)):
            s=Session(t)
            s.call("submit",{"fill":{},"confidence":1,"abstain":True,"evidence":[]})
            self.assertFalse(s.result["success"])
            self.assertEqual(s.result["decision_correct"],not t.answerable)

    def test_public_objects_are_defensive_copies(self):
        t=WordsTask(0);s=Session(t)
        p=s.public();p["slots"].clear();p["files"].append("/hidden")
        self.assertTrue(t.slots)
        self.assertNotIn("/hidden",s.public()["files"])

    def test_equivalent_workflow_expression_passes(self):
        t=WorkflowTask(4,"transfer",3)
        self.assertTrue(t.evaluate({"expression":"min(ceiling,max(reserve,balance-fee-scale*amount))"}).success)


class MaskPlannerTests(unittest.TestCase):
    def test_causal_selection_excludes_unobservable_and_matches_token_count(self):
        p=MaskPlanner([Component("a",token_count=2,evidence_cost=2),
            Component("b",("a",),token_count=2,evidence_cost=None,consequence_weight=5),
            Component("comment",token_count=2,evidence_cost=1,consequence_weight=0)])
        out=p.choose(1,2,"causal",token_target=2)
        self.assertEqual(out["masked"],["a"])
        self.assertEqual(p.choose(1,2,"random",7,2)["tokens_masked"],2)

    def test_impossible_masks_and_cycles_are_rejected(self):
        with self.assertRaises(ValueError): MaskPlanner([Component("a",("b",)),Component("b",("a",))])
        p=MaskPlanner([Component("x",evidence_cost=None)])
        with self.assertRaises(ValueError):p.choose(1,10)


if __name__=="__main__":unittest.main()
