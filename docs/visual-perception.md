# Controlled pixel perception and decision recovery

Version 0.5 adds the `visual` family. The solver receives actual 240 by 240 RGB
PNG observations, rather than the symbolic camera-coordinate lists in the
original robotics family. It must recover a target pose in a world coordinate
frame, count objects in a spatial relation to that target, and complete a
routing rule whose result changes when the target moves.

This is a small, deliberately controlled raster benchmark. There is no learned
vision model, natural-image dataset, photorealistic renderer, or demonstrated
robot transfer in this family. Its value is that the entire chain from a hidden
scene to image pixels to a scored decision can be inspected and perturbed.

## Public task and observation boundary

Read `/scene/visual.json` through the normal public `read_file` tool. The file
provides the palette, three landmark world coordinates, sensor bounds, two view
names, the routing rule, and the answer tolerance. It does not provide target
coordinates, token coordinates, a camera matrix, a seed, or a rendered answer.

The `capture` tool accepts exactly `{"view":"overview"}` or
`{"view":"inspection"}`. Each costs three synthetic units. A reference reads
the contract once and captures one inspection image, for four total units. The
episode cap is twelve; it is a resource convention, not elapsed physical time
or camera energy. Rejected calls still follow the common session accounting.

Every capture response contains the requested view name and an `image` object:

```json
{
  "mime_type": "image/png",
  "width": 240,
  "height": 240,
  "png_base64": "...",
  "sha256": "..."
}
```

Only `IHDR`, `IDAT`, and `IEND` PNG chunks are emitted. The pixel payload contains
no EXIF, comments, labels, segmentation channel, scene-graph attributes, latent
coordinates, or solver instructions. The hash checks byte integrity; it is not
a statement of semantic correctness. Image length, compression, hashes, and
all other public payload fields are included when testing twin equivalence.

The evaluator owns the renderer inputs and latent scene. A scored solver must
receive only the public task and permitted tool outputs. Evaluator contact
sheets, manifests, task source, private seeds, and reference helpers remain
outside that solver's environment. A shared host does not enforce this boundary.

## The visual task

The scene contains three uniquely colored landmark discs, one target disc,
three to five token discs, and one or two square distractors. The colors are
specified by the public legend. In transfer, their assignments are permuted.
There is no universally correct fixed target color across those episodes.

The fill has three fields:

| Field | Required completion | Verification |
|---|---|---|
| `target_world` | Target center `[x,y]` in world coordinates | Each coordinate within 0.6 world units of latent truth |
| `tokens_left_of_target` | Number of token objects whose world x is smaller than the target's x | Exact integer comparison against latent geometry |
| `dispatch` | `WEST` when target x is below 48, otherwise `EAST` | Execute the declared branch condition against latent truth |

All three must be correct for strict success. The outcome component records the
routing decision separately. A correct route with an incorrect recovered pose
can therefore have outcome one and strict success zero. This makes the
recovery and decision obligations explicit; it does not require an agent to
recover all scene details in the separate decision-sufficiency robotics track.

The pose checker uses exact represented-decimal rational differences at the
published tolerance boundary. It never calls the pixel detector or calibrator
used by the scripted reference. Booleans, nonfinite numbers, out-of-range
coordinates, incorrect field sets, and noninteger counts are rejected.

## Camera, noise, and occlusion semantics

The camera is an invertible two-dimensional affine map. Pixel `(column,row)`
samples its center, `(column + 0.5,row + 0.5)`. Opaque circles and rectangles are
rasterized by inverse mapping that point into the shape. Later primitives cover
earlier primitives. This model has no depth or perspective projection.

Three visible, noncollinear world landmarks determine an affine map from their
pixel centers. This calibrates reflection, rotation, translation, and the
transfer split's shear and quarter-pixel translation. World-west is defined by the x coordinate after
calibration. It need not be the left side of the displayed image.

Difficulty one, two, and three use integer photometric noise bounded by two,
four, and six RGB levels per channel. Noise is applied to every pixel after
all occlusion has been resolved, independently of the hidden target position.
The realization is fixed within an episode/view pair; repeated captures are
identical and cannot be averaged as independent measurements. The palette is
separated sufficiently for a task-aware threshold detector to retain every
visible object pixel under the advertised bound.

