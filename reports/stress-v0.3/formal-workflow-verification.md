# Workflow certification verification

35 tests passed: True. Failures: 0. Errors: 0. Runtime: 1.392 seconds.

```sh
python -m unittest tests.test_workflow_certificate tests.test_formal_stress_regressions tests.test_core_audit tests.test_session -v
```

## Concrete repaired exploit

In every split, adding `max(0,scale-19)` still passes all 131 behavioral cases but now has strict success false and outcome zero because symbolic equality is not certified. The new domain includes scale=20, where a direct numerical witness contradicts the specification.

## Coverage

- 905 min/max expressions over three variables, checked on all 27 small relative-value assignments; 18 functions represented.
- Seven complete original-AST bound traces, each checked independently on 486 endpoint input vectors.
- 200 fixed-seed rational polynomial identities over min/max atoms, with direct Fraction comparison.
- Pole cancellation, zero cancellation, oversized original intermediates, exact Fraction numerator/denominator boundaries, malformed grammar, and proof-expansion limits.
- Public-reference completion across split, difficulty, and twin combinations while the private reference-answer helper is disabled.
- Six formal-harness regressions and seventeen existing core/session tests.

## Exact test output

```text
test_all_split_dimension_twin_references_and_public_reference_policy (tests.test_workflow_certificate.WorkflowCertificateTests.test_all_split_dimension_twin_references_and_public_reference_policy) ... ok
test_every_reported_intermediate_bound_matches_independent_extreme_inputs (tests.test_workflow_certificate.WorkflowCertificateTests.test_every_reported_intermediate_bound_matches_independent_extreme_inputs) ... ok
test_exact_fraction_resource_boundary_and_conservative_incompleteness (tests.test_workflow_certificate.WorkflowCertificateTests.test_exact_fraction_resource_boundary_and_conservative_incompleteness) ... ok
test_exhaustive_small_lattice_forms_agree_with_direct_truth_semantics (tests.test_workflow_certificate.WorkflowCertificateTests.test_exhaustive_small_lattice_forms_agree_with_direct_truth_semantics) ... ok
test_lattice_identities_and_clamp_reordering_require_correct_assumptions (tests.test_workflow_certificate.WorkflowCertificateTests.test_lattice_identities_and_clamp_reordering_require_correct_assumptions) ... ok
test_legitimate_rational_polynomial_alternatives (tests.test_workflow_certificate.WorkflowCertificateTests.test_legitimate_rational_polynomial_alternatives) ... ok
test_malformed_and_expanding_expressions_return_not_certified (tests.test_workflow_certificate.WorkflowCertificateTests.test_malformed_and_expanding_expressions_return_not_certified) ... ok
test_original_intermediate_overflow_cannot_be_cancelled_away (tests.test_workflow_certificate.WorkflowCertificateTests.test_original_intermediate_overflow_cannot_be_cancelled_away) ... ok
test_pole_zero_and_variable_divisor_cancellation_fail_closed (tests.test_workflow_certificate.WorkflowCertificateTests.test_pole_zero_and_variable_divisor_cancellation_fail_closed) ... ok
test_public_integer_contract_and_conditional_order_assumption (tests.test_workflow_certificate.WorkflowCertificateTests.test_public_integer_contract_and_conditional_order_assumption) ... ok
test_randomized_polynomial_identities_over_lattice_atoms (tests.test_workflow_certificate.WorkflowCertificateTests.test_randomized_polynomial_identities_over_lattice_atoms) ... ok
test_threshold_attacks_pass_sample_suite_but_fail_strict_certificate (tests.test_workflow_certificate.WorkflowCertificateTests.test_threshold_attacks_pass_sample_suite_but_fail_strict_certificate) ... ok
test_complete_policy_oracle_detects_restricted_query_gap_without_optimizer (tests.test_formal_stress_regressions.FormalStressRegressions.test_complete_policy_oracle_detects_restricted_query_gap_without_optimizer) ... ok
test_complete_policy_oracle_does_not_fabricate_solution_beyond_depth_limit (tests.test_formal_stress_regressions.FormalStressRegressions.test_complete_policy_oracle_does_not_fabricate_solution_beyond_depth_limit) ... ok
test_independent_blocker_proofs_allow_redundancy_and_different_models (tests.test_formal_stress_regressions.FormalStressRegressions.test_independent_blocker_proofs_allow_redundancy_and_different_models) ... ok
test_resolution_semantic_audit_kills_accept_everything_mutant (tests.test_formal_stress_regressions.FormalStressRegressions.test_resolution_semantic_audit_kills_accept_everything_mutant) ... ok
test_resolution_semantic_audit_kills_reject_everything_mutant (tests.test_formal_stress_regressions.FormalStressRegressions.test_resolution_semantic_audit_kills_reject_everything_mutant) ... ok
test_satisfiable_multistep_oracle_and_nonvacuity_regressions (tests.test_formal_stress_regressions.FormalStressRegressions.test_satisfiable_multistep_oracle_and_nonvacuity_regressions) ... ok
test_ambiguous_twins_have_identical_entire_permitted_evidence (tests.test_core_audit.CoreIntegrityAudit.test_ambiguous_twins_have_identical_entire_permitted_evidence) ... ok
test_expression_interpreter_rejects_execution_and_unbounded_arithmetic (tests.test_core_audit.CoreIntegrityAudit.test_expression_interpreter_rejects_execution_and_unbounded_arithmetic) ... ok
test_gate_is_not_a_deterministic_function_of_split_and_arity (tests.test_core_audit.CoreIntegrityAudit.test_gate_is_not_a_deterministic_function_of_split_and_arity) ... ok
test_huge_integer_confidence_is_rejected_and_charged_without_crash (tests.test_core_audit.CoreIntegrityAudit.test_huge_integer_confidence_is_rejected_and_charged_without_crash) ... ok
test_masked_gate_is_not_revealed_in_public_structural_metadata (tests.test_core_audit.CoreIntegrityAudit.test_masked_gate_is_not_revealed_in_public_structural_metadata) ... ok
test_workflow_does_not_accept_hardcoded_hidden_case_constants (tests.test_core_audit.CoreIntegrityAudit.test_workflow_does_not_accept_hardcoded_hidden_case_constants) ... ok
test_causal_selection_excludes_unobservable_and_matches_token_count (tests.test_session.MaskPlannerTests.test_causal_selection_excludes_unobservable_and_matches_token_count) ... ok
test_impossible_masks_and_cycles_are_rejected (tests.test_session.MaskPlannerTests.test_impossible_masks_and_cycles_are_rejected) ... ok
test_abstention_does_not_earn_capability_success (tests.test_session.SessionTests.test_abstention_does_not_earn_capability_success) ... ok
test_call_budget_terminates_without_free_error_search (tests.test_session.SessionTests.test_call_budget_terminates_without_free_error_search) ... ok
test_equivalent_workflow_expression_passes (tests.test_session.SessionTests.test_equivalent_workflow_expression_passes) ... ok
test_final_response_never_leaks_grade_and_cannot_resubmit (tests.test_session.SessionTests.test_final_response_never_leaks_grade_and_cannot_resubmit) ... ok
test_invalid_calls_are_charged_and_trace_is_complete (tests.test_session.SessionTests.test_invalid_calls_are_charged_and_trace_is_complete) ... ok
test_public_objects_are_defensive_copies (tests.test_session.SessionTests.test_public_objects_are_defensive_copies) ... ok
test_trace_detects_modified_response_but_is_not_signature (tests.test_session.SessionTests.test_trace_detects_modified_response_but_is_not_signature) ... ok
test_unknown_evidence_is_invalid_and_charged (tests.test_session.SessionTests.test_unknown_evidence_is_invalid_and_charged) ... ok
test_virtual_paths_never_access_host_or_private_task (tests.test_session.SessionTests.test_virtual_paths_never_access_host_or_private_task) ... ok

----------------------------------------------------------------------
Ran 35 tests in 1.392s

OK
```

The detailed JSON records exact source hashes and all three post-fix exploit verdicts. These are evaluator-development checks; no model performance was measured. The certificate is a sufficient Python proof system on an explicit integer domain, not a complete symbolic solver or Lean formalization.
