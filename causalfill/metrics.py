"""Transparent grouped metrics and structural-cluster uncertainty estimates.

The headline is answerable-only macro family success. Correct abstention on
unanswerable tasks is reported separately and never increases that headline.
There is deliberately no omnibus capability/safety/cost score.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import statistics
from collections import defaultdict
from typing import Any


_MEAN_FIELDS = (
    "tool_cost", "tool_calls", "wall_seconds", "recovery", "outcome", "safety",
    "invalid_calls", "brier_decision",
)
_UNIT_FIELDS = {"recovery", "outcome", "safety", "brier_decision", "confidence"}


def _ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _correct_decision(record: dict) -> bool:
    return bool((not record["answerable"] and record["abstained"])
                or (record["answerable"] and not record["abstained"] and record["success"]))


def _validate(record: Any, index: int) -> None:
    if not isinstance(record, dict):
        raise ValueError(f"record {index} must be an object")
    for name in ("family", "structural_signature"):
        if type(record.get(name)) is not str or not record[name]:
            raise ValueError(f"record {index} needs a nonempty {name}")
    for name in ("answerable", "success", "abstained"):
        if type(record.get(name)) is not bool:
            raise ValueError(f"record {index} needs boolean {name}")
    if record["success"] and (record["abstained"] or not record["answerable"]):
        raise ValueError(f"record {index} reports inconsistent strict success")
    if "decision_correct" in record and (
        type(record["decision_correct"]) is not bool
        or record["decision_correct"] != _correct_decision(record)
    ):
        raise ValueError(f"record {index} reports inconsistent decision correctness")
    for name in _MEAN_FIELDS + ("confidence",):
        if name not in record or record[name] is None:
            continue
        value = record[name]
        try:
            finite = type(value) in (int, float) and math.isfinite(value)
        except OverflowError:
            finite = False
        if (not finite or value < 0
                or (name in _UNIT_FIELDS and value > 1)):
            raise ValueError(f"record {index} has invalid {name}")
    if record.get("confidence") is not None and record.get("brier_decision") is not None:
        expected = (record["confidence"] - float(_correct_decision(record))) ** 2
        if not math.isclose(record["brier_decision"], expected, rel_tol=1e-8, abs_tol=1e-8):
            raise ValueError(f"record {index} has inconsistent decision Brier score")
    for name in ("policy", "config_id", "model", "model_id", "harness", "harness_id"):
        if name in record and record[name] is not None and type(record[name]) is not str:
            raise ValueError(f"record {index} has non-string {name}")
    for primary, alias in (("model", "model_id"), ("harness", "harness_id")):
        if record.get(primary) is not None and record.get(alias) is not None and record[primary] != record[alias]:
            raise ValueError(f"record {index} has conflicting {primary} identifiers")
    if "twin_kind" in record and (type(record["twin_kind"]) is not str or not record["twin_kind"]):
        raise ValueError(f"record {index} needs a nonempty twin_kind when supplied")
    if "scoring_version" in record and (type(record["scoring_version"]) is not str
                                         or not record["scoring_version"].strip()):
        raise ValueError(f"record {index} needs a nonempty scoring_version when supplied")
    condition = record.get("condition", {})
    if not isinstance(condition, dict):
        raise ValueError(f"record {index} condition must be an object")
    try:
        _canonical(condition)
    except (TypeError, ValueError):
        raise ValueError(f"record {index} condition must be finite JSON") from None


def _identity(record: dict) -> dict:
    return {
        "scoring_version": record.get("scoring_version", "legacy-unspecified"),
        "policy": record.get("policy") or "unspecified",
        "config_id": record.get("config_id") or "unspecified",
        "model": record.get("model") or record.get("model_id"),
        "harness": record.get("harness") or record.get("harness_id"),
        "condition": record.get("condition", {}),
    }


def _aggregate(records: list[dict]) -> dict:
    answerable = [record for record in records if record["answerable"]]
    unanswerable = [record for record in records if not record["answerable"]]
    answered = [record for record in records if not record["abstained"]]
    solvable_answered = [record for record in answerable if not record["abstained"]]
    passed = sum(record["success"] for record in answerable)
    abstained_correctly = sum(record["abstained"] for record in unanswerable)
    invalid_observed = [record for record in records if record.get("invalid_calls") is not None]
    means = {}
    for name in _MEAN_FIELDS:
        values = [float(record[name]) for record in records if record.get(name) is not None]
        # Exact intermediate summation in statistics.mean avoids both overflow
        # of a finite mean and underflow from dividing tiny inputs separately.
        means[name] = {"mean": statistics.mean(values) if values else None, "n": len(values)}
    return {
        "episodes": len(records),
        "answerable_episodes": len(answerable),
        "unanswerable_episodes": len(unanswerable),
        "solvable_successes": passed,
        "solvable_success_rate": _ratio(passed, len(answerable)),
        "unanswerable_correct_abstentions": abstained_correctly,
        "unanswerable_correct_abstention_rate": _ratio(abstained_correctly, len(unanswerable)),
        "answered_episodes": len(answered),
        "coverage": _ratio(len(answered), len(records)),
        "answered_accuracy": _ratio(passed, len(answered)),
        "solvable_coverage": _ratio(len(solvable_answered), len(answerable)),
        "solvable_answered_accuracy": _ratio(passed, len(solvable_answered)),
        "decision_accuracy": _ratio(sum(_correct_decision(record) for record in records), len(records)),
        "invalid_call_episode_rate": _ratio(sum(record["invalid_calls"] > 0 for record in invalid_observed), len(invalid_observed)),
        "metric_means": means,
    }


def _percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    at = (len(ordered) - 1) * probability
    below = math.floor(at)
    above = math.ceil(at)
    return ordered[below] + (ordered[above] - ordered[below]) * (at - below)


def _interval(values: list[float]) -> list[float]:
    return [_percentile(values, 0.025), _percentile(values, 0.975)]


def _bootstrap(families: dict[str, list[dict]], seed: int, group_key: str, n: int) -> dict:
    clusters_by_family: dict[str, dict[str, list[dict]]] = {}
    for family, records in families.items():
        clusters: dict[str, list[dict]] = defaultdict(list)
        for record in records:
            if record["answerable"]:
                clusters[record["structural_signature"]].append(record)
        if clusters:
            clusters_by_family[family] = dict(clusters)
    counts = {family: len(clusters) for family, clusters in clusters_by_family.items()}
    per_family = {}
    family_draws: dict[str, list[float]] = {}
    for family, clusters in sorted(clusters_by_family.items()):
        if len(clusters) < 2:
            per_family[family] = {"clusters": len(clusters), "ci95": None,
                                  "reason": "fewer_than_two_structure_clusters"}
            continue
        # Selecting a cluster repeats EVERY episode in it. Counts are an exact
        # sufficient-statistic implementation; individual seeds are never sampled.
        stats = [(sum(record["success"] for record in clusters[name]), len(clusters[name]))
                 for name in sorted(clusters)]
        material = f"{seed}\n{group_key}\n{family}"
        rng = random.Random(hashlib.sha256(material.encode()).digest())
        draws = []
        for _ in range(n):
            sampled = [stats[rng.randrange(len(stats))] for _ in stats]
            draws.append(sum(success for success, _ in sampled) / sum(count for _, count in sampled))
        family_draws[family] = draws
        per_family[family] = {"clusters": len(clusters), "ci95": _interval(draws), "reason": None}
    total_clusters = sum(counts.values())
    singleton = sorted(family for family, count in counts.items() if count < 2)
    if not counts:
        interval, reason = None, "no_answerable_episodes"
    elif total_clusters < 2:
        interval, reason = None, "fewer_than_two_structure_clusters"
    elif singleton:
        # Equal family weights require uncertainty for EACH participating family.
        # Keeping singleton families fixed would hide their unmeasured uncertainty.
        interval, reason = None, "at_least_one_family_has_fewer_than_two_structure_clusters"
    else:
        macro_draws = [math.fsum(draws[index] for draws in family_draws.values()) / len(family_draws)
                       for index in range(n)]
        interval, reason = _interval(macro_draws), None
    return {
        "method": "percentile bootstrap of structural_signature clusters within family",
        "level": 0.95,
        "resamples": n,
        "cluster_count": total_clusters,
        "clusters_per_family": counts,
        "singleton_families": singleton,
        "macro_family_success_ci95": interval,
        "ci_unavailable_reason": reason,
        "per_family": per_family,
        "interpretation": "Descriptive resampling uncertainty over the sampled structures; not a reliability guarantee or evidence about unseen task families.",
    }


def _pairs(records: list[dict]) -> dict:
    buckets: dict[str, dict[int, list[dict]]] = defaultdict(lambda: {0: [], 1: []})
    unpaired = 0
    malformed = 0
    for record in records:
        pair_id, twin = record.get("pair_id"), record.get("twin")
        if pair_id is None and twin is None:
            unpaired += 1
            continue
        if (type(pair_id) not in (str, int) or pair_id == ""
                or type(twin) is not int or twin not in (0, 1)):
            malformed += 1
            continue
        key = _canonical([record["family"], record.get("split"), record.get("difficulty"),
                          record["structural_signature"], record.get("twin_kind", "unspecified"), pair_id])
        buckets[key][twin].append(record)
    complete = []
    incomplete = duplicate = 0
    for sides in buckets.values():
        if len(sides[0]) > 1 or len(sides[1]) > 1:
            duplicate += 1
        elif len(sides[0]) == len(sides[1]) == 1:
            complete.append((sides[0][0], sides[1][0]))
        else:
            incomplete += 1
    solvable = [(left, right) for left, right in complete if left["answerable"] and right["answerable"]]
    mixed = [(left, right) for left, right in complete if left["answerable"] != right["answerable"]]
    impossible = [(left, right) for left, right in complete if not left["answerable"] and not right["answerable"]]

    def ambiguity_summary(pairs: list[tuple[dict, dict]]) -> dict:
        correct = sum(_correct_decision(left) and _correct_decision(right) for left, right in pairs)
        return {"complete_pairs": len(pairs), "joint_correct_decisions": correct,
                "joint_decision_accuracy": _ratio(correct, len(pairs))}

    joint = sum(left["success"] and right["success"] for left, right in solvable)
    return {
        "complete_pairs": len(complete),
        "solvable_complete_pairs": len(solvable),
        "joint_solvable_successes": joint,
        "joint_solvable_success_rate": _ratio(joint, len(solvable)),
        "incomplete_pairs_excluded": incomplete,
        "duplicate_pairs_excluded": duplicate,
        "unpaired_records_excluded": unpaired,
        "malformed_pair_metadata_records_excluded": malformed,
        "mixed_answerability_pairs": ambiguity_summary(mixed),
        "both_unanswerable_pairs": ambiguity_summary(impossible),
        "pairing_fields": ["group_identity", "family", "split", "difficulty", "structural_signature", "twin_kind", "pair_id"],
        "interpretation": "Joint success on complete solvable twins measures robustness under the specified variation. Consult paired_by_twin_kind; theorem polarity and diagnostic state are not physical causal interventions.",
    }


def summarize(records: list[dict], bootstrap_seed: int = 0, n_bootstrap: int = 1000) -> dict:
    """Summarize trusted evaluator results without pooling configurations.

    ``scoring_version``, ``policy``, ``config_id``, optional model/harness IDs, and
    the complete ``condition`` object define groups. Legacy records without a
    scoring version remain separate from explicitly versioned results. Missing
    identifiers are marked unspecified; callers must label configurations before
    mixing result files.
    """
    if not isinstance(records, list):
        raise ValueError("records must be a list")
    if type(bootstrap_seed) is not int:
        raise ValueError("bootstrap_seed must be an integer")
    if type(n_bootstrap) is not int or not 1 <= n_bootstrap <= 100000:
        raise ValueError("n_bootstrap must be an integer from 1 to 100000")
    grouped: dict[str, list[dict]] = defaultdict(list)
    for index, record in enumerate(records):
        _validate(record, index)
        grouped[_canonical(_identity(record))].append(record)
    groups = []
    for key, rows in sorted(grouped.items()):
        families: dict[str, list[dict]] = defaultdict(list)
        twin_kinds: dict[str, list[dict]] = defaultdict(list)
        for record in rows:
            families[record["family"]].append(record)
            twin_kinds[record.get("twin_kind", "unspecified")].append(record)
        per_family = {family: _aggregate(values) for family, values in sorted(families.items())}
        family_rates = [summary["solvable_success_rate"] for summary in per_family.values()
                        if summary["solvable_success_rate"] is not None]
        macro = math.fsum(family_rates) / len(family_rates) if family_rates else None
        uncertainty = _bootstrap(dict(families), bootstrap_seed, key, n_bootstrap)
        notes = []
        identity = json.loads(key)
        if identity["scoring_version"] == "legacy-unspecified":
            notes.append("No scoring version was recorded; these rows stay separate from versioned results. Revised diagnostics require a new evaluator run.")
        if identity["policy"] == "unspecified" or identity["config_id"] == "unspecified":
            notes.append("Some configuration identifiers are unspecified; unseen differences cannot be separated automatically.")
        if uncertainty["singleton_families"]:
            notes.append("Seeds within one structural template do not provide independent template replication; a macro interval is withheld.")
        if 0 < uncertainty["cluster_count"] < 10:
            notes.append("Very few structural clusters: any available bootstrap interval is exploratory and may be unstable.")
        if n_bootstrap < 200:
            notes.append("Fewer than 200 bootstrap resamples give coarse percentile estimates.")
        if family_rates and all(rate in (0.0, 1.0) for rate in family_rates):
            notes.append("Boundary outcomes can produce degenerate bootstrap intervals; these do not imply zero uncertainty on unseen tasks.")
        groups.append({
            "group_id": hashlib.sha256(key.encode()).hexdigest()[:16],
            "identity": identity,
            "headline": {"name": "macro_family_solvable_success", "value": macro,
                         "answerable_families": len(family_rates),
                         "ci95": uncertainty["macro_family_success_ci95"]},
            "aggregate": _aggregate(rows),
            "per_family": per_family,
            "paired": _pairs(rows),
            "paired_by_twin_kind": {kind: _pairs(values) for kind, values in sorted(twin_kinds.items())},
            "uncertainty": uncertainty,
            "notes": notes,
        })
    return {
        "schema_version": "causalfill.metrics.v2",
        "record_count": len(records),
        "group_count": len(groups),
        "groups": groups,
        "methodology": {
            "headline": "Equal-weight mean of family success rates on answerable episodes only; abstentions on answerable tasks are failures.",
            "configuration_separation": "scoring_version + policy + config_id + model + harness + complete condition object",
            "legacy_scoring": "Records without scoring_version are labelled legacy-unspecified and never pooled with explicitly versioned scoring results.",
            "bootstrap_seed": bootstrap_seed,
            "n_bootstrap": n_bootstrap,
            "no_pooled_configuration_score": True,
            "no_composite_score": True,
            "missing_metrics": "Each metric mean includes only records with that numeric field; its n is reported. Missing rates use null.",
        },
    }