These are **photometric** noise bounds. They are not a learned uncertainty
model, a calibrated probabilistic confidence interval, realistic sensor drift,
lens distortion, blur, or a geometric error distribution. The reference's
estimated affine map is a point estimate. Quarter-pixel translation in transfer produces measurable centroid-quantization error; it is scored against the same declared pose tolerance. The generated inspection views keep
all landmarks and task objects fully in frame and separated. Claims outside
that support require additional experiments.

| Split | Mechanism in this implementation |
|---|---|
| `train` | Clear overview; translated affine camera without shear |
| `dev` | Overview shutter hides the target; camera rotations/reflections and translation |
| `transfer` | Overview shutter, other orientation combinations, affine shear, quarter-pixel translation, and palette permutation |

The inspection view uses the same camera and noise with the opaque shutter
absent. It is an explicit 2D mask intervention, not a physically modeled camera
trajectory through a 3D environment. New random seeds create new instances of
these public mechanisms, not independently authored task families.

## Paired intervention and information necessity

Both members of a pair share the complete public contract, colors, landmarks,
tokens, distractors, camera, noise realization, and target y coordinate. The
sole intervention changes target x between 28 and 68. A randomized initial
polarity prevents a fixed twin label from always selecting the same side.

This translation reverses `dispatch` and changes the relational token count.
In `dev` and `transfer`, the overview shutter covers the complete target support
in both worlds. The complete overview response is byte-for-byte identical,
including the PNG length and hash. The inspection image differs.

Consequently an observation restricted to that overview and static contract
cannot identify which of the two different required completions is correct.
That is an information-necessity example for this declared observation set. It
does not establish general model difficulty, computational hardness, uniqueness
of the inspection tool, or novelty of active perception. The `train` overview
is clear and deliberately does not have this indistinguishability property.

## Scripted pixel reference

`solve_visual(public, call)` reads only the public contract and the capture
response. It decodes the PNG, finds connected pixels within the advertised RGB
interval around each landmark color, estimates the camera, detects the target
and tokens, converts their centroids to world coordinates, and evaluates the
relation and routing rule. It receives no `Task` object or hidden scene data.

This is a task-aware color-segmentation control. It establishes solvability and
checks the observation pipeline. Its performance is not a general vision model
score. The reference refuses to produce a pose when the target is absent,
landmarks are absent or ambiguous, or a relation is within the declared
resolution margin. The inspection family avoids partial target occlusion;
visible centroids alone need not locate the full center of a partial object.

## Image QA and stress reproduction

Core task execution has no third-party runtime dependency. `vision.py` contains
a narrow RGB8 PNG encoder/decoder with CRC, dimensions, decompression, stream,
chunk-order and envelope checks. It intentionally rejects many legitimate PNG
features outside this wire format. It is not a universal image decoder.

```bash
python -m unittest tests.test_vision tests.test_visual -v
python tools/render_visual_qa.py --output private-runs/visual-qa --seeds 8
```

The second command requires Pillow only for development QA and contact sheets.
Its default matrix produces 288 benchmark captures from 144 paired episodes,
plus 48 diagnostic fixtures, for **336 observation PNGs**. Those images are
separate from 21 annotated contact-sheet composites. The exported manifest
includes every image's hash and source hashes, independently checks each PNG
with Pillow against the benchmark decoder, measures bounded photometric noise,
checks expected visibility and pixel-reference behavior, and verifies paired
public/overview equivalence and inspection changes.

The 48 diagnostics cover eight orientations, noise levels zero/six/32, and
clear/half-occluded targets, plus an auxiliary circle clipped by the image
boundary. They intentionally extend beyond the scored family's support. The
half-occluded target's visible centroid is biased; the manifest records that
error instead of counting it as a correctly recovered full pose. Noise 32 is
an engineering stress condition, not an additional declared task difficulty.

Automated generation and a contact-sheet file do not prove a human inspected
an image. Manual review must be recorded separately with inspected sheet IDs,
findings, and any repairs. Image counts, correlated pixel checks, rendered
instances, unit tests, and actual model runs remain different measurement units.

The meaningful next extension is to change both the sensing model and the
controller, then test whether uncertainty in a recovered pose predicts action
failures. Adding more seeds to this family alone would not supply that evidence.
