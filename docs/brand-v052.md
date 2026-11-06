# CausalFill-Bench v0.5.2 visual guide

The v0.5.2 visual system gives each runnable configuration its own icon and adds
readable explanations of Signal Repair, scoring and evidence provenance. The
original open frame, missing center and separate completion tile remain the
project mark. The palette retains deep ink, warm paper and labeled evidence
colors from the [existing brand system](brand.md).

The assets are original vector artwork under the repository's [MIT
license](../LICENSE). Preserve **Phillip A. Holland Jr.** as the project's concept
and direction credit. Implementation and design are AI-assisted.

## Start here

- Open [the visual feature gallery](../branding/v052/index.html) from a local
  checkout to browse the complete guide offline. It contains native expandable
  verification and scope notes for all 15 task configurations.
- Use the [wide hero](../branding/v052/hero.svg) and
  [mobile hero](../branding/v052/hero-mobile.svg) for the current release.
- Use the [task icon atlas](../branding/v052/icon-atlas.svg) to see every
  configuration, or select an individual SVG from the map below.
- Use the [social cover](../branding/v052/social-card.svg) for a release
  announcement that describes capability without inventing a model result.

GitHub displays SVGs directly. The gallery is ordinary static HTML; download or
open the checkout locally to view it as a page instead of GitHub's source view.
No web service, external fonts or remote assets are needed.

## What the feature plates explain

| Feature | Wide asset | Mobile asset | Exact scope |
|---|---|---|---|
| Signal Repair | [signal-repair.svg](../branding/v052/features/signal-repair.svg) | [signal-repair-mobile.svg](../branding/v052/features/signal-repair-mobile.svg) | Costly once-only probes, one global corruption cap, compatible worlds, irreversible commitment and accepted pre-commit witnesses. |
| Outcome and acceptance | [outcome-acceptance.svg](../branding/v052/features/outcome-acceptance.svg) | [outcome-acceptance-mobile.svg](../branding/v052/features/outcome-acceptance-mobile.svg) | An actual successful action remains a successful operational outcome if its final certificate is malformed. Strict acceptance still rejects that certificate. |
| Evidence language | [evidence-language.svg](../branding/v052/features/evidence-language.svg) | [evidence-language-mobile.svg](../branding/v052/features/evidence-language-mobile.svg) | Measured observations, selected formal statements and proposed research have different provenance and scope requirements. |

The gallery also explains the offline `review` command. It creates a
self-contained evaluator page from recorded episodes, with separate
configuration summaries, episode filters, outcome and cost columns, and
inspectable records. Optional trace verification checks supplied chains and
their final record bindings. This establishes internal consistency of the
provided artifacts; it does not authenticate model authorship or prove that a
solver was isolated.

The feature plates are **capability illustrations and scoring explanations**.
They contain no new model score, empirical comparison or proof-check result.
The success/failure rows in the scoring plate are illustrative cases. They are
not sampled episodes or an empirical distribution. The quantity `k+1` expresses
the Signal Repair witness rule, not a result count.

## Configuration icon map

Every filename uses the exact public registry key. The builder checks the full
ordered key list against [`causalfill/registry.py`](../causalfill/registry.py), so a
new or renamed configuration cannot silently disappear from the atlas.

| Configuration | Icon | Visual meaning | Documentation |
|---|---|---|---|
| `words` | [SVG](../branding/v052/icons/words.svg) | A missing routing word and the branch it controls. | [Research specification](research-spec.md) |
| `workflow` | [SVG](../branding/v052/icons/workflow.svg) | A missing expression inside a bounded executable program. | [Workflow certification](workflow-certification.md) |
| `grid` | [SVG](../branding/v052/icons/grid.svg) | A discrete pattern transformed by an inferred program. | [Grid tasks](grid.md) |
| `vending` | [SVG](../branding/v052/icons/vending.svg) | Inventory, payment and delivery inside an operating machine. | [Research specification](research-spec.md) |
| `vending_adaptive` | [SVG](../branding/v052/icons/vending_adaptive.svg) | A contingent decision branches into actual procurement. | [Adaptive vending](vending-adaptive.md) |
| `robotics` | [SVG](../branding/v052/icons/robotics.svg) | An articulated symbolic arm and a target in its workspace. | [Symbolic robotics](robotics.md) |
| `robotics_barrier` | [SVG](../branding/v052/icons/robotics_barrier.svg) | A sensed path passes through separate barrier openings. | [Barrier profile](robotics-barrier.md) |
| `latent` | [SVG](../branding/v052/icons/latent.svg) | A dense affine operator with explicit finite entries. | [Finite-field algebra](math-and-100d.md) |
| `latent_sparse` | [SVG](../branding/v052/icons/latent_sparse.svg) | A few active coefficients among many potential entries. | [Finite-field algebra](math-and-100d.md) |
| `ambiguity` | [SVG](../branding/v052/icons/ambiguity.svg) | One observation supports different required answers. | [Scoring](scoring.md) |
| `proof` | [SVG](../branding/v052/icons/proof.svg) | Premises, an inference line and a checked conclusion. | [Proof track](proof-track.md) |
| `diagnosis` | [SVG](../branding/v052/icons/diagnosis.svg) | Observations eliminate alternative candidate worlds. | [Identification](identification-track.md) |
| `visual` | [SVG](../branding/v052/icons/visual.svg) | Pixels, visible calibration landmarks and a located target. | [Controlled perception](visual-perception.md) |
| `robotics_vision` | [SVG](../branding/v052/icons/robotics_vision.svg) | Rendered observation guides a route and simulated handling. | [Rendered robotics](robotics-vision.md) |
| `robust_sensing` | [SVG](../branding/v052/icons/robust_sensing.svg) | Distinct sensor reports support an action despite a faulty signal. | [Signal Repair](robust-sensing.md) |

