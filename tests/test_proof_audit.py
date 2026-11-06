"""Independent statement semantics and actual transport checks for proof tasks.

These are evaluator-integrity tests, not model runs or a Lean formalization.
"""
import copy
import itertools
import json
from pathlib import Path
import random
import tempfile
import threading
import unittest
import urllib.request

from causalfill.domains.proof import ProofTask
from causalfill.logic_kernel import verify_resolution
from causalfill.proof_search import resolution_refutation, solve_statement
from causalfill.server import create_server, MAX_BODY_BYTES
from causalfill.session import Session
from causalfill.decision_certificates import (
    build_decision_certificate, extract_decision_tree, validate_table,
    verify_decision_certificate, verify_decision_tree,
)


def satisfies(clauses, assignment):
    # Independent direct truth semantics; do not call the proof/model checker.
    return all(any((assignment[abs(lit)-1] if lit > 0 else not assignment[abs(lit)-1])
                   for lit in clause) for clause in clauses)


class ProofIndependentAudit(unittest.TestCase):
    def test_small_generated_statements_are_nonvacuous_and_entail_signed_goal(self):
        for split in ("train", "dev", "transfer"):
            for twin in (0, 1):
                task = ProofTask(6, split, 1, twin)
                statement = json.loads(task.files["/formal/statement.json"])
                model_count = 0
                for assignment in itertools.product((False, True), repeat=statement["nvars"]):
                    if satisfies(statement["clauses"], assignment):
                        model_count += 1
                        conclusion = assignment[abs(statement["goal"])-1]
                        if statement["goal"] < 0:
                            conclusion = not conclusion
                        self.assertTrue(conclusion, (split, twin, assignment))
                self.assertGreater(model_count, 0, (split, twin))

    def test_proof_search_matches_independent_small_truth_tables(self):
        rng = random.Random(73496)
        clause_pool = []
        for signs in itertools.product((-1, 0, 1), repeat=3):
            clause_pool.append([sign*(i+1) for i,sign in enumerate(signs) if sign])
        assignments = list(itertools.product((False, True), repeat=3))
        for _ in range(160):
            clauses = [rng.choice(clause_pool) for _ in range(rng.randrange(0, 9))]
            sat = any(satisfies(clauses, a) for a in assignments)
            if sat:
                with self.assertRaises(ValueError):
                    resolution_refutation(clauses, 3)
            else:
                steps = resolution_refutation(clauses, 3)
                result = verify_resolution(clauses, steps, 3)
                self.assertTrue(result["valid"] and result["derived_empty"], clauses)

    def test_polarity_transport_accepts_an_equivalent_rebound_certificate(self):
        first = ProofTask(14, "transfer", 1, 0)
        second = ProofTask(14, "transfer", 1, 1)
        fill = first.reference_answer()
        self.assertFalse(second.evaluate(fill).success)
        # A simultaneous goal-sign change can preserve the resolution DAG.
        # Updating the fixed commitment and a valid model makes that reuse
        # mathematically legitimate; the task must not demand different text.
        rebound = copy.deepcopy(fill)
        rebound["statement_sha256"] = second.statement["statement_sha256"]
        rebound["consistency_model"][abs(second.goal)-1] = second.goal > 0
        self.assertTrue(second.evaluate(rebound).success)

    def test_correct_proof_cannot_bypass_model_or_import_new_assumptions(self):
        task = ProofTask(5, "dev", 2)
        good = task.reference_answer()
        candidates = []
        foreign_model = copy.deepcopy(good)
        foreign_model["consistency_model"][abs(task.goal)-1] = task.goal < 0
        candidates.append(foreign_model)
        weakened = copy.deepcopy(good)
        weakened["clauses"] = [[]]
        candidates.append(weakened)
        foreign_statement = copy.deepcopy(good)
        foreign_statement["statement_sha256"] = ProofTask(5, "dev", 2, 1).statement["statement_sha256"]
        candidates.append(foreign_statement)
        invented = copy.deepcopy(good)
        invented["proof_steps"] = [{"clause": []}]
        candidates.append(invented)
        for candidate in candidates:
            self.assertFalse(task.evaluate(candidate).success)

    def test_prefix_checks_do_not_modify_the_statement_or_candidate(self):
        task = ProofTask(11, "dev", 3)
        good = task.reference_answer()
        before = copy.deepcopy(task.statement)
        steps = good["proof_steps"][:2]
        argument = {"proof_steps": steps}
        argument_before = copy.deepcopy(argument)
        task.query("check_prefix", argument)
        self.assertEqual(task.statement, before)
        self.assertEqual(argument, argument_before)

    def test_strongest_reference_submits_over_actual_http_within_wire_limits(self):
        task = ProofTask(0, "transfer", 3)
        session = Session(task)
        token = "local-proof-audit-credential-0123456789"
        with tempfile.TemporaryDirectory(prefix="causalfill-proof-audit-") as directory:
            server = create_server(session, "127.0.0.1", 0, token=token, output_dir=Path(directory))
            thread = threading.Thread(target=server.serve_forever,
                                      kwargs={"poll_interval": 0.005}, daemon=True)
            thread.start()
            url = "http://127.0.0.1:" + str(server.server_address[1]) + "/v1/tool"

            def call(payload):
                # Match the supplied HTTP client's default serialization, not
                # only the more compact serialization used by the search helper.
                wire = json.dumps(payload, allow_nan=False).encode("utf-8")
                self.assertLessEqual(len(wire), MAX_BODY_BYTES)
                request = urllib.request.Request(url, data=wire, headers={
                    "Authorization": "Bearer " + token,
                    "Content-Type": "application/json",
                })
                with urllib.request.urlopen(request, timeout=30) as response:
                    self.assertEqual(response.status, 200)
                    return json.loads(response.read())

            try:
                observation = call({"tool": "read_file", "arguments": {"path": "/formal/statement.json"}})
                fill = solve_statement(json.loads(observation["content"]))
                # This certificate specifically exceeds the former 8192-node
                # parser bound while fitting the actual 128 KiB byte limit.
                self.assertGreater(len(fill["proof_steps"])*4, 8192)
                final = call({"tool": "submit", "arguments": {
                    "fill": fill, "confidence": 1.0, "abstain": False,
                    "evidence": [observation["event_id"]],
                }})
                self.assertTrue(final["accepted"])
                self.assertNotIn("verdict", final)
                self.assertNotIn("success", final)
                self.assertTrue(session.result["success"])
                self.assertEqual(session.invalid, 0)
                saved = list(Path(directory).glob("*.result.json"))
                self.assertEqual(len(saved), 1)
                self.assertTrue(json.loads(saved[0].read_text())["success"])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)


