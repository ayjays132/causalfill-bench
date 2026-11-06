# Robotics barrier profile: a checkable need for route sensing

> Scope: this document describes the original symbolic track. Version 0.5 adds a separate [rendered active-perception track](robotics-vision.md) and [controlled image task](visual-perception.md).


## Purpose and version

`robotics_barrier` is a separate symbolic task profile, with public profile version `robotics_barrier_v1`. It addresses a measured limitation of the original `robotics` family: every original scene permits a fixed route through height 10 after target reconstruction, so obstacle sensing is unnecessary for a valid plan. The original family still accepts that legal route. This new profile changes the generated geometry rather than retroactively disallowing valid original solutions.

The new profile has two individually solvable worlds with identical public files and camera observations but incompatible sets of safe routes. A small independent certificate verifier checks that a geometry-dependent observation is necessary to guarantee solving both worlds. This is an information-necessity result inside a declared geometric model. It is not a claim of frontier-model hardness.

Observations are numeric coordinates. There are no raster images, arm kinematics, contact dynamics, real grasp-force measurements, physical robot actions, or demonstrated transfer to hardware.

## Public task contract

The submission schema is unchanged from symbolic robotics:

```json
{
  "target_world_position": [10.25, 7.75, 1.5],
  "safe_waypoints": [[1, 9.75, 1], [10.25, 9.75, 1.5]],
  "grasp_precondition": {"gripper": "open", "force_limit_n": 0.5}
}
```

The coordinates above illustrate a possible plan; they are not defaults that solve every episode. The route connects the start, up to 16 waypoints, and the submitted target with straight segments. Every segment must avoid every closed obstacle expanded by the gripper clearance. Contact is collision, positive gaps are clear, and the gripper must remain within the workspace. The geometric predicates use exact decimal-rational arithmetic.

The target must be reconstructed from complementary calibrated cameras. A target ID, fiducials, projection axes and declared material handling limits are public evidence. The minimum lifting force remains 0.5 N and the common valid setting of 0.5 N is deliberately retained; this profile makes route sensing consequential without inventing physical force requirements.

The public files are:

- `/scene/workspace.json`: target ID, start, bounds, clearance, view names, force limits, target tolerance, and `profile_version`.
- `/docs/robotics-manual.txt`: the common camera, path and handling semantics.
- `/docs/barrier-profile.txt`: the full-height wall and unknown passage contract.

No public file contains the target coordinates, wall position, twin index, seed, or paired-world certificate.

| Tool | Cost | Observation |
|---|---:|---|
| `camera` | 3 | Numeric orthographic object projections and calibration fiducials |
| `lidar` | 3 | Occupied axis-aligned boxes in world coordinates |
| `probe_path` | 4 | Collision and workspace validity of a proposed path; no target-correctness feedback |

The episode budget is 40 cost units and 60 calls. Common file reads also cost budget. A reference controller can read the workspace, request three cameras and one lidar reading, and solve with cost 13. Documentation reads or an optional path probe add their normal costs. Any behaviorally valid completion is accepted; the evaluator requires neither a particular route template nor a specific sensor.

## Paired generation

All random draws are shared across the two twins. Target, material, start, cameras, clutter, workspace and wall dimensions stay fixed. Only the wall's y translation changes.

The workspace is `[0,12]^3`, the start is `[1,1,1]`, and the gripper clearance is 0.15. As in the original camera task, the target is to the right at x in `[9,11]`, y in `[7.5,10]`, z in `[1.5,3]`.

The wall has:

- Left x face in `[4.5,5.5]`, in quarter-unit increments.
- X width in `[0.75,1.25]`, in quarter-unit increments.
- Y extent `h` in `[7,9]`, in quarter-unit increments.
- Full z extent `[0,12]`.

Twin 0 occupies y `[0,h]` and leaves an upper passage. Twin 1 occupies y `[12-h,12]` and leaves a lower passage. Their two y intervals overlap because `h >= 7 > 6`. Both passages have ample positive width after clearance, and both walls share the same interior x slab. Camera outputs intentionally describe objects and calibration, not wall geometry, so changing the wall does not change camera projections.

Train, dev and transfer retain positive-diagonal, signed-diagonal and affine-shear camera transforms respectively. Difficulty controls clutter and the possible missing target view as in the original family. These are finite procedural variations, not evidence of broad unknown-distribution generalization.

## Why a common route cannot solve both worlds

Choose a plane `x=c` in the shared wall slab. The start lies strictly left of the plane. Every acceptable endpoint in the target-tolerance region lies strictly right of it. Therefore every continuous path from start to an acceptable endpoint intersects this plane.

