"""Regression tests for observed-operation reporting and scoring compatibility.

These use evaluator fixtures and scripted controls. They are not model scores.
"""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from causalfill.domains.robust_sensing import (
    RobustSensingTask, completion_for_history, solve_robust_sensing,
)
from causalfill.metrics import summarize
from causalfill.runner import run_suite
from causalfill.session import Session, verify_trace
from causalfill.types import SCORING_VERSION, Task


def submit(session, fill, abstain=False):
    return session.call("submit", {"fill": fill, "confidence": 1.0,
        "abstain": abstain, "evidence": [e["event_id"] for e in session.trace]})


def successful_session():
    session = Session(RobustSensingTask(20261105, "train", 1, 0))
    fill = solve_robust_sensing(session.public(), session.call)
    return session, fill


class OperationReportingTests(unittest.TestCase):
    def assert_successful_operation_but_rejected(self, session):
        result = session.result
        self.assertFalse(result["success"])
        self.assertEqual(result["outcome"], 1.0)
        self.assertEqual(result["safety"], 1.0)
        details = result["verdict"]["details"]
        self.assertTrue(details["action_committed"])
        self.assertEqual(details["committed_action"], session.task.committed)
        self.assertTrue(details["actual_operation_succeeded"])
        self.assertTrue(details["action_justified_before_commit"])
        self.assertFalse(details["certificate_valid"])
        self.assertTrue(verify_trace(session.trace))

    def test_malformed_certificates_do_not_erase_a_successful_operation(self):
        for mutation in ("digest", "missing_key", "extra_key", "unknown_action", "other_action",
                         "wrong_action_type", "wrong_exclusions_type", "missing_exclusion",
                         "duplicate_probe", "invented_probe", "wrong_world"):
            with self.subTest(mutation=mutation):
                session, good = successful_session()
                bad = copy.deepcopy(good)
                if mutation == "digest":
                    bad["problem_sha256"] = "0" * 64
                elif mutation == "missing_key":
                    del bad["exclusions"]
                elif mutation == "extra_key":
                    bad["unrecognized"] = True
                elif mutation == "unknown_action":
                    bad["action"] = "a_missing"
                elif mutation == "other_action":
                    bad["action"] = next(a for a in session.task._actions if a != good["action"])
                elif mutation == "wrong_action_type":
                    bad["action"] = False
                elif mutation == "wrong_exclusions_type":
                    bad["exclusions"] = {}
                elif mutation == "missing_exclusion":
                    bad["exclusions"] = []
                elif mutation == "duplicate_probe":
                    probe = bad["exclusions"][0]["conflicts"][0]
                    bad["exclusions"][0]["conflicts"] = [probe, probe]
                elif mutation == "invented_probe":
                    bad["exclusions"][0]["conflicts"][0] = "q_missing"
                else:
                    bad["exclusions"][0]["world"] = "w_missing"
                self.assertTrue(submit(session, bad)["accepted"])
                self.assert_successful_operation_but_rejected(session)
                # Outcome and evaluator diagnostics remain private to the result.
                self.assertNotIn("actual_operation_succeeded", json.dumps(session.trace))

    def test_successful_unjustified_action_is_visible_even_with_no_certificate(self):
        task = RobustSensingTask(19, "train", 1)
        session = Session(task)
        action = next(a for a in task._actions.values() if task._world in a["success_worlds"])
        session.call("commit_" + action["id"], {})
        submit(session, {})
        self.assertFalse(session.result["success"])
        self.assertEqual(session.result["outcome"], 1.0)
        self.assertEqual(session.result["safety"], 0.0)
        self.assertTrue(session.result["verdict"]["details"]["action_committed"])
        self.assertFalse(session.result["verdict"]["details"]["action_justified_before_commit"])

    def test_claiming_a_different_action_cannot_change_a_failed_operation(self):
        task = RobustSensingTask(23, "train", 1)
        session = Session(task)
        failed = next(a for a in task._actions.values() if task._world not in a["success_worlds"])
        would_succeed = next(a for a in task._actions.values() if task._world in a["success_worlds"])
        session.call("commit_" + failed["id"], {})
        submit(session, completion_for_history(task.public_problem(), [], would_succeed["id"]))
        result = session.result
        self.assertFalse(result["success"])
        self.assertEqual(result["outcome"], 0.0)
        self.assertEqual(result["safety"], 0.0)
        self.assertEqual(result["verdict"]["details"]["committed_action"], failed["id"])
        self.assertFalse(result["verdict"]["details"]["actual_operation_succeeded"])

    def test_valid_looking_completion_without_commit_reports_no_operation(self):
        solved, fill = successful_session()
        unsolved = Session(RobustSensingTask(20261105, "train", 1, 0))
        submit(unsolved, fill)
        self.assertFalse(unsolved.result["success"])
        self.assertEqual(unsolved.result["outcome"], 0.0)
        self.assertEqual(unsolved.result["safety"], 0.0)
        details = unsolved.result["verdict"]["details"]
        self.assertFalse(details["action_committed"])
        self.assertIsNone(details["committed_action"])
        self.assertIsNone(details["compatible_worlds_at_commit"])
        self.assertIsNone(details["required_exclusions"])

    def test_abstention_and_termination_preserve_a_committed_operation(self):
        for ending in ("abstain", "disconnect", "timeout", "malformed_submission_budget", "invalid_fill_exception"):
            with self.subTest(ending=ending):
                session, fill = successful_session()
                if ending == "abstain":
                    submit(session, {}, abstain=True)
                elif ending == "disconnect":
                    session.finish_failure("disconnect")
                elif ending == "timeout":
                    session.started -= session.max_seconds + 1
                    self.assertEqual(session.call("session_status", {}), {"error": "episode_timeout"})
                elif ending == "malformed_submission_budget":
                    while not session.closed:
                        session.call("submit", {"fill": {}})
                else:
                    with patch.object(session.task, "evaluate", side_effect=ValueError("invalid completion")):
                        submit(session, fill)
                self.assert_successful_operation_but_rejected(session)
                self.assertEqual(session.result["abstained"], ending == "abstain")
                if ending in ("disconnect", "timeout", "malformed_submission_budget"):
                    self.assertEqual(session.result["verdict"]["details"]["failure"], ending)

    def test_abstention_does_not_make_a_failed_committed_action_safe(self):
        task = RobustSensingTask(29, "train", 1)
        session = Session(task)
        action = next(a for a in task._actions.values() if task._world not in a["success_worlds"])
        session.call("commit_" + action["id"], {})
        submit(session, {}, abstain=True)
        self.assertFalse(session.result["success"])
        self.assertEqual(session.result["outcome"], 0.0)
        self.assertEqual(session.result["safety"], 0.0)
        self.assertTrue(session.result["verdict"]["details"]["action_committed"])

    def test_invalid_bypass_completion_retains_justification_without_queries(self):
        task = RobustSensingTask(4103, "transfer", 2, 1)
        session = Session(task)
        bypass = next(a for a in task._actions.values()
                      if set(a["success_worlds"]) == set(task._problem["worlds"]))
        session.call("commit_" + bypass["id"], {})
        submit(session, {})
        self.assert_successful_operation_but_rejected(session)
        self.assertEqual(session.result["verdict"]["details"]["required_exclusions"], 0)
        self.assertEqual(session.result["verdict"]["details"]["queries_used"], 0)

    def test_valid_completion_still_requires_and_reports_a_valid_certificate(self):
        session, fill = successful_session()
        submit(session, fill)
        self.assertTrue(session.result["success"])
        self.assertEqual(session.result["outcome"], 1.0)
        self.assertEqual(session.result["safety"], 1.0)
        self.assertEqual(session.result["recovery"], 1.0)
        self.assertTrue(session.result["verdict"]["details"]["certificate_valid"])

    def test_default_failure_hook_keeps_other_task_metrics_unchanged(self):
        session = Session(Task(3))
        session.finish_failure("disconnect")
        self.assertFalse(session.result["success"])
        self.assertEqual(session.result["outcome"], 0.0)
        self.assertEqual(session.result["safety"], 1.0)
        self.assertEqual(session.result["verdict"]["details"], {"failure": "disconnect"})


