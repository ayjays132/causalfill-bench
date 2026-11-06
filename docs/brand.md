# CausalFill-Bench visual system

The identity turns the benchmark's central action into a simple mark: an open
frame, a missing component, and a separate tile that can complete it. Deep ink
and warm paper give research material a consistent editorial frame. Bright
accents identify evidence classes; they do not rank models or imply a result.

The project name is **CausalFill-Bench**. The compact wordmark may split this as
“CausalFill” and “BENCH.” Preserve **Phillip A. Holland Jr.** as the project's
concept and direction credit. The graphics are original vector work generated
by [the card builder](../tools/build_release_cards.py) under the repository's
[MIT license](../LICENSE).

## Evidence language

| Visible label | Appearance | Meaning and required context |
|---|---|---|
| **Measured** | Cobalt, bars symbol | An observation in a recorded run. State the units, configuration, population and source. Development controls and tests are not model intelligence scores. |
| **Formally checked** | Teal, checked square | A specific theorem checked by a named proof system. Identify its statement, assumptions, checker and evidence version. A finite Python certificate check alone does not establish a new Lean theorem. |
| **Proposed** | Amber, diamond | A research question, planned experiment or unestablished transfer claim. Use a textual status; do not dress a target number as an achieved score. |

Words and distinct symbols accompany every evidence color. A check mark in the
brand illustration is visual language, not a theorem or leaderboard badge.
The headline “Prove the result” expresses the benchmark's verification goal;
individual claims retain the narrower scope documented in their source.

Retained evidence keeps its original version. For example, a proof record from
an earlier release should visibly say “v0.4 evidence” if it has not been rerun
for the current release. Newly checked robust finite certificates should be
presented according to the evidence actually obtained.

## Asset map

| Asset | Intended use |
|---|---|
| `branding/hero.svg` / `hero-mobile.svg` | README introduction; deliberately version-free |
| `branding/wordmark-{dark,light}.svg` | Wide project identity |
| `branding/icon-{dark,light}.svg` | Square avatar or small identity mark |
| `branding/cover.svg` | Downloadable research cover, 1600 × 1000 |
| `branding/social-card.svg` | Downloadable sharing card, 1280 × 640 |
| `branding/tasks/*.svg` | Nine conceptual-domain cards with gap, evidence and acceptance |
| `branding/features/robust-sensing.svg` | Signal Repair feature card within the diagnosis/decision domain |
| `branding/evidence-legend*.svg` | Explicit evidence definitions, desktop and mobile |
| `branding/results/*.svg` | One source-bound metric per card |
| `branding/results-sheet*.svg` | Coordinated result grid and mobile stack |
| `branding/benchmark-card*.svg` | Author-facing task summary, desktop and mobile |
| `branding/design-preview/` | Clearly marked layout samples; no results asserted |
| `branding/previews/` | Raster exports and visual QA contact sheets |

The task cards summarize conceptual domains, not a count of runnable task
configurations. Keep the detailed task contracts and limitations in normal
Markdown beside the images.

## Build from evidence

The authoring tool requires Python and Pillow. PNG exports additionally require
Inkscape on `PATH`; neither is required to display the committed SVGs. If local
fonts differ, supply `--font-regular`, `--font-bold` and `--font-mono` paths.

```bash
# Identity and explicitly unscored design samples
python3 tools/build_release_cards.py --design-preview --render

# Source-bound release cards and the same identity assets
python3 tools/build_release_cards.py --metrics branding/release-metrics.json --render
```

The input uses the schema
[`causalfill.release-cards.v1`](../branding/release-cards.schema.json).
This is a specification template; replace the source path and JSON pointers
with the exact recorded evidence before building:

```json
{
  "schema": "causalfill.release-cards.v1",
  "release": {"version": "release version"},
  "metrics": [{
    "id": "certificate-audit",
    "kind": "measured",
    "label": "Certificate checks accepted",
    "scope": "Recorded development audit; state its population and limits.",
    "record_label": "evidence version",
    "source": "results/your-record.json",
    "pointers": ["/passed", "/total"],
    "format": "integer"
  }]
}
```

