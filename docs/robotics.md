# Robotics: active sensing and executable completion

> Scope: this document describes the original symbolic track. Version 0.5 adds a separate [rendered active-perception track](robotics-vision.md) and [controlled image task](visual-perception.md).


## Scope

This release implements a **symbolic 3D tabletop simulator**. Camera tools return numeric object projections and fiducial coordinates. They do not render images. There is no arm kinematics, contact dynamics, grasp simulation, continuous controller, real robot integration, learned vision model, or demonstrated transfer to hardware. The geometric units are declared metres inside a deliberately simplified virtual scene; they are not a physical workcell specification.

The task asks an agent to fill three typed gaps: a hidden target position, a safe sequence of intermediate waypoints, and a grasp precondition. Success requires completing an executable plan. A verbal explanation or matching one reference route is insufficient. Alternative safe routes and valid force limits are accepted.

## Observation and action boundary

The public workspace file contains a target identifier, start pose, workspace bounds, robot clearance, available view names, handling thresholds, and a target tolerance. It does not contain the target location, camera calibration, obstacle location, hidden seed, or answer. The target is identified by an arbitrary object ID, not by a particular colour or a semantic stereotype.

The `camera` tool costs 3 units. It returns an orthographic projection onto two declared world axes, transformed by an unknown invertible affine map. Three visible calibration fiducials identify the map. Two complementary visible projections identify all three target coordinates. At difficulty 3 and above, one view omits the target, so an agent may need another observation. Other detected objects are distractors.

The `lidar` tool costs 3 units. It returns observed obstacle bounding boxes in a calibrated world frame. This is an explicitly permitted measurement, not a leak from the verifier.

The `probe_path` tool costs 4 units. It checks only collision and workspace bounds for a proposed route, without moving anything and without revealing whether the proposed endpoint is the hidden target. Its output does not include the true target, distance to the target, or a target-correctness bit. The core also charges invalid requests. The episode budget is 40 cost units, with a 60-call ceiling.

All tools are simulated and local. They neither operate a user's computer nor move a robot. An external host adapter can expose this observation boundary to an agent, but unrestricted access to the evaluator process or its memory would invalidate an evaluation.

## Calibration and geometric verification

Each camera supplies `image = A * projected_world + b`. The agent can solve for `A` and `b` from the three fiducials. Inverting this map gives two world coordinates per observed object. Complementary views recover the complete location. No metric rewards an explanation that merely sounds geometric.

The final route connects the start, submitted waypoints, and submitted target by straight segments. The verifier uses a slab intersection test between every closed segment and every obstacle's axis-aligned box expanded by the gripper clearance. Touching the expanded surface counts as a collision. Every point must also lie within the workspace reduced by that clearance. Convex bounds then contain each connecting segment. This is a point-path approximation with conservative box clearance, not swept-volume robot kinematics.

The gripper must approach open. Its submitted force limit must be at least 0.5 N and no greater than the observed material's declared limit. The simulator treats this as a symbolic handling constraint. It does not calculate real contact forces.

Malformed submissions fail before execution. The implementation rejects boolean-as-number values, NaN, infinities, excessively large coordinates, oversized waypoint arrays, malformed vector shapes, and unknown fields. No submitted string is executed as code.

## Splits and counterfactuals

The training split uses positive diagonal camera transforms. Development permits signed diagonal transforms, including reflections. The transfer split uses genuinely nonzero off-diagonal affine terms. Thus the transfer split changes a geometric mechanism, not only the random seed. These are still a small hand-designed family of tasks: success does not establish general robotic intelligence.

Difficulty increases clutter, and from level 3 introduces one missing camera view. Higher difficulty is a configurable stress setting, not a claim that a frontier model finds the task hard.

For a counterfactual twin, every random draw and target property stays fixed. Exactly one pivotal causal variable changes: the obstacle's vertical offset increases by 4 metres. This makes the original direct route unsafe and the twin's direct route safe. Camera observations, materials, target identity, target position, and workspace files remain unchanged. The lidar observation changes because it measures the affected variable. A valid detour may succeed in both twins; the benchmark should not demand different text when one plan is behaviorally valid for both.

