# Operational stress audit

Evaluator-development checks; no model-performance or certified-difficulty claim.

Master seed: `371905`. Total wall time: 0.320 seconds.

| Section | Checks | False accepts | False rejects | Oracle mismatches | Unexpected exceptions | Seconds |
|---|---:|---:|---:|---:|---:|---:|
| robotics_barrier | 468 | 0 | 0 | 0 | 0 | 0.319 |

## robotics_barrier

Separate versioned profile; original robotics routes remain valid. Both twins share public files and cameras. Exact paired certificates establish no common continuous route, while geometry-dependent probes or lidar can distinguish the worlds.

The stress oracle independently reconstructs camera targets and checks route segments by exact face intersection. Forged certificates include recomputed hashes with an uncovered section, shortened walls, or changed shared observations.

Counters:

```json
{
  "certificate_forgeries_rejected": 144,
  "certificate_forgery_attempts": 144,
  "check:barrier_alternative_valid_certificate": 18,
  "check:barrier_certificate_forgery": 144,
  "check:barrier_fixed_roof_adjudication": 36,
  "check:barrier_fixed_roof_never_solves_pair": 18,
  "check:barrier_independent_constructive_route": 36,
  "check:barrier_pair_certificate": 18,
  "check:barrier_probe_is_distinguishing_geometry_evidence": 18,
  "check:barrier_reference_route": 36,
  "check:barrier_shared_camera_observations": 54,
  "check:barrier_shared_public_contract": 18,
  "check:barrier_swapped_route_independently_collides": 36,
  "check:barrier_swapped_route_rejected": 36,
  "checks": 468,
  "constructive_route_successes": 36,
  "episodes": 36,
  "expected_accepts": 73,
  "expected_rejects": 215,
  "fixed_roof_successes_twin_0": 0,
  "fixed_roof_successes_twin_1": 1,
  "pairs": 18,
  "passed_checks": 468,
  "valid_pair_certificates": 18,
  "verdict_checks": 288
}
```

## Scope and interpretation

The source hashes, command arguments, actual seed lists, and bounded failure examples are in the adjacent JSON. Source files were not treated as a solver interface. Geometry checks cover sampled and targeted cases, not a formal proof of all possible JSON numeric inputs. Grid checks are finite and affine certificates are complete only inside the declared affine hypothesis class. Legal constant controls are reported as task-distribution shortcuts, not as false successes. Workflow threshold mutants supply explicit new-input counterexamples; older baseline reports capture finite-suite-only acceptance, while current strict success additionally requires a symbolic certificate over the declared integer domain.