Measured and formal values come from one source JSON value or a
numerator/denominator pair. Formats are `integer`, `decimal` or short `text`.
The optional `expected_source_sha256` rejects changed source files. The builder
records actual source hashes and resolved values in
[`build-manifest.json`](../branding/build-manifest.json). A proposed card uses a
short string `value` instead of pointers. Every card needs a specific `scope`.
The generator refuses overlong prose instead of silently cropping it.

The builder verifies file binding, text bounds and palette contrast. It does
not rerun the experiment, check a proof or determine that a claim is warranted.
An author must review labels against the actual evidence and inspect the PNGs
after each content change.

## Author-facing benchmark card

The optional `benchmark_card` input has a `title`, `subtitle`, six `fields`
containing `label` and `body`, and an optional `source_label`. Each field can
hold up to four concise lines. The desktop layout uses two columns; the mobile
layout preserves reading order in one column.

| Field | Author should state |
|---|---|
| Missing component | What is masked, why it matters, and the intended construct |
| Public evidence | Allowed observations, tool contract and solver/evaluator separation |
| Actions and budget | Costs, limits, stopping rule and irreversible effects |
| Strict acceptance | Typed answer, scoring rule, certificates and valid alternatives |
| Evidence and claims | Recorded run or theorem, split/seed policy, comparison and reproduction link |
| Known boundaries | Assumptions, leakage risks, uncertainty and transfer not established |

The visual card is an index into a complete written task contract. Put dataset
generation, licenses, full split definitions, model settings and detailed
limitations in that linked contract. A polished card cannot replace them.

## GitHub and mobile use

Use the wide hero at full README width and switch to the purpose-built mobile
asset below 700 pixels. This preserves the headline and illustration without
cropping words or shrinking a two-column composition into a narrow strip.

```html
<picture>
  <source media="(max-width: 700px)" srcset="branding/hero-mobile.svg">
  <img src="branding/hero.svg" alt="CausalFill-Bench. Recover the missing. Prove the result. Choose evidence and make the completed procedure work.">
</picture>
```

Apply the same pattern to `results-sheet-mobile.svg`,
`benchmark-card-mobile.svg` and `evidence-legend-mobile.svg`. For individual
task cards, use full width on mobile; do not force a three-column table there.
Keep numeric result details and source links available as Markdown text so
screen readers and readers who disable images receive the same information.

## Accessibility and visual QA

Core colors are ink `#172B43`, deep ink `#102037`, paper `#F6F4ED`, measured blue
`#2455D9`, formal teal `#126B52`, and proposed amber `#825000`. Exact tokens are
in [`tokens.json`](../branding/tokens.json). All checked body-text palette pairs
meet 4.5:1 contrast; the build manifest reports their calculated ratios. This
does not constitute a full accessibility certification.

SVGs include a title and description, use local font fallbacks, and have no
scripts, remote images, external fonts, filters or animation. Check the wide
hero at 900 pixels and mobile layouts at 375 pixels, then inspect the full
cards for overlaps, clipping, source labels and evidence-version accuracy.
The manifest records generated assets; the separate visual QA record identifies
the renders that a reviewer actually inspected.

## Release report

The same identity is used by
[`tools/build_v051_report.py`](../tools/build_v051_report.py). It produces a
14-page PDF only after the consolidated v0.5.1 verification record passes. It
loads the recorded counts, cost profiles, ablations and pilot details directly;
it does not infer missing results. ReportLab, Pillow, pypdf and the local DejaVu
Sans fonts are authoring dependencies. Poppler's `pdftoppm` renders the page
previews.

```bash
python3 tools/build_v051_report.py \
  --record reports/v051/release-verification.json \
  --output ../CausalFill_Research_Report_v0.5.1.pdf --render
```

The build record is `branding/report-build.json`, and rendered pages are in
`branding/report-preview/`. The report's evidence labels use the same words,
palette and scope rules as the GitHub cards. Its references print complete
primary-source URLs, and its provenance page records the verification JSON
hash. Review every rendered page after changing the evidence input.

