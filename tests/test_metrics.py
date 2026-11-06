import unittest

from causalfill.metrics import summarize


def record(family="alpha", signature="alpha:one", success=True, answerable=True,
           abstained=False, policy="p", config="c", confidence=1.0, **extra):
    correct = (not answerable and abstained) or (answerable and success and not abstained)
    result = {
        "family": family, "structural_signature": signature,
        "answerable": answerable, "success": success, "abstained": abstained,
        "policy": policy, "config_id": config, "condition": {"skill": True, "tools": True},
        "confidence": confidence, "brier_decision": (confidence - float(correct)) ** 2,
        "decision_correct": bool(correct), "tool_cost": 4, "tool_calls": 2,
        "invalid_calls": 0, "recovery": float(success), "outcome": float(success), "safety": 1.0,
    }
    result.update(extra)
    return result


class MetricsTests(unittest.TestCase):
    def test_impossible_correct_abstention_never_increases_capability(self):
        base = [record(success=True), record(success=False)]
        first = summarize(base)["groups"][0]
        extra = [record(family="ambiguity", signature="ambiguity:hidden", answerable=False,
                        success=False, abstained=True) for _ in range(100)]
        second = summarize(base + extra)["groups"][0]
        self.assertEqual(first["headline"]["value"], 0.5)
        self.assertEqual(second["headline"]["value"], 0.5)
        self.assertEqual(second["aggregate"]["solvable_success_rate"], 0.5)
        self.assertEqual(second["aggregate"]["unanswerable_correct_abstention_rate"], 1.0)
        self.assertEqual(second["aggregate"]["answered_accuracy"], 0.5)

    def test_abstaining_on_answerable_task_is_failure_not_removal(self):
        result = summarize([record(), record(success=False, abstained=True)])["groups"][0]
        self.assertEqual(result["headline"]["value"], 0.5)
        self.assertEqual(result["aggregate"]["coverage"], 0.5)
        self.assertEqual(result["aggregate"]["answered_accuracy"], 1.0)
        self.assertEqual(result["aggregate"]["metric_means"]["brier_decision"]["mean"], 0.5)

    def test_incomplete_duplicate_and_ambiguity_pairs_are_separate(self):
        rows = [
            record(pair_id="a", twin=0), record(success=False, pair_id="a", twin=1),
            record(pair_id="b", twin=0), record(),
            record(pair_id="dup", twin=0), record(pair_id="dup", twin=0), record(pair_id="dup", twin=1),
            record(answerable=False, success=False, abstained=True, pair_id="unknown", twin=0),
            record(answerable=False, success=False, abstained=True, pair_id="unknown", twin=1),
            record(pair_id="mixed", twin=0),
            record(answerable=False, success=False, abstained=True, pair_id="mixed", twin=1),
        ]
        pairs = summarize(rows)["groups"][0]["paired"]
        self.assertEqual(pairs["complete_pairs"], 3)
        self.assertEqual(pairs["solvable_complete_pairs"], 1)
        self.assertEqual(pairs["joint_solvable_success_rate"], 0.0)
        self.assertEqual(pairs["incomplete_pairs_excluded"], 1)
        self.assertEqual(pairs["duplicate_pairs_excluded"], 1)
        self.assertEqual(pairs["unpaired_records_excluded"], 1)
        self.assertEqual(pairs["both_unanswerable_pairs"]["joint_decision_accuracy"], 1.0)
        self.assertEqual(pairs["mixed_answerability_pairs"]["joint_decision_accuracy"], 1.0)

    def test_replicating_seeds_does_not_increase_cluster_count(self):
        rows = [record(seed=seed, success=bool(seed % 2)) for seed in range(100)]
        result = summarize(rows)["groups"][0]
        self.assertEqual(result["uncertainty"]["cluster_count"], 1)
        self.assertIsNone(result["headline"]["ci95"])
        self.assertEqual(result["uncertainty"]["ci_unavailable_reason"], "fewer_than_two_structure_clusters")

    def test_policies_models_configs_and_conditions_do_not_pool(self):
        rows = [record(policy="p1"), record(policy="p2", success=False),
                record(policy="p1", config="different"),
                record(policy="p1", condition={"skill": False, "tools": True}),
                record(policy="p1", model="model-a"), record(policy="p1", model="model-b")]
        report = summarize(rows)
        self.assertEqual(report["group_count"], 6)
        self.assertTrue(all(group["aggregate"]["episodes"] == 1 for group in report["groups"]))
        self.assertNotIn("headline", report)

    def test_macro_weights_families_equally_and_withholds_singleton_ci(self):
        rows = [record() for _ in range(100)] + [record(family="beta", signature="beta:one", success=False)]
        result = summarize(rows)["groups"][0]
        self.assertEqual(result["headline"]["value"], 0.5)
        self.assertEqual(result["aggregate"]["solvable_success_rate"], 100 / 101)
        self.assertIsNone(result["headline"]["ci95"])
        self.assertEqual(result["uncertainty"]["cluster_count"], 2)
        self.assertEqual(result["uncertainty"]["singleton_families"], ["alpha", "beta"])

    def test_bootstrap_resamples_whole_structures_not_individual_episodes(self):
        rows = [record(signature="alpha:easy", success=True) for _ in range(50)]
        rows += [record(signature="alpha:hard", success=False) for _ in range(50)]
        first = summarize(rows, bootstrap_seed=31, n_bootstrap=400)
        second = summarize(rows, bootstrap_seed=31, n_bootstrap=400)
        self.assertEqual(first, second)
        result = first["groups"][0]
        self.assertEqual(result["uncertainty"]["cluster_count"], 2)
        self.assertEqual(result["headline"]["ci95"], [0.0, 1.0])

    def test_empty_and_missing_optional_metrics_are_explicit(self):
        self.assertEqual(summarize([])["groups"], [])
        minimal = {"family": "a", "structural_signature": "a:1", "answerable": True,
                   "success": False, "abstained": False}
        metric = summarize([minimal])["groups"][0]["aggregate"]["metric_means"]["tool_cost"]
        self.assertEqual(metric, {"mean": None, "n": 0})

    def test_rejects_nonfinite_inconsistent_or_unclustered_records(self):
        cases = [record(tool_cost=float("nan")), record(brier_decision=1.0),
                 record(tool_cost=10**1000), record(twin_kind=False),
                 record(structural_signature=""), record(answerable=False, success=True),
                 record(model="a", model_id="b")]
        for row in cases:
            with self.subTest(row=row):
                with self.assertRaises(ValueError):
                    summarize([row])

    def test_twin_sides_never_pair_across_configurations(self):
        rows = [record(pair_id="same", twin=0, policy="a"), record(pair_id="same", twin=1, policy="b")]
        report = summarize(rows)
        for group in report["groups"]:
            self.assertEqual(group["paired"]["complete_pairs"], 0)
            self.assertEqual(group["paired"]["incomplete_pairs_excluded"], 1)
            self.assertIsNone(group["paired"]["joint_solvable_success_rate"])

    def test_twin_types_are_separate_and_cannot_cross_pair(self):
        rows = [record(pair_id="same", twin=0, twin_kind="causal_parameter"),
                record(pair_id="same", twin=1, twin_kind="theorem_polarity"),
                record(pair_id="theorem", twin=0, twin_kind="theorem_polarity"),
                record(pair_id="theorem", twin=1, twin_kind="theorem_polarity")]
        result = summarize(rows)["groups"][0]
        self.assertEqual(result["paired"]["complete_pairs"], 1)
        self.assertEqual(result["paired"]["incomplete_pairs_excluded"], 2)
        self.assertEqual(result["paired_by_twin_kind"]["causal_parameter"]["complete_pairs"], 0)
        self.assertEqual(result["paired_by_twin_kind"]["theorem_polarity"]["complete_pairs"], 1)


if __name__ == "__main__":
    unittest.main()