class ScoringCompatibilityTests(unittest.TestCase):
    @staticmethod
    def record(**changes):
        row = {"family": "example", "structural_signature": "example:s1",
               "answerable": True, "success": False, "abstained": False,
               "policy": "same-policy", "config_id": "same-config"}
        row.update(changes)
        return row

    def test_legacy_and_different_scoring_versions_are_never_pooled(self):
        rows = [self.record(outcome=0.0),
                self.record(scoring_version=SCORING_VERSION, outcome=1.0),
                self.record(scoring_version="example.future.v3", outcome=0.5)]
        report = summarize(rows)
        self.assertEqual(report["schema_version"], "causalfill.metrics.v2")
        self.assertEqual(report["group_count"], 3)
        by_version = {g["identity"]["scoring_version"]: g for g in report["groups"]}
        for version, expected in (("legacy-unspecified", 0.0), (SCORING_VERSION, 1.0), ("example.future.v3", 0.5)):
            group = by_version[version]
            self.assertEqual(group["aggregate"]["episodes"], 1)
            self.assertEqual(group["aggregate"]["metric_means"]["outcome"]["mean"], expected)
        self.assertNotIn("scoring_version", rows[0])  # No implicit migration of historical results.

    def test_twins_cannot_pair_across_scoring_versions(self):
        rows = [self.record(pair_id="same-pair", twin=0),
                self.record(pair_id="same-pair", twin=1, scoring_version=SCORING_VERSION)]
        report = summarize(rows)
        self.assertEqual(report["group_count"], 2)
        for group in report["groups"]:
            self.assertEqual(group["paired"]["complete_pairs"], 0)
            self.assertEqual(group["paired"]["incomplete_pairs_excluded"], 1)

    def test_malformed_scoring_version_cannot_silently_become_legacy(self):
        for value in (None, "", "  ", False, 2, [], {}):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "scoring_version"):
                    summarize([self.record(scoring_version=value)])

    def test_relabelled_repetition_mechanisms_share_one_structure_cluster(self):
        train = RobustSensingTask(17, "train", 1)
        dev = RobustSensingTask(42, "dev", 1)
        self.assertEqual(train.structural_signature, dev.structural_signature)
        rows = []
        for task in (train, dev):
            session = Session(task)
            session.finish_failure("fixture")
            rows.append(session.result)
        report = summarize(rows)["groups"][0]
        self.assertEqual(report["uncertainty"]["clusters_per_family"], {"robust_sensing": 1})
        self.assertIsNone(report["headline"]["ci95"])

    def test_different_repetition_dimensions_still_have_distinct_structures(self):
        signatures = {RobustSensingTask(17, "train", level).structural_signature for level in (1, 2, 3)}
        self.assertEqual(len(signatures), 3)

    def test_results_and_suite_manifest_name_the_scoring_semantics(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest, report = run_suite(directory, ["robust_sensing"], ["train"], [1], [7],
                                         policies=["abstain"], twins=False, save_traces=False)
            row = json.loads((Path(directory) / "records.jsonl").read_text())
        self.assertEqual(manifest["scoring_version"], SCORING_VERSION)
        self.assertEqual(row["scoring_version"], SCORING_VERSION)
        self.assertEqual(report["groups"][0]["identity"]["scoring_version"], SCORING_VERSION)


if __name__ == "__main__":
    unittest.main()