## Reference solver and tests

`reference_answer()` is an evidence-based debugging oracle. It reads the same public workspace file, calls the allowed camera and lidar queries, inverts fiducials, and plans from those observations. Its `solve_from_observations` helper never accesses the task's latent position, camera matrices, or obstacle members. It is specialized to the documented one-obstacle scene family and is not a learned-agent result.

The tests cover crossing and grazing collisions, a clearance near miss, zero-length segments, affine inversion, the split/difficulty/seed/twin matrix, alternative valid routes and force settings, observation identifiability, counterfactual direct-route validity, strict validation, non-destructive probes, defensive copies, and the public observation boundary. A query error cannot modify the world.

## What to measure next

Report endpoint recovery, end-to-end task success, collision or handling violations, sensor cost, and uncertainty calibration separately. Compare full observations, missing observations without tools, random sensing, and active sensing under matched budgets. Use paired counterfactual episodes and bootstrap at the independent scene or seed level, not at the correlated twin level.

An intentionally underdetermined task must admit abstention, or accept all solutions equivalent under observable evidence. Do not create difficulty by withholding information that no allowed tool can recover. This particular family is generated to be identifiable, and tests verify the evidence-based solver can solve its sampled instances.

Before claiming robot transfer, evaluate on held-out physical or validated simulation environments, camera geometries, sensor noise, object shapes, contacts, and embodiments. Do not interpret a 100-variable latent state as 100 physical spatial dimensions: a real tabletop scene remains three-dimensional.

## Research grounding and closest prior art

- [Multi-View Masked World Models for Visual Robotic Manipulation, ICML 2023](https://proceedings.mlr.press/v202/seo23a.html) already trains representations by reconstructing masked viewpoints and evaluates downstream robotic control. Masked visual completion benefiting robotics is established prior art.
- [VIMA, ICML 2023](https://proceedings.mlr.press/v202/jiang23b.html), with [official VIMABench code](https://github.com/vimalabs/VIMABench), supplies multimodal procedural manipulation tasks and systematic generalization evaluation. It informs compositional split design; no code or task assets are copied here.
- [V-JEPA 2](https://ai.meta.com/research/publications/v-jepa-2-self-supervised-video-models-enable-understanding-prediction-and-planning/), with [official code](https://github.com/facebookresearch/vjepa2), connects masked latent prediction with action-conditioned planning. The present benchmark does not implement or train V-JEPA.
- [Masked Visual Actions for Unified World Modeling](https://masked-visual-actions.github.io/) studies partially revealed visual action trajectories and forward/inverse world modeling. It is close prior work, not a new capability claimed here.
- [ESI-Bench](https://esi-bench.github.io/), with [official code](https://github.com/ESI-Bench/ESI-Bench), evaluates active perception and action for spatial reasoning on OmniGibson. This release makes no claim to be the first active sensing or embodied reasoning benchmark.
- [BAVO-Bench](https://hcplab-sysu.github.io/BAVO-Bench/) studies active viewpoint recovery under occlusion; [SaPaVe / ActiveManip-Bench](https://lmzpai.github.io/SaPaVe/) couples active camera control with manipulation. Both are relevant active perception precedents.
- [LIBERO](https://github.com/Lifelong-Robot-Learning/LIBERO), [RoboCasa](https://github.com/robocasa/robocasa), [BEHAVIOR-1K](https://github.com/StanfordVL/BEHAVIOR-1K), [ALFRED](https://github.com/askforalfred/alfred), and [robomimic](https://github.com/ARISE-Initiative/robomimic) are potential future validation environments or adapters. They are not bundled or integrated in this release.

The listed repositories distinguish code from datasets, model weights, and third-party assets. For example, LIBERO's official README identifies MIT code and CC BY 4.0 datasets. No third-party code, weights, robot demonstrations, images, or simulation assets are redistributed in this module. Links were researched for this project on 2026-11-01; a future integration must verify the particular release's terms.
