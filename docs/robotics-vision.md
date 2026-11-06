# Pixel observations that change a robot decision

`robotics_vision_v1` is an executable, finite robotics simulator for testing the
chain from observation to calibrated geometric interpretation to an irreversible
action. It extends the symbolic robotics tracks with actual RGB PNG observations,
photometric noise, hidden camera calibration, visual occlusion, contact probes
that change the world, a time limit, and a physical resource ledger. It remains a
controlled 2D raster and synthetic contact experiment. It does not establish
natural-image understanding, general robot competence, or a safety certification.

## What an episode asks

A payload must cross one of two lanes. Exactly one lane is open. In the initial
camera station an opaque roof covers both candidate openings, so neither the
pixels nor their file length can disclose which lane is open. Moving to the
inspection station removes that declared 2D occluder. The opening appears as a
colored patch whose **world** position identifies the usable lane. The camera
can reflect, rotate, translate by subpixel amounts, or shear the scene depending
on the split. Three colored fiducials with public world coordinates support
calibration; the camera matrix itself is private.

The surface has either a dry or a slick friction regime. Its appearance is
identical in both cases. A gentle or firm contact probe measures friction after
contact has worn the surface. An execution chooses a lane and one of three
contact modes. The wrong lane collides with the gate. Insufficient rolling
traction causes slip. Excess resistance in the sliding grip fixture causes a
stall. A slow, supported transport mode tolerates either friction regime, but it
needs more time. A slow detour bypasses both the gate and the contact fixture.

The strict deadline excludes slow transport and the detour. The relaxed deadline
permits the detour without any observation. This difference is public. It tests
whether a controller uses available information only when it can affect a useful
action, while preserving an explicit control that succeeds without identifying
all hidden details.

## Public interface and accounting

The family is `robotics_vision`; its public contract is
`/scene/robotics_vision.json`. The four tools are listed below. Tool credits and
simulated physical resources are separate ledgers.

| Tool and arguments | Tool credits | Time | Energy | Physical consequence |
|---|---:|---:|---:|---|
| `robot_move_camera({"view":"overview"})` or `"inspection"` | 2 | 1 | 1 | Change camera station; moving to the same station also costs resources |
| `robot_capture({})` | 3 | 1 | 0 | Observe the current station as PNG pixels |
| `robot_probe({"force":"gentle"})` | 4 | 2 | 1 | Add one unit of surface wear, then measure |
| `robot_probe({"force":"firm"})` | 4 | 2 | 2 | Add two units of surface wear, then measure |
| `robot_execute({"route":"upper" or "lower","mode":"roll" or "grip"})` | 2 | 5 | 5 | Irreversible primary transport |
| `robot_execute({"route":"upper" or "lower","mode":"slow"})` | 2 | 12 | 4 | Irreversible supported primary transport |
| `robot_execute({"route":"detour","mode":"slow"})` | 2 | 18 | 6 | Irreversible bypass |

The tool-credit budget is 30 and the call cap is 24. Reading the public contract
uses one additional common-tool credit and no simulated physical time. The
energy cap is 14. Strict episodes have deadline 10; relaxed episodes have deadline
26. Equality at a resource bound is allowed. A valid action that exceeds a bound
can be attempted, but the resulting execution cannot complete successfully.
This convention makes wasted sensing and late actions visible in outcomes.

Every argument, enum, exact key set, and terminal-state precondition is checked
before domain state changes. Booleans and numeric values are not accepted as
strings; an extra key is invalid. `detour` accepts only `slow`. A valid execution
is terminal even if it collides, slips, stalls, or misses the deadline. All later
domain calls fail without changing the robot state. Invalid requests still cost
tool credits under the shared `Session` protocol; they do not spend simulated
time or energy and do not wear the surface.

The completion is `{"delivered":true}`. The verifier requires a successful
terminal execution; submitting this string without acting cannot pass. An
execution's observed outcome does not create a retry opportunity. There is no
mutable success flag exposed to the solver. The common score field `recovery`
mirrors achieved delivery in this family; it does not separately grade a numeric
latent-state estimate.

## Sensor model and its limitations

A capture returns a PNG envelope containing MIME type, dimensions, base64 PNG
bytes, and a SHA-256 of those bytes. The response also reports the camera station
and public resource ledger. It contains no scene coordinates, segmentation mask,
object annotations, camera transform, hidden state, generator seed, or answer.
The public palette is a task convention, not an embedded image annotation.