Icons use a 128 × 128 view box. They are designed primarily for 64-pixel cards;
the committed [UI contact sheet](../branding/v052/previews/icons-ui-contact-sheet.png)
also shows their appearance at 32 pixels. Use a visible text label beside the
icon. If that label already names the configuration, an HTML image can use an
empty `alt` attribute to avoid repeating the same label to screen readers.
Standalone SVG files include their own descriptive title and description.

The nine conceptual domains group related configurations. The fifteen icons
identify fifteen runnable configurations; they do not imply fifteen independent
capability dimensions or fifteen independent research findings.

## Identity assets and responsive use

The [identity directory](../branding/v052/identity/) contains light and dark
wordmarks and square marks. The main wordmark spells the project compactly as
“CausalFill” with “BENCH” underneath. Use **CausalFill-Bench** in prose.

Use the mobile composition at narrow widths instead of shrinking a wide
two-column plate into unreadable text:

```html
<picture>
  <source media="(max-width: 700px)"
          srcset="branding/v052/hero-mobile.svg">
  <img src="branding/v052/hero.svg"
       alt="CausalFill-Bench v0.5.2. Recover what is missing. Show why it works.">
</picture>
```

Use the same pattern for each feature's `-mobile.svg` companion. The gallery
already includes those responsive pairs. The images explain the mechanism;
normal HTML text alongside them preserves searchable descriptions, detailed
scope notes and links to the complete task contracts.

## Evidence colors and readable labels

| Role | Color | Visible symbol and label |
|---|---|---|
| Primary text | Ink `#172B43` | Ordinary prose and names. |
| Dark field | Deep ink `#102037` | Light text and the project identity. |
| Main surface | Paper `#F6F4ED` | Background, with fine neutral borders. |
| Measured | Cobalt `#2455D9` | Bars and **Measured**. |
| Formally checked | Teal `#126B52` | Checked square and **Formally checked**. |
| Proposed | Amber `#825000` | Diamond and **Proposed**. |

In task glyphs, cobalt also indicates the active component. An icon's check
shape is explanatory visual language; it is not a claim that the task's entire
implementation has been proved in Lean. A formal claim needs a named statement,
its assumptions, the checker and the exact evidence version in accompanying
text. Previously recorded formal work keeps its original release attribution.

The builder checks selected body-text palette pairs at a 4.5:1 threshold and
records their computed ratios. Colors always have accompanying words or
distinct shapes. This is a set of specific checks, not a full accessibility
certification.

## Rebuild and validate

From the repository root:

```bash
# Write the current SVGs, gallery, tokens and asset manifest.
python tools/build_brand_v052.py

# Require exact deterministic outputs and current source bindings.
python tools/build_brand_v052.py --check

# Also render desktop/mobile PNGs and the task icon contact sheet.
python tools/build_brand_v052.py --render
```

Authoring requires Python 3.10 or later, Pillow and local DejaVu Sans/Mono font
files. Rendering additionally requires Inkscape on `PATH`. These are development
tools; the benchmark core remains independent of them. The committed SVGs can
be displayed without Python, Pillow or Inkscape.

The default font directory is `/usr/share/fonts/truetype/dejavu`. A different
installation can supply `--font-dir PATH`; it must contain regular and bold
`DejaVuSans` and `DejaVuSansMono` `.ttf` files. Deterministic rebuilding assumes
the same font metrics. Review changed wrapping if another font version is used.

The builder checks XML parsing, title/description presence, the absence of
active or remote SVG content, registry coverage and measured text fits. It
rejects overlong text instead of cropping it. The asset
[manifest](../branding/v052/manifest.json) records exact byte lengths and SHA-256
digests, the builder digest, the registry configuration list, palette checks and
source-file bindings. It intentionally asserts no new model result or proof run.

Rebuild after a bound task source or document changes. A stale manifest is a
release error to resolve; updating a source binding does not itself repeat the
experiment or prove that new wording is correct. The author still reviews the
description against the implementation.

`--render` records source and PNG hashes in
[`render-record.json`](../branding/v052/render-record.json). The separate
[`visual-qa.json`](../branding/v052/visual-qa.json) names the exports that were
actually inspected. Renders alone are not evidence that a person or assistant
looked at them.

## Release boundaries

The new assets live under `branding/v052/`. Earlier source-bound result cards
and formal records retain their original names and evidence versions. Do not
replace an old record's version label merely because the current code or cover
uses v0.5.2.

Keep numeric performance cards source-bound through the existing
[`build_release_cards.py`](../tools/build_release_cards.py) workflow. This new
builder serves identity, capability diagrams and explanatory icons. A polished
visual should make the stated scope easier to understand; it cannot establish
novelty, model hardness or real-world transfer.