def minimum_depth_by_explicit_policies(table):
    """Exhaust full binary-query policies, without Bellman/bit-mask recurrence.

    For a fixed depth, assign a query to every internal node of a full binary
    tree. Simulate each world through it. Distinct final leaf positions permit
    correct labels; a shorter successful branch may be padded harmlessly.
    This is deliberately tiny and slow, suitable only for the small audit.
    """
    width = len(table[0])
    for depth in range(width+1):
        if len(table) > 2**depth:
            continue
        for queries in itertools.product(range(width), repeat=2**depth-1):
            leaves = []
            for responses in table:
                node = 0
                for _ in range(depth):
                    node = 2*node + 1 + responses[queries[node]]
                leaves.append(node)
            if len(set(leaves)) == len(table):
                return depth
    raise AssertionError("distinct rows must be identifiable by querying all columns")


class DecisionCertificateIndependentAudit(unittest.TestCase):
    def test_exact_depth_matches_exhaustive_explicit_policies_for_small_tables(self):
        all_rows = list(itertools.product((0, 1), repeat=3))
        table_count = 0
        for n in (2, 3, 4):
            for rows in itertools.combinations(all_rows, n):
                table = [list(row) for row in rows]
                expected = minimum_depth_by_explicit_policies(table)
                checked = verify_decision_certificate(table, build_decision_certificate(table))
                self.assertTrue(checked["valid"], table)
                self.assertEqual(checked["optimal_depth"], expected, table)
                table_count += 1
        self.assertEqual(table_count, 154)

    def test_every_required_certificate_state_is_really_required(self):
        table = [[0,0,0], [1,0,0], [0,1,0], [0,0,1]]
        certificate = build_decision_certificate(table)
        for index in range(len(certificate["nodes"])):
            missing = copy.deepcopy(certificate)
            missing["nodes"].pop(index)
            self.assertFalse(verify_decision_certificate(table, missing)["valid"], index)

    def test_wrong_bounds_and_spurious_states_cannot_certify_optimality(self):
        table = [[0,0,0], [1,0,0], [0,1,0], [0,0,1]]
        certificate = build_decision_certificate(table)
        for claimed in (0, 1, 2, 4, True, float("nan")):
            altered = copy.deepcopy(certificate)
            for node in altered["nodes"]:
                if node[0] == altered["root_mask"]:
                    node[1] = claimed
            self.assertFalse(verify_decision_certificate(table, altered)["valid"], claimed)
        altered = copy.deepcopy(certificate)
        # Change a required singleton into an unrelated state; the checker must
        # recompute the actual table partition rather than trust node labels.
        altered["nodes"][0][0] = 0
        self.assertFalse(verify_decision_certificate(table, altered)["valid"])

    def test_malformed_response_tables_and_nonfinite_claims_fail_closed(self):
        invalid_tables = (
            [[0], [float("nan")]], [[0], [float("inf")]], [[0], [True]],
            [[0], ["1"]], [[0], [1+0j]], [[0], [0]], [[0], [1,0]],
        )
        valid_table = [[0],[1]]
        certificate = build_decision_certificate(valid_table)
        tree = extract_decision_tree(valid_table, certificate)
        for table in invalid_tables:
            with self.assertRaises(ValueError):
                validate_table(table)
            self.assertFalse(verify_decision_certificate(table, certificate)["valid"])
            self.assertFalse(verify_decision_tree(table, tree)["valid"])
        for position in (0,1,2):
            altered = copy.deepcopy(certificate)
            altered["nodes"][-1][position] = float("nan")
            self.assertFalse(verify_decision_certificate(valid_table, altered)["valid"])

    def test_leaf_identity_and_cyclic_or_aliased_trees_cannot_spoof_strategy(self):
        table = [[0,0], [0,1], [1,0], [1,1]]
        certificate = build_decision_certificate(table)
        tree = extract_decision_tree(table, certificate)
        aliased = copy.deepcopy(tree)
        aliased["one"] = aliased["zero"]
        self.assertFalse(verify_decision_tree(table, aliased)["valid"])
        cycle = {"query": 0, "one": {"world": 0}}
        cycle["zero"] = cycle
        self.assertFalse(verify_decision_tree(table, cycle)["valid"])
        guessed = {"world": 0}
        self.assertFalse(verify_decision_tree(table, guessed)["valid"])


if __name__ == "__main__":
    unittest.main()