At that plane, the union of the two clearance-expanded obstacles covers the entire clearance-safe y-z workspace section. Any crossing point therefore belongs to the forbidden region of at least one world. A path safe in both worlds would have to avoid that union, which is impossible.

Each world is nevertheless solvable. In the low-wall world, travel to an upper y passage while still left of the wall, cross in that passage, then approach the target on the right. Use the corresponding lower passage for the high-wall world. The checker independently verifies explicit routes for both worlds.

Consequently, a deterministic policy that receives only the shared public files and camera observations must return the same plan in both worlds and cannot guarantee success on the pair. A randomized policy with the same observation distribution has at most one successful world per sampled plan, so its average success across equally weighted twins is at most one half unless it obtains distinguishing evidence. This is a bound on a precisely defined observation restriction, not on all policies or all models.

The needed observation is **geometry-dependent**, not necessarily lidar. A path probe through one passage also distinguishes the worlds. A policy may use either permitted tool. The certificate makes no claim that cameras alone reveal the wall or that a fixed policy must fail every individual world.

## Independent certificate

Evaluator code can export a paired artifact:

```python
from causalfill.domains.robotics_barrier import (
    RoboticsBarrierTask,
    verify_barrier_certificate,
)

artifact = RoboticsBarrierTask(17, "transfer", 3, 0).separation_certificate()
result = verify_barrier_certificate(artifact["statement"], artifact["certificate"])
assert result["valid"]
```

`separation_certificate()` is evaluator-only and is not an episode tool. Exporting it during a scored solver run would violate the observation boundary.

The statement contains both worlds' public descriptions, virtual files, three camera readings and lidar readings. The certificate contains its version, the SHA-256 digest of the statement, a separating plane, and two constructive route submissions. The hash binds the proof to the supplied statement; it is not a signature establishing provenance or authenticity.

The verifier treats both arguments as bounded untrusted JSON and checks:

1. Supported profile/certificate versions, bounded shapes, finite numbers, strict field sets, and the statement digest.
2. Identical public descriptions, files and camera observations before geometry sensing.
3. Independent exact camera calibration and consistent target/material reconstruction.
4. A single nonzero y translation between the two wall geometries.
5. Strict separation of the start and the entire target-tolerance region.
6. Complete coverage of the transverse workspace section by the union of expanded obstacles.
7. A valid constructive path and symbolic handling setting in each world.

Section coverage uses an exact rectangle-union sweep. It checks one-dimensional interval coverage both at every rectangle edge and in every intervening strip. A tiny uncovered positive gap is rejected; exact closed contact covers the boundary. Constructive routes use endpoint and six-face intersection tests, independently of the production slab predicate. Camera reconstruction uses exact Gaussian elimination, independently of the production camera inversion helper. The verifier never calls the task constructor, reference planner, production path checker, or generator-private state.

The certificate establishes the stated geometric property for the supplied worlds. It does not prove a general motion-planning lower bound, a runtime lower bound, or hard performance for strong AI systems. Both individual solutions are intentionally simple.

## Policy integration hook

The public-observation helper is:

```python
solve_robotics_barrier_from_observations(
    workspace: dict,
    camera_readings: list[dict],
    lidar_reading: dict,
) -> dict
```

Import it from `causalfill.domains.robotics_barrier`. The result uses the existing robotics submission schema. Inputs can be raw task observations or public `Session` responses with tracing metadata. The function uses no task handle, seed, hidden geometry or certificate and does not mutate its inputs.

The registry class is `RoboticsBarrierTask`; the family key is `robotics_barrier`. Structural signatures are `robotics_barrier:orthographic-{camera_transform}:opposite-y-passages:v1`, and `twin_kind` is `wall_y_translation`.

## Verification performed

The initial implementation passed 29 unit tests: 13 barrier tests and all 16 existing robotics tests. The barrier matrix includes seven seeds, all three splits and difficulties, and both twins: 63 paired certificates and 126 individually valid reference routes. Swapping the two route witnesses fails in every paired case. Tests also check public observation equivalence, statement binding, forged matching hashes with missing section coverage, tiny positive gaps, exact contact, valid alternative witness routes, malformed proof payloads, remaining camera-target requirements, budgeted public callbacks, and geometry-probe distinguishability.

The original family retains its previous default behavior, including the legal height-10/0.5-N route. Broader run counts and source hashes belong in the versioned stress reports; unit-test success alone is not a difficulty measurement.