The images are RGB8, 192 by 192 pixels. Difficulty levels use integer additive
per-channel photometric noise bounds of 2, 4, and 8, with clipping at the byte
range. Noise is applied **after** occlusion, using a single fixed field shared
across captures and stations. Repeating a capture at the same station produces
identical bytes. Repeated captures therefore cannot be treated as independent
measurements or averaged into a better estimate. Twin episodes share the camera,
noise realization, and all irrelevant geometry.

The scripted pixel interpreter detects the three fiducials, fits the affine
camera from their centroids, finds the unique opening-color component, and maps
its center to world coordinates. It accepts a lane only when the recovered
center is within one world unit of the advertised opening support. The centers
are 28 world units apart, with a wide separation margin. This deliberately
comfortable geometry tests the operational chain and isolation boundaries.

The one-unit allowance is a tested assumption of this restricted renderer family,
not a statistical confidence interval or a guarantee for unmodeled scenes.
Photometric error bounds alone do not imply a bound on geometric error in an
arbitrary camera or scene. The delivered tests check recovered poses across the
specified split transforms, noise levels, and paired interventions. Natural
textures, motion blur, lens distortion, real three-dimensional parallax, sensor
dropout, calibration drift during motion, and partial landmark visibility remain
outside this version. The camera station change is a declared occluder change;
it is not an undisclosed 3D renderer.

## Contact is an intervention, not a free measurement

The public contract declares the finite initial friction support. The two
contact profiles are deliberately distinct:

| Public contact profile | Initial slick coefficient | Initial dry coefficient | Maximum coefficient after one firm probe |
|---|---:|---:|---:|
| `conditionable` | 0.25 | 0.65 | 0.41 |
| `resistant` | 0.25 | 0.75 | 0.51 |

For cumulative wear `w`, the post-contact coefficient is
`mu = max(0.1, initial_mu - 0.12*w)`. Gentle contact adds one unit, firm contact two.
The probe returns an interval centered on post-contact `mu` plus a persistent
bias in `[-0.015,+0.015]`, with half-width 0.015. Every returned interval contains
the actual post-contact coefficient. The same bias is used for all probes and
force settings, so repeating contact changes the world and retains correlated
measurement error. It does not produce independent samples of a static latent.

For a primary lane that is open, rolling requires `mu * 9.81 >= 3.0` in the
synthetic traction rule. The grip carriage is modeled as a sliding fixture with
a normalized drive limit `mu <= 0.45`; above that value it stalls. Slow transport
uses its supported fixture and succeeds in either regime if time and energy
permit. These declared transition rules are intentionally small and directly
checkable. They do not model general rigid-body dynamics, actuator saturation,
contact impulses, stochastic stick-slip, payload stability, or a real material
law. The verifier computes the transition from hidden state and the chosen action,
independently of the pixel detector and reference controller.

One firm probe in a `conditionable` episode puts **both** possible surfaces in
the grip-safe range. A controller can then ignore the numeric friction reading
and use grip. This is a valid intervention-based solution. It was included
explicitly during design review; it is not evidence that friction identification
is necessary. In `resistant` episodes, one firm probe leaves the possible dry
surface at 0.51, so the same argument fails. A controller can instead use the
reading to choose an appropriate mode, or choose a slower universally valid mode
and accept a missed strict deadline. A second firm probe would condition this
surface, but inspection plus two probes plus fast execution needs 11 time units,
which exceeds the strict deadline. This is an operational cost consequence of
the declared model, not a ban on intervention.

Repeated contact can also make a previously feasible rolling action slip. The
physical cost of asking a question is therefore part of the next decision.

## Scripted controls and fair comparisons

`solve_robotics_vision(public, call, mode=...)` receives only the public episode
and a tool callback. It never receives a task object, hidden camera, hidden seed,
or evaluator score. The available modes are:

| Mode | Schedule and decision rule | Purpose |
|---|---|---|
| `query_free` / `blind` | Read the common contract, then upper-lane rolling execution; no sensor observation | Baseline for acting without distinguishing evidence |
| `robust` | Slow detour | Demonstrates success without latent recovery under a relaxed deadline, and the cost under a strict deadline |
| `fixed` | Initial overview image, inspection move and image, gentle probe, interval-safe contact mode | A deliberately redundant fixed schedule; its extra overview is not informative |
| `fixed_minimal` | Inspection move and image, gentle probe, interval-safe contact mode | The nonredundant fixed-sensing comparator |
| `adaptive` | Use the detour if the public deadline permits it; otherwise use the `fixed_minimal` sensing schedule | Resource-aware selection from a public contract |
| `conditioning` | Inspection move and image, firm probe, ignore its reading, use grip only if the public support proves safety; otherwise slow | A guaranteed-contact-mode control, subject to the deadline |
| `conditioning_grip` | Inspection move and image, firm probe, ignore its reading, always use grip | A stronger completion comparator that accepts a possible safe stall on a resistant dry surface |

`adaptive` adapts the **sensing schedule to the known deadline**. Its subsequent
contact-mode choice depends on the observed interval. It does not choose the next
sensor based on a stochastic visual observation; this version does not establish
observation-adaptive sensing superiority. In strict episodes its sensing schedule
is identical to `fixed_minimal`. Savings against `fixed` alone would merely show
the cost of a deliberately redundant overview image, which is why both fixed
controls are provided.

The conditioning control's conservative slow fallback misses a strict deadline
on `resistant` episodes. That failure is a limitation of that named no-reading
control, not a claim that no policy can solve those episodes.
`conditioning_grip` can complete on the resistant slick surface and stalls on the
resistant dry surface. It is included so that the conservative slow fallback is
not mistaken for the strongest expected-completion baseline. The regular public
reference succeeds by reading a gentle probe and selecting the feasible contact
mode. An image-decoding or calibration failure produces a conservative detour;
that fallback is safe from collision in this model but may miss the deadline.

Run all modes under the same observations, tool cap, action set, and resource
rules. Report completion, collision, slip, stall, deadline/energy violations,
observation count, sensing credits, elapsed simulated time, energy used, wear,
primitive steps, and terminal action. Distinguish tool credits from simulation
time and distinguish a missing decision from an unsafe one. Conditional results
should identify both deadline profile and contact profile.

## Paired causal intervention and what it proves

The twin changes exactly one causal component: either the open gate lane or the
initial friction regime. Public prompt, files, tool schemas, costs, camera,
initial resource state, and noise process stay identical. Initial overview pixels
are byte-identical. Friction twins remain visually identical even at inspection;
the post-contact numeric readings can distinguish them. Gate twins become
visually different at inspection. All random draws are independent of the twin.

For strict episodes, enumerating the seven legal **initial immediate terminal
actions** gives nonempty but disjoint successful action sets across each twin
pair. This is a precise, limited statement about acting before information or
intervention. It is not a theorem that every successful policy must identify the
initial friction regime. The conditioning control is an explicit counterexample
to that stronger statement on the conditionable support. In relaxed episodes the
same detour action succeeds in both worlds. Decision sufficiency and state
identification must be evaluated separately.

## Verification and continuation

`python -m unittest tests.test_robotics_vision -v` checks PNG payloads and repeated
noise, paired public equivalence, calibrated pose recovery, all controller modes,
strict initial action-set separation, invalid-input atomicity, terminal
irreversibility, independent physics boundaries, probe correlation and wear,
conditioning without using numeric readings, resource accounting, pure oracle
answers, and the requirement to execute before claiming success. The broader
release stress runner and independent audit add episode sweeps, replay,
intervention comparisons, and image QA; use their reports for measured counts.

The evaluator-only `reference_actions()` produces an oracle execution sequence
that must pass through `Session` for cost and trace accounting.
`reference_answer()` is pure and cannot deliver a payload by mutating task state.
These oracle helpers are distinct from the public-only scripted controls and
must not be reported as model scores.

A useful next experiment would introduce an explicitly bounded geometric
abstraction with off-grid openings and uncertain calibration, require interval
preconditions for each route, and test whether failed abstraction assumptions
predict failures. Subsequent work could use rendered 3D scenes and held-out
materials and cameras. Controlled physical trials require separately validated
sensors, dynamics, actuators, intervention safeguards, and hardware evidence.
Nothing in a 100-variable algebraic track or in these successful finite episodes
supplies that evidence by itself.
